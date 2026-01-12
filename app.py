import streamlit as st
import json
from pathlib import Path
from datetime import datetime

from openai import OpenAI

# --------------------
# Settings
# --------------------
MODEL = "gpt-4.1-mini"  # можно поменять на gpt-4.1 / gpt-5.1 если доступно в твоём аккаунте
MAX_TURNS = 20
KNOWLEDGE_DIR = Path("knowledge")

# --------------------
# Helpers
# --------------------
def now_iso():
    return datetime.utcnow().isoformat()

def read_file(p: Path) -> str:
    if not p.exists():
        return ""
    return p.read_text(encoding="utf-8", errors="ignore")

def load_knowledge_bundle() -> dict:
    # Подтягиваем всё, что есть в knowledge/
    # (если каких-то файлов нет — просто будет пусто)
    return {
        "positions": read_file(KNOWLEDGE_DIR / "positions_potentials.md") or read_file(KNOWLEDGE_DIR / "positions.md"),
        "shifts": read_file(KNOWLEDGE_DIR / "shifts.md"),
        "methodology": read_file(KNOWLEDGE_DIR / "methodology.md"),
        "examples": read_file(KNOWLEDGE_DIR / "examples_transcripts.md"),
    }

def init_state():
    st.session_state.setdefault("turn", 0)
    st.session_state.setdefault("done", False)
    st.session_state.setdefault("log", [])  # список событий
    st.session_state.setdefault("name", "")
    st.session_state.setdefault("request", "")
    st.session_state.setdefault("asked_questions", [])  # тексты вопросов (для анти-повторов)
    st.session_state.setdefault("last_ai", None)         # последний JSON от модели
    st.session_state.setdefault("phase", "stage0_intake")# текущая фаза
    st.session_state.setdefault("hypothesis", {})        # текущая гипотеза профиля (как модель считает)

def client():
    api_key = st.secrets.get("OPENAI_API_KEY", None)
    if not api_key:
        st.error("Нет OPENAI_API_KEY в Streamlit Secrets. Добавь его в настройках приложения.")
        st.stop()
    return OpenAI(api_key=api_key)

def build_system_prompt(knowledge: dict) -> str:
    # Жёстко ограничиваем поведение: только на основе knowledge, формат JSON, без повтора вопросов.
    return f"""
Ты — ИИ-интервьюер диагностики NEO Потенциалов. Твоя задача: провести живой разбор как мастер.
ВАЖНО:
- НЕЛЬЗЯ использовать заранее заданный банк вопросов. Ты сам формулируешь вопросы.
- Но ты обязан опираться на материалы в knowledge: positions, shifts, methodology, examples.
- Вопросы должны идти по логике: intake → текущая ситуация → детство/биография → проверка гипотез → смещения → wrap.
- НИКАКИХ повторов. Пользователь устал от повторов.
- Каждый вопрос должен быть максимально понятный, “по-человечески”, как мастер в живом разборе.

ФОРМАТ ОТВЕТА: строго JSON, без текста вокруг.

JSON-схема, которую ты обязан возвращать:
{{
  "phase": "stage0_intake|stage1_now|stage2_childhood|stage3_hypothesis|stage4_shifts|stage5_wrap",
  "question": "текст следующего вопроса",
  "answer_type": "single|multi|text",
  "options": ["..."] ,      // обязателен только если answer_type=single или multi
  "allow_free_text": true|false, // если true — пользователь может дописать “другое”
  "why_this_question": "коротко для мастера (1-2 предложения), НЕ для клиента",
  "update": {{
      "hypothesis": {{
         "top_potentials": ["...","...","..."],
         "rows_guess": {{
            "row1": ["...","...","..."],
            "row2": ["...","...","..."],
            "row3": ["...","...","..."]
         }},
         "columns_guess": {{
            "col1": "ВОСПРИЯТИЕ: ...",
            "col2": "МОТИВАЦИЯ: ...",
            "col3": "ИНСТРУМЕНТ: ..."
         }},
         "shift_risk": "low|medium|high",
         "notes_for_master": ["..."]
      }},
      "done": true|false,
      "client_micro_reflection": "1 короткая фраза-отзеркаливание ответа (без терапии и морали)"
  }}
}}

ПРАВИЛА ДЛЯ options:
- single: 6–9 вариантов максимум
- multi: 6–10 вариантов, выбрать до 3
- обязательно добавляй вариант "Другое (напишу)" если allow_free_text=true

КРИТЕРИИ ЗАВЕРШЕНИЯ (done=true):
- Уже есть устойчивая гипотеза top3 потенциалов
- Есть распределение по рядам (силы/энергия/слабости) и столбцам (восприятие/мотивация/инструмент) хотя бы как гипотеза
- Есть проверка на смещения (минимум 1–2 вопроса) ИЛИ явных триггеров нет
- turn >= 10 (минимум), либо turn >= 7 если уверенность высокая

НИЖЕ — знания (используй как первичный источник):
--- positions ---
{knowledge["positions"]}

--- shifts ---
{knowledge["shifts"]}

--- methodology ---
{knowledge["methodology"]}

--- examples ---
{knowledge["examples"]}
""".strip()

