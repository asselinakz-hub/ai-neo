# =========================
# app.py — PART 1/3
# =========================

import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# =========================
# KNOWLEDGE (RAG over /knowledge/*.md)
# =========================
import re
from typing import List, Dict, Tuple

KNOWLEDGE_DIR = Path("knowledge")

def _clean_text(t: str) -> str:
    t = t.replace("\r\n", "\n")
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()

def load_knowledge_docs() -> List[Tuple[str, str]]:
    """Load .md knowledge files. Returns [(filename, text), ...]"""
    if not KNOWLEDGE_DIR.exists():
        return []
    docs = []
    for p in sorted(KNOWLEDGE_DIR.glob("*.md")):
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
            docs.append((p.name, _clean_text(txt)))
        except Exception:
            continue
    return docs

@st.cache_resource(show_spinner=False)
def build_knowledge_index():
    """
    TF-IDF index over knowledge markdowns.
    Returns callable retrieve(query, top_k) -> [{source, score, excerpt}]
    """
    docs = load_knowledge_docs()
    if not docs:
        return None

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    names = [d[0] for d in docs]
    texts = [d[1] for d in docs]

    # Векторизатор по словам (рус/англ смешано) — работает нормально
    vectorizer = TfidfVectorizer(
        max_features=50000,
        ngram_range=(1, 2),
        lowercase=True
    )
    X = vectorizer.fit_transform(texts)

    def retrieve(query: str, top_k: int = 5) -> List[Dict]:
        q = (query or "").strip()
        if not q:
            return []
        qv = vectorizer.transform([q])
        sims = cosine_similarity(qv, X)[0]
        idxs = sims.argsort()[::-1][:top_k]

        out = []
        for i in idxs:
            score = float(sims[i])
            if score <= 0:
                continue
            # короткий отрывок (первые 1800 символов) — можно улучшить чанкингом позже
            excerpt = texts[i][:1800]
            out.append({"source": names[i], "score": round(score, 4), "excerpt": excerpt})
        return out

    return retrieve

def knowledge_query_from_payload(payload: dict) -> str:
    """
    Формируем запрос к knowledge так, чтобы доставать методику, позиции, смещения и т.п.
    """
    meta = payload.get("meta", {})
    answers = payload.get("answers", {})
    scores = payload.get("scores", {})

    req = str(answers.get("intake.ask_request", "") or "")
    goal = str(answers.get("intake.goal_3m", "") or "")
    hate = str(answers.get("antipattern.hate_task", "") or "")
    leak = str(answers.get("antipattern.energy_leak", "") or "")

    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:4]
    top_names = [t[0] for t in top if t[1] > 0]

    return " | ".join([
        f"Запрос: {req}",
        f"Цель 3м: {goal}",
        f"Топ потенциалы: {', '.join(top_names)}",
        f"Нелюбимое: {hate}",
        f"Слив энергии: {leak}",
        "позиции потенциалов",
        "смещения",
        "методика диагностики",
        "рекомендации по реализации"
    ])

def get_knowledge_snippets(payload: dict, top_k: int = 6) -> List[Dict]:
    retriever = build_knowledge_index()
    if not retriever:
        return []
    query = knowledge_query_from_payload(payload)
    return retriever(query, top_k=top_k)

# ---------------------------------
# Streamlit config (MUST be first)
# ---------------------------------
st.set_page_config(
    page_title="NEO — диагностика потенциалов",
    page_icon="💠",
    layout="centered",
)

# ---------------------------------
# Paths & constants
# ---------------------------------
APP_VERSION = "mvp-7.0"

BASE_DIR = Path(".")
DATA_DIR = BASE_DIR / "data"
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------
# Secrets / env
# ---------------------------------
MASTER_PASSWORD = st.secrets.get(
    "MASTER_PASSWORD",
    os.getenv("MASTER_PASSWORD", "")
)

OPENAI_API_KEY = st.secrets.get(
    "OPENAI_API_KEY",
    os.getenv("OPENAI_API_KEY", "")
)

DEFAULT_MODEL = st.secrets.get(
    "OPENAI_MODEL",
    os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
)

# ---------------------------------
# Utils
# ---------------------------------
def utcnow_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

# ---------------------------------
# OpenAI helper (SAFE)
# ---------------------------------
def get_openai_client():
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        return None

def safe_model_name(model: str) -> str:
    if not model:
        return DEFAULT_MODEL
    m = model.strip()
    if m.startswith("gpt-5"):
        return DEFAULT_MODEL
    return m

