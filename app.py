# app.py
import os
import json
import time
from pathlib import Path

import streamlit as st
from openai import OpenAI


# -----------------------------
# Paths
# -----------------------------
DEFAULT_CONFIG_PATH = "configs/diagnosis_config.json"
KNOWLEDGE_DIR = Path("knowledge")


# -----------------------------
# Loaders
# -----------------------------
def load_json(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_text(path: Path, max_chars: int = 9000) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")[:max_chars]


def build_knowledge_digest(max_chars_each: int = 7000) -> str:
    parts = []
    for fn in ["positions.md", "shifts.md", "methodology.md", "question_bank.md", "examples_transcripts.md"]:
        p = KNOWLEDGE_DIR / fn
        if p.exists():
            parts.append(f"\n\n--- FILE: {fn} ---\n{load_text(p, max_chars_each)}")
    return "".join(parts).strip()


def model_name(cfg: dict) -> str:
    return cfg.get("runtime", {}).get("model", os.environ.get("AI_NEO_MODEL", "gpt-4.1-mini"))


def max_turns(cfg: dict) -> int:
    d = cfg.get("diagnosis", {})
    return int(d.get("hard_stop_at_questions", d.get("max_questions_total", 30) or 30))


# -----------------------------
# Session state
# -----------------------------
def init_state(cfg: dict):
    st.session_state.setdefault("cfg", cfg)
    st.session_state.setdefault("turn", 0)
    st.session_state.setdefault("max_turns", max_turns(cfg))
    st.session_state.setdefault("stage", "intake")
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("current_q", None)
    st.session_state.setdefault("name", "")
    st.session_state.setdefault("request", "")
    st.session_state.setdefault("finished", False)
    st.session_state.setdefault("client_report", None)
    st.session_state.setdefault("knowledge_digest", None)
    st.session_state.setdefault("debug_last_error", None)
    st.session_state.setdefault("ui_error", "")


def reset_all():
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()


# -----------------------------
# OpenAI helpers
# -----------------------------
def get_client() -> OpenAI:
    return OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))


def compact_context(state: dict, keep_last: int = 6) -> str:
    hist = state["history"][-keep_last:]
    lines = []
    for item in hist:
        lines.append(f"[{item.get('stage','')}] Q: {item.get('q','')}\nA: {item.get('a','')}")
    return "\n\n".join(lines).strip()


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
            "options": {"type": "array", "items": {"type": "string"}},
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


def call_llm_next_question(state: dict) -> dict:
    cfg = state["cfg"]
    if state["knowledge_digest"] is None:
        state["knowledge_digest"] = build_knowledge_digest()

    kd = state["knowledge_digest"]
    ctx = compact_context(state, keep_last=6)

    asked_intents = [h.get("intent") for h in state["history"]]
    last_intent = asked_intents[-1] if asked_intents else ""

    system_text = f"""
Ты — AI-диагност Neo Potentials (русский язык).
Правила:
- Не повторяй вопросы по смыслу. Смотри историю.
- Не задавай "почему?" больше одного раза подряд.
- Этапы: intake -> now -> childhood -> behavior -> antipattern -> shifts(if needed) -> wrap.
- Если answer_type=single/multi, options должны быть >=2. Иначе answer_type=text.
- Коротко и по-человечески.
- Используй ТОЛЬКО знания из дайджеста ниже.

ДАЙДЖЕСТ:
{kd}
""".strip()

    user_text = f"""
Состояние:
turn={state["turn"]} из {state["max_turns"]}
stage={state["stage"]}
name={state.get("name","") or "(нет)"}
request={state.get("request","") or "(нет)"}
last_intent={last_intent or "(нет)"}
asked_intents={asked_intents}

История:
{ctx or "(пока нет)"}

Сформируй следующий вопрос (1 шт.) по схеме.
""".strip()

    client = get_client()

    resp = client.responses.create(
        model=model_name(cfg),
        input=[
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text},
        ],
        response_format={"type": "json_schema", "json_schema": QUESTION_SCHEMA},
        max_output_tokens=650,
    )
    data = resp.output_parsed
    if not isinstance(data, dict):
        return {}
    return data


def next_question(state: dict) -> dict:
    # retry x1; иначе fallback
    try:
        q = call_llm_next_question(state)
        if isinstance(q, dict) and q.get("question_text"):
            return q
    except Exception as e:
        st.session_state["debug_last_error"] = str(e)

    # Fallback (НЕ стопорим пользователя)
    return {
        "question_id": f"fallback_{state['turn']}",
        "stage": state["stage"],
        "intent": "fallback",
        "question_text": "Техническая пауза. Если можешь — напиши 1 конкретный пример (ситуация → что сделала → результат). Если не хочешь — просто нажми «Далее».",
        "answer_type": "text",
        "options": [],
        "required": False,          # ВАЖНО: чтобы «Далее» работало даже пустым
        "should_stop": False,
        "why_next": "Fallback при ошибке/лимитах.",
    }


