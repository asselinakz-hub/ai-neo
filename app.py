# app.py
# ai-neo — Client interview + Master panel + Storage + AI report generator (hybrid-ready)
# Run: streamlit run app.py

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import streamlit as st

# Optional OpenAI for master report generation
try:
    from openai import OpenAI
except Exception:
    OpenAI = None  # type: ignore


# -----------------------------
# Paths
# -----------------------------
ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "configs" / "diagnosis_config.json"

DATA_DIR = ROOT / "data"
CLIENTS_DIR = DATA_DIR / "clients"
REPORTS_DIR = DATA_DIR / "reports"

CLIENTS_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# -----------------------------
# Helpers
# -----------------------------
def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def safe_read_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def safe_write_json(path: Path, payload: Dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def normalize(s: str) -> str:
    s = (s or "").lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


# -----------------------------
# Default minimal bank (если конфиг пустой)
# -----------------------------
POTENTIALS = ["Янтарь", "Шунгит", "Цитрин", "Изумруд", "Рубин", "Гранат", "Сапфир", "Гелиодор", "Аметист"]

KEYWORDS = {
    "Янтарь": ["порядок", "структура", "система", "организация", "регламент", "инструкция", "документы", "таблица", "детали", "схема"],
    "Шунгит": ["движение", "тело", "спорт", "тренировка", "физически", "выносливость", "активность"],
    "Цитрин": ["деньги", "результат", "быстро", "эффективность", "выгода", "оптимизация", "скорость", "доход", "сделка"],
    "Изумруд": ["красота", "гармония", "уют", "эстетика", "дизайн", "стиль", "атмосфера", "красиво"],
    "Рубин": ["драйв", "сцена", "адреналин", "эмоции", "перезагрузка", "приключение", "путешествия", "новые места"],
    "Гранат": ["люди", "команда", "общение", "близкие", "семья", "забота", "поддержка", "отношения", "объединяю", "гости"],
    "Сапфир": ["смысл", "идея", "почему", "концепция", "философия", "глубина", "мировоззрение", "как устроено"],
    "Гелиодор": ["знания", "учёба", "обучение", "изучать", "объяснять", "наставник", "курс", "развитие", "учиться"],
    "Аметист": ["цель", "стратегия", "управление", "лидерство", "план", "координация", "вектор", "проект"],
}

DEFAULT_BANK: List[Dict[str, Any]] = [
    # -------- BLOCK 0: Intake (как мастер начинает) --------
    {"id": "intake.ask_name", "stage": "intake", "type": "text", "text": "Как мне к тебе обращаться? (имя/как удобно)", "weight": 1.0},
    {"id": "intake.ask_request", "stage": "intake", "type": "text", "text": "С каким запросом ты пришёл(пришла)? Что хочешь понять/изменить? (1–2 фразы)", "weight": 1.2},
    {"id": "intake.current_state", "stage": "intake", "type": "text", "text": "Если коротко: что сейчас больше всего НЕ устраивает или забирает энергию?", "weight": 1.1},
    {"id": "intake.goal_3m", "stage": "intake", "type": "text", "text": "Представь: прошло 3 месяца и стало лучше. Что изменилось бы в первую очередь?", "weight": 1.0},
    {"id": "intake.priority_area", "stage": "intake", "type": "single", "text": "Что важнее всего прояснить сегодня?",
     "options": ["Деньги/реализация", "Отношения", "Здоровье/энергия", "Смысл/путь", "Другое"], "weight": 1.0,
     "option_map": {
         "Деньги/реализация": {"Цитрин": 1.0, "Аметист": 0.7},
         "Отношения": {"Гранат": 1.0, "Рубин": 0.4},
         "Здоровье/энергия": {"Шунгит": 0.8},
         "Смысл/путь": {"Сапфир": 1.0, "Гелиодор": 0.6},
     }},
    {"id": "intake.contact", "stage": "intake", "type": "text", "text": "Контакт для отчёта (телефон/Telegram/Email). Можно пропустить.", "weight": 0.3},

    # -------- NOW (ситуация сейчас) --------
    {"id": "now.easy_tasks", "stage": "now", "type": "text", "text": "Какие задачи тебе обычно даются легко (как будто само получается)?", "weight": 1.2},
    {"id": "now.praise_for", "stage": "now", "type": "text", "text": "За что тебя чаще всего хвалят? (1–3 пункта)", "weight": 1.1},
    {"id": "now.time_flow", "stage": "now", "type": "text", "text": "В какой деятельности ты теряешь счёт времени?", "weight": 1.2},
    {"id": "now.attention_first", "stage": "now", "type": "single", "text": "Когда попадаешь в новую ситуацию, что ты замечаешь первым?",
     "options": ["Смысл/идею/почему так", "Людей/эмоции/атмосферу", "Цифры/выгоду/результат", "Порядок/структуру/что сломано", "Красоту/детали/стиль"], "weight": 1.2,
     "option_map": {
         "Смысл/идею/почему так": {"Сапфир": 1.0},
         "Людей/эмоции/атмосферу": {"Гранат": 0.9, "Рубин": 0.2},
         "Цифры/выгоду/результат": {"Цитрин": 1.0},
         "Порядок/структуру/что сломано": {"Янтарь": 1.0},
         "Красоту/детали/стиль": {"Изумруд": 1.0},
     }},
    {"id": "now.best_result_example", "stage": "now", "type": "text", "text": "Дай 1 конкретный пример: ситуация → что ты сделал(а) → результат (то, что у тебя получается лучше большинства).", "weight": 1.35},
    {"id": "now.motivation_trigger", "stage": "now", "type": "single", "text": "Что сильнее всего тебя включает?",
     "options": ["Цель/стратегия/вектор", "Деньги/результат/скорость", "Люди/общение/тёплая связь", "Сцена/драйв/эмоции", "Красота/уют/эстетика", "Знания/учёба/обучать"], "weight": 1.2,
     "option_map": {
         "Цель/стратегия/вектор": {"Аметист": 1.0},
         "Деньги/результат/скорость": {"Цитрин": 1.0},
         "Люди/общение/тёплая связь": {"Гранат": 1.0},
         "Сцена/драйв/эмоции": {"Рубин": 0.9},
         "Красота/уют/эстетика": {"Изумруд": 1.0},
         "Знания/учёба/обучать": {"Гелиодор": 1.0},
     }},
    {"id": "now.energy_fill", "stage": "now", "type": "multi", "text": "Что тебя реально наполняет (выбери 1–4)?",
     "options": ["Общение и близкие люди", "Красивые места/эстетика/уют", "Тишина/чтение/мысли", "Учёба/обучение/новые знания", "Движение/спорт/тело", "Цель/план/стратегия", "Быстрые результаты/сделал(а) и готово"],
     "weight": 1.0,
     "option_map": {
         "Общение и близкие люди": {"Гранат": 1.0},
         "Красивые места/эстетика/уют": {"Изумруд": 1.0},
         "Тишина/чтение/мысли": {"Сапфир": 0.9},
         "Учёба/обучение/новые знания": {"Гелиодор": 1.0},
         "Движение/спорт/тело": {"Шунгит": 1.0},
         "Цель/план/стратегия": {"Аметист": 1.0},
         "Быстрые результаты/сделал(а) и готово": {"Цитрин": 1.0},
     }},

    # -------- CHILDHOOD --------
    {"id": "childhood.child_play", "stage": "childhood", "type": "multi", "text": "В детстве (6–12) что любил(а) больше всего? (1–4)",
     "options": ["Выступать/быть заметным(ой)", "Организовывать людей/игры", "Учить/объяснять", "Строить/схемы/конструктор", "Рисовать/делать красиво", "Соревноваться/побеждать", "Двигаться/спорт"],
     "weight": 1.25,
     "option_map": {
         "Выступать/быть заметным(ой)": {"Рубин": 0.9},
         "Организовывать людей/игры": {"Гранат": 0.8, "Аметист": 0.3},
         "Учить/объяснять": {"Гелиодор": 1.0},
         "Строить/схемы/конструктор": {"Янтарь": 1.0},
         "Рисовать/делать красиво": {"Изумруд": 1.0},
         "Соревноваться/побеждать": {"Цитрин": 0.9},
         "Двигаться/спорт": {"Шунгит": 1.0},
     }},
    {"id": "childhood.teen_dream", "stage": "childhood", "type": "text", "text": "Подростком (12–16) кем хотелось быть/чем заниматься?", "weight": 1.1},
    {"id": "childhood.first_success", "stage": "childhood", "type": "text", "text": "Какое раннее достижение/сильная сторона вспоминается первым?", "weight": 1.1},
    {"id": "childhood.family_role", "stage": "childhood", "type": "single", "text": "В семье/классе ты чаще был(а) кем?",
     "options": ["Душа компании/коммуникатор", "Организатор/лидер", "Тихий наблюдатель/ум", "Умный объясняющий/учитель", "Эстет/создатель уюта", "Боец за результат/соревновательный"],
     "weight": 1.0,
     "option_map": {
         "Душа компании/коммуникатор": {"Гранат": 1.0},
         "Организатор/лидер": {"Аметист": 1.0},
         "Тихий наблюдатель/ум": {"Сапфир": 0.8},
         "Умный объясняющий/учитель": {"Гелиодор": 1.0},
         "Эстет/создатель уюта": {"Изумруд": 1.0},
         "Боец за результат/соревновательный": {"Цитрин": 0.9},
     }},
    {"id": "childhood.child_aversion", "stage": "childhood", "type": "text", "text": "Что в детстве/школе было тяжело/не хотелось и ты избегал(а)?", "weight": 1.0},

    # -------- BEHAVIOR --------
    {"id": "behavior.free_time", "stage": "behavior", "type": "text", "text": "Если есть свободные 2 часа — что ты чаще всего делаешь?", "weight": 1.0},
    {"id": "behavior.money_spend", "stage": "behavior", "type": "multi", "text": "На что ты импульсивно тратишь деньги/силы? (1–3)",
     "options": ["На обучение/курсы/информацию", "На людей/подарки/семью", "На красоту/дом/уют", "На спорт/здоровье/тело", "На проекты/инструменты/работу", "На путешествия/эмоции"],
     "weight": 1.1,
     "option_map": {
         "На обучение/курсы/информацию": {"Гелиодор": 1.0},
         "На людей/подарки/семью": {"Гранат": 1.0},
         "На красоту/дом/уют": {"Изумруд": 1.0},
         "На спорт/здоровье/тело": {"Шунгит": 1.0},
         "На проекты/инструменты/работу": {"Цитрин": 0.6, "Аметист": 0.4},
         "На путешествия/эмоции": {"Рубин": 1.0},
     }},
    {"id": "behavior.group_role_now", "stage": "behavior", "type": "single", "text": "В группе/команде ты обычно кто?",
     "options": ["Объединяю людей", "Даю стратегию/направление", "Ускоряю результат", "Обучаю/объясняю", "Создаю атмосферу/красоту", "Навожу порядок/структуру"],
     "weight": 1.1,
     "option_map": {
         "Объединяю людей": {"Гранат": 1.0},
         "Даю стратегию/направление": {"Аметист": 1.0},
         "Ускоряю результат": {"Цитрин": 1.0},
         "Обучаю/объясняю": {"Гелиодор": 1.0},
         "Создаю атмосферу/красоту": {"Изумруд": 1.0},
         "Навожу порядок/структуру": {"Янтарь": 1.0},
     }},
    {"id": "behavior.decision_style", "stage": "behavior", "type": "single", "text": "Как ты принимаешь решения чаще всего?",
     "options": ["Через выгоду/цифры", "Через смысл/идею", "Через людей/эмоции", "Через правила/порядок", "Через вдохновение/драйв"],
     "weight": 1.1,
     "option_map": {
         "Через выгоду/цифры": {"Цитрин": 1.0},
         "Через смысл/идею": {"Сапфир": 1.0},
         "Через людей/эмоции": {"Гранат": 0.9, "Рубин": 0.2},
         "Через правила/порядок": {"Янтарь": 1.0},
         "Через вдохновение/драйв": {"Рубин": 1.0},
     }},
    {"id": "behavior.fast_win", "stage": "behavior", "type": "text", "text": "Что ты умеешь делать быстро и качественно, когда надо ‘собраться и сделать’?", "weight": 1.0},

    # -------- ANTIPATTERN --------
    {"id": "antipattern.avoid", "stage": "antipattern", "type": "text", "text": "Какие задачи ты стабильно откладываешь (и внутренне сопротивляешься)?", "weight": 1.0},
    {"id": "antipattern.hate_task", "stage": "antipattern", "type": "single", "text": "Что для тебя самое нелюбимое?",
     "options": ["Рутина/порядок/регламенты", "Публичность/быть на виду", "Долго учиться/разбираться", "Продажи/дожим/торг", "Физнагрузка/спорт", "Чужие эмоции/конфликты"],
     "weight": 1.1,
     "option_map": {
         "Рутина/порядок/регламенты": {"Янтарь": -0.8},
         "Публичность/быть на виду": {"Рубин": -0.8},
         "Долго учиться/разбираться": {"Гелиодор": -0.8},
         "Продажи/дожим/торг": {"Цитрин": -0.8},
         "Физнагрузка/спорт": {"Шунгит": -0.8},
         "Чужие эмоции/конфликты": {"Гранат": -0.6},
     }},
    {"id": "antipattern.energy_leak", "stage": "antipattern", "type": "text", "text": "Где ты сильнее всего сливаешь энергию сейчас? (коротко)", "weight": 1.0},

    # -------- SHIFTS (2 вопроса) --------
    {"id": "shifts.shift_1", "stage": "shifts", "type": "single", "text": "Бывает ли так: результат есть, а удовольствия почти нет?",
     "options": ["Да", "Иногда", "Редко", "Почти никогда"], "weight": 1.2},
    {"id": "shifts.shift_2", "stage": "shifts", "type": "single", "text": "Есть ли ощущение, что ты часто делаешь ‘как надо’, а не ‘как хочу’?",
     "options": ["Да", "Иногда", "Редко", "Почти никогда"], "weight": 1.2},
]


STAGES = ["intake", "now", "childhood", "behavior", "antipattern", "shifts"]


def load_cfg() -> Dict[str, Any]:
    if CONFIG_PATH.exists():
        cfg = safe_read_json(CONFIG_PATH)
    else:
        cfg = {}

    cfg.setdefault("diagnosis", {})
    cfg["diagnosis"].setdefault("max_questions_total", 30)

    cfg.setdefault("matrix", {})
    cfg["matrix"].setdefault("potentials", POTENTIALS)

    cfg.setdefault("scoring", {})
    cfg["scoring"].setdefault("keywords", KEYWORDS)

    # Use question_bank from config if present, else default
    cfg.setdefault("question_bank", DEFAULT_BANK)
    return cfg


def build_order(cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    bank = cfg["question_bank"]
    maxq = int(cfg["diagnosis"].get("max_questions_total", 30))

    by_stage: Dict[str, List[Dict[str, Any]]] = {s: [] for s in STAGES}
    for q in bank:
        by_stage[q.get("stage", "now")].append(q)

    ordered: List[Dict[str, Any]] = []
    for s in STAGES:
        ordered.extend(by_stage.get(s, []))

    return ordered[:maxq]


# -----------------------------
# Session state
# -----------------------------
def init_state(cfg: Dict[str, Any]) -> None:
    st.session_state.setdefault("client_id", str(uuid.uuid4()))
    st.session_state.setdefault("q_index", 0)
    st.session_state.setdefault("answers", {})
    st.session_state.setdefault("event_log", [])
    st.session_state.setdefault("scores", {p: 0.0 for p in cfg["matrix"]["potentials"]})
    st.session_state.setdefault("evidence", {p: [] for p in cfg["matrix"]["potentials"]})
    st.session_state.setdefault("finished", False)


def reset_session(cfg: Dict[str, Any]) -> None:
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    init_state(cfg)


# -----------------------------
# Scoring
# -----------------------------
def add_score(p: str, v: float, note: str) -> None:
    st.session_state["scores"][p] = float(st.session_state["scores"].get(p, 0.0)) + float(v)
    st.session_state["evidence"].setdefault(p, []).append(note)


def keyword_hits(text: str, keywords: Dict[str, List[str]]) -> Dict[str, int]:
    t = normalize(text)
    hits: Dict[str, int] = {}
    for pot, words in keywords.items():
        c = 0
        for w in words:
            ww = w.lower()
            if ww and ww in t:
                c += 1
        if c:
            hits[pot] = c
    return hits


def apply_scoring(cfg: Dict[str, Any], q: Dict[str, Any], ans: Any) -> None:
    base_w = float(q.get("weight", 1.0))
    qid = q["id"]
    qtype = q["type"]

    option_map: Dict[str, Dict[str, float]] = q.get("option_map", {}) or {}
    keywords = cfg.get("scoring", {}).get("keywords", KEYWORDS)

    if qtype == "single":
        if isinstance(ans, str) and ans in option_map:
            for pot, w in option_map[ans].items():
                add_score(pot, base_w * float(w), f"{qid}: {ans}")

    elif qtype == "multi":
        if isinstance(ans, list) and ans:
            per = 1.0 / max(1, len(ans))
            for a in ans:
                if a in option_map:
                    for pot, w in option_map[a].items():
                        add_score(pot, base_w * float(w) * per, f"{qid}: {a}")

    elif qtype == "text":
        text = str(ans or "")
        hits = keyword_hits(text, keywords)
        for pot, cnt in hits.items():
            add_score(pot, base_w * 0.35 * min(cnt, 3), f"{qid}: текст-маркер ({cnt})")

        # bonus for concrete example
        if qid == "now.best_result_example":
            if len(normalize(text)) >= 40:
                add_score("Аметист", 0.35, f"{qid}: конкретика-бонус")
                add_score("Цитрин", 0.25, f"{qid}: конкретика-бонус")
                add_score("Янтарь", 0.15, f"{qid}: конкретика-бонус")


def log_event(q: Dict[str, Any], ans: Any) -> None:
    st.session_state["event_log"].append({
        "timestamp": utc_now(),
        "question_id": q["id"],
        "question_text": q["text"],
        "answer_type": q["type"],
        "answer": ans,
    })


# -----------------------------
# Reports
# -----------------------------
def topk(scores: Dict[str, float], k: int = 3) -> List[Tuple[str, float]]:
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:k]


def client_teaser(answers: Dict[str, Any], scores: Dict[str, float]) -> str:
    # no potential names — only plain vectors
    pot2plain = {
        "Аметист": "стратегирование и управление (цели, план, направление)",
        "Гелиодор": "знания и обучение (разбор, объяснение, развитие)",
        "Сапфир": "смысл и идеи (почему, глубина, как устроено)",
        "Гранат": "люди и связь (объединять, поддерживать, команда)",
        "Рубин": "драйв и проявленность (сцена, эмоции, публичность)",
        "Изумруд": "красота и гармония (эстетика, уют, атмосфера)",
        "Цитрин": "результат и деньги (скорость, эффективность, выгода)",
        "Янтарь": "структура и система (организация, правила, порядок)",
        "Шунгит": "тело и движение (физический ресурс, действие)",
    }

    name = (answers.get("intake.ask_name") or "Тебя").strip()
    request = (answers.get("intake.ask_request") or "").strip()
    goal = (answers.get("intake.goal_3m") or "").strip()

    lines = [f"## Мини-отчёт (черновик)\n",
             f"**Имя:** {name}"]
    if request:
        lines.append(f"**Запрос:** {request}")
    if goal:
        lines.append(f"**Как ты видишь результат за 3 месяца:** {goal}")

    lines.append("\n### Ведущие векторы (без ярлыков):")
    for pot, _ in topk(scores, 3):
        lines.append(f"- {pot2plain.get(pot, 'вектор')}")

    lines.append("\n### Что делать дальше (1-й шаг):")
    lines.append("1) Выбери 1 фокус на 14 дней и доведи до мини-результата (без распыления).")
    lines.append("2) Убери одну ‘сливающую’ активность из списка, который ты сам(а) назвал(а).")
    lines.append("3) Если хочешь разбор с реализацией и деньгами — мастер сформирует расширенный отчёт и план на 3 месяца.")
    return "\n".join(lines)


def make_payload(cfg: Dict[str, Any]) -> Dict[str, Any]:
    answers = st.session_state["answers"]
    meta = {
        "schema": "ai-neo.master_report.v4",
        "timestamp": utc_now(),
        "client_id": st.session_state["client_id"],
        "name": (answers.get("intake.ask_name") or "").strip(),
        "request": (answers.get("intake.ask_request") or "").strip(),
        "contact": (answers.get("intake.contact") or "").strip(),
        "question_count": len(st.session_state["event_log"]),
    }
    return {
        "meta": meta,
        "answers": answers,
        "scores": st.session_state["scores"],
        "evidence": st.session_state["evidence"],
        "event_log": st.session_state["event_log"],
    }


def save_client(payload: Dict[str, Any]) -> Path:
    cid = payload["meta"]["client_id"]
    path = CLIENTS_DIR / f"{cid}.json"
    safe_write_json(path, payload)
    return path


def list_clients() -> List[Path]:
    files = list(CLIENTS_DIR.glob("*.json"))
    return sorted(files, key=lambda p: p.stat().st_mtime, reverse=True)


# -----------------------------
# OpenAI report
# -----------------------------
def get_openai_client() -> Optional[Any]:
    api_key = None
    if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets:
        api_key = st.secrets["OPENAI_API_KEY"]
    if not api_key:
        api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    if OpenAI is None:
        return None
    return OpenAI(api_key=api_key)


def build_ai_prompt(session_json: Dict[str, Any]) -> str:
    return f"""
Ты — мастер диагностики NEO Потенциалов.

Сгенерируй два блока:
1) CLIENT_OFFER — “апсельный” текст для клиента: тёплый, ясный, без названий потенциалов и без баллов. Дай ощущение точности + 3–5 практических шагов на 7–14 дней. Заверши предложением купить полный отчёт + консультацию.
2) MASTER_FULL — полный отчёт для мастера: топ-3 потенциала с названиями, аргументы по ответам, риски смещений, противоречия, и 7 уточняющих вопросов на следующий шаг.

Вот данные сессии (JSON):
{json.dumps(session_json, ensure_ascii=False, indent=2)}

Формат строго:
CLIENT_OFFER:
<текст>

MASTER_FULL:
<текст>
""".strip()


def generate_ai_report(session_json: Dict[str, Any], model: str = "gpt-5.2-thinking") -> Tuple[str, str]:
    client = get_openai_client()
    if client is None:
        raise RuntimeError("Нет OPENAI_API_KEY (или openai не установлен).")

    prompt = build_ai_prompt(session_json)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "Пиши по-русски. Не придумывай факты. Опирайся на ответы."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.35,
    )
    text = resp.choices[0].message.content or ""

    # Parse blocks
    a = re.split(r"CLIENT_OFFER:\s*", text, flags=re.I)
    if len(a) < 2:
        return "", text
    rest = a[1]
    b = re.split(r"MASTER_FULL:\s*", rest, flags=re.I)
    if len(b) < 2:
        return rest.strip(), ""
    return b[0].strip(), b[1].strip()


