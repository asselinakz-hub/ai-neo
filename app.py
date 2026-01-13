import json
import re
import time
from typing import Dict, List, Optional, Any

import streamlit as st

from openai import OpenAI

# =========================
# BASIC SETTINGS
# =========================
st.set_page_config(page_title="NEO Диагностика", page_icon="🧭", layout="centered")

POTENTIALS = ["Янтарь", "Шунгит", "Цитрин", "Изумруд", "Рубин", "Гранат", "Сапфир", "Гелиодор", "Аметист"]
COLUMNS = ["ВОСПРИЯТИЕ", "МОТИВАЦИЯ", "ИНСТРУМЕНТ"]

MAX_QUESTIONS = 30
MIN_QUESTIONS = 14

MODEL_PRIMARY = st.secrets.get("OPENAI_MODEL", "gpt-4.1-mini")
MODEL_FALLBACKS = [
    MODEL_PRIMARY,
    "gpt-4.1-mini",
    "gpt-4o-mini",
]

MASTER_CODE = str(st.secrets.get("MASTER_CODE", "")).strip()

KEYWORDS = {
    "Янтарь": ["порядок", "структур", "система", "организа", "регламент", "по полочкам", "документ", "детали", "схема", "разложить"],
    "Шунгит": ["тело", "движ", "спорт", "физичес", "руками", "активност", "вынослив", "качал", "прогул"],
    "Цитрин": ["деньги", "результат", "быстр", "эффектив", "оптимиза", "доход", "сделк", "скорост"],
    "Изумруд": ["красот", "гармони", "уют", "эстет", "дизайн", "стиль", "атмосфер"],
    "Рубин": ["драйв", "адреналин", "нов", "путешеств", "перезагруз", "приключ", "трансформац", "эмоци"],
    "Гранат": ["люди", "команда", "общен", "близк", "родн", "семья", "забот", "поддерж", "отношен"],
    "Сапфир": ["смысл", "идея", "концепц", "философ", "почему", "глубин", "мировоззрен"],
    "Гелиодор": ["знани", "изучен", "обучен", "объясня", "настав", "курс", "развит", "учиться"],
    "Аметист": ["цель", "стратег", "управлен", "лидер", "план", "координа", "проект", "вектор"],
}

NEGATION_WINDOW = 3

SYSTEM_INTERVIEW = """Ты — ИИ-диагност. Проводишь живой разбор потенциалов (как мастер), без повторов и без бесконечных «почему».

Этапы:
0) intake: имя + запрос
1) now: что сейчас не так / где энергия утекает / что хоть немного наполняет
2) childhood: детство 5–12 + подростковый период 12–16 (что тянуло, роли, игры)
3) columns: вопросы по столбцам ВОСПРИЯТИЕ/МОТИВАЦИЯ/ИНСТРУМЕНТ
4) validation: проверка гипотез, 1 уточнение максимум
5) shifts: 1–2 вопроса на смещения (если есть «надо/должен», тревога, противоречия)
6) wrap: что изменится через 3 месяца, если станет лучше

Ты возвращаешь СТРОГО JSON:
{
  "question_id": "string",
  "stage": "intake|now|childhood|columns|validation|shifts|wrap",
  "answer_type": "single|multi|text|single_plus_text|multi_plus_text",
  "question_text": "string",
  "options": ["..."],
  "allow_comment": true|false,
  "comment_prompt": "string",
  "scoring_hints": {
    "potentials": {"Янтарь": 0.0, "...": 0.0},
    "column": "ВОСПРИЯТИЕ|МОТИВАЦИЯ|ИНСТРУМЕНТ|",
    "shift_risk": true|false
  },
  "master_note": "1-2 предложения",
  "avoid_reask_signature": "смысл вопроса коротко"
}

Правила:
- options 4–9 пунктов максимум (если answer_type это single/multi/..)
- НЕ повторяй смысл вопроса: avoid_reask_signature должен быть уникален среди уже заданных
- 1 уточнение максимум, затем двигайся дальше
"""

SYSTEM_REPORT_CLIENT = """Сделай короткий клиентский итог на русском, без сырых логов и без чисел.
Структура:
- Имя + запрос (1 строка)
- ТОП-3 СИЛЫ (по 1–2 строки)
- ТОП-3 ЭНЕРГИЯ (как наполняться)
- ТОП-3 СЛАБОСТИ (что лучше делегировать/минимизировать)
- Ведущий столбец (Восприятие/Мотивация/Инструмент) — 2–3 строки
- 3 шага на 7 дней (конкретные)
"""