# -----------------------------
# Validation
# -----------------------------
def normalize_q_type(q: dict):
    q_type = q.get("answer_type", "text")
    opts = q.get("options") or []
    if q_type in ("single", "multi") and len(opts) < 2:
        q_type = "text"
        opts = []
    return q_type, opts


def validate_answer(q: dict, answer) -> bool:
    if not q.get("required", True):
        return True
    q_type, opts = normalize_q_type(q)

    if q_type == "single":
        return isinstance(answer, str) and answer.strip() != ""
    if q_type == "multi":
        return isinstance(answer, list) and len(answer) > 0
    return isinstance(answer, str) and answer.strip() != ""


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title="NEO Диагностика", page_icon="🧭", layout="centered")

cfg = load_json(DEFAULT_CONFIG_PATH)
init_state(cfg)

st.title("Диагностика потенциалов")
st.caption("Формат: живой разбор. Вопросы формирует ИИ по логике этапов. В конце — короткая картина + следующий шаг.")

if st.button("🔄 Сбросить диагностику"):
    reset_all()

st.write(f"Ход: вопрос {min(st.session_state['turn'] + 1, st.session_state['max_turns'])} из {st.session_state['max_turns']} | фаза: {st.session_state['stage']}")

# Показываем заметную ошибку UI (если была)
if st.session_state.get("ui_error"):
    st.error(st.session_state["ui_error"])
    st.session_state["ui_error"] = ""

# Finish (пока просто показываем историю)
if st.session_state["finished"] or st.session_state["turn"] >= st.session_state["max_turns"]:
    st.session_state["finished"] = True
    st.success("Диагностика завершена ✅")
    st.markdown(f"**Имя:** {st.session_state.get('name') or '—'}")
    st.markdown(f"**Запрос:** {st.session_state.get('request') or '—'}")

    # Транскрипт
    lines = []
    for item in st.session_state["history"]:
        lines.append(f"{item.get('stage','')} | {item.get('intent','')}\nQ: {item.get('q','')}\nA: {item.get('a','')}\n")
    txt = "\n".join(lines)
    st.download_button("📥 Скачать транскрипт (TXT)", data=txt.encode("utf-8"), file_name="neo_transcript.txt", mime="text/plain")

    if st.session_state.get("debug_last_error"):
        st.caption("Тех. лог (если нужно мастеру): ошибка вызова модели была зафиксирована в session.")
    st.stop()

# Create question if missing
if st.session_state["current_q"] is None:
    q = next_question(st.session_state)
    if q.get("stage"):
        st.session_state["stage"] = q["stage"]
    st.session_state["current_q"] = q
else:
    q = st.session_state["current_q"]

q_type, options = normalize_q_type(q)

# ---- FORM (важно для мобилки) ----
with st.form(key="neo_form", clear_on_submit=True):
    st.markdown(f"### {q.get('question_text','').strip()}")

    answer = None
    if q_type == "single":
        answer = st.radio("Выбери один вариант:", options)
    elif q_type == "multi":
        answer = st.multiselect("Выбери варианты:", options)
    else:
        answer = st.text_area("Ответ:", height=130)

    col1, col2 = st.columns([1, 1])
    with col1:
        submitted = st.form_submit_button("Далее ➜")
    with col2:
        finish_now = st.form_submit_button("Завершить сейчас")

if finish_now:
    st.session_state["finished"] = True
    st.rerun()

if submitted:
    if not validate_answer(q, answer):
        # это будет видно СРАЗУ сверху на экране
        st.session_state["ui_error"] = "Пожалуйста, напиши ответ (или выбери вариант), чтобы продолжить."
        st.rerun()

    # Save intake quickly (простая логика)
    intent = q.get("intent", "")
    if intent in ("ask_name", "name") and isinstance(answer, str):
        st.session_state["name"] = answer.strip()
    if intent in ("ask_request", "request") and isinstance(answer, str):
        st.session_state["request"] = answer.strip()

    # Запись истории
    st.session_state["history"].append(
        {
            "turn": st.session_state["turn"],
            "question_id": q.get("question_id", f"q_{st.session_state['turn']}"),
            "intent": intent,
            "stage": q.get("stage", st.session_state["stage"]),
            "q": q.get("question_text", ""),
            "a": answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False),
        }
    )

    st.session_state["turn"] += 1
    st.session_state["current_q"] = None

    # если модель сказала стоп — завершаем (после минимума вопросов)
    if q.get("should_stop") is True and st.session_state["turn"] >= 8:
        st.session_state["finished"] = True

    st.rerun()
    