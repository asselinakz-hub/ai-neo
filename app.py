import streamlit as st
import json
from pathlib import Path
from datetime import datetime

CONFIG_PATH = "configs/diagnosis_config.json"


# ----------------- Load -----------------
def load_cfg(path=CONFIG_PATH):
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def now_iso():
    return datetime.utcnow().isoformat()


# ----------------- State -----------------
def init_state(cfg):
    st.session_state.setdefault("asked_ids", set())
    st.session_state.setdefault("answers_log", [])   # event log
    st.session_state.setdefault("scores", {p: 0.0 for p in cfg["matrix"]["potentials"]})
    st.session_state.setdefault("evidence", {p: [] for p in cfg["matrix"]["potentials"]})
    st.session_state.setdefault("turn", 0)

    st.session_state.setdefault("user_name", "")
    st.session_state.setdefault("user_request", "")

    # stage control
    st.session_state.setdefault("stage_index", 0)  # index in stage_order
    st.session_state.setdefault("current_qid", None)

    # flags
    st.session_state.setdefault("shift_phrase_triggered", False)
    st.session_state.setdefault("finished", False)


# ----------------- Helpers -----------------
def by_id(question_bank):
    return {q["id"]: q for q in question_bank}


def detect_phrase_triggers(text, cfg):
    if not text:
        return False
    t = text.lower()
    for phrase in cfg["mapping"].get("shift_triggers_phrases", []):
        if phrase.lower() in t:
            return True
    return False


def apply_text_keyword_scoring(text, cfg, base_weight):
    """Adds keyword hits from cfg.mapping.keywords"""
    if not text:
        return
    text_l = text.lower()
    kw_map = cfg["mapping"].get("keywords", {})
    boost = cfg["scoring"]["text_signals"].get("keywords_boost", 0.35)

    for pot, words in kw_map.items():
        hits = 0
        for w in words:
            if w.lower() in text_l:
                hits += 1
        if hits > 0:
            add_score(pot, base_weight * boost * min(3, hits) / 3.0, note=f"KW({hits})")


def add_score(potential, value, note=""):
    st.session_state["scores"][potential] += float(value)
    if note:
        st.session_state["evidence"][potential].append(note)


def apply_scoring(question, answer, cfg):
    """Scoring uses option_map + text keywords. Anti-pattern handled via negative weights in option_map."""
    base_w = float(question.get("weight", 1.0))
    q_type = question.get("type")

    option_map = question.get("option_map", {})

    def apply_option(opt_text, split_coef=1.0):
        if opt_text in option_map:
            for pot, w in option_map[opt_text].items():
                v = base_w * float(w) * split_coef
                # anti pattern penalty coef: if w is negative -> multiply penalty
                if float(w) < 0:
                    v = v * float(cfg["scoring"].get("anti_pattern_penalty_coef", 0.8))
                add_score(pot, v, note=f"{question['id']}: {opt_text}")

    if q_type == "single":
        if isinstance(answer, str):
            apply_option(answer, 1.0)

    elif q_type == "multi":
        if isinstance(answer, list) and len(answer) > 0:
            split = 1.0 / len(answer) if cfg["scoring"].get("selection_split", True) else 1.0
            for a in answer:
                apply_option(a, split)

    elif q_type == "text":
        if isinstance(answer, str):
            apply_text_keyword_scoring(answer, cfg, base_w)

    # shift trigger phrase detection on any text answers
    if q_type == "text" and isinstance(answer, str):
        if detect_phrase_triggers(answer, cfg):
            st.session_state["shift_phrase_triggered"] = True


def log_event(turn, stage_id, q, answer):
    event = {
        "turn": turn,
        "timestamp": now_iso(),
        "stage": stage_id,
        "question_id": q["id"],
        "intent": q.get("intent", ""),
        "question_text": q.get("text", ""),
        "answer_type": q.get("type", ""),
        "answer": answer
    }
    st.session_state["answers_log"].append(event)


def top_potentials(n=3):
    items = list(st.session_state["scores"].items())
    items.sort(key=lambda x: x[1], reverse=True)
    return items[:n]


def evidence_ok_for_top3(cfg):
    min_ev = cfg["diagnosis"]["stop_rules"].get("min_evidence_per_top_potential", 3)
    top3 = top_potentials(3)
    for p, _ in top3:
        if len(st.session_state["evidence"].get(p, [])) < min_ev:
            return False
    return True


def no_major_conflicts(cfg):
    # MVP: conflict = too many top potentials have very close score but little evidence.
    # Keep simple: if top1 - top4 < small epsilon and not enough evidence => conflict
    items = list(st.session_state["scores"].items())
    items.sort(key=lambda x: x[1], reverse=True)
    if len(items) < 4:
        return True
    top1 = items[0][1]
    top4 = items[3][1]
    # if very tight and evidence not ok => conflict
    if (top1 - top4) < 0.8 and not evidence_ok_for_top3(cfg):
        return False
    return True