SYSTEM_REPORT_MASTER = """Сделай мастер-отчёт:
- Итог: топы + ведущий столбец
- Доказательства по топам (3–6 пунктов на каждый)
- Противоречия/смещения (если есть)
- 5 уточняющих вопросов для продолжения сессии
Можно показывать баллы.
"""

# =========================
# Utils
# =========================
def safe_json_load(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except Exception:
        return None

def extract_json(text: str) -> Optional[dict]:
    # попытка вытащить JSON из текста
    if not text:
        return None
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        return None
    return safe_json_load(m.group(0))

def tokenise(text: str) -> List[str]:
    return re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", (text or "").lower())

def contains_negated_keyword(text: str, kw: str) -> bool:
    words = tokenise(text)
    k = kw.lower()
    for i, w in enumerate(words):
        if k in w:
            start = max(0, i - NEGATION_WINDOW)
            window = words[start:i]
            if "не" in window or "нет" in window:
                return True
    return False

def keyword_score(text: str) -> Dict[str, float]:
    text_l = (text or "").lower()
    out = {p: 0.0 for p in POTENTIALS}
    if not text_l:
        return out
    for pot, kws in KEYWORDS.items():
        for kw in kws:
            if kw in text_l:
                if contains_negated_keyword(text_l, kw):
                    out[pot] -= 0.9
                else:
                    out[pot] += 0.6
    return out

def add_scores(base: Dict[str, float], delta: Dict[str, float], w: float = 1.0):
    for p in POTENTIALS:
        base[p] = float(base.get(p, 0.0)) + float(delta.get(p, 0.0)) * float(w)

def topn(scores: Dict[str, float], n: int) -> List[str]:
    return [k for k, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:n]]

def bottomn(scores: Dict[str, float], n: int) -> List[str]:
    return [k for k, _ in sorted(scores.items(), key=lambda x: x[1])[:n]]

def derive_column(column_votes: Dict[str, float]) -> str:
    if not column_votes:
        return "МОТИВАЦИЯ"
    return max(column_votes.items(), key=lambda x: x[1])[0]

def derive_rows(scores: Dict[str, float]) -> Dict[str, List[str]]:
    ordered = [k for k, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
    return {"СИЛЫ": ordered[:3], "ЭНЕРГИЯ": ordered[3:6], "СЛАБОСТИ": ordered[6:9]}

def compact_state_for_llm(state: dict) -> dict:
    return {
        "name": state.get("name"),
        "goal": state.get("goal"),
        "q_count": state["q_count"],
        "stage": state["stage"],
        "top3_now": topn(state["scores"], 3),
        "bottom3_now": bottomn(state["scores"], 3),
        "used_signatures": list(state["used_signatures"])[:80],
        "last_turns": state["history"][-6:],
        "column_votes": state["column_votes"],
        "shift_risk_events": state["shift_risk_events"],
    }

def should_stop(state: dict) -> bool:
    if state["q_count"] < MIN_QUESTIONS:
        return False
    if state["q_count"] >= MAX_QUESTIONS:
        return True
    # простая логика: если уже есть 3+ доказательства по топ-3
    top3 = topn(state["scores"], 3)
    ok = all(len(state["evidence"].get(p, [])) >= 3 for p in top3)
    return ok

# =========================
# OpenAI wrapper (CHAT COMPLETIONS)
# =========================
def get_openai_client() -> OpenAI:
    api_key = st.secrets.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("Не найден OPENAI_API_KEY в Streamlit Secrets.")
    return OpenAI(api_key=api_key)

def chat_json(client: OpenAI, model: str, system: str, user_payload: dict) -> dict:
    # максимально «дешёвый» запрос: маленький контекст, json_object если поддерживается
    msg_user = json.dumps(user_payload, ensure_ascii=False)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": msg_user},
            ],
            temperature=0.3,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content or ""
        data = safe_json_load(text) or extract_json(text)
        if not data:
            raise RuntimeError("Модель вернула не-JSON.")
        return data
    except Exception as e:
        raise e

def chat_text(client: OpenAI, model: str, system: str, user_payload: dict) -> str:
    msg_user = json.dumps(user_payload, ensure_ascii=False)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": msg_user},
        ],
        temperature=0.4,
    )
    return resp.choices[0].message.content or ""

def llm_next_question(state: dict) -> dict:
    client = get_openai_client()
    payload = {
        "state": compact_state_for_llm(state),
        "instruction": "Сгенерируй следующий лучший вопрос строго по этапам. Не повторяй сигнатуры."
    }

    last_err = None
    for m in MODEL_FALLBACKS:
        try:
            data = chat_json(client, m, SYSTEM_INTERVIEW, payload)
            return data
        except Exception as e:
            last_err = e
            continue

    # если все модели упали — отдаём безопасный fallback
    return {
        "question_id": f"fallback_{int(time.time())}",
        "stage": "now",
        "answer_type": "text",
        "question_text": "Коротко: что сейчас в жизни сильнее всего забирает энергию?",
        "options": [],
        "allow_comment": False,
        "comment_prompt": "",
        "scoring_hints": {"potentials": {}, "column": "МОТИВАЦИЯ", "shift_risk": False},
        "master_note": f"OpenAI error: {type(last_err).__name__}",
        "avoid_reask_signature": "fallback_energy_drain"
    }

