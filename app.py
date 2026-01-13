import json
import re
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

import streamlit as st

# OpenAI SDK (new)
from openai import OpenAI

# =========================
# CONFIG (single-file MVP)
# =========================
MODEL_DEFAULT = "gpt-5.2-mini"

MAX_QUESTIONS = 30
MIN_QUESTIONS = 14  # чтобы не завершал слишком рано
MAX_FOLLOWUP_REPEAT = 1  # уточнение одного вопроса максимум 1 раз
TARGET_TOP = 3

POTENTIALS = ["Янтарь", "Шунгит", "Цитрин", "Изумруд", "Рубин", "Гранат", "Сапфир", "Гелиодор", "Аметист"]
COLUMNS = ["ВОСПРИЯТИЕ", "МОТИВАЦИЯ", "ИНСТРУМЕНТ"]
ROWS = ["СИЛЫ", "ЭНЕРГИЯ", "СЛАБОСТИ"]

# Внутренняя логика: мы "собираем" столбцы, но не показываем пользователю сырьё
COLUMN_QUESTIONS_TARGET = {"ВОСПРИЯТИЕ": 4, "МОТИВАЦИЯ": 4, "ИНСТРУМЕНТ": 4}
CHILDHOOD_QUESTIONS_TARGET = 4
SHIFT_QUESTIONS_TARGET = 2

# Ключевые слова (используй как базовую поддержку; ИИ всё равно рулит)
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

NEGATION_WINDOW = 3  # "не" + 3 слова рядом => считаем отрицанием к ключевому слову

# =========================
# LLM PROMPTS
# =========================
SYSTEM_INTERVIEW = """Ты — ИИ-диагност, проводишь живой разбор потенциалов в стиле мастера.
Важное:
1) Вопросы НЕ должны повторяться. Уточнить один раз можно только если ответ противоречивый.
2) Начинаем мягко: имя → запрос → ситуация сейчас → затем детство → затем проверка гипотез (восприятие/мотивация/инструмент) → затем 1-2 вопроса на смещения.
3) Ты НЕ задаешь бесконечные «почему». Максимум один уточняющий вопрос, и дальше двигаемся.
4) Ты формируешь вопрос так, чтобы человек мог отвечать легко: либо выбор вариантов (radio/checkbox), либо короткий текст.
5) Твоя задача — собрать доказательства по 9 потенциалам и определить:
   - ТОП-3 «СИЛЫ»
   - ТОП-3 «ЭНЕРГИЯ» (ресурс/хобби)
   - ТОП-3 «СЛАБОСТИ» (делегировать/минимизировать)
   - ведущий столбец: ВОСПРИЯТИЕ / МОТИВАЦИЯ / ИНСТРУМЕНТ
6) В ответе ты возвращаешь СТРОГО JSON.

Формат JSON:
{
  "question_id": "string",
  "stage": "intake|now|childhood|columns|validation|shifts|wrap",
  "answer_type": "single|multi|text|single_plus_text|multi_plus_text",
  "question_text": "string",
  "options": ["..."] ,
  "allow_comment": true|false,
  "comment_prompt": "string",
  "scoring_hints": {
    "potentials": {"Янтарь": 0.0, "...": 0.0},
    "column": "ВОСПРИЯТИЕ|МОТИВАЦИЯ|ИНСТРУМЕНТ|",
    "row_signal": "СИЛЫ|ЭНЕРГИЯ|СЛАБОСТИ|",
    "shift_risk": true|false
  },
  "master_note": "короткая заметка для мастера (1-2 предложения)",
  "avoid_reask_signature": "короткая сигнатура смысла вопроса, чтобы не повторять"
}

Правила:
- options должны быть 4-9 пунктов максимум.
- question_id должен быть уникальным.
- scoring_hints: ставь положительные веса тем потенциалам, которые вопрос выявляет. Это подсказка, не истина.
- avoid_reask_signature: опиши смысл вопроса (например: "детство: игры/роль в компании").
"""

SYSTEM_REPORT_CLIENT = """Ты пишешь короткий клиентский отчет на русском, без сырого лога.
Тон: поддерживающе, ясно, без мистики.
Структура:
1) Заголовок с именем
2) ТОП-3 СИЛЫ (1-2 строки на каждый)
3) ТОП-3 ЭНЕРГИЯ (как пополняться)
4) ТОП-3 СЛАБОСТИ (что делегировать/минимизировать)
5) Ведущий столбец (Восприятие/Мотивация/Инструмент) — что это значит
6) 3 шага на ближайшие 7 дней (очень конкретно)
НЕ показывай числовые баллы и внутренние коэффициенты.
"""

