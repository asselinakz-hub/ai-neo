import streamlit as st
import json
from pathlib import Path

# --- Загрузка банка вопросов (пример: configs/diagnosis_config.json) ---
def load_bank(path="configs/diagnosis_config.json"):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

# --- Инициализация памяти ---
def init_state():
    st.session_state.setdefault("asked", set())
    st.session_state.setdefault("answers", {})      # qid -> user answer
    st.session_state.setdefault("scores", {})       # потенциал -> float
    st.session_state.setdefault("evidence", {})     # потенциал -> [str]
    st.session_state.setdefault("stage", "warmup")  # warmup/targeted/shifts/final
    st.session_state.setdefault("turn", 0)          # сколько вопросов задали
    st.session_state.setdefault("current_qid", None)

# --- Простейшее начисление баллов по маппингу вариантов ---
def apply_scoring(question, user_answer, cfg):
    """
    question: dict из банка
    user_answer: str | list | text
    cfg: весь config
    """
    scores = st.session_state["scores"]
    evidence = st.session_state["evidence"]

    # 1) если вопрос имеет option_map: option -> {potential: weight}
    option_map = question.get("option_map", {})  # {"вариант текста": {"Янтарь": 1.2, ...}}
    base_w = float(question.get("weight", 1.0))

    def add(p, v, note):
        scores[p] = float(scores.get(p, 0.0)) + float(v)
        evidence.setdefault(p, []).append(note)

    if question.get("type") == "single":
        if user_answer in option_map:
            for pot, w in option_map[user_answer].items():
                add(pot, base_w * float(w), f"{question['id']}: {user_answer}")
    elif question.get("type") == "multi":
        if isinstance(user_answer, list) and len(user_answer) > 0:
            per = 1.0 / len(user_answer)
            for ans in user_answer:
                if ans in option_map:
                    for pot, w in option_map[ans].items():
                        add(pot, base_w * float(w) * per, f"{question['id']}: {ans}")
    elif question.get("type") == "text":
        # text scoring: по словарю ключевых слов (из твоих файлов)
        # в cfg можно держать keywords: {potential: ["слово1","слово2"]}
        text = (user_answer or "").lower()
        kw = cfg.get("keywords", {})
        for pot, words in kw.items():
            hit = any(w.lower() in text for w in words)
            if hit:
                add(pot, base_w * 0.6, f"{question['id']}: текстовый маркер")

# --- Выбор следующего вопроса по логике ---
def pick_next_question(cfg):
    bank = cfg["question_bank"]  # список вопросов
    asked = st.session_state["asked"]
    stage = st.session_state["stage"]
    turn = st.session_state["turn"]

    # helper: вернуть вопрос по id
    by_id = {q["id"]: q for q in bank}

    # 1) Warmup: первые N вопросов из warmup_ids
    warmup_ids = cfg.get("warmup_ids", [])
    if stage == "warmup":
        for qid in warmup_ids:
            if qid not in asked:
                return by_id[qid]
        st.session_state["stage"] = "targeted"

    # 2) Targeted: выбираем потенциалы с максимальной неопределенностью
    # MVP-эвристика: спрашиваем больше по ТОП-3, но только если evidence мало
    scores = st.session_state["scores"]
    evidence = st.session_state["evidence"]

    # если пока нет скоринга — просто бери любые "general" вопросы
    if not scores:
        for q in bank:
            if q["id"] not in asked and "general" in q.get("tags", []):
                return q

    # топ потенциалы по score
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_pots = [p for p,_ in top[:3]]

    # ищем потенциал, где мало доказательств
    need_pot = None
    for p in top_pots:
        if len(evidence.get(p, [])) < cfg.get("min_evidence_per_potential", 3):
            need_pot = p
            break

    # если все топы уже подтверждены — берем следующий по рейтингу
    if need_pot is None and top:
        need_pot = top[0][0]

    # 3) Сначала follow-up вопросы, если они есть
    for q in bank:
        if q["id"] in asked:
            continue
        # если вопрос помечен potential_tag и совпадает с need_pot — приоритет
        if need_pot and need_pot in q.get("potential_tags", []):
            return q

    # 4) Затем вопросы на смещения ближе к концу
    if turn >= cfg.get("shift_check_after_turn", 12) and stage != "shifts":
        st.session_state["stage"] = "shifts"

    if stage == "shifts":
        for q in bank:
            if q["id"] not in asked and "shift" in q.get("tags", []):
                return q
        st.session_state["stage"] = "final"

    # 5) fallback — любой не заданный
    for q in bank:
        if q["id"] not in asked:
            return q

    return None

def should_stop(cfg):
    # стоп по лимиту
    if st.session_state["turn"] >= cfg.get("max_turns", 20):
        return True
    # стоп по уверенности (MVP: когда есть хотя бы 7-9 доказательств по топам)
    scores = st.session_state["scores"]
    evidence = st.session_state["evidence"]
    if not scores:
        return False
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:3]
    ok = all(len(evidence.get(p, [])) >= cfg.get("min_evidence_per_potential", 3) for p,_ in top)
    return ok

# ---------------- Streamlit flow ----------------
cfg = load_bank()
init_state()

# если нет текущего вопроса — выбираем
if st.session_state["current_qid"] is None:
    q = pick_next_question(cfg)
    if q is None or should_stop(cfg):
        st.write("Диагностика завершена ✅")
        st.json({"scores": st.session_state["scores"], "answers": st.session_state["answers"]})
        st.stop()
    st.session_state["current_qid"] = q["id"]
else:
    q = next(qq for qq in cfg["question_bank"] if qq["id"] == st.session_state["current_qid"])

st.subheader(q["text"])

# UI ответа
answer = None
if q["type"] == "single":
    answer = st.radio("Выберите:", q["options"])
elif q["type"] == "multi":
    answer = st.multiselect("Выберите:", q["options"])
elif q["type"] == "text":
    answer = st.text_area("Ответ:", height=120)

if st.button("Далее ➜"):
    qid = q["id"]
    st.session_state["asked"].add(qid)
    st.session_state["answers"][qid] = answer
    apply_scoring(q, answer, cfg)
    st.session_state["turn"] += 1
    st.session_state["current_qid"] = None
    st.rerun()