def llm_make_reports(state: dict) -> (str, str):
    client = get_openai_client()

    rows = derive_rows(state["scores"])
    col = derive_column(state["column_votes"])

    summary = {
        "name": state.get("name", ""),
        "goal": state.get("goal", ""),
        "rows": rows,
        "lead_column": col,
        "scores": state["scores"],
        "events": state["events"][-35:],
    }

    # отчёт тоже через fallback по моделям
    last_err = None
    for m in MODEL_FALLBACKS:
        try:
            client_report = chat_text(client, m, SYSTEM_REPORT_CLIENT, summary)
            master_report = chat_text(client, m, SYSTEM_REPORT_MASTER, summary)
            return client_report, master_report
        except Exception as e:
            last_err = e
            continue

    # если упали — вернем простую заглушку
    cr = f"Имя: {summary['name']}\nЗапрос: {summary['goal']}\n\n(Не удалось сгенерировать отчёт: {type(last_err).__name__})"
    mr = cr + "\n\nСырые баллы:\n" + json.dumps(summary["scores"], ensure_ascii=False, indent=2)
    return cr, mr

# =========================
# State
# =========================
def init_state():
    st.session_state.setdefault("state", {
        "name": "",
        "goal": "",
        "stage": "intake",
        "q_count": 0,
        "scores": {p: 0.0 for p in POTENTIALS},
        "column_votes": {c: 0.0 for c in COLUMNS},
        "used_signatures": set(),
        "asked_ids": set(),
        "evidence": {p: [] for p in POTENTIALS},
        "events": [],
        "history": [],
        "shift_risk_events": 0,
        "final_client_report": "",
        "final_master_report": "",
    })
    st.session_state.setdefault("current_question", None)
    st.session_state.setdefault("show_master", False)

def reset_all():
    st.session_state.clear()
    st.rerun()

def apply_answer(state: dict, q: dict, selected, text_value: str):
    qid = q.get("question_id", f"q_{int(time.time())}")
    sig = q.get("avoid_reask_signature", qid) or qid
    stage = q.get("stage", "")

    state["asked_ids"].add(qid)
    if sig in state["used_signatures"]:
        state["shift_risk_events"] += 1
    state["used_signatures"].add(sig)

    hints = q.get("scoring_hints", {}) or {}
    hint_pots = hints.get("potentials", {}) or {}
    col = hints.get("column", "") or ""
    shift_risk = bool(hints.get("shift_risk", False))

    # full text
    sel_text = ""
    if isinstance(selected, list):
        sel_text = "; ".join(selected)
    elif isinstance(selected, str):
        sel_text = selected
    full_text = (sel_text + " " + (text_value or "")).strip()

    # scoring
    hint_delta = {p: float(hint_pots.get(p, 0.0)) for p in POTENTIALS}
    kw_delta = keyword_score(full_text)

    add_scores(state["scores"], hint_delta, w=0.7)
    add_scores(state["scores"], kw_delta, w=1.0)

    if col in COLUMNS:
        state["column_votes"][col] = float(state["column_votes"].get(col, 0.0)) + 1.0

    if shift_risk:
        state["shift_risk_events"] += 1

    # detect intake fields by signature text (простая эвристика)
    sig_l = (sig or "").lower()
    if "name" in sig_l or "имя" in sig_l:
        if text_value.strip():
            state["name"] = text_value.strip()
        elif isinstance(selected, str):
            state["name"] = selected.strip()
    if "goal" in sig_l or "запрос" in sig_l or "цель" in sig_l:
        if text_value.strip():
            state["goal"] = text_value.strip()

    # evidence: фиксируем по текущему топу
    cur_top = topn(state["scores"], 3)
    for p in cur_top:
        state["evidence"].setdefault(p, []).append(f"{qid}: {full_text[:160]}")

    # logs
    state["events"].append({
        "ts": int(time.time()),
        "question_id": qid,
        "stage": stage,
        "question_text": q.get("question_text", ""),
        "answer_type": q.get("answer_type", ""),
        "selected": selected,
        "text": text_value,
        "signature": sig,
        "column": col,
        "shift_risk": shift_risk,
        "master_note": q.get("master_note", ""),
    })
    state["history"].append({"role": "assistant", "content": q.get("question_text", "")})
    state["history"].append({"role": "user", "content": full_text})

    state["q_count"] += 1

