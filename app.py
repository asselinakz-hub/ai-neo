# app.py
import os
import json
import time
from pathlib import Path
import streamlit as st

# OpenAI SDK (new style)
from openai import OpenAI


# -----------------------------
# Config + Knowledge loaders
# -----------------------------
DEFAULT_CONFIG_PATH = "configs/diagnosis_config.json"
KNOWLEDGE_DIR = Path("knowledge")
PROMPTS_DIR = Path("prompts")


def load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path: Path, max_chars: int = 12000) -> str:
    if not path.exists():
        return ""
    txt = path.read_text(encoding="utf-8", errors="ignore")
    return txt[:max_chars]


def build_knowledge_digest(max_chars_each: int = 8000) -> str:
    # берем только краткий дайджест, чтобы не сносить лимиты токенов
    parts = []
    files_order = [
        "positions.md",
        "shifts.md",
        "methodology.md",
        "question_bank.md",
        "examples_transcripts.md",
    ]
    for fn in files_order:
        p = KNOWLEDGE_DIR / fn
        if p.exists():
            parts.append(f"\n\n--- FILE: {fn} ---\n{load_text(p, max_chars_each)}")
    return "".join(parts).strip()


def model_name(cfg: dict) -> str:
    # Можно задать в configs/diagnosis_config.json: { "runtime": { "model": "gpt-4.1-mini" } }
    return (
        cfg.get("runtime", {})
        .get("model", os.environ.get("AI_NEO_MODEL", "gpt-4.1-mini"))
    )


def max_turns(cfg: dict) -> int:
    return int(cfg.get("diagnosis", {}).get("hard_stop_at_questions", cfg.get("diagnosis", {}).get("max_questions_total", 30) or 30))


def target_language(cfg: dict) -> str:
    return cfg.get("language", "ru")


# -----------------------------
# Session state
# -----------------------------
def init_state(cfg: dict):
    st.session_state.setdefault("cfg", cfg)
    st.session_state.setdefault("turn", 0)
    st.session_state.setdefault("max_turns", max_turns(cfg))
    st.session_state.setdefault("stage", "intake")
    st.session_state.setdefault("history", [])  # list of {turn, stage, q, a, meta}
    st.session_state.setdefault("current_q", None)  # dict question
    st.session_state.setdefault("name", "")
    st.session_state.setdefault("request", "")
    st.session_state.setdefault("finished", False)
    st.session_state.setdefault("client_report", None)
    st.session_state.setdefault("debug_last_error", None)

    # Кэш дайджеста, чтобы не читать файлы заново
    st.session_state.setdefault("knowledge_digest", None)


def reset_all():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


# -----------------------------
# OpenAI helpers
# -----------------------------
def get_client() -> OpenAI:
    # Streamlit Cloud: добавь OPENAI_API_KEY в Secrets
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def compact_context(state: dict, keep_last: int = 6) -> str:
    """
    Сжимаем контекст: держим только последние N шагов.
    """
    hist = state["history"][-keep_last:]
    lines = []
    for item in hist:
        q = item.get("q", "").strip()
        a = item.get("a", "").strip()
        stage = item.get("stage", "")
        lines.append(f"[{stage}] Q: {q}\nA: {a}")
    return "\n\n".join(lines).strip()


def safe_json(obj) -> dict:
    if isinstance(obj, dict):
        return obj
    return {}


def call_llm_json(system_text: str, user_text: str, cfg: dict, response_schema: dict, max_output_tokens: int = 600):
    client = get_client()
    m = model_name(cfg)
    return client.responses.create(
        model=m,
        input=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": response_schema,
        },
        max_output_tokens=max_output_tokens,
    )


# -----------------------------
# Question generator (HYBRID)
# -----------------------------
QUESTION_SCHEMA = {
    "name": "next_question",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "question_id": {"type": "string"},
            "stage": {"type": "string"},
            "intent": {"type": "string"},
            "question_text": {"type": "string"},
            "answer_type": {"type": "string", "enum": ["text", "single", "multi"]},
            "options": {
                "type": "array",
                "items": {"type": "string"},
            },
            "required": {"type": "boolean"},
            "should_stop": {"type": "boolean"},
            "why_next": {"type": "string"},
        },
        "required": [
            "question_id",
            "stage",
            "intent",
            "question_text",
            "answer_type",
            "options",
            "required",
            "should_stop",
            "why_next",
        ],
    },
}


