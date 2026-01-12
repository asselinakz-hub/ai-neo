import streamlit as st
import json
from pathlib import Path

# ---------- LOAD CONFIG ----------
def load_config():
    with open("configs/diagnosis_config.json", "r", encoding="utf-8") as f:
        return json.load(f)

# ---------- INIT STATE ----------
def init_state():
    st.session_state.setdefault("turn", 0)
    st.session_state.setdefault("asked", [])
    st.session_state.setdefault("answers", {})
    st.session_state.setdefault("scores", {})
    st.session_state.setdefault("finished", False)

# ---------- SIMPLE QUESTION BANK (TEMP) ----------
# ВАЖНО: это временно, пока мы подключаем твой question_bank.md
QUESTION_BANK = [
    {
        "id": "q1",
        "text": "В каких ситуациях ты чувствуешь себя наиболее уверенно?",
        "type": "text"
    },
    {
        "id": "q2",
        "text": "Что тебя по-настоящему вдохновляет в жизни?",
        "type": "text"
    },
    {
        "id": "q3",
        "text": "За что тебя чаще всего ценят или хвалят?",
        "type": "text"
    },
    {
        "id": "q4",
        "text": "Какие дела ты откладываешь до последнего?",
        "type": "text"
    },
    {
        "id": "q5",
        "text": "Во что ты любил(а) играть в детстве?",
        "type": "text"
    }
]

# ---------- PICK NEXT QUESTION ----------
def pick_next_question():
    for q in QUESTION_BANK:
        if q["id"] not in st.session_state["asked"]:
            return q
    return None

# ---------- SHOULD STOP ----------
def should_stop(cfg):
    if st.session_state["turn"] == 0:
        return False
    if st.session_state["turn"] < cfg["diagnosis"]["min_questions_before_finish"]:
        return False
    if st.session_state["turn"] >= cfg["diagnosis"]["max_questions_total"]:
        return True
    return False

# ---------- APP ----------
cfg = load_config()
init_state()

st.title("Диагностика потенциалов (MVP)")

if st.session_state["finished"]:
    st.success("Диагностика завершена ✅")
    st.subheader("Ответы пользователя:")
    st.json(st.session_state["answers"])
    st.stop()

q = pick_next_question()

if q is None or should_stop(cfg):
    st.session_state["finished"] = True
    st.rerun()

st.caption(f"Вопрос {st.session_state['turn'] + 1} из {cfg['diagnosis']['max_questions_total']}")
st.write(q["text"])

answer = st.text_area("Ваш ответ")

if st.button("Далее ➜"):
    st.session_state["answers"][q["id"]] = answer
    st.session_state["asked"].append(q["id"])
    st.session_state["turn"] += 1
    st.rerun()