# =========================
# UI
# =========================
init_state()
state = st.session_state["state"]

st.title("🧭 Диагностика потенциалов")
st.caption("Формат: живой разбор. В конце — короткая картина + следующий шаг.")

# master sidebar
with st.sidebar:
    st.markdown("### 🔒 Мастер-доступ")
    code = st.text_input("Код мастера", type="password")
    if code and MASTER_CODE and code == MASTER_CODE:
        st.session_state["show_master"] = True
        st.success("Режим мастера включён")
    elif code and MASTER_CODE and code != MASTER_CODE:
        st.error("Неверный код")
    elif code and not MASTER_CODE:
        st.info("MASTER_CODE не задан в Secrets (необязательно).")

    st.divider()
    if st.button("♻️ Сбросить диагностику"):
        reset_all()

# финал
if state.get("final_client_report"):
    st.subheader("✅ Результат диагностики")
    st.write(state["final_client_report"])

    if st.session_state.get("show_master"):
        st.divider()
        st.subheader("Отчет мастера")
        st.write(state.get("final_master_report", ""))

        with st.expander("Сырые данные (event log)"):
            st.json(state["events"])

        with st.expander("Баллы (для калибровки)"):
            st.json(state["scores"])

    st.stop()

# получить следующий вопрос
if st.session_state["current_question"] is None:
    try:
        q = llm_next_question(state)
    except Exception as e:
        st.error(f"Не удалось получить вопрос от ИИ: {type(e).__name__}: {e}")
        st.stop()

    # защита от повтора сигнатуры
    sig = q.get("avoid_reask_signature", "")
    if sig and sig in state["used_signatures"]:
        q = llm_next_question(state)

    st.session_state["current_question"] = q

q = st.session_state["current_question"]

# progress
st.caption(f"Ход: вопрос {state['q_count'] + 1} из {MAX_QUESTIONS} | фаза: {q.get('stage','')}")

st.subheader(q.get("question_text", "Вопрос"))

atype = q.get("answer_type", "text")
options = q.get("options", []) or []
comment_prompt = q.get("comment_prompt", "Комментарий (необязательно):")

# important: unique keys per question => no sticky answers
qid_key = q.get("question_id", f"q_{state['q_count']+1}")

selected = None
text_value = ""

if atype == "single":
    selected = st.radio("Выбери один вариант:", options, key=f"single_{qid_key}")
elif atype == "multi":
    selected = st.multiselect("Выбери несколько:", options, key=f"multi_{qid_key}")
elif atype == "text":
    text_value = st.text_area("Ответ:", key=f"text_{qid_key}", height=120, placeholder="Коротко, по-человечески…")
elif atype == "single_plus_text":
    selected = st.radio("Выбери один вариант:", options, key=f"single_{qid_key}")
    text_value = st.text_area(comment_prompt, key=f"text_{qid_key}", height=90)
elif atype == "multi_plus_text":
    selected = st.multiselect("Выбери несколько:", options, key=f"multi_{qid_key}")
    text_value = st.text_area(comment_prompt, key=f"text_{qid_key}", height=90)
else:
    text_value = st.text_area("Ответ:", key=f"text_{qid_key}", height=120)

c1, c2 = st.columns([1, 1])
with c1:
    next_btn = st.button("Далее ➜", use_container_width=True)
with c2:
    stop_btn = st.button("Завершить сейчас", use_container_width=True)

if stop_btn and state["q_count"] >= 5:
    # generate reports
    try:
        cr, mr = llm_make_reports(state)
        state["final_client_report"] = cr
        state["final_master_report"] = mr
        st.session_state["current_question"] = None
        st.rerun()
    except Exception as e:
        st.error(f"Не удалось сформировать отчёт: {type(e).__name__}: {e}")
        st.stop()

if next_btn:
    # validate
    if atype in ("single", "single_plus_text") and not selected:
        st.warning("Выбери вариант.")
        st.stop()
    if atype in ("multi", "multi_plus_text") and (not selected or len(selected) == 0):
        st.warning("Выбери хотя бы один вариант.")
        st.stop()
    if atype == "text" and not (text_value or "").strip():
        st.warning("Напиши короткий ответ.")
        st.stop()

    apply_answer(state, q, selected, text_value)

    # stop?
    if should_stop(state) or state["q_count"] >= MAX_QUESTIONS:
        cr, mr = llm_make_reports(state)
        state["final_client_report"] = cr
        state["final_master_report"] = mr
        st.session_state["current_question"] = None
        st.rerun()

    # next
    st.session_state["current_question"] = None
    st.rerun()