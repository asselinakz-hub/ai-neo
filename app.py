import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# OpenAI SDK v1+
try:
    from openai import OpenAI
    from openai import RateLimitError, APIError, APITimeoutError
except Exception:
    OpenAI = None
    RateLimitError = Exception
    APIError = Exception
    APITimeoutError = Exception


# ----------------------------
# Utils
# ----------------------------
def load_json(path: str) -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Не найден файл конфигурации: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


def normalize_text(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


def tokenize_ru(s: str) -> List[str]:
    s = normalize_text(s)
    # простая токенизация без морфологии (MVP)
    return re.findall(r"[а-яa-z0-9]+", s, flags=re.IGNORECASE)


@dataclass
class Chunk:
    source: str
    idx: int
    text: str


def chunk_text(text: str, max_chars: int = 1800, overlap: int = 120) -> List[str]:
    text = text.strip()
    if not text:
        return []
    chunks = []
    i = 0
    n = len(text)
    while i < n:
        end = min(n, i + max_chars)
        chunk = text[i:end]
        chunks.append(chunk)
        if end == n:
            break
        i = max(0, end - overlap)
    return chunks


@st.cache_data(show_spinner=False)
def load_knowledge_chunks(knowledge_dir: str, files: List[str], max_chars: int, overlap: int) -> List[Chunk]:
    chunks: List[Chunk] = []
    kdir = Path(knowledge_dir)
    for fname in files:
        fp = kdir / fname
        if not fp.exists():
            # Не падаем: просто пропускаем, но показываем в debug позже
            continue
        raw = fp.read_text(encoding="utf-8", errors="ignore")
        parts = chunk_text(raw, max_chars=max_chars, overlap=overlap)
        for idx, part in enumerate(parts):
            chunks.append(Chunk(source=fname, idx=idx, text=part))
    return chunks


def retrieve_chunks(chunks: List[Chunk], query: str, top_k: int, max_total_chars: int) -> Tuple[List[Chunk], List[Tuple[Chunk, float]]]:
    """
    Очень простой поиск: скор = пересечение токенов запроса и чанка.
    Это специально, чтобы не тянуть эмбеддинги и не жечь токены.
    """
    q_tokens = set(tokenize_ru(query))
    scored: List[Tuple[Chunk, float]] = []
    for ch in chunks:
        c_tokens = set(tokenize_ru(ch.text))
        inter = q_tokens.intersection(c_tokens)
        score = float(len(inter))
        if score > 0:
            scored.append((ch, score))
    scored.sort(key=lambda x: x[1], reverse=True)

    picked: List[Chunk] = []
    total = 0
    for ch, _s in scored[: max(top_k * 5, top_k)]:  # чуть шире, потом режем по лимиту символов
        if total >= max_total_chars:
            break
        t = ch.text
        if total + len(t) > max_total_chars:
            t = t[: max(0, max_total_chars - total)]
            picked.append(Chunk(source=ch.source, idx=ch.idx, text=t))
            total = max_total_chars
            break
        picked.append(ch)
        total += len(t)

        if len(picked) >= top_k and total >= (max_total_chars * 0.7):
            break

    return picked, scored[:20]


def get_openai_client() -> Any:
    api_key = None
    # Streamlit Cloud: st.secrets
    if hasattr(st, "secrets"):
        api_key = st.secrets.get("OPENAI_API_KEY") or st.secrets.get("api_key")
    # env fallback (редко нужно)
    if not api_key:
        api_key = st.session_state.get("_OPENAI_API_KEY")

    if not api_key:
        st.error("Нет ключа OpenAI. Добавь OPENAI_API_KEY в Streamlit Secrets.")
        st.stop()

    if OpenAI is None:
        st.error("Пакет openai не установлен или неправильная версия. Проверь requirements.txt (openai>=1.0.0).")
        st.stop()

    return OpenAI(api_key=api_key)


def safe_json_loads(s: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s)
    except Exception:
        # иногда модель оборачивает JSON в текст
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if not m:
            return None
        try:
            return json.loads(m.group(0))
        except Exception:
            return None


# ----------------------------
# LLM protocol (strict JSON)
# ----------------------------
SYSTEM_PROMPT = """
Ты — AI-интервьюер, проводишь "живой разбор" потенциалов (NEO).
Твоя задача: задавать ОДИН следующий вопрос за раз, опираясь на методологию и примеры из контекста.
Важно:
- НЕ повторяй вопросы (смотри историю).
- Делай вопросы естественными, по-человечески, как мастер в реальном разборе.
- Если можно — давай варианты ответов (radio/checkbox), чтобы клиенту не пришлось писать много.
- Если нужен текст — попроси коротко + 1 конкретный пример.
- Уважай запрос клиента и удерживай нить разговора.
- Иногда делай уточнения по детству/поведению/энергии/антипаттернам, но без "анкеты".
- Если обнаруживаешь противоречие — мягко уточни и проверь.
- Смещения: если видишь "надо/должен/ради семьи", сильную тревогу, социально-идеальные ответы — задай 1–2 вопроса на смещение.

ТЫ ОБЯЗАН вернуть СТРОГО JSON без лишнего текста, в формате:

{
  "finish": false,
  "stage": "stage0_intake|stage1_now|stage2_childhood|stage3_hypothesis|stage4_shifts|stage5_wrap",
  "intent": "ask_name|ask_request|current_state|energy_source|childhood|behavior|hypothesis_check|shift_probe|wrap",
  "question_id": "string",
  "question_text": "string",
  "answer_type": "text|single|multi",
  "options": ["..."],             // только если single/multi
  "allow_comment": true,          // если уместно
  "running_hypothesis": {
    "top_candidates": ["..."],    // любые из 9 потенциалов
    "notes": ["..."]              // 1-3 коротких заметки
  },
  "client_preview": {             // заполняй только когда finish=true (иначе null)
    "name": "...",
    "request": "...",
    "top3_hypothesis": ["..."],
    "fills_energy": ["..."],
    "drains_energy": ["..."],
    "next_step": "..."
  }
}

Правила:
- options максимум 6, добавляй вариант "Другое (напишу)" если уместно.
- question_id должен быть уникальным по смыслу (не повторяй).
- Не придумывай потенциалы вне списка 9.
"""


def build_user_prompt(cfg: Dict[str, Any], state: Dict[str, Any], retrieved: List[Chunk]) -> str:
    name = state.get("name") or ""
    request = state.get("request") or ""
    turn = state.get("turn", 0)
    max_turns = cfg["diagnosis"]["max_turns"]

    # История (коротко)
    history_lines = []
    for ev in state.get("log", []):
        q = ev.get("question_text", "")
        a = ev.get("answer", "")
        history_lines.append(f"- Q: {q}\n  A: {a}")
    history = "\n".join(history_lines[-12:])  # не раздуваем

    # Контекстные куски
    ctx_blocks = []
    for ch in retrieved:
        ctx_blocks.append(f"[{ch.source}#{ch.idx}]\n{ch.text}")
    ctx = "\n\n".join(ctx_blocks)

    # Короткое состояние гипотезы
    rh = state.get("running_hypothesis") or {}
    top_cand = rh.get("top_candidates", [])
    notes = rh.get("notes", [])

    return f"""
КОНФИГ:
- max_turns: {max_turns}
- current_turn: {turn}

КЛИЕНТ:
- name: {name}
- request: {request}

ИСТОРИЯ (последние шаги):
{history if history else "- (пока нет)"}

ТЕКУЩАЯ ГИПОТЕЗА (если есть):
- top_candidates: {top_cand}
- notes: {notes}

ДОКУМЕНТЫ (релевантные куски из knowledge/):
{ctx if ctx else "(нет найденных кусков по запросу — задай общий, но умный следующий вопрос)"}

ЗАДАЧА:
Сгенерируй СЛЕДУЮЩИЙ вопрос и формат ответа (single/multi/text).
Не повторяй уже заданные вопросы. Двигайся по логике живого разбора:
ситуация сейчас → детство/история → проверка гипотез → (если надо) смещения → завершение.
Если turn уже >= {cfg["diagnosis"]["stop_rules"]["soft_stop_if_confident_after_turn"]}, можешь завершать, если гипотеза устойчива.
"""


def call_llm(cfg: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
    client = get_openai_client()
    model = cfg["llm"]["model"]
    temperature = cfg["llm"].get("temperature", 0.5)
    max_output_tokens = cfg["llm"].get("max_output_tokens", 450)

    max_retries = cfg["llm"]["retry"]["max_retries"]
    base_sleep = cfg["llm"]["retry"]["base_sleep_seconds"]
    max_sleep = cfg["llm"]["retry"]["max_sleep_seconds"]

    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.chat.completions.create(
                model=model,
                temperature=temperature,
                max_tokens=max_output_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
            )
            text = resp.choices[0].message.content or ""
            data = safe_json_loads(text)
            if not data:
                raise ValueError("Model did not return valid JSON.")
            return data
        except RateLimitError as e:
            last_err = e
            sleep = min(max_sleep, base_sleep * (2 ** attempt))
            time.sleep(sleep)
        except (APITimeoutError, APIError, ValueError) as e:
            last_err = e
            sleep = min(max_sleep, base_sleep * (2 ** attempt))
            time.sleep(sleep)

    raise RuntimeError(f"LLM error after retries: {last_err}")


# ----------------------------
# Streamlit state
# ----------------------------
def init_state():
    st.session_state.setdefault("turn", 0)
    st.session_state.setdefault("log", [])  # list of events
    st.session_state.setdefault("current", None)  # current question dict from LLM
    st.session_state.setdefault("name", "")
    st.session_state.setdefault("request", "")
    st.session_state.setdefault("running_hypothesis", {"top_candidates": [], "notes": []})
    st.session_state.setdefault("finished", False)
    st.session_state.setdefault("client_preview", None)
    st.session_state.setdefault("debug_last_raw", None)
    st.session_state.setdefault("debug_retrieved_titles", [])
    st.session_state.setdefault("debug_scored_preview", [])


def reset_all():
    for k in list(st.session_state.keys()):
        if k.startswith("_"):
            continue
        del st.session_state[k]


# ----------------------------
# UI helpers
# ----------------------------
def render_question(q: Dict[str, Any]) -> Tuple[Optional[Any], bool]:
    st.caption(q.get("stage", ""))
    st.subheader(q.get("question_text", ""))
    a_type = q.get("answer_type", "text")
    opts = q.get("options") or []

    answer = None
    submitted = False

    if a_type == "single":
        answer = st.radio("Выберите:", opts, index=0 if opts else None)
    elif a_type == "multi":
        answer = st.multiselect("Выберите:", opts)
    else:
        answer = st.text_area("Ответ:", height=140, placeholder="Можно коротко. Если есть — один конкретный пример.")

    col1, col2 = st.columns([1, 1])
    with col1:
        submitted = st.button("Далее ➜", use_container_width=True)
    with col2:
        if st.button("Повторить запрос к ИИ", use_container_width=True):
            # просто перегенерим вопрос на том же turn
            st.session_state["current"] = None
            st.rerun()

    return answer, submitted


def build_retrieval_query(state: Dict[str, Any]) -> str:
    parts = []
    if state.get("request"):
        parts.append(state["request"])
    # последний ответ
    if state.get("log"):
        parts.append(str(state["log"][-1].get("answer", "")))
    # гипотеза
    rh = state.get("running_hypothesis") or {}
    tc = rh.get("top_candidates", [])
    if tc:
        parts.append(" ".join(tc))
    return " ".join(parts).strip()


# ----------------------------
# Main
# ----------------------------
st.set_page_config(page_title="NEO Диагностика потенциалов (MVP)", layout="centered")

cfg = load_json("configs/diagnosis_config.json")
init_state()

st.title("NEO Диагностика потенциалов")
st.write("Формат: живой разбор. Вопросы формирует ИИ по логике этапов, без повторов.")

topbar1, topbar2 = st.columns([1, 1])
with topbar1:
    st.write(f"Ход: вопрос {st.session_state['turn'] + 1} из {cfg['diagnosis']['max_turns']}")
with topbar2:
    if st.button("🔄 Сбросить диагностику"):
        reset_all()
        st.rerun()

# preload knowledge chunks
retr_cfg = cfg["retrieval"]
knowledge_chunks = load_knowledge_chunks(
    retr_cfg["knowledge_dir"],
    retr_cfg["files"],
    retr_cfg["chunking"]["max_chars_per_chunk"],
    retr_cfg["chunking"]["overlap_chars"],
)

# If finished, show result
if st.session_state.get("finished"):
    st.success("Диагностика завершена ✅")
    preview = st.session_state.get("client_preview") or {}
    st.markdown(f"**Имя:** {preview.get('name','')}")
    st.markdown(f"**Запрос:** {preview.get('request','')}")
    top3 = preview.get("top3_hypothesis") or []
    st.markdown("**Гипотеза (топ-3 потенциала):** " + (", ".join(top3) if top3 else "—"))

    fills = preview.get("fills_energy") or []
    drains = preview.get("drains_energy") or []
    if fills:
        st.markdown("**Что вас наполняет:**")
        for x in fills[:6]:
            st.write(f"• {x}")
    if drains:
        st.markdown("**Что забирает энергию:**")
        for x in drains[:6]:
            st.write(f"• {x}")

    st.markdown("**Что дальше:**")
    st.write(preview.get("next_step", "Следующий шаг — мастерская версия отчёта."))

    with st.expander("Технические данные (для мастера / отладки)"):
        st.json(st.session_state.get("log", []))
        st.json({"running_hypothesis": st.session_state.get("running_hypothesis")})
        st.json({"retrieved": st.session_state.get("debug_retrieved_titles")})
        if st.session_state.get("debug_last_raw"):
            st.json(st.session_state["debug_last_raw"])
    st.stop()

# Generate next question if needed
if st.session_state.get("current") is None:
    # Stop guard by hard limit
    if st.session_state["turn"] >= cfg["diagnosis"]["max_turns"]:
        st.session_state["finished"] = True
        st.session_state["client_preview"] = {
            "name": st.session_state.get("name", ""),
            "request": st.session_state.get("request", ""),
            "top3_hypothesis": (st.session_state.get("running_hypothesis") or {}).get("top_candidates", [])[:3],
            "fills_energy": [],
            "drains_energy": [],
            "next_step": "Следующий шаг — мастерская версия отчёта (детали, реализация, деньги, план действий)."
        }
        st.rerun()

    # Retrieval
    query = build_retrieval_query(st.session_state)
    retrieved, scored_preview = retrieve_chunks(
        knowledge_chunks,
        query=query,
        top_k=retr_cfg["top_k"],
        max_total_chars=retr_cfg["max_context_chars_total"],
    )
    st.session_state["debug_retrieved_titles"] = [f"{c.source}#{c.idx}" for c in retrieved]
    st.session_state["debug_scored_preview"] = [
        {"source": f"{c.source}#{c.idx}", "score": s} for c, s in scored_preview[:10]
    ]

    # Build prompt and call LLM
    user_prompt = build_user_prompt(cfg, st.session_state, retrieved)

    try:
        data = call_llm(cfg, user_prompt)
        st.session_state["debug_last_raw"] = data

        # basic validation and anti-repeat guard
        asked_texts = set(normalize_text(ev.get("question_text", "")) for ev in st.session_state.get("log", []))
        qtext = data.get("question_text", "")
        if normalize_text(qtext) in asked_texts and not data.get("finish", False):
            # If repeated, force regenerate once by clearing current and rerun
            st.warning("ИИ попытался повторить вопрос — перегенерирую…")
            st.session_state["current"] = None
            # tiny perturbation: append to logless state? simplest: add note to hypothesis
            rh = st.session_state.get("running_hypothesis") or {"top_candidates": [], "notes": []}
            rh["notes"] = (rh.get("notes") or []) + ["Не повторяй предыдущие вопросы, задай новый уточняющий."]
            st.session_state["running_hypothesis"] = rh
            st.rerun()

        st.session_state["current"] = data
    except Exception as e:
        msg = str(e)
        # If rate limit – show friendly
        if "rate" in msg.lower() or "429" in msg:
            st.error("Не удалось получить вопрос от ИИ: лимит/429. Нажми «Повторить запрос к ИИ» через пару секунд.")
        else:
            st.error(f"Не удалось получить вопрос от ИИ: {e}")
        with st.expander("Debug"):
            st.code(user_prompt[:4000] + ("\n...\n" if len(user_prompt) > 4000 else ""))
        st.stop()

# Render current question
q = st.session_state["current"]

# If model says finish now
if q.get("finish", False):
    st.session_state["finished"] = True
    st.session_state["client_preview"] = q.get("client_preview") or {}
    # ensure name/request
    st.session_state["client_preview"]["name"] = st.session_state.get("name", st.session_state["client_preview"].get("name", ""))
    st.session_state["client_preview"]["request"] = st.session_state.get("request", st.session_state["client_preview"].get("request", ""))
    st.rerun()

answer, submitted = render_question(q)

if submitted:
    # Validate empty answers a bit
    if q.get("answer_type") in ("single", "text") and (answer is None or str(answer).strip() == ""):
        st.warning("Ответ пустой. Выбери вариант или напиши коротко.")
        st.stop()

    # persist intake fields if applicable
    intent = q.get("intent", "")
    if intent == "ask_name":
        st.session_state["name"] = str(answer).strip()
    if intent == "ask_request":
        st.session_state["request"] = str(answer).strip()

    # update running hypothesis from LLM output
    rh = q.get("running_hypothesis")
    if isinstance(rh, dict):
        st.session_state["running_hypothesis"] = {
            "top_candidates": rh.get("top_candidates", [])[:9],
            "notes": rh.get("notes", [])[:6],
        }

    # log event
    st.session_state["log"].append(
        {
            "turn": st.session_state["turn"],
            "question_id": q.get("question_id", f"turn_{st.session_state['turn']}"),
            "intent": intent,
            "stage": q.get("stage", ""),
            "question_text": q.get("question_text", ""),
            "answer": answer,
        }
    )

    st.session_state["turn"] += 1
    st.session_state["current"] = None
    st.rerun()

# Debug expander
if cfg["output"]["debug_panel"]["enabled"]:
    with st.expander("Технические данные (для мастера / отладки)"):
        st.write("retrieved:", st.session_state.get("debug_retrieved_titles"))
        st.write("scored preview:", st.session_state.get("debug_scored_preview"))
        st.json({"running_hypothesis": st.session_state.get("running_hypothesis")})
        st.json({"turn_log_tail": st.session_state.get("log", [])[-5:]})