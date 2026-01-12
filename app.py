# app.py
import json
import re
from pathlib import Path
import streamlit as st

# -----------------------------
# Helpers: load repo knowledge
# -----------------------------
ROOT = Path(__file__).parent

def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""

def load_config() -> dict:
    return json.loads((ROOT / "configs" / "diagnosis_config.json").read_text(encoding="utf-8"))

def load_question_bank_md() -> str:
    return read_text(ROOT / "knowledge" / "question_bank.md")

def load_examples_md() -> str:
    return read_text(ROOT / "knowledge" / "examples_transcripts.md")

def load_methodology_md() -> str:
    return read_text(ROOT / "knowledge" / "methodology.md")

def load_positions_md() -> str:
    return read_text(ROOT / "knowledge" / "positions.md")

def load_shifts_md() -> str:
    return read_text(ROOT / "knowledge" / "shifts.md")

# -----------------------------
# Parse question_bank.md blocks
# We expect blocks like:
# ### ID: ...
# intent: ...
# stage: ...
# type: text|single|multi
# options: - ...
# question: ...
# -----------------------------
def parse_question_bank(md: str):
    blocks = re.split(r"\n(?=### ID: )", md.strip())
    questions = []
    for b in blocks:
        b = b.strip()
        if not b.startswith("### ID: "):
            continue
        qid = re.search(r"### ID:\s*(.+)", b)
        qid = qid.group(1).strip() if qid else None

        def get_field(name):
            m = re.search(rf"^{name}:\s*(.+)$", b, flags=re.MULTILINE)
            return m.group(1).strip() if m else None

        intent = get_field("intent")
        stage = get_field("stage")
        qtype = get_field("type")
        column = get_field("column")
        weight = get_field("weight")

        # options: lines starting with "- "
        opts = re.findall(r"^- (.+)$", b, flags=re.MULTILINE)
        # question text: after "Вопрос:" line until next meta or end
        qtext = None
        m = re.search(r"Вопрос:\s*\n(.+?)(\n[A-Za-z_]+:|\Z)", b, flags=re.DOTALL)
        if m:
            qtext = m.group(1).strip()

        questions.append({
            "id": qid,
            "intent": intent,
            "stage": stage,
            "type": qtype,
            "column": column if column and column != "null" else None,
            "weight": float(weight) if weight else 1.0,
            "text": qtext or "",
            "options": opts
        })
    return questions

# -----------------------------
# Session state
# -----------------------------
def init_state():
    st.session_state.setdefault("asked_ids", [])
    st.session_state.setdefault("answers", [])   # list of dict events
    st.session_state.setdefault("stage", "stage0_intake")
    st.session_state.setdefault("name", "")
    st.session_state.setdefault("request", "")
    st.session_state.setdefault("last_user_text", "")
    st.session_state.setdefault("locks", {"top_potentials": [], "row": None, "col": None})
    st.session_state.setdefault("turn", 0)
    st.session_state.setdefault("current_qid", None)

# -----------------------------
# Basic “no repeats” semantic guard
# (lightweight MVP): we block asking same intent twice in same stage,
# and we never repeat exact question ID.
# -----------------------------
def already_asked(q, asked_ids, answers):
    if q["id"] in asked_ids:
        return True
    # prevent repeating same intent too often
    same_intent_count = sum(1 for a in answers if a.get("intent") == q["intent"])
    if same_intent_count >= 1 and q["stage"] == "stage0_intake":
        return True
    return False

# -----------------------------
# Pick next question (deterministic state machine MVP)
# Stage0: name -> request -> current_situation -> goal_3m
# Then: move through stages from config priorities.
# -----------------------------
def pick_next_question(cfg, questions):
    asked_ids = st.session_state["asked_ids"]
    answers = st.session_state["answers"]
    stage = st.session_state["stage"]

    # ordered stage plan for MVP (master-like)
    stage_plan = [
        "stage0_intake",
        "stage1_now",
        "stage2_childhood",
        "stage3_hypothesis_checks",
        "stage4_shifts",
        "stage5_wrap"
    ]

    # if stage not in plan -> reset
    if stage not in stage_plan:
        stage = "stage0_intake"
        st.session_state["stage"] = stage

    # find first not-asked question in current stage
    candidates = [q for q in questions if q["stage"] == stage and not already_asked(q, asked_ids, answers)]
    if candidates:
        return candidates[0]

    # else advance stage
    idx = stage_plan.index(stage)
    if idx < len(stage_plan) - 1:
        st.session_state["stage"] = stage_plan[idx + 1]
        return pick_next_question(cfg, questions)

    return None

