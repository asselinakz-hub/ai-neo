import streamlit as st
import json
from collections import deque
from pathlib import Path

CONFIG_PATH = "configs/diagnosis_config.json"


# -----------------------
# Loading
# -----------------------
def load_cfg(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


# -----------------------
# State
# -----------------------
def init_state(cfg):
    st.session_state.setdefault("asked_ids", set())
    st.session_state.setdefault("asked_families", deque(maxlen=3))  # anti-repeat families
    st.session_state.setdefault("answers", {})  # qid -> answer
    st.session_state.setdefault("scores", {})  # potential -> float
    st.session_state.setdefault("evidence", {})  # potential -> [notes]
    st.session_state.setdefault("trace", [])  # list of events
    st.session_state.setdefault("turn", 0)
    st.session_state.setdefault("phase_idx", 0)
    st.session_state.setdefault("current_qid", None)
    st.session_state.setdefault("shift_active", False)
    st.session_state.setdefault("locked_top3", None)

    # slots progress
    st.session_state.setdefault("slots", {
        "columns": {"ВОСПРИЯТИЕ": 0, "МОТИВАЦИЯ": 0, "ИНСТРУМЕНТ": 0},
        "rows": {"СИЛЫ": 0, "ЭНЕРГИЯ": 0, "СЛАБОСТИ": 0},
        "shifts": 0
    })


# -----------------------
# Helpers
# -----------------------
def safe_lower(x):
    return (x or "").strip().lower()


def top_potentials(scores, n=3):
    if not scores:
        return []
    return [p for p, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:n]]


def add_score(pot, delta, note):
    st.session_state["scores"][pot] = float(st.session_state["scores"].get(pot, 0.0)) + float(delta)
    st.session_state["evidence"].setdefault(pot, []).append(note)


def detect_shift(answer_text, cfg):
    triggers = cfg.get("shift_detection", {}).get("triggers", [])
    t = safe_lower(answer_text)
    return any(safe_lower(tr) in t for tr in triggers)


def increment_slots(question):
    # columns/rows are tags that questions may carry
    slots = st.session_state["slots"]
    col_tags = question.get("column_tags", []) or []
    row_tags = question.get("row_tags", []) or []
    if isinstance(col_tags, str):
        col_tags = [col_tags]
    if isinstance(row_tags, str):
        row_tags = [row_tags]

    for c in col_tags:
        if c in slots["columns"]:
            slots["columns"][c] += 1
    for r in row_tags:
        if r in slots["rows"]:
            slots["rows"][r] += 1

    # shifts slot
    if "shift" in (question.get("tags", []) or []):
        slots["shifts"] += 1


def slots_needed(cfg):
    dist_col = cfg.get("diagnostic_slots", {}).get("columns", {}).get("distribution", {})
    dist_row = cfg.get("diagnostic_slots", {}).get("rows", {}).get("distribution", {})
    required_shifts = cfg.get("diagnostic_slots", {}).get("shifts", {}).get("required", 2)

    cur = st.session_state["slots"]
    need = {"columns": {}, "rows": {}, "shifts": 0}

    for k, req in dist_col.items():
        need["columns"][k] = max(0, int(req) - int(cur["columns"].get(k, 0)))
    for k, req in dist_row.items():
        need["rows"][k] = max(0, int(req) - int(cur["rows"].get(k, 0)))

    need["shifts"] = max(0, int(required_shifts) - int(cur.get("shifts", 0)))
    return need


def phase_limits(cfg):
    phases = cfg.get("question_flow", {}).get("phases", [])
    # return list of (name, max_questions)
    return [(p.get("name"), int(p.get("max_questions", 0))) for p in phases]


def current_phase(cfg):
    phases = cfg.get("question_flow", {}).get("phases", [])
    idx = st.session_state["phase_idx"]
    if idx >= len(phases):
        return {"name": "locking", "max_questions": 2}
    return phases[idx]


def advance_phase_if_needed(cfg):
    # move to next phase if we exhausted max for this phase
    phases = cfg.get("question_flow", {}).get("phases", [])
    idx = st.session_state["phase_idx"]
    if idx >= len(phases):
        return

    # count how many questions already asked within current phase
    phase_name = phases[idx].get("name", "")
    asked_in_phase = sum(1 for e in st.session_state["trace"] if e.get("phase") == phase_name)

    if asked_in_phase >= int(phases[idx].get("max_questions", 0)):
        st.session_state["phase_idx"] = min(idx + 1, len(phases))