# ---------------------------------
# Question plan (30 вопросов)
# ---------------------------------
def question_plan():
    """
    ВАЖНО:
    - без «выбери из 3» в начале
    - сначала контакт и контекст
    - потом настоящее
    - потом детство
    - потом поведение
    - потом антипаттерны
    """
    return [

        # ===== INTAKE =====
        {
            "id": "intake.ask_name",
            "stage": "intake",
            "type": "text",
            "text": "Как мне к тебе обращаться? (имя или как удобно)"
        },
        {
            "id": "intake.ask_request",
            "stage": "intake",
            "type": "text",
            "text": "С каким запросом ты пришёл(пришла)? Что хочешь понять или изменить?"
        },
        {
            "id": "intake.contact",
            "stage": "intake",
            "type": "text",
            "text": "Оставь телефон или email — куда мастер сможет отправить полный отчёт"
        },
        {
            "id": "intake.current_state",
            "stage": "intake",
            "type": "text",
            "text": "Если коротко: что сейчас в жизни больше всего НЕ устраивает или забирает энергию?"
        },
        {
            "id": "intake.goal_3m",
            "stage": "intake",
            "type": "text",
            "text": "Представь: прошло 3 месяца и стало лучше. Что изменилось бы в первую очередь?"
        },
        {
            "id": "intake.priority_area",
            "stage": "intake",
            "type": "single",
            "text": "Что важнее всего прояснить сегодня?",
            "options": [
                "Реализация / дело",
                "Деньги / доход",
                "Отношения / люди",
                "Энергия / силы",
                "Смысл / направление"
            ]
        },

        # ===== NOW =====
        {
            "id": "now.easy_tasks",
            "stage": "now",
            "type": "text",
            "text": "Какие задачи тебе даются легко — как будто само получается?"
        },
        {
            "id": "now.praise_for",
            "stage": "now",
            "type": "text",
            "text": "За что тебя чаще всего хвалят люди?"
        },
        {
            "id": "now.time_flow",
            "stage": "now",
            "type": "text",
            "text": "В какой деятельности ты теряешь счёт времени?"
        },
        {
            "id": "now.attention_first",
            "stage": "now",
            "type": "single",
            "text": "Когда попадаешь в новую ситуацию, что замечаешь первым?",
            "options": [
                "Людей и эмоции",
                "Смысл / идею / почему так",
                "Деньги / выгоду / результат",
                "Риски / порядок / систему",
                "Красоту / атмосферу"
            ]
        },
        {
            "id": "now.best_result_example",
            "stage": "now",
            "type": "text",
            "text": "Пример из жизни: ситуация → что ты сделал(а) → результат (чем ты реально гордишься)"
        },
        {
            "id": "now.motivation_trigger",
            "stage": "now",
            "type": "single",
            "text": "Что сильнее всего тебя включает?",
            "options": [
                "Цель / стратегия / вектор",
                "Люди / влияние / связь",
                "Красота / уют / эстетика",
                "Смысл / идея / глубина",
                "Драйв / сцена / эмоции",
                "Деньги / скорость / результат"
            ]
        },
        {
            "id": "now.stress_pattern",
            "stage": "now",
            "type": "single",
            "text": "Когда давление или стресс, что происходит чаще всего?",
            "options": [
                "Ускоряюсь и становлюсь резкой(им)",
                "Ухожу в себя",
                "Начинаю всё контролировать",
                "Становлюсь эмоциональной(ым)",
                "Замираю / прокрастинирую"
            ]
        },
        {
            "id": "now.energy_fill",
            "stage": "now",
            "type": "multi",
            "text": "Что тебя реально наполняет? (1–4)",
            "options": [
                "Общение и близкие люди",
                "Красивые места / уют",
                "Тишина / чтение / размышления",
                "Учёба / новые знания",
                "Спорт / движение / тело",
                "Сцена / события / впечатления"
            ]
        },

        # ===== CHILDHOOD =====
        {
            "id": "childhood.child_play",
            "stage": "childhood",
            "type": "multi",
            "text": "В детстве (6–12 лет) что ты любил(а) больше всего?",
            "options": [
                "Организовывать / руководить",
                "Учиться / читать / объяснять",
                "Выступать / быть заметным(ой)",
                "Общаться / дружить",
                "Рисовать / украшать / делать красиво",
                "Бегать / соревноваться"
            ]
        },
        {
            "id": "childhood.teen_dream",
            "stage": "childhood",
            "type": "text",
            "text": "Подростком (12–16 лет) кем хотелось быть?"
        },
        {
            "id": "childhood.first_success",
            "stage": "childhood",
            "type": "text",
            "text": "Какое раннее достижение ты вспоминаешь первым?"
        },
        {
            "id": "childhood.family_role",
            "stage": "childhood",
            "type": "single",
            "text": "В семье или классе ты чаще был(а)…",
            "options": [
                "Лидер / организатор",
                "Душа компании",
                "Умник / аналитик",
                "Творческий / эстет",
                "Спортивный",
                "Тихий наблюдатель"
            ]
        },
        {
            "id": "childhood.child_aversion",
            "stage": "childhood",
            "type": "text",
            "text": "Что в детстве или школе было тяжело и хотелось избегать?"
        },

        # ===== BEHAVIOR =====
        {
            "id": "behavior.free_time",
            "stage": "behavior",
            "type": "text",
            "text": "Если есть 2 свободных часа — что ты делаешь?"
        },
        {
            "id": "behavior.money_spend",
            "stage": "behavior",
            "type": "multi",
            "text": "На что ты импульсивно тратишь деньги или силы?",
            "options": [
                "Обучение / курсы",
                "Проекты / инструменты",
                "Красота / дом / уют",
                "Люди / подарки",
                "Путешествия",
                "Здоровье / спорт"
            ]
        },
        {
            "id": "behavior.group_role_now",
            "stage": "behavior",
            "type": "single",
            "text": "В группе ты обычно…",
            "options": [
                "Объединяю людей",
                "Давлю на результат",
                "Придумываю идеи",
                "Навожу порядок",
                "Создаю атмосферу",
                "Зажигаю"
            ]
        },

        # ===== ANTIPATTERNS =====
        {
            "id": "antipattern.avoid",
            "stage": "antipattern",
            "type": "text",
            "text": "Какие задачи ты стабильно откладываешь?"
        },
        {
            "id": "antipattern.hate_task",
            "stage": "antipattern",
            "type": "single",
            "text": "Что для тебя самое нелюбимое?",
            "options": [
                "Рутина / регламенты",
                "Продажи и самопрезентация",
                "Физическая нагрузка",
                "Конфликты",
                "Долгие разговоры",
                "Учёба без смысла"
            ]
        },
        {
            "id": "antipattern.energy_leak",
            "stage": "antipattern",
            "type": "text",
            "text": "Где ты сейчас сильнее всего сливаешь энергию?"
        },
    ]

# ---------------------------------
# Potentials & keyword scoring
# ---------------------------------
POTS = [
    "Янтарь", "Шунгит", "Цитрин",
    "Изумруд", "Рубин", "Гранат",
    "Сапфир", "Гелиодор", "Аметист"
]

KEYWORDS = {
    "Янтарь": ["порядок", "система", "регламент", "документ", "структур"],
    "Шунгит": ["тело", "спорт", "движ", "физ", "энергия"],
    "Цитрин": ["деньги", "результат", "выгода", "быстро", "доход"],
    "Изумруд": ["красота", "уют", "эстет", "дизайн", "атмосфер"],
    "Рубин": ["драйв", "сцена", "эмоци", "впечатлен"],
    "Гранат": ["люди", "общен", "поддерж", "отношен"],
    "Сапфир": ["смысл", "идея", "почему", "глубин"],
    "Гелиодор": ["уч", "обуч", "знан", "курс"],
    "Аметист": ["цель", "стратег", "вектор", "управлен"],
}

ANTI_AMBER = [
    "не люблю порядок",
    "ненавижу порядок",
    "рутина бесит",
    "регламенты бесят"
]