SYSTEM_REPORT_MASTER = """Ты пишешь отчет для мастера: структурировано и практично.
Дай:
- Итоговую матрицу 3x3 (ряды: СИЛЫ/ЭНЕРГИЯ/СЛАБОСТИ; столбцы: ВОСПРИЯТИЕ/МОТИВАЦИЯ/ИНСТРУМЕНТ)
- Обоснование по каждому топ-потенциалу: 3-5 доказательств из ответов (цитаты/пересказ)
- Конфликты/противоречия и гипотезы смещений
- Какие 5 уточняющих вопросов задать, если мастер будет продолжать разбор
Тон деловой. Можно показывать баллы.
"""

# =========================
# Helpers
# =========================
def get_client() -> OpenAI:
    return OpenAI(api_key=st.secrets.get("OPENAI_API_KEY"))

def model_name() -> str:
    return st.secrets.get("OPENAI_MODEL", MODEL_DEFAULT)

def safe_json_load(s: str) -> Optional[dict]:
    try:
        return json.loads(s)
    except Exception:
        return None

def normalize_text(t: str) -> str:
    return (t or "").strip()

def tokenise(text: str) -> List[str]:
    # очень грубо, но достаточно для negation window
    return re.findall(r"[а-яА-ЯёЁa-zA-Z0-9]+", text.lower())

def contains_negated_keyword(text: str, kw: str) -> bool:
    words = tokenise(text)
    k = kw.lower()
    # проверяем по подстроке в словах
    for i, w in enumerate(words):
        if k in w:
            start = max(0, i - NEGATION_WINDOW)
            window = words[start:i]
            if "не" in window or "нет" in window:
                return True
    return False

def keyword_score(text: str) -> Dict[str, float]:
    """
    +0.6 за попадание ключевого слова
    -0.9 если рядом отрицание ("не люблю порядок")
    """
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

def add_scores(base: Dict[str, float], delta: Dict[str, float], w: float = 1.0) -> Dict[str, float]:
    for p in POTENTIALS:
        base[p] = float(base.get(p, 0.0)) + float(delta.get(p, 0.0)) * float(w)
    return base

def topn(scores: Dict[str, float], n: int) -> List[str]:
    return [k for k, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)[:n]]

def bottomn(scores: Dict[str, float], n: int) -> List[str]:
    return [k for k, _ in sorted(scores.items(), key=lambda x: x[1])[:n]]

def derive_rows(scores: Dict[str, float]) -> Dict[str, List[str]]:
    # MVP: делим по рангу (верх/середина/низ)
    ordered = [k for k, _ in sorted(scores.items(), key=lambda x: x[1], reverse=True)]
    return {
        "СИЛЫ": ordered[:3],
        "ЭНЕРГИЯ": ordered[3:6],
        "СЛАБОСТИ": ordered[6:9],
    }

def derive_column(column_votes: Dict[str, float]) -> str:
    if not column_votes:
        return "МОТИВАЦИЯ"
    return max(column_votes.items(), key=lambda x: x[1])[0]

def should_stop(state: dict) -> bool:
    # останавливаемся не раньше MIN_QUESTIONS
    if state["q_count"] < MIN_QUESTIONS:
        return False
    if state["q_count"] >= MAX_QUESTIONS:
        return True

    # если уже есть 3-4 подтверждения на ТОП-3 и покрыты столбцы/детство/смещения — можно стоп
    top3 = topn(state["scores"], 3)
    ok_evidence = all(len(state["evidence"].get(p, [])) >= 3 for p in top3)

    col_ok = all(state["column_coverage"].get(c, 0) >= COLUMN_QUESTIONS_TARGET[c] for c in COLUMNS)
    child_ok = state["childhood_count"] >= CHILDHOOD_QUESTIONS_TARGET
    shifts_ok = state["shifts_count"] >= SHIFT_QUESTIONS_TARGET

    # если shifts не понадобились (нет конфликтов) — допускаем 1
    if state["shift_risk_events"] == 0:
        shifts_ok = state["shifts_count"] >= 1

    return ok_evidence and col_ok and child_ok and shifts_ok