def next_question_llm(state: dict) -> dict:
    cfg = state["cfg"]

    if state["knowledge_digest"] is None:
        state["knowledge_digest"] = build_knowledge_digest()

    kd = state["knowledge_digest"]
    # супер-важно: НЕ кормим модель всем подряд, иначе словим TPM.
    # Даем только дайджест + компактный контекст.
    ctx = compact_context(state, keep_last=6)

    # Правила: гибрид — ИИ задаёт вопросы, но:
    # 1) не повторяет уже заданные по смыслу
    # 2) не “мусолит” эмоции бесконечно (не более 1 уточнения подряд)
    # 3) держит темп: конкретика -> пример -> проверка в детстве -> проверка антипаттерна -> фиксация
    # 4) если генерирует варианты, то они должны быть НЕ пустыми; если пусто — пусть будет text
    # 5) первые 2 шага — имя и запрос (intake)
    asked_intents = [h.get("intent") for h in state["history"]]
    last_intent = asked_intents[-1] if asked_intents else ""

    system_text = f"""
Ты — AI-диагност, который проводит живой разбор потенциалов (Neo Potentials).
Язык: {target_language(cfg)}.

ЖЕСТКИЕ ПРАВИЛА:
- Не повторяй вопросы по смыслу. Смотри историю.
- Не задавай "почему?" больше одного раза подряд. Если уже был уточняющий вопрос — переходи к фактам/примерам.
- Двигайся по этапам: intake -> now -> childhood -> behavior -> antipattern -> shifts(if needed) -> wrap.
- Если answer_type = "single" или "multi", options должны быть НЕ пустыми (>=2). Иначе ставь answer_type="text" и options=[].
- Вопросы должны быть короткие, человеческие, без лекций.
- Используй знания ТОЛЬКО из загруженных материалов (дайджест ниже). Не выдумывай теорию вне них.
- Максимум один вопрос за шаг. Верни строго JSON по схеме.

ВАЖНО ПРО UX:
- Клиент отвечает в одном поле. Не добавляй лишние элементы интерфейса.
- required=true почти всегда. required=false только если вопрос "если хочешь/по желанию".

ДАЙДЖЕСТ ЗНАНИЙ (используй как базу формулировок и логики):
{kd}
""".strip()

    user_text = f"""
ТЕКУЩЕЕ СОСТОЯНИЕ:
- turn: {state["turn"]} из {state["max_turns"]}
- stage: {state["stage"]}
- имя: {state.get("name","").strip() or "(не задано)"}
- запрос: {state.get("request","").strip() or "(не задан)"}
- последний intent: {last_intent or "(нет)"}
- уже заданные intents: {asked_intents}

ИСТОРИЯ (последние шаги):
{ctx or "(пока нет)"}

СЕЙЧАС:
Сформируй следующий вопрос так, чтобы он:
1) продвинул разбор,
2) проверил гипотезы по потенциалам/позициям,
3) был конкретным и не повторялся.

Верни should_stop=true только если уже достаточно информации для краткой клиентской картины.
""".strip()

    # retry logic for rate limits / transient errors
    last_err = None
    for _ in range(2):
        try:
            resp = call_llm_json(
                system_text=system_text,
                user_text=user_text,
                cfg=cfg,
                response_schema=QUESTION_SCHEMA,
                max_output_tokens=650,
            )
            data = resp.output_parsed  # dict
            return safe_json(data)
        except Exception as e:
            last_err = str(e)
            # не говорим "подожди 30 сек", просто даем кнопку Retry в UI
            time.sleep(0.2)

    st.session_state["debug_last_error"] = last_err
    # fallback вопрос если LLM временно недоступен
    return {
        "question_id": f"fallback_{state['turn']}",
        "stage": state["stage"],
        "intent": "fallback",
        "question_text": "У меня техническая пауза. Напиши, пожалуйста, один конкретный пример из жизни (ситуация → что ты сделал(а) → какой был результат), который у тебя получается лучше большинства людей.",
        "answer_type": "text",
        "options": [],
        "required": True,
        "should_stop": False,
        "why_next": "Fallback при ошибке модели/лимитах.",
    }


# -----------------------------
# Report generator
# -----------------------------
REPORT_SCHEMA = {
    "name": "client_report",
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "top3_potentials": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 3,
            },
            "rows": {"type": "string"},
            "columns": {"type": "string"},
            "short_summary": {"type": "string"},
            "strengths_bullets": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 6,
            },
            "energy_fillers_bullets": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 3,
                "maxItems": 6,
            },
            "next_step": {"type": "string"},
        },
        "required": [
            "top3_potentials",
            "rows",
            "columns",
            "short_summary",
            "strengths_bullets",
            "energy_fillers_bullets",
            "next_step",
        ],
    },
}