def build_context_for_model():
    # Укороченная “память” — чтобы модель не повторялась и держала логику.
    log = st.session_state["log"]
    asked = st.session_state["asked_questions"]
    hypo = st.session_state.get("hypothesis", {})
    name = st.session_state.get("name", "")
    req = st.session_state.get("request", "")
    phase = st.session_state.get("phase", "stage0_intake")
    turn = st.session_state.get("turn", 0)

    return {
        "turn": turn,
        "phase": phase,
        "name": name,
        "request": req,
        "asked_questions": asked[-12:],    # чтобы модель видела последние, не повторялась
        "recent_log": log[-10:],           # последние ответы
        "current_hypothesis": hypo
    }

def call_next_question(oclient, system_prompt: str, context: dict):
    user_msg = {
        "role": "user",
        "content": json.dumps(context, ensure_ascii=False)
    }
    resp = oclient.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            user_msg
        ],
        temperature=0.35
    )
    text = resp.choices[0].message.content.strip()
    # Иногда модель может случайно добавить текст — пытаемся вытащить JSON
    try:
        return json.loads(text)
    except Exception:
        # fallback: ищем первый { ... } блок
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
        raise

def log_event(q_json, answer, free_text=None):
    event = {
        "timestamp": now_iso(),
        "turn": st.session_state["turn"],
        "phase": q_json.get("phase", ""),
        "question": q_json.get("question", ""),
        "answer_type": q_json.get("answer_type", ""),
        "answer": answer,
        "free_text": free_text or ""
    }
    st.session_state["log"].append(event)
    st.session_state["asked_questions"].append(q_json.get("question", ""))

# --------------------
# UI
# --------------------
st.set_page_config(page_title="NEO Диагностика", page_icon="✨", layout="centered")

init_state()
knowledge = load_knowledge_bundle()
sys_prompt = build_system_prompt(knowledge)
oclient = client()

st.title("NEO Диагностика потенциалов")
st.caption("Формат: живой разбор. Вопросы формирует ИИ по логике этапов, без повторов.")