def compact_state_for_llm(state: dict) -> dict:
    # чтобы LLM видел прогресс и не повторялся
    return {
        "name": state.get("name"),
        "goal": state.get("goal"),
        "q_count": state["q_count"],
        "stage": state["stage"],
        "top3_now": topn(state["scores"], 3),
        "bottom3_now": bottomn(state["scores"], 3),
        "column_coverage": state["column_coverage"],
        "childhood_count": state["childhood_count"],
        "shifts_count": state["shifts_count"],
        "shift_risk_events": state["shift_risk_events"],
        "used_signatures": list(state["used_signatures"])[:60],
        "last_questions": state["history"][-4:],
    }

# =========================
# Streamlit state
# =========================
def init_state():
    st.session_state.setdefault("state", {
        "name": "",
        "goal": "",
        "stage": "intake",
        "q_count": 0,
        "scores": {p: 0.0 for p in POTENTIALS},
        "column_votes": {c: 0.0 for c in COLUMNS},
        "column_coverage": {c: 0 for c in COLUMNS},
        "childhood_count": 0,
        "shifts_count": 0,
        "shift_risk_events": 0,
        "used_signatures": set(),
        "asked_ids": set(),
        "evidence": {p: [] for p in POTENTIALS},
        "events": [],     # full event log for master
        "history": [],    # short chat-like transcript (for LLM + user feel)
        "last_answer_text": "",
        "last_question_id": "",
        "last_question_signature": "",
        "followup_used_for_signature": {},
        "final_client_report": "",
        "final_master_report": "",
    })
    st.session_state.setdefault("current_question", None)
    st.session_state.setdefault("ui_answer_cache", {"single": None, "multi": [], "text": ""})
    st.session_state.setdefault("show_master", False)

def clear_answer_widgets():
    # очищаем между вопросами — чтобы не оставалось текста
    st.session_state["ui_answer_cache"] = {"single": None, "multi": [], "text": ""}

# =========================
# LLM calls
# =========================
def llm_next_question(state: dict) -> dict:
    client = get_client()

    payload = {
        "state": compact_state_for_llm(state),
        "instruction": "Сгенерируй следующий лучший вопрос. Не повторяй сигнатуры из used_signatures. Не начинай заново."
    }

    resp = client.responses.create(
        model=model_name(),
        input=[
            {"role": "system", "content": SYSTEM_INTERVIEW},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
        ],
        response_format={"type": "json_object"},
    )

    data = safe_json_load(resp.output_text)
    if not data:
        # fallback — очень простой вопрос
        data = {
            "question_id": f"fallback_{int(time.time())}",
            "stage": state.get("stage", "columns"),
            "answer_type": "text",
            "question_text": "Опиши один пример: какая деятельность в последнее время реально заряжала тебя энергией (и почему)?",
            "options": [],
            "allow_comment": False,
            "comment_prompt": "",
            "scoring_hints": {"potentials": {}, "column": "МОТИВАЦИЯ", "row_signal": "СИЛЫ", "shift_risk": False},
            "master_note": "fallback",
            "avoid_reask_signature": "fallback_energy_example"
        }
    return data

def llm_make_reports(state: dict) -> (str, str):
    client = get_client()

    rows = derive_rows(state["scores"])
    col = derive_column(state["column_votes"])

    summary = {
        "name": state.get("name", ""),
        "goal": state.get("goal", ""),
        "rows": rows,
        "lead_column": col,
        "evidence": state["events"][-30:],  # последние события — достаточно
        "scores": state["scores"],
    }

    client_report = client.responses.create(
        model=model_name(),
        input=[
            {"role": "system", "content": SYSTEM_REPORT_CLIENT},
            {"role": "user", "content": json.dumps(summary, ensure_ascii=False)},
        ],
    ).output_text

    master_report = client.responses.create(
        model=model_name(),
        input=[
            {"role": "system", "content": SYSTEM_REPORT_MASTER},
            {"role": "user", "content": json.dumps(summary, ensure_ascii=False)},
        ],
    ).output_text

    return client_report, master_report