def hard_stop(cfg):
    max_q = cfg.get("diagnosis", {}).get("stop_rules", {}).get("hard_stop_at_questions", 20)
    return st.session_state["turn"] >= max_q

# -----------------------------
# UI render for a question
# -----------------------------
def render_answer_ui(q):
    st.markdown(f"### {q['text']}")
    if q["type"] == "text":
        return st.text_area("Ваш ответ:", height=120, key=f"ans_{q['id']}")
    if q["type"] == "single":
        return st.radio("Выберите вариант:", q["options"], key=f"ans_{q['id']}")
    if q["type"] == "multi":
        return st.multiselect("Выберите варианты:", q["options"], key=f"ans_{q['id']}")
    return st.text_area("Ваш ответ:", height=120, key=f"ans_{q['id']}")

def save_answer(q, answer):
    event = {
        "turn": st.session_state["turn"],
        "question_id": q["id"],
        "intent": q["intent"],
        "stage": q["stage"],
        "question_text": q["text"],
        "answer": answer
    }
    st.session_state["answers"].append(event)
    st.session_state["asked_ids"].append(q["id"])
    st.session_state["turn"] += 1

    # store name + request early
    if q["intent"] == "ask_name" and isinstance(answer, str):
        st.session_state["name"] = answer.strip()
    if q["intent"] == "ask_request" and isinstance(answer, str):
        st.session_state["request"] = answer.strip()

# -----------------------------
# Minimal report (client mini)
# (scoring can be added after; MVP: show structured summary)
# -----------------------------
def client_mini_report():
    name = st.session_state.get("name") or "Вы"
    req = st.session_state.get("request") or "запрос не указан"
    st.success("Диагностика завершена ✅")
    st.markdown(f"**Имя:** {name}")
    st.markdown(f"**Запрос:** {req}")
    st.markdown("**Что дальше:**")
    st.markdown("- Я сформировал(а) гипотезу по потенциалам и рядам на основе ваших ответов.")
    st.markdown("- Следующий шаг: мастерская версия отчёта (детали, реализация, деньги, план действий).")
    st.markdown("**Ваши ответы (лог):**")
    st.json(st.session_state["answers"])

# -----------------------------
# Streamlit App
# -----------------------------
st.set_page_config(page_title="ai-neo диагностика", page_icon="🧠", layout="centered")
init_state()

cfg = load_config()
questions_md = load_question_bank_md()
questions = parse_question_bank(questions_md)

st.title("NEO Диагностика потенциалов")
st.caption("Формат: живой разбор. Вопросы подбираются по логике этапов, без повторов.")

if hard_stop(cfg):
    client_mini_report()
    st.stop()

# pick question
q = pick_next_question(cfg, questions)
if not q:
    client_mini_report()
    st.stop()

# friendly “master-like” reflection line at stage0
if q["stage"] == "stage0_intake":
    st.info("Сначала зафиксируем контекст — это нужно, чтобы разбор был точным.")
elif q["stage"] == "stage1_now":
    st.info("Сейчас важно понять вашу текущую ситуацию (точка А).")
elif q["stage"] == "stage2_childhood":
    st.info("Теперь посмотрим детство — там часто самые чистые мотиваторы.")
elif q["stage"] == "stage3_hypothesis_checks":
    st.info("Проверяем гипотезы: что даёт энергию, что забирает, какие роли естественны.")
elif q["stage"] == "stage4_shifts":
    st.warning("Пара вопросов на смещения — только чтобы не ошибиться из-за “надо/должен”.")
elif q["stage"] == "stage5_wrap":
    st.info("Финальные уточнения перед итогом.")

answer = render_answer_ui(q)

col1, col2 = st.columns([1, 1])
with col1:
    next_btn = st.button("Далее ➜", type="primary")
with col2:
    reset_btn = st.button("Сбросить диагностику")

if reset_btn:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

if next_btn:
    # basic validation
    if q["type"] == "multi" and isinstance(answer, list) and len(answer) == 0:
        st.error("Выберите хотя бы один вариант.")
        st.stop()
    if q["type"] == "text" and (not isinstance(answer, str) or len(answer.strip()) < 2):
        st.error("Напишите короткий ответ (хотя бы 2 символа).")
        st.stop()

    save_answer(q, answer)
    st.rerun()