def score_all(answers: dict):
    scores = {p: 0.0 for p in POTS}
    evidence = {p: [] for p in POTS}

    def add(p, v, note):
        scores[p] += v
        evidence[p].append(note)

    for qid, ans in answers.items():
        text = ""
        if isinstance(ans, list):
            text = " ".join(ans).lower()
        else:
            text = str(ans).lower()

        for p, kws in KEYWORDS.items():
            for kw in kws:
                if kw in text:
                    add(p, 0.3, f"{qid}: {kw}")

    hate = str(answers.get("antipattern.hate_task", "")).lower()
    if "рутина" in hate or "регламент" in hate:
        scores["Янтарь"] -= 0.8
        evidence["Янтарь"].append("Антипаттерн: ненависть к рутине")

    for p in POTS:
        scores[p] = max(scores[p], 0)

    return scores, evidence
    # app.py  (PART 2/3)

# =========================================================
# Session state (fixes “text carries over”)
# =========================================================
def init_state():
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("q_index", 0)
    st.session_state.setdefault("answers", {})
    st.session_state.setdefault("event_log", [])
    st.session_state.setdefault("master_authed", False)
    st.session_state.setdefault("master_selected_session", None)
    st.session_state.setdefault("ai_client_report", "")
    st.session_state.setdefault("ai_master_report", "")

def reset_diagnostic():
    # очищаем только диагностические поля
    for k in [
        "q_index","answers","event_log",
        "ai_client_report","ai_master_report",
        "_q_widget_seed"
    ]:
        if k in st.session_state:
            del st.session_state[k]
    # новый session_id, чтобы не “вечно завершено”
    st.session_state["session_id"] = str(uuid.uuid4())
    st.session_state["q_index"] = 0
    st.session_state["answers"] = {}
    st.session_state["event_log"] = []
    st.session_state["ai_client_report"] = ""
    st.session_state["ai_master_report"] = ""
    st.session_state["_q_widget_seed"] = str(uuid.uuid4())

# =========================================================
# Helpers: vectors, payload, mini-report
# =========================================================
def vectors_without_labels(scores: dict):
    v = []
    if scores.get("Цитрин",0) >= 1.2:
        v.append("результат и деньги (скорость, эффективность, выгода)")
    if scores.get("Аметист",0) >= 1.2:
        v.append("стратегирование и управление (цели, план, направление)")
    if scores.get("Гелиодор",0) >= 1.2:
        v.append("знания и обучение (разбор, объяснение, развитие)")
    if scores.get("Сапфир",0) >= 1.1:
        v.append("смысл и глубина (почему так, концепции, идеи)")
    if scores.get("Гранат",0) >= 1.1:
        v.append("люди и связь (поддержка, объединение, отношения)")
    if scores.get("Изумруд",0) >= 1.1:
        v.append("эстетика и атмосфера (красота, уют, стиль)")
    if scores.get("Рубин",0) >= 1.1:
        v.append("сцена и эмоции (впечатления, проявленность)")
    if scores.get("Шунгит",0) >= 1.1:
        v.append("тело и энергия (движение, выносливость)")
    if scores.get("Янтарь",0) >= 1.4:
        v.append("структура и система (порядок, процессы, регламенты)")
    return v[:6]

def current_meta_from_answers(answers: dict):
    name = str(answers.get("intake.ask_name","") or "").strip()
    request = str(answers.get("intake.ask_request","") or "").strip()
    contact = str(answers.get("intake.contact","") or "").strip()
    return name, request, contact

def build_payload(answers: dict, event_log: list, session_id: str):
    scores, evidence = score_all(answers)
    name, request, contact = current_meta_from_answers(answers)
    return {
        "meta": {
            "schema": "ai-neo.master_report.v7",
            "app_version": APP_VERSION,
            "timestamp": utcnow_iso(),
            "session_id": session_id,
            "name": name,
            "request": request,
            "contact": contact,
            "question_count": len(question_plan()),
            "answered_count": len(event_log),
        },
        "answers": answers,
        "scores": scores,
        "evidence": evidence,
        "event_log": event_log,
        "ai_client_report": st.session_state.get("ai_client_report",""),
        "ai_master_report": st.session_state.get("ai_master_report",""),
    }

def build_client_mini_report(payload: dict) -> str:
    meta = payload.get("meta", {})
    answers = payload.get("answers", {})
    scores = payload.get("scores", {})
    vectors = vectors_without_labels(scores)

    name = (meta.get("name") or "").strip() or "тебя"
    req = (meta.get("request") or "").strip() or (answers.get("intake.priority_area") or "—")
    current_state = (answers.get("intake.current_state") or "—").strip() if isinstance(answers.get("intake.current_state"), str) else "—"
    goal3m = (answers.get("intake.goal_3m") or "—").strip() if isinstance(answers.get("intake.goal_3m"), str) else "—"

    easy = (answers.get("now.easy_tasks") or "").strip()
    praise = (answers.get("now.praise_for") or "").strip()
    leak = (answers.get("antipattern.energy_leak") or "").strip()

    lines = []
    lines.append(f"**Имя:** {name}")
    lines.append(f"**Запрос:** {req}")
    lines.append(f"**Что сейчас забирает энергию:** {current_state if current_state else '—'}")
    lines.append(f"**Ожидаемый сдвиг за 3 месяца:** {goal3m if goal3m else '—'}")
    lines.append("")
    lines.append("### Твой текущий вектор (без ярлыков)")
    if vectors:
        for v in vectors:
            lines.append(f"- {v}")
    else:
        lines.append("- Вектор пока не до конца проявился — нужно больше фактов/примеров.")
    lines.append("")
    if easy:
        lines.append("### Что у тебя уже получается естественно")
        lines.append(f"- {easy}")
        lines.append("")
    if praise:
        lines.append("### Что люди в тебе ценят")
        lines.append(f"- {praise}")
        lines.append("")
    if leak:
        lines.append("### Где теряется энергия")
        lines.append(f"- {leak}")
        lines.append("")
    lines.append("### 3 шага на ближайшие 7 дней")
    lines.append("1) Выпиши 3 направления, где ты уже даёшь результат людям (по фактам).")
    lines.append("2) Выбери 1 направление и сделай мини-продукт (1 страница: кому/что/результат).")
    lines.append("3) Найди 5 людей и проверь спрос: короткий созвон/сообщение + один конкретный оффер.")
    lines.append("")
    lines.append("**Хочешь полный разбор?** Мастер соберёт расширенный отчёт (с гипотезой по потенциалам, смещениям и планом реализации) и отправит тебе по контакту.")
    return "\n".join(lines)