# =========================
# Scoring
# =========================
def apply_answer(state: dict, q: dict, answer: dict):
    """
    answer: {
      "selected": str|list|None,
      "text": str
    }
    """
    qid = q.get("question_id", f"q_{int(time.time())}")
    signature = q.get("avoid_reask_signature", "") or qid

    # 防 повторов: если сигнатура уже была — это ошибка логики, но мы не ломаемся
    if signature in state["used_signatures"]:
        # мягко отмечаем
        state["shift_risk_events"] += 1

    state["asked_ids"].add(qid)
    state["used_signatures"].add(signature)

    # followup лимит
    follow = state["followup_used_for_signature"].get(signature, 0)
    if follow > MAX_FOLLOWUP_REPEAT:
        # если ИИ пытается мусолить — штрафуем и считаем как shift-risk
        state["shift_risk_events"] += 1

    # Колонка/ряд — голоса
    hints = q.get("scoring_hints", {}) or {}
    col = hints.get("column") or ""
    row_signal = hints.get("row_signal") or ""
    shift_risk = bool(hints.get("shift_risk", False))

    # текст ответа как единая строка
    sel = answer.get("selected")
    txt = normalize_text(answer.get("text") or "")
    if isinstance(sel, list):
        sel_text = "; ".join(sel)
    else:
        sel_text = sel or ""
    full_text = (sel_text + " " + txt).strip()

    # 1) базовые подсказки от LLM
    hint_pots = (hints.get("potentials") or {})
    hint_delta = {p: float(hint_pots.get(p, 0.0)) for p in POTENTIALS}

    # 2) keyword scoring + negation handling
    kw_delta = keyword_score(full_text)

    # 3) row signal: усиливаем/ослабляем
    row_w = 1.0
    if row_signal == "СИЛЫ":
        row_w = 1.15
    elif row_signal == "ЭНЕРГИЯ":
        row_w = 0.95
    elif row_signal == "СЛАБОСТИ":
        row_w = 0.8

    # 4) применяем: подсказки умеренно, keywords сильнее (потому что у тебя именно смысловые маркеры)
    add_scores(state["scores"], hint_delta, w=0.7 * row_w)
    add_scores(state["scores"], kw_delta, w=1.0 * row_w)

    # 5) колонка
    if col in COLUMNS:
        state["column_votes"][col] = float(state["column_votes"].get(col, 0.0)) + 1.0
        state["column_coverage"][col] = int(state["column_coverage"].get(col, 0)) + 1

    # 6) этапы учета
    stage = q.get("stage", "")
    if stage == "childhood":
        state["childhood_count"] += 1
    if stage == "shifts":
        state["shifts_count"] += 1
    if shift_risk:
        state["shift_risk_events"] += 1

    # 7) evidence (для мастера): по ТОП-3 на момент ответа
    current_top = topn(state["scores"], 3)
    for p in current_top:
        state["evidence"].setdefault(p, []).append(f"{qid}: {full_text[:160]}")

    # 8) event log
    state["events"].append({
        "ts": int(time.time()),
        "question_id": qid,
        "stage": stage,
        "question_text": q.get("question_text", ""),
        "answer_type": q.get("answer_type", ""),
        "selected": sel,
        "text": txt,
        "signature": signature,
        "column": col,
        "row_signal": row_signal,
        "shift_risk": shift_risk,
        "master_note": q.get("master_note", ""),
    })

    # 9) user-visible chat history (кратко)
    state["history"].append({"role": "assistant", "content": q.get("question_text", "")})
    state["history"].append({"role": "user", "content": full_text})

    # 10) увеличиваем счётчик вопросов только на смысловые (не на служебные)
    state["q_count"] += 1

# =========================
# UI
# =========================
st.set_page_config(page_title="NEO Диагностика", page_icon="🧭", layout="centered")
init_state()
state = st.session_state["state"]

# -------- Header (clean) ----------
st.title("🧭 NEO Диагностика потенциалов")
st.caption("Формат: живой разбор. Без лишней воды. В конце — короткая картина + следующий шаг.")

# -------- Master access (hidden) ----------
with st.sidebar:
    st.markdown("### ⚙️ Доступ мастера")
    code = st.text_input("Код мастера", type="password", placeholder="если есть")
    if code and code == str(st.secrets.get("MASTER_CODE", "")):
        st.session_state["show_master"] = True
        st.success("Режим мастера включен")
    elif code and not st.secrets.get("MASTER_CODE"):
        st.info("MASTER_CODE не задан в Secrets.")
    elif code and code != str(st.secrets.get("MASTER_CODE", "")):
        st.error("Неверный код")