def should_finish(cfg):
    max_q = cfg["diagnosis"].get("max_questions_total", 20)
    min_q = cfg["diagnosis"].get("min_questions_total", 10)

    if st.session_state["turn"] >= max_q:
        return True

    if st.session_state["turn"] < min_q:
        return False

    # soft finish: min reached + evidence ok + no major conflicts
    if evidence_ok_for_top3(cfg) and no_major_conflicts(cfg):
        return True

    return False


# ----------------- Question selection (master-style stages) -----------------
def next_stage_id(cfg):
    order = cfg["adaptive_logic"]["stage_order"]
    idx = st.session_state["stage_index"]
    if idx >= len(order):
        return None
    return order[idx]


def advance_stage(cfg):
    st.session_state["stage_index"] += 1


def stage_question_ids(cfg, stage_id):
    for s in cfg["stages"]:
        if s["id"] == stage_id:
            return s.get("question_ids", [])
    return []


def pick_next_question(cfg):
    qb = cfg["question_bank"]
    qmap = by_id(qb)

    stage_id = next_stage_id(cfg)
    if stage_id is None:
        return None, None

    # stage4_shifts can be skipped if no triggers and we already have enough
    if stage_id == "stage4_shifts":
        triggers = st.session_state["shift_phrase_triggered"]
        # also: if diagnosis nearing end and everything clean -> skip shifts
        if (not triggers) and evidence_ok_for_top3(cfg):
            advance_stage(cfg)
            return pick_next_question(cfg)

    ids = stage_question_ids(cfg, stage_id)

    # pick first unasked in this stage
    for qid in ids:
        if qid not in st.session_state["asked_ids"]:
            return qmap[qid], stage_id

    # if stage exhausted, move on
    advance_stage(cfg)
    return pick_next_question(cfg)


# ----------------- UI -----------------
def header_ui(cfg):
    st.title(cfg["ui"].get("title", "NEO Диагностика"))
    st.caption(cfg["ui"].get("subtitle", ""))


def progress_ui(cfg, stage_id):
    n = st.session_state["turn"] + 1
    mx = cfg["diagnosis"].get("max_questions_total", 20)
    label_tpl = cfg["ui"].get("progress_label_template", "Вопрос {n}/{max} | {stage}")
    st.write(label_tpl.format(n=n, max=mx, stage=stage_id))


def render_question(q):
    st.subheader(q["text"])

    q_type = q["type"]
    answer = None

    if q_type == "single":
        answer = st.radio("Выберите:", q["options"], index=None)
    elif q_type == "multi":
        answer = st.multiselect("Выберите (до 3):", q["options"])
    elif q_type == "text":
        answer = st.text_area("Ответ:", height=120)

    return answer


def client_summary(cfg):
    name = st.session_state.get("user_name") or "Вы"
    req = st.session_state.get("user_request") or "запрос не указан"

    top3 = [p for p, _ in top_potentials(3)]
    st.markdown("## Результат (MVP)")
    st.write("**Топ-3 потенциала (гипотеза):**")
    st.write(top3)

    st.write(f"**Имя:** {name}")
    st.write(f"**Запрос:** {req}")

    st.markdown("### Что дальше:")
    st.markdown("- Я сформировал(а) гипотезу по потенциалам на основе ваших ответов.")
    st.markdown("- Следующий шаг: мастерская версия отчёта (детали, реализация, деньги, план действий).")

    with st.expander("Технические данные (для мастера / отладки)"):
        st.json({
            "scores": st.session_state["scores"],
            "evidence": {k: v[:5] for k, v in st.session_state["evidence"].items()},
            "log": st.session_state["answers_log"]
        })


# ----------------- Main -----------------
def main():
    cfg = load_cfg()
    init_state(cfg)
    header_ui(cfg)

    if st.session_state["finished"]:
        st.success("Диагностика завершена ✅")
        client_summary(cfg)
        return

    # pick next question if none
    if st.session_state["current_qid"] is None:
        q, stage_id = pick_next_question(cfg)
        if q is None or should_finish(cfg):
            st.session_state["finished"] = True
            st.rerun()
        st.session_state["current_qid"] = q["id"]
        st.session_state["current_stage_id"] = stage_id

    # fetch current question
    qid = st.session_state["current_qid"]
    q = next(qq for qq in cfg["question_bank"] if qq["id"] == qid)
    stage_id = st.session_state.get("current_stage_id", "unknown")

    progress_ui(cfg, stage_id)

    answer = render_question(q)

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
        if q["type"] == "single" and not answer:
            st.warning("Выберите вариант, чтобы продолжить.")
            st.stop()

        # store name/request for header
        if q["id"] == "q_name":
            st.session_state["user_name"] = (answer or "").strip()
        if q["id"] == "q_request":
            st.session_state["user_request"] = (answer or "").strip()

        st.session_state["asked_ids"].add(qid)
        apply_scoring(q, answer, cfg)

        log_event(st.session_state["turn"], stage_id, q, answer)

        st.session_state["turn"] += 1
        st.session_state["current_qid"] = None
        st.rerun()


if __name__ == "__main__":
    main()