def generate_client_report(state: dict) -> dict:
    cfg = state["cfg"]
    if state["knowledge_digest"] is None:
        state["knowledge_digest"] = build_knowledge_digest()

    kd = state["knowledge_digest"]

    # Полная история, но аккуратно
    hist_lines = []
    for item in state["history"]:
        hist_lines.append(f"[{item.get('stage')}] {item.get('q')}\nA: {item.get('a')}")
    transcript = "\n\n".join(hist_lines)[:14000]

    system_text = f"""
Ты формируешь КЛИЕНТСКИЙ мини-результат диагностики потенциалов.
Язык: {target_language(cfg)}.

Правила:
- НЕ показывай сырые логи/баллы/веса.
- Дай только краткую картину: топ-3 потенциала + коротко ряды/столбцы + что делать дальше.
- Опирайся на материалы (дайджест).
- Если есть сомнение — выбирай наиболее подтвержденное формулировками клиента и фактами.

ДАЙДЖЕСТ:
{kd}
""".strip()

    user_text = f"""
Имя клиента: {state.get('name','')}
Запрос: {state.get('request','')}

Транскрипт:
{transcript}

Собери клиентский мини-отчет.
""".strip()

    try:
        resp = call_llm_json(
            system_text=system_text,
            user_text=user_text,
            cfg=cfg,
            response_schema=REPORT_SCHEMA,
            max_output_tokens=850,
        )
        return safe_json(resp.output_parsed)
    except Exception as e:
        st.session_state["debug_last_error"] = str(e)
        return {
            "top3_potentials": ["(не удалось)", "(не удалось)", "(не удалось)"],
            "rows": "—",
            "columns": "—",
            "short_summary": "Не удалось сформировать отчет из-за технической ошибки. Попробуйте перезапустить.",
            "strengths_bullets": ["—", "—", "—"],
            "energy_fillers_bullets": ["—", "—", "—"],
            "next_step": "Перезапустить диагностику и пройти снова.",
        }


# -----------------------------
# UI helpers
# -----------------------------
def render_question(q: dict):
    # защита от пустых options
    q_type = q.get("answer_type", "text")
    options = q.get("options") or []

    if q_type in ("single", "multi") and len(options) < 2:
        q_type = "text"
        options = []

    st.markdown(f"### {q.get('question_text','').strip()}")

    answer_key = f"answer_{st.session_state['turn']}"
    answer = None

    if q_type == "single":
        answer = st.radio("Выбери один вариант:", options, key=answer_key)
    elif q_type == "multi":
        answer = st.multiselect("Выбери варианты:", options, key=answer_key)
    else:
        answer = st.text_area("Ответ:", height=130, key=answer_key)

    return answer, answer_key


def validate_answer(q: dict, answer) -> bool:
    if not q.get("required", True):
        return True
    q_type = q.get("answer_type", "text")
    options = q.get("options") or []
    if q_type in ("single", "multi") and len(options) < 2:
        q_type = "text"

    if q_type == "single":
        return isinstance(answer, str) and answer.strip() != ""
    if q_type == "multi":
        return isinstance(answer, list) and len(answer) > 0
    return isinstance(answer, str) and answer.strip() != ""


# -----------------------------
# Main app
# -----------------------------
st.set_page_config(page_title="NEO Диагностика потенциалов", page_icon="🧭", layout="centered")

cfg = load_json(DEFAULT_CONFIG_PATH)
init_state(cfg)

# Minimal header
st.title("Диагностика потенциалов")
st.caption("Формат: живой разбор. Вопросы формирует ИИ по логике этапов, без повторов. В конце — короткая картина + следующий шаг.")

# Reset button
col_a, col_b = st.columns([1, 1])
with col_a:
    if st.button("🔄 Сбросить диагностику"):
        reset_all()

# Progress line
st.write(f"Ход: вопрос {min(st.session_state['turn'] + 1, st.session_state['max_turns'])} из {st.session_state['max_turns']}  |  фаза: {st.session_state['stage']}")