# -------- Final screen ----------
if state.get("final_client_report"):
    st.subheader("✅ Результат диагностики")
    st.write(state["final_client_report"])

    # Мастер-панель (только если включена)
    if st.session_state.get("show_master"):
        st.divider()
        st.subheader("🔒 Отчет мастера")
        st.write(state.get("final_master_report", ""))

        with st.expander("Сырые данные (event log)"):
            st.json(state["events"])

        with st.expander("Баллы (для калибровки)"):
            st.json(state["scores"])

    st.stop()

# -------- Get / create question ----------
if st.session_state["current_question"] is None:
    # если совсем старт
    q = llm_next_question(state)

    # защита от повторов по signature (жёстче)
    sig = q.get("avoid_reask_signature", "")
    if sig and sig in state["used_signatures"]:
        # попросим LLM другой вопрос один раз
        state["shift_risk_events"] += 1
        q = llm_next_question(state)

    st.session_state["current_question"] = q
    clear_answer_widgets()
else:
    q = st.session_state["current_question"]

# -------- Render question ----------
st.subheader(q.get("question_text", "Вопрос"))

atype = q.get("answer_type", "text")
options = q.get("options", []) or []
allow_comment = bool(q.get("allow_comment", False))
comment_prompt = q.get("comment_prompt", "Комментарий (необязательно):")

# ключи чтобы не залипало поле между вопросами
qid_key = q.get("question_id", f"q_{state['q_count']}")

selected = None
text_value = ""

# UI строго под тип
if atype == "single":
    selected = st.radio("Выберите один вариант:", options, key=f"single_{qid_key}")
elif atype == "multi":
    selected = st.multiselect("Выберите несколько:", options, key=f"multi_{qid_key}")
elif atype == "text":
    text_value = st.text_area("Ответ:", key=f"text_{qid_key}", height=120, placeholder="Напиши коротко, как есть…")
elif atype == "single_plus_text":
    selected = st.radio("Выберите один вариант:", options, key=f"single_{qid_key}")
    text_value = st.text_area(comment_prompt, key=f"text_{qid_key}", height=90)
elif atype == "multi_plus_text":
    selected = st.multiselect("Выберите несколько:", options, key=f"multi_{qid_key}")
    text_value = st.text_area(comment_prompt, key=f"text_{qid_key}", height=90)
else:
    text_value = st.text_area("Ответ:", key=f"text_{qid_key}", height=120)

# Кнопки (чисто)
colA, colB = st.columns([1, 1])
with colA:
    next_btn = st.button("Далее ➜", use_container_width=True)
with colB:
    restart_btn = st.button("Начать заново", use_container_width=True)

if restart_btn:
    st.session_state.clear()
    st.rerun()

# -------- Validate + Apply ----------
if next_btn:
    # простая валидация: нельзя пусто
    if atype in ("single", "single_plus_text") and not selected:
        st.warning("Выбери вариант.")
        st.stop()
    if atype in ("multi", "multi_plus_text") and (not selected or len(selected) == 0):
        st.warning("Выбери хотя бы один вариант.")
        st.stop()
    if atype == "text" and not normalize_text(text_value):
        st.warning("Напиши короткий ответ.")
        st.stop()

    # intake: сохраняем имя/запрос если вопрос был про это
    # (ИИ должен сам это спросить; мы ловим по сигнатуре)
    sig = (q.get("avoid_reask_signature") or "").lower()
    full_for_detect = (str(selected) + " " + str(text_value)).strip()

    if "имя" in sig or "name" in sig:
        state["name"] = normalize_text(text_value) or normalize_text(str(selected))
    if "запрос" in sig or "цель" in sig or "problem" in sig:
        if normalize_text(text_value):
            state["goal"] = normalize_text(text_value)

    # применяем ответ
    apply_answer(state, q, {"selected": selected, "text": text_value})

    # если пора заканчивать — формируем отчеты
    if should_stop(state):
        client_report, master_report = llm_make_reports(state)
        state["final_client_report"] = client_report
        state["final_master_report"] = master_report
        st.session_state["current_question"] = None
        st.rerun()

    # иначе следующий вопрос
    st.session_state["current_question"] = None
    st.rerun()