# =========================================================
# UI: render question (NO carry-over via unique keys)
# =========================================================
def is_nonempty(q, ans):
    if q["type"] == "multi":
        return isinstance(ans, list) and len(ans) > 0
    return bool(str(ans or "").strip())

def render_question(q, seed: str):
    """
    seed меняется на каждом вопросе — ключи виджетов уникальны => текст НЕ переносится дальше.
    """
    st.markdown(f"### {q['text']}")
    st.caption("Отвечай коротко и конкретно. Можно 1–5 предложений.")

    qtype = q["type"]
    options = q.get("options", [])

    if qtype == "single":
        if not options:
            return st.text_input("Ответ:", key=f"{seed}_single_text")
        return st.radio("Выбери один вариант:", options, key=f"{seed}_single_radio")
    if qtype == "multi":
        if not options:
            return st.text_area("Ответ:", height=120, key=f"{seed}_multi_text")
        return st.multiselect("Выбери 1–4:", options, key=f"{seed}_multi_select")
    # text
    return st.text_area("Ответ:", height=140, key=f"{seed}_text")

# =========================================================
# AI report generation (MASTER) — FIX: no response_format error
# We use chat.completions.create() and parse JSON manually.
# =========================================================
def build_ai_data(payload: dict):
    meta = payload.get("meta", {})
    answers = payload.get("answers", {})
    scores = payload.get("scores", {})
    vectors = vectors_without_labels(scores)

    important_keys = [
        "intake.ask_request",
        "intake.current_state",
        "intake.goal_3m",
        "now.easy_tasks",
        "now.praise_for",
        "now.best_result_example",
        "now.energy_fill",
        "antipattern.hate_task",
        "antipattern.energy_leak",
    ]
    excerpt = {k: answers.get(k) for k in important_keys if k in answers}

    return {
        "meta": meta,
        "vectors_no_labels": vectors,
        "scores_hint_for_master": scores,   # мастеру можно
        "answers_excerpt": excerpt,
    }

def _extract_json(text: str):
    """
    Простая попытка вытащить JSON из ответа модели.
    Если модель вернула текст вокруг — ищем первый '{' и последний '}'.
    """
    if not text:
        return None
    t = text.strip()
    if t.startswith("{") and t.endswith("}"):
        try:
            return json.loads(t)
        except Exception:
            pass
    i = t.find("{")
    j = t.rfind("}")
    if i >= 0 and j > i:
        chunk = t[i:j+1]
        try:
            return json.loads(chunk)
        except Exception:
            return None
    return None

def call_openai_reports(payload: dict, model: str):
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY не задан (добавь в secrets или env)")

    model = safe_model_name(model)

    data = {
        "meta": payload.get("meta", {}),
        "answers": payload.get("answers", {}),
        "scores": payload.get("scores", {}),
        "evidence": payload.get("evidence", {}),
    }

    system = (
        "Ты мастер-диагност потенциалов. "
        "Сформируй ДВА текста:\n"
        "1) client_report: 12-18 строк, НЕ называй потенциалы/камни. "
        "Дай сильные стороны, что наполняет, где слив, 3 шага на 7 дней, мягкий CTA на полный разбор.\n"
        "2) master_report: можно называть потенциалы. "
        "Дай гипотезу по топ-3, позиции если видно, противоречия, 5 уточняющих вопросов, и рекомендации по реализации.\n"
        "Ответ верни строго JSON: {\"client_report\":\"...\",\"master_report\":\"...\"}"
    )

    # ❗️ВАЖНО: без response_format (иначе падает на старом openai)
    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}
        ],
    )

    # достаём текст
    raw = getattr(resp, "output_text", None)
    if not raw:
        try:
            raw = resp.output[0].content[0].text
        except Exception:
            raw = str(resp)

    raw = raw.strip()

    # пробуем распарсить JSON
    try:
        obj = json.loads(raw)
    except Exception:
        # fallback: вытащить первую JSON-структуру из текста
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError(f"Модель вернула не-JSON:\n{raw[:800]}")
        obj = json.loads(raw[start:end+1])

    return obj.get("client_report", ""), obj.get("master_report", "")

# =========================================================
# Session state (fixes “text carries over”)
# =========================================================
def init_state():
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("q_index", 0)
    st.session_state.setdefault("answers", {})
    st.session_state.setdefault("event_log", [])
    st.session_state.setdefault("master_authed", False)
    st.session_state.setdefault("master_selected_session", None)
    st.session_state.setdefault("ai_client_report", "")
    st.session_state.setdefault("ai_master_report", "")

def reset_diagnostic():
    # очищаем только диагностические поля
    for k in [
        "q_index","answers","event_log",
        "ai_client_report","ai_master_report",
        "_q_widget_seed"
    ]:
        if k in st.session_state:
            del st.session_state[k]
    # новый session_id, чтобы не “вечно завершено”
    st.session_state["session_id"] = str(uuid.uuid4())
    st.session_state["q_index"] = 0
    st.session_state["answers"] = {}
    st.session_state["event_log"] = []
    st.session_state["ai_client_report"] = ""
    st.session_state["ai_master_report"] = ""
    st.session_state["_q_widget_seed"] = str(uuid.uuid4())

# =========================================================
# Helpers: vectors, payload, mini-report
# =========================================================
def vectors_without_labels(scores: dict):
    v = []
    if scores.get("Цитрин",0) >= 1.2:
        v.append("результат и деньги (скорость, эффективность, выгода)")
    if scores.get("Аметист",0) >= 1.2:
        v.append("стратегирование и управление (цели, план, направление)")
    if scores.get("Гелиодор",0) >= 1.2:
        v.append("знания и обучение (разбор, объяснение, развитие)")
    if scores.get("Сапфир",0) >= 1.1:
        v.append("смысл и глубина (почему так, концепции, идеи)")
    if scores.get("Гранат",0) >= 1.1:
        v.append("люди и связь (поддержка, объединение, отношения)")
    if scores.get("Изумруд",0) >= 1.1:
        v.append("эстетика и атмосфера (красота, уют, стиль)")
    if scores.get("Рубин",0) >= 1.1:
        v.append("сцена и эмоции (впечатления, проявленность)")
    if scores.get("Шунгит",0) >= 1.1:
        v.append("тело и энергия (движение, выносливость)")
    if scores.get("Янтарь",0) >= 1.4:
        v.append("структура и система (порядок, процессы, регламенты)")
    return v[:6]

