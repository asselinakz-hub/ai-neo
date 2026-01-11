import os
import json
from datetime import datetime

import streamlit as st

# --- OpenAI SDK (new style) ---
# pip install openai
try:
    from openai import OpenAI
except Exception:
    OpenAI = None


# -----------------------------
# Helpers: load repo files
# -----------------------------
def read_text(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_read(path: str, default: str = "") -> str:
    try:
        return read_text(path)
    except Exception:
        return default


def safe_json(path: str, default: dict | None = None) -> dict:
    if default is None:
        default = {}
    try:
        return load_json(path)
    except Exception:
        return default


def build_knowledge_bundle(knowledge_dir: str) -> str:
    """
    Собираем ВСЕ знания в один текстовый блок.
    ИИ будет использовать их как внутреннюю базу.
    """
    parts = []
    for fname in [
        "positions.md",
        "shifts.md",
        "methodology.md",
        "question_bank.md",
        "examples_transcripts.md",
    ]:
        fpath = os.path.join(knowledge_dir, fname)
        content = safe_read(fpath, default="")
        if content.strip():
            parts.append(f"\n\n# FILE: {fname}\n{content}\n")
    return "\n".join(parts).strip()


def build_system_prompt(prompts_dir: str, knowledge_dir: str, config_path: str) -> str:
    system_txt = safe_read(os.path.join(prompts_dir, "system.txt"), "")
    knowledge_bundle = build_knowledge_bundle(knowledge_dir)
    cfg = safe_json(config_path, {})

    cfg_block = json.dumps(cfg, ensure_ascii=False, indent=2) if cfg else ""

    prompt = f"""
{system_txt}

# CONFIG (diagnosis_config.json)
{cfg_block}

# KNOWLEDGE BASE (from knowledge/)
{knowledge_bundle}

# IMPORTANT
- Используй ТОЛЬКО знания и вопросы из knowledge/ (question_bank.md и методология).
- Не придумывай новые вопросы "от себя".
- Если данных мало — задавай уточняющие вопросы из банка.
- Держи формат: задаёшь 1 вопрос за раз и ждёшь ответ.
- По завершению: выдай 2 версии результата:
  1) CLIENT_REPORT: понятный, без “внутренней кухни”
  2) MASTER_REPORT_JSON: строгий JSON (структура из config если есть), с confidence и противоречиями.
""".strip()

    return prompt


# -----------------------------
# OpenAI call
# -----------------------------
def get_client():
    api_key = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error("Нет OPENAI_API_KEY. Добавь в Streamlit Secrets или переменную окружения.")
        st.stop()

    if OpenAI is None:
        st.error("Не установлен пакет openai. Добавь его в requirements.txt: openai")
        st.stop()

    return OpenAI(api_key=api_key)


def chat_completion(client, model: str, messages: list[dict], temperature: float = 0.2) -> str:
    """
    Возвращает текст ответа ассистента.
    """
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content


# -----------------------------
# Streamlit UI
# -----------------------------
st.set_page_config(page_title="AI-NEO Diagnostic", page_icon="🧠", layout="wide")

st.title("🧠 AI-NEO — Диагностика потенциалов (MVP)")

with st.sidebar:
    st.header("Настройки")
    model = st.selectbox("Модель", ["gpt-4.1-mini", "gpt-4o-mini", "gpt-4.1"], index=0)
    temperature = st.slider("Температура", 0.0, 1.0, 0.2, 0.05)

    st.divider()
    st.caption("Файлы в репо")
    prompts_dir = st.text_input("prompts dir", value="prompts")
    knowledge_dir = st.text_input("knowledge dir", value="knowledge")
    config_path = st.text_input("config path", value="configs/diagnosis_config.json")

    st.divider()
    if st.button("🔄 Пересобрать SYSTEM_PROMPT"):
        st.session_state["system_prompt"] = build_system_prompt(prompts_dir, knowledge_dir, config_path)
        st.success("SYSTEM_PROMPT пересобран.")

    if st.button("🧹 Новый диалог"):
        for k in ["messages", "system_prompt", "final_client_report", "final_master_json"]:
            if k in st.session_state:
                del st.session_state[k]
        st.rerun()

# Build system prompt once
if "system_prompt" not in st.session_state:
    st.session_state["system_prompt"] = build_system_prompt(prompts_dir, knowledge_dir, config_path)

# Init messages
if "messages" not in st.session_state:
    st.session_state["messages"] = [
        {"role": "system", "content": st.session_state["system_prompt"]},
        {"role": "assistant", "content": "Привет! Я проведу диагностику. Скажи, ты хочешь пройти её текстом или голосом (если голосом — просто диктуй сюда текстом)?"}
    ]

# Show chat
for m in st.session_state["messages"]:
    if m["role"] == "system":
        continue
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

# Chat input
user_text = st.chat_input("Напиши ответ…")

if user_text:
    st.session_state["messages"].append({"role": "user", "content": user_text})

    with st.chat_message("user"):
        st.markdown(user_text)

    with st.chat_message("assistant"):
        with st.spinner("Думаю…"):
            client = get_client()
            answer = chat_completion(
                client=client,
                model=model,
                messages=st.session_state["messages"],
                temperature=temperature,
            )
            st.markdown(answer)

    st.session_state["messages"].append({"role": "assistant", "content": answer})

st.divider()

# Export transcript
col1, col2 = st.columns(2)

with col1:
    if st.button("📥 Скачать транскрипт (TXT)"):
        lines = []
        for m in st.session_state["messages"]:
            if m["role"] == "system":
                continue
            lines.append(f"{m['role'].upper()}: {m['content']}\n")
        txt = "\n".join(lines)
        st.download_button(
            "Скачать",
            data=txt.encode("utf-8"),
            file_name=f"ai-neo-transcript-{datetime.now().strftime('%Y%m%d-%H%M')}.txt",
            mime="text/plain",
        )

with col2:
    st.caption("Если хочешь — добавим кнопку “Сгенерировать финальный отчёт” отдельной командой.")