# -----------------------------
# UI: render question
# -----------------------------
def render_question(q: Dict[str, Any]) -> Any:
    st.markdown(f"### {q['text']}")

    # IMPORTANT: each question has its own widget key -> no answer carryover
    wkey = f"ans::{st.session_state['client_id']}::{q['id']}"

    if q["type"] == "single":
        return st.radio("Выбери вариант:", q.get("options", []), key=wkey)
    if q["type"] == "multi":
        return st.multiselect("Выбери:", q.get("options", []), key=wkey)
    if q["type"] == "text":
        return st.text_area("Ответ:", height=130, key=wkey)

    st.warning("Неизвестный тип вопроса.")
    return None


# -----------------------------
# Pages
# -----------------------------
def page_client(cfg: Dict[str, Any]) -> None:
    st.subheader("Диагностика (клиент)")

    ordered = build_order(cfg)
    total = len(ordered)
    idx = int(st.session_state["q_index"])

    if st.session_state["finished"]:
        st.success("Диагностика завершена ✅")

        payload = make_payload(cfg)
        saved = save_client(payload)

        # Client teaser (no potential names)
        st.markdown(client_teaser(st.session_state["answers"], st.session_state["scores"]))

        st.download_button(
            "Скачать JSON (для мастера)",
            data=json.dumps(payload, ensure_ascii=False, indent=2),
            file_name=f"{payload['meta']['client_id']}.json",
            mime="application/json",
            use_container_width=True,
        )
        st.caption(f"Сохранено: {saved.name}")

        if st.button("Начать новую диагностику", use_container_width=True):
            reset_session(cfg)
            st.rerun()
        return

    # progress
    if total > 0:
        st.progress(min(1.0, idx / total))
        st.caption(f"Вопрос {min(idx+1,total)} из {total}")

    if idx >= total:
        st.session_state["finished"] = True
        st.rerun()
        return

    q = ordered[idx]
    ans = render_question(q)

    col1, col2 = st.columns([1, 1])
    with col1:
        next_btn = st.button("Далее ➜", type="primary", use_container_width=True)
    with col2:
        stop_btn = st.button("Завершить сейчас", use_container_width=True)

    if next_btn:
        st.session_state["answers"][q["id"]] = ans
        apply_scoring(cfg, q, ans)
        log_event(q, ans)
        st.session_state["q_index"] += 1
        st.rerun()

    if stop_btn:
        st.session_state["finished"] = True
        st.rerun()