def build_insight_table(payload: dict) -> dict:
    """
    Делает структурную таблицу-инсайт по ответам + скорингу.
    Возвращает словарь, который удобно показывать мастеру и давать в AI.
    """
    answers = payload.get("answers", {}) or {}
    scores = payload.get("scores", {}) or {}
    evidence = payload.get("evidence", {}) or {}

    # топ потенциалы (для мастера)
    top = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top3 = [{"pot": k, "score": round(v, 3)} for k, v in top[:3]]
    top5 = [{"pot": k, "score": round(v, 3)} for k, v in top[:5]]

    # ключевые ответы (для смысловой интерпретации)
    keys = [
        "intake.ask_request",
        "intake.current_state",
        "intake.goal_3m",
        "intake.priority_area",
        "now.easy_tasks",
        "now.praise_for",
        "now.time_flow",
        "now.attention_first",
        "now.best_result_example",
        "now.motivation_trigger",
        "now.stress_pattern",
        "now.energy_fill",
        "behavior.group_role_now",
        "behavior.decision_style",
        "antipattern.avoid",
        "antipattern.hate_task",
        "antipattern.energy_leak",
    ]
    excerpt = {k: answers.get(k) for k in keys if answers.get(k) not in [None, "", []]}

    # вектора без ярлыков (если у тебя уже есть vectors_without_labels — используй её)
    try:
        vectors = vectors_without_labels(scores)
    except Exception:
        vectors = []

    # “сильные зоны” и “риски”
    strong = [x["pot"] for x in top5 if x["score"] >= 1.2]
    weak = [k for k, v in scores.items() if float(v) < 0.7]

    table = {
        "meta": payload.get("meta", {}),
        "top3": top3,
        "top5": top5,
        "vectors_no_labels": vectors,
        "strong_pots": strong,
        "weak_pots": weak,
        "answers_excerpt": excerpt,
        "evidence_top": {p: evidence.get(p, [])[:6] for p in [t["pot"] for t in top3]},
    }
    return table

def current_meta_from_answers(answers: dict):
    name = str(answers.get("intake.ask_name","") or "").strip()
    request = str(answers.get("intake.ask_request","") or "").strip()
    contact = str(answers.get("intake.contact","") or "").strip()
    return name, request, contact

def build_payload(answers: dict, event_log: list, session_id: str):
    scores, evidence = score_all(answers)
    name, request, contact = current_meta_from_answers(answers)
    return {
        "meta": {
            "schema": "ai-neo.master_report.v7",
            "app_version": APP_VERSION,
            "timestamp": utcnow_iso(),
            "session_id": session_id,
            "name": name,
            "request": request,
            "contact": contact,
            "question_count": len(question_plan()),
            "answered_count": len(event_log),
        },
        "answers": answers,
        "scores": scores,
        "evidence": evidence,
        "event_log": event_log,
        "ai_client_report": st.session_state.get("ai_client_report",""),
        "ai_master_report": st.session_state.get("ai_master_report",""),
    }

def build_client_mini_report(payload: dict) -> str:
    meta = payload.get("meta", {})
    answers = payload.get("answers", {})
    scores = payload.get("scores", {})
    vectors = vectors_without_labels(scores)

    name = (meta.get("name") or "").strip() or "тебя"
    req = (meta.get("request") or "").strip() or (answers.get("intake.priority_area") or "—")
    current_state = (answers.get("intake.current_state") or "—").strip() if isinstance(answers.get("intake.current_state"), str) else "—"
    goal3m = (answers.get("intake.goal_3m") or "—").strip() if isinstance(answers.get("intake.goal_3m"), str) else "—"

    easy = (answers.get("now.easy_tasks") or "").strip()
    praise = (answers.get("now.praise_for") or "").strip()
    leak = (answers.get("antipattern.energy_leak") or "").strip()

    lines = []
    lines.append(f"**Имя:** {name}")
    lines.append(f"**Запрос:** {req}")
    lines.append(f"**Что сейчас забирает энергию:** {current_state if current_state else '—'}")
    lines.append(f"**Ожидаемый сдвиг за 3 месяца:** {goal3m if goal3m else '—'}")
    lines.append("")
    lines.append("### Твой текущий вектор (без ярлыков)")
    if vectors:
        for v in vectors:
            lines.append(f"- {v}")
    else:
        lines.append("- Вектор пока не до конца проявился — нужно больше фактов/примеров.")
    lines.append("")
    if easy:
        lines.append("### Что у тебя уже получается естественно")
        lines.append(f"- {easy}")
        lines.append("")
    if praise:
        lines.append("### Что люди в тебе ценят")
        lines.append(f"- {praise}")
        lines.append("")
    if leak:
        lines.append("### Где теряется энергия")
        lines.append(f"- {leak}")
        lines.append("")
    lines.append("### 3 шага на ближайшие 7 дней")
    lines.append("1) Выпиши 3 направления, где ты уже даёшь результат людям (по фактам).")
    lines.append("2) Выбери 1 направление и сделай мини-продукт (1 страница: кому/что/результат).")
    lines.append("3) Найди 5 людей и проверь спрос: короткий созвон/сообщение + один конкретный оффер.")
    lines.append("")
    lines.append("**Хочешь полный разбор?** Мастер соберёт расширенный отчёт (с гипотезой по потенциалам, смещениям и планом реализации) и отправит тебе по контакту.")
    return "\n".join(lines)

# =========================================================
# UI: render question (NO carry-over via unique keys)
# =========================================================
def is_nonempty(q, ans):
    if q["type"] == "multi":
        return isinstance(ans, list) and len(ans) > 0
    return bool(str(ans or "").strip())

def render_question(q, seed: str):
    """
    seed меняется на каждом вопросе — ключи виджетов уникальны => текст НЕ переносится дальше.
    """
    st.markdown(f"### {q['text']}")
    st.caption("Отвечай коротко и конкретно. Можно 1–5 предложений.")

    qtype = q["type"]
    options = q.get("options", [])

    if qtype == "single":
        if not options:
            return st.text_input("Ответ:", key=f"{seed}_single_text")
        return st.radio("Выбери один вариант:", options, key=f"{seed}_single_radio")
    if qtype == "multi":
        if not options:
            return st.text_area("Ответ:", height=120, key=f"{seed}_multi_text")
        return st.multiselect("Выбери 1–4:", options, key=f"{seed}_multi_select")
    # text
    return st.text_area("Ответ:", height=140, key=f"{seed}_text")