# -----------------------
# Scoring
# -----------------------
def apply_scoring(question, user_answer, cfg):
    option_map = question.get("option_map", {}) or {}
    base_w = float(question.get("weight", 1.0))

    # keyword scoring from cfg["potential_keywords"]
    kw = cfg.get("potential_keywords", {}) or {}
    text_analysis = cfg.get("scoring", {}).get("text_analysis", {}) or {}
    kw_boost = float(text_analysis.get("keyword_boost", 0.0))
    certainty_boost = float(text_analysis.get("certainty_boost", 0.0))
    example_depth_boost = float(text_analysis.get("example_depth_boost", 0.0))
    abstract_penalty = float(text_analysis.get("abstract_penalty", 1.0))

    def add(p, val, note):
        add_score(p, val, note)

    qid = question.get("id", "unknown")
    qtype = question.get("type")

    # -------- option-based scoring
    if qtype == "single":
        if user_answer in option_map:
            for pot, w in option_map[user_answer].items():
                add(pot, base_w * float(w), f"{qid}: {user_answer}")
    elif qtype == "multi":
        if isinstance(user_answer, list) and user_answer:
            per = 1.0 / len(user_answer)
            for ans in user_answer:
                if ans in option_map:
                    for pot, w in option_map[ans].items():
                        add(pot, base_w * float(w) * per, f"{qid}: {ans}")

    # -------- text signals (even for single/multi if user adds extra comment later)
    if qtype == "text":
        txt = safe_lower(user_answer)
        if not txt:
            return

        # shift triggers (flag only; scoring not here)
        if detect_shift(txt, cfg):
            st.session_state["shift_active"] = True

        # abstract penalty heuristic
        # (если слишком мало конкретики: очень коротко и без глаголов/примеров)
        penal = 1.0
        if len(txt.split()) < 7:
            penal *= abstract_penalty

        # keyword hits
        for pot, words in kw.items():
            hit_count = sum(1 for w in words if safe_lower(w) in txt)
            if hit_count > 0:
                add(pot, base_w * kw_boost * min(1.0, hit_count / 2.0) * penal,
                    f"{qid}: keyword_hit({hit_count})")

        # certainty words
        certainty_words = ["точно", "всегда", "реально", "обожаю", "ненавижу", "прям", "100%"]
        if any(w in txt for w in certainty_words):
            # boost top potentials lightly
            for pot in top_potentials(st.session_state["scores"], 3) or []:
                add(pot, base_w * certainty_boost * penal, f"{qid}: certainty_words")

        # example depth
        markers = ["например", "когда", "вот", "как-то", "вчера", "недавно"]
        if any(m in txt for m in markers):
            for pot in top_potentials(st.session_state["scores"], 3) or []:
                add(pot, base_w * example_depth_boost * penal, f"{qid}: example_depth")


# -----------------------
# Question selection (MASTER STYLE)
# -----------------------
def pick_next_question(cfg):
    bank = cfg.get("question_bank", [])
    asked_ids = st.session_state["asked_ids"]
    recent_families = set(st.session_state["asked_families"])

    need = slots_needed(cfg)
    phase = current_phase(cfg).get("name", "core_detection")

    # candidates: not asked, not repeating family in recent window
    candidates = []
    for q in bank:
        qid = q.get("id")
        if not qid or qid in asked_ids:
            continue
        fam = q.get("family")
        if cfg.get("session_rules", {}).get("no_repeat_families_in_row", True) and fam and fam in recent_families:
            continue
        candidates.append(q)

    if not candidates:
        return None

    # score each candidate by priority
    scores = st.session_state["scores"]
    top3 = top_potentials(scores, 3)

    # if no scores yet, prefer phase-tagged or "orientation"
    def q_has_tag(q, tag):
        return tag in (q.get("tags", []) or [])

    def need_col_bonus(q):
        bonus = 0.0
        for c, n in need["columns"].items():
            if n <= 0:
                continue
            if c in (q.get("column_tags", []) or []):
                bonus += 2.5
        return bonus

    def need_row_bonus(q):
        bonus = 0.0
        for r, n in need["rows"].items():
            if n <= 0:
                continue
            if r in (q.get("row_tags", []) or []):
                bonus += 2.0
        return bonus

    def top_potential_bonus(q):
        tags = q.get("potential_tags", []) or []
        if isinstance(tags, str):
            tags = [tags]
        # if we have ties (top2 close) → ask questions that separate them
        bonus = 0.0
        for p in top3:
            if p in tags:
                bonus += 1.5
        return bonus

    def phase_bonus(q):
        # allow question to declare phase tag in tags
        # (e.g., "orientation", "validation", "shift", "locking")
        bonus = 0.0
        if phase == "orientation" and q_has_tag(q, "orientation"):
            bonus += 2.0
        if phase == "validation" and q_has_tag(q, "validation"):
            bonus += 2.0
        if phase == "shift_probe":
            if q_has_tag(q, "shift"):
                bonus += 3.0
            else:
                bonus -= 1.0
        if phase == "locking" and q_has_tag(q, "locking"):
            bonus += 2.5
        return bonus

    def shift_policy_bonus(q):
        # if shift active, we need validation + shift probes (but limit count)
        max_shift = cfg.get("diagnostic_slots", {}).get("shifts", {}).get("max", 2)
        asked_shifts = st.session_state["slots"].get("shifts", 0)
        if st.session_state["shift_active"] and asked_shifts < max_shift:
            if q_has_tag(q, "shift"):
                return 3.0
            if q_has_tag(q, "validation"):
                return 1.0
        # if no shift active, avoid shift questions too early
        if not st.session_state["shift_active"] and q_has_tag(q, "shift") and st.session_state["turn"] < 10:
            return -2.5
        return 0.0

    def weight_bonus(q):
        return float(q.get("weight", 1.0)) * 0.6

    ranked = []
    for q in candidates:
        s = 0.0
        s += need_col_bonus(q)
        s += need_row_bonus(q)
        s += top_potential_bonus(q)
        s += phase_bonus(q)
        s += shift_policy_bonus(q)
        s += weight_bonus(q)

        # gentle preference for "core" questions early
        if st.session_state["turn"] < 6 and q_has_tag(q, "core"):
            s += 1.0

        ranked.append((s, q))

    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


