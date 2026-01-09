import json
import os
import streamlit as st
from openai import OpenAI

st.set_page_config(page_title="Potentials AI (MVP)", page_icon="💎", layout="centered")

# --- OpenAI client ---
# API key берется из переменной окружения OPENAI_API_KEY (Streamlit Cloud / локально)
client = OpenAI()

def load_system_prompt() -> str:
    with open("prompts/system.txt", "r", encoding="utf-8") as f:
        return f.read()

SYSTEM = load_system_prompt()

def ask_ai(history_messages):
    """
    history_messages: list[dict] in OpenAI format:
      [{"role":"system","content":"..."}, {"role":"user","content":"..."}, ...]
    """
    # Базовый запрос (без стриминга)
    resp = client.responses.create(
        model="gpt-5.2",
        input=history_messages
    )
    # У Responses API удобное поле output_text
    text = resp.output_text.strip()
    return text

def safe_parse_json(text: str):
    """
    Мягко пытаемся распарсить JSON.
    Если модель добавила лишний текст — пробуем вырезать JSON-блок.
    """
    try:
        return json.loads(text)
    except Exception:
        # попробуем найти первый { и последний }
        if "{" in text and "}" in text:
            chunk = text[text.find("{"):text.rfind("}")+1]
            return json.loads(chunk)
        raise

# --- UI state ---
if "chat" not in st.session_state:
    st.session_state.chat = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Начни интервью. Твой стиль: тепло, конкретно, бытовыми ситуациями. Один вопрос за раз."}
    ]
if "last_ai" not in st.session_state:
    st.session_state.last_ai = None
if "done" not in st.session_state:
    st.session_state.done = False

st.title("💎 Potentials — AI интервью (MVP)")
st.caption("Это не “тест на 100%”, а умное интервью: уточняет и собирает картинку, потом выдаёт таблицу и объяснение.")

# --- Run next AI turn if needed ---
if st.session_state.last_ai is None and not st.session_state.done:
    ai_text = ask_ai(st.session_state.chat)
    st.session_state.last_ai = safe_parse_json(ai_text)

# --- Render conversation ---
last = st.session_state.last_ai

if st.session_state.done:
    st.success("Готово.")
else:
    if last.get("done") is True:
        st.session_state.done = True
        table = last["table"]
        conf = last.get("confidence", {})
        exp = last.get("explanation", {})
        steps = last.get("next_steps", [])

        st.subheader("Таблица")
        st.write("**Восприятие**:", table["perception"])
        st.write("**Мотивация**:", table["motivation"])
        st.write("**Инструмент**:", table["instrument"])

        st.subheader("Почему так (коротко)")
        st.write(f"**Восприятие ({conf.get('perception', 0)}%)** — {exp.get('perception','')}")
        st.write(f"**Мотивация ({conf.get('motivation', 0)}%)** — {exp.get('motivation','')}")
        st.write(f"**Инструмент ({conf.get('instrument', 0)}%)** — {exp.get('instrument','')}")

        st.subheader("Что проверить дальше")
        for s in steps:
            st.write("• " + s)

    else:
        st.subheader("Вопрос")
        st.write(last["question"])

        if last.get("mode") == "buttons":
            opts = last.get("options", [])
            cols = st.columns(2) if len(opts) <= 4 else st.columns(3)
            clicked = None
            for i, opt in enumerate(opts):
                with cols[i % len(cols)]:
                    if st.button(opt, use_container_width=True):
                        clicked = opt
            if clicked:
                st.session_state.chat.append({"role": "user", "content": clicked})
                st.session_state.last_ai = None
                st.rerun()

        else:
            user_text = st.text_input("Твой ответ", placeholder="Напиши как есть, одной фразой…")
            if st.button("Отправить"):
                if user_text.strip():
                    st.session_state.chat.append({"role": "user", "content": user_text.strip()})
                    st.session_state.last_ai = None
                    st.rerun()

st.divider()
st.caption("Тех.заметка: ключ берется из переменной окружения OPENAI_API_KEY.")