# =========================================================
# AI report generation (MASTER) — FIX: no response_format error
# We use chat.completions.create() and parse JSON manually.
# =========================================================
def build_ai_data(payload: dict):
    meta = payload.get("meta", {})
    answers = payload.get("answers", {})
    scores = payload.get("scores", {})
    vectors = vectors_without_labels(scores)

    important_keys = [
        "intake.ask_request",
        "intake.current_state",
        "intake.goal_3m",
        "now.easy_tasks",
        "now.praise_for",
        "now.best_result_example",
        "now.energy_fill",
        "antipattern.hate_task",
        "antipattern.energy_leak",
    ]
    excerpt = {k: answers.get(k) for k in important_keys if k in answers}

    return {
        "meta": meta,
        "vectors_no_labels": vectors,
        "scores_hint_for_master": scores,   # мастеру можно
        "answers_excerpt": excerpt,
    }

# Перед генерацией полезно показать, что knowledge реально подмешалось
table = build_insight_table(selected_payload)
snips = get_knowledge_snippets(selected_payload, top_k=6)

with st.expander("📌 Таблица инсайтов (для мастера)"):
    st.json(table)

with st.expander("📚 Knowledge snippets (что подмешали)"):
    if not snips:
        st.info("Нет knowledge snippets. Проверь папку knowledge/ и наличие .md файлов.")
    else:
        for s in snips:
            st.markdown(f"**{s['source']}** (score={s['score']})")
            st.code(s["excerpt"][:1200])

if st.button("Сгенерировать AI-отчёт", use_container_width=True):
    client = get_openai_client()
    if not client:
        st.error("Нет OPENAI_API_KEY")
    else:
        try:
            model = safe_model_name(st.session_state.get("master_model", DEFAULT_MODEL))
            cr, mr, table2, snips2 = call_openai_for_reports(client, model, selected_payload)
            st.session_state["ai_client_report"] = cr
            st.session_state["ai_master_report"] = mr

            # сохраним обратно в файл сессии
            selected_payload["ai_client_report"] = cr
            selected_payload["ai_master_report"] = mr
            selected_payload["ai_table"] = table2
            selected_payload["ai_knowledge_snips"] = snips2
            save_session(selected_payload)

            st.success("Готово ✅")
        except Exception as e:
            st.error(f"Ошибка генерации: {e}")

def generate_ai_reports_v1(payload: dict, model: str):
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY не задан")

    model = safe_model_name(model)

    system = (
        "Сформируй JSON строго вида: "
        "{\"client_report\":\"...\",\"master_report\":\"...\"}.\n"
        "client_report: 12-18 строк, без названий камней, сильные стороны, что наполняет/сливает, 3 шага на 7 дней, CTA.\n"
        "master_report: можно с камнями, гипотеза топ-3, противоречия, 5 уточняющих вопросов, рекомендации."
    )

    data = {
        "meta": payload.get("meta", {}),
        "answers": payload.get("answers", {}),
        "scores": payload.get("scores", {}),
        "evidence": payload.get("evidence", {}),
    }

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}
        ],
    )

    raw = getattr(resp, "output_text", "") or ""
    raw = raw.strip()

    # fallback если output_text пустой
    if not raw:
        try:
            raw = resp.output[0].content[0].text.strip()
        except Exception:
            raw = str(resp)

    # парсим JSON (модель иногда добавляет текст вокруг)
    try:
        obj = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1:
            raise RuntimeError(f"Модель вернула не-JSON:\n{raw[:800]}")
        obj = json.loads(raw[start:end+1])

    return obj.get("client_report",""), obj.get("master_report","")

def _extract_text_from_openai(resp) -> str:
    # Универсально достаём текст
    if hasattr(resp, "output_text"):
        return resp.output_text or ""
    # chat.completions
    try:
        return resp.choices[0].message.content or ""
    except Exception:
        return str(resp)

def call_openai_for_reports(client, model: str, payload: dict):
    """
    Возвращает (client_report, master_report).
    Использует knowledge snippets + insight table.
    """
    table = build_insight_table(payload)
    snippets = get_knowledge_snippets(payload, top_k=6)

    # Важно: в клиентском отчёте НЕ называем камни.
    sys = (
        "Ты — эксперт по диагностике потенциалов (СПЧ/NEO). "
        "Пиши по-русски. Без воды. Не повторяй ответы клиента. "
        "Опирайся на: (1) таблицу инсайтов, (2) фрагменты методики из knowledge. "
        "Если чего-то не хватает — формулируй как гипотезу.\n\n"
        "СДЕЛАЙ 2 ТЕКСТА:\n"
        "A) CLIENT_REPORT (250–450 слов):\n"
        "- 3 НЕОЧЕВИДНЫХ инсайта (что человек про себя не видит)\n"
        "- 1 ключевой конфликт/узкое горлышко\n"
        "- 2 сценария: если включает нужный формат / если избегает\n"
        "- 3 конкретных эксперимента на 7 дней (измеримые)\n"
        "- мягкий CTA: 'полный отчёт + разбор'\n"
        "Важно: НЕ упоминай названия потенциалов/камней.\n\n"
        "B) MASTER_REPORT (структурно, 400–900 слов):\n"
        "- топ-гипотезы по потенциалам (можно камни)\n"
        "- позиции/смещения (если видишь) + риск зоны\n"
        "- что уточнить: 5 вопросов\n"
        "- рекомендации по реализации/монетизации/формату деятельности\n"
        "Пиши так, чтобы мастер мог сразу провести консультацию."
    )

    user_payload = {
        "insight_table": table,
        "knowledge_snippets": snippets,
        "raw_scores": payload.get("scores", {}),
        "raw_vectors_hint": vectors_without_labels(payload.get("scores", {})),
    }

    # 1) Пробуем Responses API (без response_format, чтобы не падало на разных версиях sdk)
    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
            ],
        )
        text = _extract_text_from_openai(resp)
    except Exception:
        # 2) Fallback: ChatCompletions
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}
            ],
            temperature=0.4,
        )
        text = _extract_text_from_openai(resp)

    # Парсим два блока по маркерам
    client_report = ""
    master_report = ""

    # ожидаем, что модель напишет "CLIENT_REPORT:" и "MASTER_REPORT:"
    t = text.strip()
    # мягкий разбор
    if "CLIENT_REPORT" in t and "MASTER_REPORT" in t:
        # разбиваем
        parts = re.split(r"MASTER_REPORT\s*:\s*", t, maxsplit=1)
        left = parts[0]
        right = parts[1] if len(parts) > 1 else ""
        client_report = re.sub(r".*CLIENT_REPORT\s*:\s*", "", left, flags=re.S).strip()
        master_report = right.strip()
    else:
        # если маркеров нет — всё в мастер, а клиентский пустой (не ломаем UI)
        master_report = t

    return client_report, master_report, table, snippets