# If finished: show report
if st.session_state["finished"]:
    st.success("Диагностика завершена ✅")
    rep = st.session_state.get("client_report")
    if not rep:
        rep = generate_client_report(st.session_state)
        st.session_state["client_report"] = rep

    st.markdown(f"**Имя:** {st.session_state.get('name','') or '—'}")
    st.markdown(f"**Запрос:** {st.session_state.get('request','') or '—'}")

    st.subheader("Результат (кратко)")
    st.markdown(f"**Топ-3 потенциала:** {', '.join(rep.get('top3_potentials', []))}")
    st.markdown(f"**Ряды:** {rep.get('rows','—')}")
    st.markdown(f"**Столбцы:** {rep.get('columns','—')}")
    st.write(rep.get("short_summary", ""))

    st.subheader("Ваши сильные стороны")
    for b in rep.get("strengths_bullets", []):
        st.write(f"• {b}")

    st.subheader("Что вас наполняет")
    for b in rep.get("energy_fillers_bullets", []):
        st.write(f"• {b}")

    st.subheader("Следующий шаг")
    st.write(rep.get("next_step", ""))

    # Download transcript (client-friendly)
    hist = st.session_state["history"]
    lines = []
    for item in hist:
        lines.append(f"{item.get('stage','')} | {item.get('intent','')}\nQ: {item.get('q','')}\nA: {item.get('a','')}\n")
    txt = "\n".join(lines)
    st.download_button("📥 Скачать транскрипт (TXT)", data=txt.encode("utf-8"), file_name="neo_transcript.txt", mime="text/plain")

    # Optional: show last error only if exists (small)
    if st.session_state.get("debug_last_error"):
        st.caption("Тех. заметка: была ошибка при запросе к модели (можно игнорировать, если всё прошло).")
    st.stop()

# If max turns reached => finish
if st.session_state["turn"] >= st.session_state["max_turns"]:
    st.session_state["finished"] = True
    st.rerun()

# Get / create current question
if st.session_state["current_q"] is None:
    q = next_question_llm(st.session_state)

    # stage management (intake helpers)
    # Сохраняем stage из вопроса, если пришло
    if q.get("stage"):
        st.session_state["stage"] = q["stage"]

    st.session_state["current_q"] = q
else:
    q = st.session_state["current_q"]

# Render question
answer, answer_key = render_question(q)

# Buttons
col1, col2 = st.columns([1, 1])
with col1:
    go_next = st.button("Далее ➜")
with col2:
    finish_now = st.button("Завершить сейчас")

if finish_now:
    st.session_state["finished"] = True
    st.rerun()

if go_next:
    if not validate_answer(q, answer):
        st.warning("Выбери вариант или напиши ответ.")
        st.stop()

    # Save name/request when intake
    qid = q.get("question_id", f"q_{st.session_state['turn']}")
    intent = q.get("intent", "")
    stage = q.get("stage", st.session_state["stage"])
    q_text = q.get("question_text", "")

    # intake capture: если вопрос про имя/запрос — вытаскиваем из текста
    if intent in ("ask_name", "q_name", "name"):
        st.session_state["name"] = (answer or "").strip()
    if intent in ("ask_request", "q_request", "request"):
        st.session_state["request"] = (answer or "").strip()

    # если вопрос объединенный "имя+запрос" — пробуем вытащить
    if intent in ("ask_name_and_request", "intake"):
        txt = (answer or "").strip()
        # очень мягкий парсер: первая строка имя, остальное запрос
        parts = [p.strip() for p in txt.split("\n") if p.strip()]
        if parts:
            # если похоже на "Меня ...", то оставим как есть
            if len(parts) == 1:
                # оставим в request, имя если уже было — не трогаем
                if not st.session_state["name"]:
                    st.session_state["name"] = "—"
                st.session_state["request"] = parts[0]
            else:
                if not st.session_state["name"] or st.session_state["name"] == "—":
                    st.session_state["name"] = parts[0]
                st.session_state["request"] = " ".join(parts[1:])

    # Append to history
    st.session_state["history"].append(
        {
            "turn": st.session_state["turn"],
            "question_id": qid,
            "intent": intent,
            "stage": stage,
            "q": q_text,
            "a": answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False),
            "meta": {"why_next": q.get("why_next", "")},
        }
    )

    # advance
    st.session_state["turn"] += 1
    st.session_state["current_q"] = None

    # clear widget for next question
    try:
        del st.session_state[answer_key]
    except Exception:
        pass

    # stop if model says stop
    if q.get("should_stop") is True and st.session_state["turn"] >= 8:
        st.session_state["finished"] = True

    st.rerun()