def page_master(cfg: Dict[str, Any]) -> None:
    st.subheader("Мастер панель")

    files = list_clients()
    if not files:
        st.info("Пока нет сохранённых клиентов. Пройди диагностику в вкладке ‘Клиент’ — и записи появятся здесь.")
        return

    # Build list labels
    labels = []
    map_label_to_path: Dict[str, Path] = {}
    for p in files:
        data = safe_read_json(p)
        meta = data.get("meta", {})
        label = f"{meta.get('timestamp','')} | {meta.get('name','(без имени)')} | {meta.get('request','')}".strip()
        labels.append(label)
        map_label_to_path[label] = p

    chosen = st.selectbox("Список клиентов:", labels)
    path = map_label_to_path[chosen]
    session_json = safe_read_json(path)
    meta = session_json.get("meta", {})
    cid = meta.get("client_id", path.stem)

    # Card
    st.markdown("### Карточка клиента")
    st.write({
        "client_id": cid,
        "name": meta.get("name", ""),
        "request": meta.get("request", ""),
        "contact": meta.get("contact", ""),
        "timestamp": meta.get("timestamp", ""),
        "question_count": meta.get("question_count", ""),
    })

    st.download_button(
        "Скачать JSON (транскрипт)",
        data=json.dumps(session_json, ensure_ascii=False, indent=2),
        file_name=f"{cid}.json",
        mime="application/json",
        use_container_width=True,
    )

    st.divider()
    st.markdown("### AI-отчёт (быстрый текст для клиента + полный для мастера)")

    model = st.text_input("Модель (оставь как есть)", value="gpt-5.2-thinking")

    colA, colB = st.columns([1, 1])
    with colA:
        gen = st.button("Сгенерировать AI-отчёт", type="primary", use_container_width=True)
    with colB:
        ok = get_openai_client() is not None
        st.caption("OpenAI подключён ✅" if ok else "OpenAI не подключён (нужен OPENAI_API_KEY)")

    if gen:
        try:
            with st.spinner("Генерирую..."):
                client_offer, master_full = generate_ai_report(session_json, model=model)

            report_path = REPORTS_DIR / f"{cid}.md"
            content = f"# CLIENT_OFFER\n\n{client_offer}\n\n---\n\n# MASTER_FULL\n\n{master_full}\n"
            report_path.write_text(content, encoding="utf-8")

            st.success("Готово ✅")

            st.markdown("#### CLIENT_OFFER (можно отправить клиенту)")
            st.markdown(client_offer)

            st.markdown("#### MASTER_FULL (внутренний)")
            st.markdown(master_full)

            st.download_button(
                "Скачать отчёт (MD)",
                data=content,
                file_name=f"{cid}.md",
                mime="text/markdown",
                use_container_width=True,
            )

        except Exception as e:
            st.error(f"Ошибка: {e}")

    # По умолчанию НЕ показываем сырой лог (чтобы не было мусора)
    with st.expander("Показать ответы (для проверки)"):
        st.json(session_json.get("answers", {}))


def main() -> None:
    st.set_page_config(page_title="ai-neo", page_icon="🧠", layout="centered")

    cfg = load_cfg()
    init_state(cfg)

    tabs = st.tabs(["👤 Клиент", "🧩 Мастер"])
    with tabs[0]:
        page_client(cfg)
    with tabs[1]:
        page_master(cfg)


if __name__ == "__main__":
    main()