# -----------------------
# Stop / Locking
# -----------------------
def should_stop(cfg):
    max_q = int(cfg.get("session_rules", {}).get("max_questions_total", 20))
    if st.session_state["turn"] >= max_q:
        return True

    # need to ask at least min before locking
    min_before_lock = int(cfg.get("session_rules", {}).get("min_questions_before_lock", 8))
    if st.session_state["turn"] < min_before_lock:
        return False

    # evidence checks for top3
    lock_rules = cfg.get("locking_rules", {})
    min_conf = int(lock_rules.get("min_confirmations_per_potential", 3))
    top3 = top_potentials(st.session_state["scores"], 3)
    if len(top3) < 3:
        return False

    ok_evidence = all(len(st.session_state["evidence"].get(p, [])) >= min_conf for p in top3)

    # slots closure
    need = slots_needed(cfg)
    slots_closed = all(v == 0 for v in need["columns"].values()) and all(v == 0 for v in need["rows"].values())

    # prevent lock if shift active (config rule)
    prevent_if_shift = bool(lock_rules.get("prevent_lock_if_shift_active", True))
    if prevent_if_shift and st.session_state["shift_active"]:
        return False

    return ok_evidence and slots_closed


def finalize(cfg):
    scores = st.session_state["scores"]
    top3 = top_potentials(scores, 3)
    st.session_state["locked_top3"] = top3
    st.success("Диагностика завершена ✅")

    st.subheader("Результат (MVP)")
    st.write("Топ-3 потенциала:", top3)

    with st.expander("Технические данные (для мастера / отладки)"):
        st.json({
            "top3": top3,
            "scores": scores,
            "slots": st.session_state["slots"],
            "shift_active": st.session_state["shift_active"],
            "answers": st.session_state["answers"],
            "trace": st.session_state["trace"][-10:]
        })


# -----------------------
# UI Rendering
# -----------------------
def render_question(q):
    st.subheader(q.get("text", "Вопрос"))

    qtype = q.get("type", "single")
    opts = q.get("options", []) or []

    answer = None
    if qtype == "single":
        answer = st.radio("Выберите:", opts, index=0 if opts else None)
    elif qtype == "multi":
        answer = st.multiselect("Выберите:", opts)
    elif qtype == "text":
        answer = st.text_area("Ответ:", height=120)
    else:
        # fallback: text
        answer = st.text_area("Ответ:", height=120)

    return answer


# -----------------------
# Streamlit app
# -----------------------
cfg = load_cfg()
init_state(cfg)

# advance phase if needed (based on trace counts)
advance_phase_if_needed(cfg)
phase = current_phase(cfg).get("name", "core_detection")

st.caption(f"Ход диагностики: вопрос {st.session_state['turn']+1} из {cfg.get('session_rules', {}).get('max_questions_total', 20)} | фаза: {phase}")

# stop?
if should_stop(cfg):
    finalize(cfg)
    st.stop()

# choose question if none
if st.session_state["current_qid"] is None:
    q = pick_next_question(cfg)
    if q is None:
        finalize(cfg)
        st.stop()
    st.session_state["current_qid"] = q["id"]
else:
    q = next((qq for qq in cfg.get("question_bank", []) if qq.get("id") == st.session_state["current_qid"]), None)
    if q is None:
        st.session_state["current_qid"] = None
        st.rerun()

answer = render_question(q)

colA, colB = st.columns([1, 1])
with colA:
    go = st.button("Далее ➜", use_container_width=True)
with colB:
    restart = st.button("Сбросить сессию", use_container_width=True)

if restart:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

if go:
    qid = q.get("id")
    st.session_state["asked_ids"].add(qid)

    fam = q.get("family")
    if fam:
        st.session_state["asked_families"].append(fam)

    st.session_state["answers"][qid] = answer

    # shift detection from text (also from single/multi if you later add comment fields)
    if q.get("type") == "text":
        if detect_shift(answer, cfg):
            st.session_state["shift_active"] = True

    apply_scoring(q, answer, cfg)
    increment_slots(q)

    st.session_state["turn"] += 1

    # trace
    st.session_state["trace"].append({
        "turn": st.session_state["turn"],
        "qid": qid,
        "phase": phase,
        "family": q.get("family"),
        "column_tags": q.get("column_tags", []),
        "row_tags": q.get("row_tags", []),
        "potential_tags": q.get("potential_tags", []),
        "answer_type": q.get("type"),
        "answer": answer
    })

    st.session_state["current_qid"] = None
    st.rerun()