# app.py — PART 3/3
# MAIN UI + MASTER PANEL
# =========================

def session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"

def save_session(payload: dict):
    sid = payload["meta"]["session_id"]
    p = session_path(sid)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def list_sessions():
    out = []
    for p in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out

def build_payload_from_state():
    answers = st.session_state.get("answers", {})
    event_log = st.session_state.get("event_log", [])
    scores, evidence = score_all(answers)

    name = str(answers.get("intake.ask_name", "") or "").strip()
    request = str(answers.get("intake.ask_request", "") or "").strip()
    contact = str(answers.get("intake.contact", "") or "").strip()

    return {
        "meta": {
            "schema": "ai-neo.master_report.v7",
            "app_version": APP_VERSION,
            "timestamp": utcnow_iso(),
            "session_id": st.session_state.get("session_id", ""),
            "name": name,
            "request": request,
            "contact": contact,
            "question_count": len(question_plan()),
            "answered_count": len(event_log),
        },
        "answers": answers,
        "scores": scores,
        "evidence": evidence,
        "event_log": event_log,
        "ai_client_report": st.session_state.get("ai_report_text", ""),
        "ai_master_report": st.session_state.get("ai_report_master_text", ""),
    }

def top_potentials(scores: dict, n=3):
    items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return [(p, v) for p, v in items[:n] if v > 0]

def build_client_mini_report(payload: dict) -> str:
    """
    Клиентский мини-отчет:
    - без названий камней
    - сильные стороны (векторно)
    - что наполняет / что сливает
    - 3 шага на 7 дней
    """
    answers = payload.get("answers", {})
    scores = payload.get("scores", {})

    # векторные "направления" (без названий потенциалов)
    vectors = []
    if scores.get("Аметист", 0) >= 1.2:
        vectors.append("стратегия и управление (цели, план, направление)")
    if scores.get("Цитрин", 0) >= 1.2:
        vectors.append("результат и деньги (скорость, эффективность, выгода)")
    if scores.get("Гелиодор", 0) >= 1.2:
        vectors.append("обучение и систематизация знаний (разбор, объяснение)")
    if scores.get("Сапфир", 0) >= 1.1:
        vectors.append("смысл и глубина (почему так, идеи, концепции)")
    if scores.get("Гранат", 0) >= 1.1:
        vectors.append("люди и связь (объединение, поддержка, отношения)")
    if scores.get("Изумруд", 0) >= 1.1:
        vectors.append("эстетика и атмосфера (красота, уют, стиль)")
    if scores.get("Рубин", 0) >= 1.1:
        vectors.append("проявленность и эмоции (сцена, впечатления)")
    if scores.get("Шунгит", 0) >= 1.1:
        vectors.append("тело и энергия (движение, тонус)")
    if scores.get("Янтарь", 0) >= 1.4:
        vectors.append("структура и процессы (порядок, регламенты, система)")

    energy_fill = answers.get("now.energy_fill", [])
    if not isinstance(energy_fill, list):
        energy_fill = [str(energy_fill)]

    leak = str(answers.get("antipattern.energy_leak", "") or "").strip()
    request = str(answers.get("intake.ask_request", "") or "").strip()
    goal = str(answers.get("intake.goal_3m", "") or "").strip()

    v_text = "\n".join([f"- {v}" for v in vectors]) if vectors else "- пока мало данных — нужен полный разбор"

    txt = f"""
**Коротко по твоему вектору (предварительно):**
{v_text}

**Твой запрос:** {request if request else "—"}
**Что хочешь через 3 месяца:** {goal if goal else "—"}

**Что тебя наполняет:**
{chr(10).join([f"- {x}" for x in energy_fill if str(x).strip()]) if energy_fill else "- —"}

**Где сейчас уходит энергия:**
{leak if leak else "—"}

**3 шага на ближайшие 7 дней:**
1) Выбери *одну* тему, где ты хочешь результат (деньги/дело/отношения/энергия) и зафиксируй “что считается результатом”.
2) Сделай 1 маленькое действие в день (10–20 минут), которое напрямую двигает к результату.
3) В конце недели: выпиши 3 вещи, которые дали энергию, и 3 вещи, которые забрали — это ключ к твоей личной системе.

Если хочешь **полный разбор** (с реализацией и денежным каналом) — мастер может собрать отчёт по твоей сессии и отправить на контакт, который ты оставил(а).
"""
    return txt.strip()

# --------- AI REPORTS (MASTER) ---------
def call_openai_reports(payload: dict, model: str):
    client = get_openai_client()
    if client is None:
        raise RuntimeError("OPENAI_API_KEY не задан (добавь в secrets или env)")

    model = safe_model_name(model)

    # очень компактный вход, чтобы не ловить ошибки/лимиты
    data = {
        "meta": payload.get("meta", {}),
        "answers": payload.get("answers", {}),
        "scores": payload.get("scores", {}),
        "evidence": payload.get("evidence", {}),
    }

    system = (
        "Ты мастер-диагност потенциалов. "
        "Сформируй ДВА текста:\n"
        "1) client_report: 12-18 строк, НЕ называй потенциалы/камни. "
        "Дай сильные стороны, что наполняет, где слив, 3 шага на 7 дней, мягкий CTA на полный разбор.\n"
        "2) master_report: можно называть потенциалы. "
        "Дай гипотезу по топ-3, позиции (силы/энергия/слабости) если видно, противоречия, 5 уточняющих вопросов, и рекомендации по реализации.\n"
        "Ответ верни строго JSON: {\"client_report\":\"...\",\"master_report\":\"...\"}"
    )

    resp = client.responses.create(
        model=model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}
        ],
    )

    raw = getattr(resp, "output_text", None)
    if not raw:
        # fallback (на случай иной структуры)
        raw = resp.output[0].content[0].text

    obj = json.loads(raw)
    return obj.get("client_report", ""), obj.get("master_report", "")