# кнопки управления
colA, colB = st.columns([1,1])
with colA:
    if st.button("🔄 Сбросить диагностику"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()
with colB:
    st.write(f"Ход: вопрос {min(st.session_state['turn']+1, MAX_TURNS)} из {MAX_TURNS} | фаза: {st.session_state.get('phase','')}")

# если закончено
if st.session_state["done"]:
    st.success("Диагностика завершена ✅")

    name = st.session_state.get("name") or "Вы"
    req = st.session_state.get("request") or "не указан"

    st.markdown(f"**Имя:** {name}")
    st.markdown(f"**Запрос:** {req}")

    hypo = st.session_state.get("hypothesis", {})
    top3 = (hypo.get("top_potentials") or [])
    rows = (hypo.get("rows_guess") or {})
    cols = (hypo.get("columns_guess") or {})
    shift_risk = hypo.get("shift_risk", "unknown")

    st.markdown("## Результат (MVP-гипотеза)")
    st.write("**Топ-3 потенциала:**", top3)
    st.write("**СИЛЫ (ряд 1):**", rows.get("row1", []))
    st.write("**ЭНЕРГИЯ (ряд 2):**", rows.get("row2", []))
    st.write("**СЛАБОСТИ (ряд 3):**", rows.get("row3", []))
    st.write("**Столбцы (гипотеза):**", cols)
    st.write("**Риск смещений:**", shift_risk)

    st.markdown("### Что дальше")
    st.markdown("- Мастерская версия отчёта: реализация, деньги, план действий.")
    st.markdown("- Мастер проверяет гипотезы и калибрует профиль по смещениям/позициям.")

    with st.expander("Тех.лог (для мастера)"):
        st.json(st.session_state["log"])

    st.download_button(
        "📄 Скачать транскрипт (JSON)",
        data=json.dumps(st.session_state["log"], ensure_ascii=False, indent=2),
        file_name="neo_transcript.json",
        mime="application/json"
    )

    st.stop()

# --------------------
# Получить следующий вопрос от модели
# --------------------
if st.session_state["last_ai"] is None:
    context = build_context_for_model()
    try:
        q_json = call_next_question(oclient, sys_prompt, context)
    except Exception as e:
        st.error(f"Не удалось получить вопрос от ИИ: {e}")
        st.stop()

    st.session_state["last_ai"] = q_json
    st.session_state["phase"] = q_json.get("phase", st.session_state["phase"])

q = st.session_state["last_ai"]

# микрорефлексия (для ощущения “со мной разговаривают”)
micro = (q.get("update", {}) or {}).get("client_micro_reflection")
if micro:
    st.info(micro)

st.subheader(q.get("question", "Вопрос"))

answer_type = q.get("answer_type", "text")
options = q.get("options", []) or []
allow_free_text = bool(q.get("allow_free_text", False))

user_answer = None
free_text = ""

if answer_type == "single":
    user_answer = st.radio("Выберите:", options, index=None)
    if allow_free_text:
        free_text = st.text_input("Если выбрали 'Другое' — напишите:", "")

elif answer_type == "multi":
    user_answer = st.multiselect("Выберите (до 3):", options)
    if allow_free_text:
        free_text = st.text_input("Если выбрали 'Другое' — напишите:", "")

else:
    user_answer = st.text_area("Ответ:", height=140)

# --------------------
# Next
# --------------------
if st.button("Далее ➜", type="primary"):
    # простая валидация
    if answer_type == "single" and not user_answer:
        st.warning("Выберите вариант, чтобы продолжить.")
        st.stop()
    if answer_type == "multi" and isinstance(user_answer, list) and len(user_answer) == 0:
        st.warning("Выберите хотя бы один вариант, чтобы продолжить.")
        st.stop()
    if answer_type == "text" and (not user_answer or not str(user_answer).strip()):
        st.warning("Напишите ответ, чтобы продолжить.")
        st.stop()

    # сохранить имя/запрос (если модель спросила)
    q_text = (q.get("question") or "").lower()
    if "как тебя зовут" in q_text or "вас зовут" in q_text:
        st.session_state["name"] = str(user_answer).strip()
    if "с каким запросом" in q_text or "что сейчас хочется понять" in q_text or "запрос" in q_text:
        st.session_state["request"] = str(user_answer).strip()

    # логируем
    log_event(q, user_answer, free_text=free_text)

    # обновляем гипотезу
    upd = (q.get("update") or {})
    if "hypothesis" in upd and isinstance(upd["hypothesis"], dict):
        st.session_state["hypothesis"] = upd["hypothesis"]

    # done?
    if bool(upd.get("done", False)) or st.session_state["turn"] >= (MAX_TURNS - 1):
        st.session_state["done"] = True

    # следующий шаг
    st.session_state["turn"] += 1
    st.session_state["last_ai"] = None
    st.rerun()