# --------- MASTER PANEL UI ---------
def render_master_panel():
    st.subheader("🛠️ Мастер-панель")

    if not MASTER_PASSWORD:
        st.warning("MASTER_PASSWORD не задан. Добавь в `.streamlit/secrets.toml` или переменную окружения.")
        return

    if not st.session_state.get("master_authed", False):
        pwd = st.text_input("Пароль мастера", type="password")
        if st.button("Войти"):
            if pwd == MASTER_PASSWORD:
                st.session_state["master_authed"] = True
                st.success("Доступ открыт ✅")
                st.rerun()
            else:
                st.error("Неверный пароль")
        return

    st.caption("Здесь видно все сессии. Клиент это не видит без пароля.")

    sessions = list_sessions()
    if not sessions:
        st.info("Пока нет сохранённых сессий (пройди диагностику хотя бы один раз).")
        return

    # список сессий
    options = []
    index_map = {}
    for i, s in enumerate(sessions):
        meta = s.get("meta", {})
        sid = meta.get("session_id", "—")
        name = meta.get("name", "—") or "—"
        ts = meta.get("timestamp", "—")
        req = meta.get("request", "—")
        label = f"{name} | {req} | {ts} | {sid[:8]}"
        options.append(label)
        index_map[label] = sid

    chosen = st.selectbox("Сессии:", options)
    chosen_sid = index_map.get(chosen)

    # загрузим выбранную
    chosen_payload = None
    if chosen_sid:
        p = session_path(chosen_sid)
        if p.exists():
            chosen_payload = json.loads(p.read_text(encoding="utf-8"))

    if not chosen_payload:
        st.error("Не удалось загрузить выбранную сессию.")
        return

    meta = chosen_payload.get("meta", {})
    st.markdown(f"**Имя:** {meta.get('name','—')}")
    st.markdown(f"**Контакт:** {meta.get('contact','—')}")
    st.markdown(f"**Запрос:** {meta.get('request','—')}")
    st.markdown(f"**Вопросов:** {meta.get('answered_count','—')}")

    # скачать JSON
    st.download_button(
        "⬇️ Скачать JSON сессии",
        data=json.dumps(chosen_payload, ensure_ascii=False, indent=2),
        file_name=f"session_{meta.get('session_id','')[:8]}.json",
        mime="application/json"
    )

    st.divider()

    # AI генерация отчёта
    st.markdown("### 🧠 AI-отчёт (для мастера)")
    model = st.text_input("Модель", value=DEFAULT_MODEL, help="Если gpt-5 недоступен, используй gpt-4.1-mini")

    if st.button("Сгенерировать AI-отчёт"):
        try:
            client_report, master_report = call_openai_reports(chosen_payload, model=model)
            # сохраняем в payload и на диск
            chosen_payload["ai_client_report"] = client_report
            chosen_payload["ai_master_report"] = master_report
            save_session(chosen_payload)

            st.success("AI-отчёты сгенерированы и сохранены ✅")
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка генерации: {e}")

    if chosen_payload.get("ai_client_report"):
        st.markdown("#### Клиентский AI-отчёт")
        st.write(chosen_payload["ai_client_report"])

    if chosen_payload.get("ai_master_report"):
        st.markdown("#### Мастерский AI-отчёт")
        st.write(chosen_payload["ai_master_report"])

    with st.expander("Показать транскрипт (event_log)"):
        st.json(chosen_payload.get("event_log", []))

# --------- CLIENT UI ---------
def render_client_flow():
    plan = question_plan()
    total = len(plan)

    # прогресс
    q_index = st.session_state.get("q_index", 0)
    done = q_index >= total

    # безопасный stage для caption (чтобы не падало в мастер панели)
    if total > 0:
        safe_idx = min(q_index, total - 1)
        stage = plan[safe_idx].get("stage", "—")
    else:
        stage = "—"

    st.caption(f"Ход: вопрос {min(q_index + 1, total)} из {total} | фаза: {stage}")

    if st.button("🔄 Сбросить диагностику"):
        reset_diagnostic()
        st.rerun()

    if not done:
        q = plan[q_index]

        # КЛЮЧЕВОЕ: чтобы текст НЕ переносился — делаем уникальные ключи на каждый вопрос
        # и при переходе чистим прошлые ключи.
        qid = q["id"]
        key_base = f"ans_{st.session_state['session_id']}_{qid}"

        # Рендер
        st.markdown(f"### {q['text']}")
        st.caption("Коротко и по делу. 1–5 предложений — достаточно.")

        ans = None
        if q["type"] == "single":
            ans = st.radio("Выбери один:", q.get("options", []), key=key_base)
        elif q["type"] == "multi":
            ans = st.multiselect("Выбери 1–4:", q.get("options", []), key=key_base)
        else:
            ans = st.text_area("Ответ:", height=150, key=key_base)

        c1, c2 = st.columns([1, 1])

        with c1:
            if st.button("Далее ➜", use_container_width=True):
                if not is_nonempty(q, ans):
                    st.warning("Заполни ответ.")
                else:
                    st.session_state["answers"][qid] = ans
                    st.session_state["event_log"].append({
                        "timestamp": utcnow_iso(),
                        "question_id": qid,
                        "question_text": q["text"],
                        "answer_type": q["type"],
                        "answer": ans
                    })
                    st.session_state["q_index"] += 1
                    st.rerun()

        with c2:
            if st.button("Завершить сейчас", use_container_width=True):
                # сохраняем то, что есть
                payload = build_payload_from_state()
                save_session(payload)
                st.session_state["q_index"] = total
                st.rerun()

    else:
        # финал: сохранить и показать мини-отчет
        payload = build_payload_from_state()
        try:
            save_session(payload)
        except Exception:
            pass

        st.success("Диагностика завершена ✅")

        st.markdown("## Мини-отчёт (предварительно)")
        st.write(build_client_mini_report(payload))

        # минимальная проверка — без сырого лога мастера
        with st.expander("Показать мои ответы (для проверки)"):
            st.json(payload.get("answers", {}))

# =========================
# MAIN
# =========================
# ВАЖНО: эти функции должны быть в части 2:
# - init_state()
# - reset_diagnostic()
# - is_nonempty(q, ans)
init_state()

st.title("💠 NEO Диагностика потенциалов (MVP)")

tab1, tab2 = st.tabs(["🧑‍💼 Клиент", "🛠️ Мастер"])

with tab1:
    render_client_flow()

with tab2:
    render_master_panel()