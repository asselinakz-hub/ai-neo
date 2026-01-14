# app.py
import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

# =========================
# MUST BE FIRST Streamlit call
# =========================
st.set_page_config(
    page_title="NEO Диагностика потенциалов (MVP)",
    page_icon="💠",
    layout="centered",
)

# =========================
# Paths / Storage
# =========================
DATA_DIR = Path("data")
SESSIONS_DIR = DATA_DIR / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

APP_VERSION = "mvp-7.0"

# =========================
# Secrets / Env
# =========================
MASTER_PASSWORD = st.secrets.get("MASTER_PASSWORD", os.getenv("MASTER_PASSWORD", ""))

OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY", ""))
DEFAULT_MODEL = st.secrets.get("OPENAI_MODEL", os.getenv("OPENAI_MODEL", "gpt-4.1-mini"))

# =========================
# OpenAI helper
# =========================
def get_openai_client():
    if not OPENAI_API_KEY:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=OPENAI_API_KEY)
    except Exception:
        return None

def safe_model_name(model: str) -> str:
    # Важно: gpt-5.2-thinking — это имя из ChatGPT, в API может не быть доступа → 404
    if not model:
        return DEFAULT_MODEL
    m = model.strip()
    if m.startswith("gpt-5"):
        return DEFAULT_MODEL
    return m

# =========================
# Utility
# =========================
def utcnow_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def session_path(session_id: str) -> Path:
    return SESSIONS_DIR / f"{session_id}.json"

def save_session(payload: dict):
    sid = payload["meta"]["session_id"]
    p = session_path(sid)
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

def load_session(sid: str):
    p = session_path(sid)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

def list_sessions():
    out = []
    for p in sorted(SESSIONS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out

# =========================
# Questions (30)
# =========================
def question_plan():
    return [
        # ---- intake
        {"id": "intake.ask_name", "stage": "intake", "type": "text",
         "text": "Как мне к тебе обращаться? (имя/как удобно)"},
        {"id": "intake.ask_request", "stage": "intake", "type": "text",
         "text": "С каким запросом ты пришёл(пришла) на диагностику? Что хочешь понять/изменить? (1–2 фразы)"},
        {"id": "intake.contact", "stage": "intake", "type": "text",
         "text": "Оставь телефон или email (куда мастер сможет отправить полный отчёт). Можно одно поле."},
        {"id": "intake.current_state", "stage": "intake", "type": "text",
         "text": "Если коротко: что сейчас в жизни больше всего НЕ устраивает или забирает энергию?"},
        {"id": "intake.goal_3m", "stage": "intake", "type": "text",
         "text": "Представь: прошло 3 месяца и стало лучше. Что изменилось бы в первую очередь?"},
        {"id": "intake.priority_area", "stage": "intake", "type": "single",
         "text": "Что важнее всего прояснить сегодня?",
         "options": ["Реализация/дело", "Деньги/доход", "Отношения/люди", "Энергия/силы", "Смысл/направление"]},

        # ---- now
        {"id": "now.easy_tasks", "stage": "now", "type": "text",
         "text": "Какие задачи тебе обычно даются легко (как будто само получается)?"},
        {"id": "now.praise_for", "stage": "now", "type": "text",
         "text": "За что тебя чаще всего хвалят люди? (1–3 пункта)"},
        {"id": "now.time_flow", "stage": "now", "type": "text",
         "text": "В какой деятельности ты теряешь счёт времени?"},
        {"id": "now.attention_first", "stage": "now", "type": "single",
         "text": "Когда попадаешь в новую ситуацию, что ты замечаешь первым?",
         "options": ["Людей/эмоции", "Смысл/идею/почему так", "Деньги/выгоду/ресурсы", "Риски/систему/порядок", "Красоту/атмосферу"]},
        {"id": "now.best_result_example", "stage": "now", "type": "text",
         "text": "Дай 1 конкретный пример из жизни: ситуация → что ты сделал(а) → результат (то, что у тебя получается лучше большинства)."},
        {"id": "now.motivation_trigger", "stage": "now", "type": "single",
         "text": "Что сильнее всего тебя заводит/включает?",
         "options": ["Цель/стратегия/вектор", "Люди/связь/влияние", "Красота/уют/эстетика", "Смысл/идея/глубина", "Драйв/сцена/эмоции", "Деньги/результат/скорость"]},
        {"id": "now.stress_pattern", "stage": "now", "type": "single",
         "text": "Когда стресс/давление, что происходит чаще всего?",
         "options": ["Ускоряюсь и становлюсь резкой(им)", "Ухожу в себя и молчу", "Начинаю контролировать всё", "Становлюсь эмоциональной(ым)", "Прокрастинация/замирание"]},
        {"id": "now.energy_fill", "stage": "now", "type": "multi",
         "text": "Что тебя реально наполняет (выбери 1–4)?",
         "options": ["Общение и близкие люди", "Красивые места/эстетика/уют", "Тишина/чтение/мысли",
                     "Учёба/обучение/новые знания", "Спорт/движение/тело", "Сцена/ивенты/впечатления"]},

        # ---- childhood
        {"id": "childhood.child_play", "stage": "childhood", "type": "multi",
         "text": "В детстве (примерно 6–12) что любил(а) больше всего? (1–3)",
         "options": ["Строить/организовывать/руководить", "Учиться/читать/объяснять", "Выступать/быть заметным(ой)",
                     "Дружить/общаться/мирить", "Рисовать/украшать/делать красиво", "Бегать/соревноваться/движ"]},
        {"id": "childhood.teen_dream", "stage": "childhood", "type": "text",
         "text": "Подростком (12–16) кем хотелось быть или чем заниматься?"},
        {"id": "childhood.first_success", "stage": "childhood", "type": "text",
         "text": "Какое раннее достижение/сильная сторона вспоминается первым?"},
        {"id": "childhood.family_role", "stage": "childhood", "type": "single",
         "text": "В семье/классе ты чаще был(а) кем?",
         "options": ["Лидер/организатор", "Душа компании/коммуникатор", "Умник/аналитик",
                     "Творческий/эстет", "Соревновательный/спорт", "Тихий наблюдатель"]},
        {"id": "childhood.child_aversion", "stage": "childhood", "type": "text",
         "text": "А что в детстве/школе было прям тяжело/не хотелось и ты избегал(а)? (1–2 вещи)"},
        {"id": "childhood.parent_expect", "stage": "childhood", "type": "text",
         "text": "Что от тебя ‘ожидали’ взрослые (каким(ой) надо быть)? И как ты к этому относился(лась)?"},
        {"id": "childhood.child_energy", "stage": "childhood", "type": "text",
         "text": "Где ты чувствовал(а) себя ‘живым(ой)’ в детстве сильнее всего? (ситуация)"},
        {"id": "childhood.child_pride", "stage": "childhood", "type": "text",
         "text": "За что ты собой в детстве реально гордился(лась)? (1 пример)"},

        # ---- behavior
        {"id": "behavior.free_time", "stage": "behavior", "type": "text",
         "text": "Если есть свободные 2 часа без обязательств — что ты чаще всего делаешь?"},
        {"id": "behavior.money_spend", "stage": "behavior", "type": "multi",
         "text": "На что ты импульсивно тратишь деньги/силы? (1–3)",
         "options": ["На обучение/курсы/информацию", "На проекты/инструменты/работу", "На красоту/одежду/дом/уют",
                     "На людей/подарки/семью", "На путешествия/впечатления", "На здоровье/спорт"]},
        {"id": "behavior.group_role_now", "stage": "behavior", "type": "single",
         "text": "В группе/команде ты обычно кто?",
         "options": ["Объединяю людей", "Продавливаю результат", "Придумываю смысл/идею",
                     "Структурирую/порядок", "Делаю красиво/атмосферу", "Вдохновляю/зажигаю"]},
        {"id": "behavior.decision_style", "stage": "behavior", "type": "single",
         "text": "Как ты принимаешь решения чаще всего?",
         "options": ["Через выгоду/цифры", "Через чувство/интуицию", "Через смысл/ценности",
                     "Через людей/отношения", "Через порядок/правила"]},
        {"id": "behavior.long_focus", "stage": "behavior", "type": "text",
         "text": "На что ты можешь удерживать внимание долго и без насилия над собой?"},
        {"id": "behavior.fast_win", "stage": "behavior", "type": "text",
         "text": "Что ты умеешь делать быстро и качественно, когда надо ‘собраться и сделать’? (1–3 примера)"},
        {"id": "behavior.teach_people", "stage": "behavior", "type": "text",
         "text": "Если бы ты учил(а) людей одному навыку, который у тебя сильный — что это было бы?"},

        # ---- antipattern
        {"id": "antipattern.avoid", "stage": "antipattern", "type": "text",
         "text": "Какие задачи ты стабильно откладываешь (и прямо внутренне сопротивляешься)?"},
        {"id": "antipattern.hate_task", "stage": "antipattern", "type": "single",
         "text": "Что для тебя самое ‘нелюбимое’ из списка?",
         "options": ["Рутина/порядок/регламенты", "Долгие разговоры ни о чём", "Продажи/заявлять о себе",
                     "Учёба/зубрёжка", "Физическая нагрузка", "Конфликты/напряжение"]},
        {"id": "antipattern.energy_leak", "stage": "antipattern", "type": "text",
         "text": "Где ты сильнее всего ‘сливаешь’ энергию сейчас? (люди/дела/мысли/тело/хаос/контроль — как у тебя)"},
    ]

# =========================
# Scoring (lightweight)
# =========================
POTS = ["Янтарь","Шунгит","Цитрин","Изумруд","Рубин","Гранат","Сапфир","Гелиодор","Аметист"]

KEYWORDS = {
    "Янтарь": ["порядок","структур","регламент","документ","система","учет","процесс","таблиц"],
    "Шунгит": ["тело","спорт","движ","вынослив","трен","физкульт"],
    "Цитрин": ["деньг","доход","результат","быстро","выгода","цифр","эффектив","продаж","прибыл"],
    "Изумруд": ["красот","эстет","уют","дизайн","атмосфер","стиль","гармони"],
    "Рубин": ["драйв","сцена","ивент","впечат","приключ","эмоц","адренал","публич"],
    "Гранат": ["люд","команд","общен","поддерж","забот","отношен","объедин","душа компании"],
    "Сапфир": ["смысл","идея","почему","глубин","философ","концепц","как устроено","ценност"],
    "Гелиодор": ["уч","обуч","знан","курс","объясн","настав","разбор","учиться","грант"],
    "Аметист": ["цель","стратег","вектор","управлен","лидер","координац","проект","план"],
}

def text_hits(text: str, pot: str) -> int:
    t = (text or "").lower()
    return sum(1 for kw in KEYWORDS.get(pot, []) if kw in t)

def score_all(answers: dict):
    scores = {p: 0.0 for p in POTS}
    evidence = {p: [] for p in POTS}

    def add(p, v, note):
        scores[p] += float(v)
        evidence[p].append(note)

    # keyword scoring
    for qid, ans in answers.items():
        if isinstance(ans, list):
            joined = " ".join([str(x) for x in ans])
            for p in POTS:
                h = text_hits(joined, p)
                if h:
                    add(p, 0.25 * h, f"{qid}: kw({p})")
        else:
            txt = str(ans or "")
            for p in POTS:
                h = text_hits(txt, p)
                if h:
                    add(p, 0.35 * h, f"{qid}: kw({p})")

    # option bumps
    def bump_if(qid, mapping, amount=0.9):
        a = answers.get(qid)
        if not a:
            return
        if isinstance(a, list):
            for x in a:
                p = mapping.get(x)
                if p:
                    add(p, amount / max(1, len(a)), f"{qid}: option→{p}")
        else:
            p = mapping.get(a)
            if p:
                add(p, amount, f"{qid}: option→{p}")

    bump_if("intake.priority_area", {
        "Реализация/дело":"Аметист",
        "Деньги/доход":"Цитрин",
        "Отношения/люди":"Гранат",
        "Энергия/силы":"Шунгит",
        "Смысл/направление":"Сапфир",
    }, amount=0.8)

    bump_if("now.attention_first", {
        "Людей/эмоции":"Гранат",
        "Смысл/идею/почему так":"Сапфир",
        "Деньги/выгоду/ресурсы":"Цитрин",
        "Риски/систему/порядок":"Янтарь",
        "Красоту/атмосферу":"Изумруд",
    }, amount=1.0)

    bump_if("now.motivation_trigger", {
        "Цель/стратегия/вектор":"Аметист",
        "Люди/связь/влияние":"Гранат",
        "Красота/уют/эстетика":"Изумруд",
        "Смысл/идея/глубина":"Сапфир",
        "Драйв/сцена/эмоции":"Рубин",
        "Деньги/результат/скорость":"Цитрин",
    }, amount=1.0)

    bump_if("now.energy_fill", {
        "Общение и близкие люди":"Гранат",
        "Красивые места/эстетика/уют":"Изумруд",
        "Тишина/чтение/мысли":"Сапфир",
        "Учёба/обучение/новые знания":"Гелиодор",
        "Спорт/движение/тело":"Шунгит",
        "Сцена/ивенты/впечатления":"Рубин",
    }, amount=0.9)

    bump_if("childhood.child_play", {
        "Строить/организовывать/руководить":"Аметист",
        "Учиться/читать/объяснять":"Гелиодор",
        "Выступать/быть заметным(ой)":"Рубин",
        "Дружить/общаться/мирить":"Гранат",
        "Рисовать/украшать/делать красиво":"Изумруд",
        "Бегать/соревноваться/движ":"Шунгит",
    }, amount=0.8)

    bump_if("childhood.family_role", {
        "Лидер/организатор":"Аметист",
        "Душа компании/коммуникатор":"Гранат",
        "Умник/аналитик":"Сапфир",
        "Творческий/эстет":"Изумруд",
        "Соревновательный/спорт":"Шунгит",
        "Тихий наблюдатель":"Сапфир",
    }, amount=0.7)

    bump_if("behavior.group_role_now", {
        "Объединяю людей":"Гранат",
        "Продавливаю результат":"Цитрин",
        "Придумываю смысл/идею":"Сапфир",
        "Структурирую/порядок":"Янтарь",
        "Делаю красиво/атмосферу":"Изумруд",
        "Вдохновляю/зажигаю":"Рубин",
    }, amount=0.8)

    bump_if("behavior.decision_style", {
        "Через выгоду/цифры":"Цитрин",
        "Через чувство/интуицию":"Гранат",
        "Через смысл/ценности":"Сапфир",
        "Через людей/отношения":"Гранат",
        "Через порядок/правила":"Янтарь",
    }, amount=0.8)

    bump_if("behavior.money_spend", {
        "На обучение/курсы/информацию":"Гелиодор",
        "На проекты/инструменты/работу":"Аметист",
        "На красоту/одежду/дом/уют":"Изумруд",
        "На людей/подарки/семью":"Гранат",
        "На путешествия/впечатления":"Рубин",
        "На здоровье/спорт":"Шунгит",
    }, amount=0.7)

    # anti-amber: если человек НЕНАВИДИТ рутины — не лепим Янтарь в топ
    hate = str(answers.get("antipattern.hate_task", "") or "").lower()
    if "рутина/порядок/регламенты" in hate:
        scores["Янтарь"] = max(0.0, scores["Янтарь"] - 0.8)
        evidence["Янтарь"].append("antipattern.hate_task: dislike routines → снижено")

    return scores, evidence

def vectors_without_labels(scores: dict):
    v = []
    if scores.get("Цитрин",0) >= 1.2: v.append("результат и деньги (скорость, эффективность, выгода)")
    if scores.get("Аметист",0) >= 1.2: v.append("стратегирование и управление (цели, план, направление)")
    if scores.get("Гелиодор",0) >= 1.2: v.append("знания и обучение (разбор, объяснение, развитие)")
    if scores.get("Сапфир",0) >= 1.1: v.append("смысл и глубина (почему так, концепции, идеи)")
    if scores.get("Гранат",0) >= 1.1: v.append("люди и связь (поддержка, объединение, отношения)")
    if scores.get("Изумруд",0) >= 1.1: v.append("эстетика и атмосфера (красота, уют, стиль)")
    if scores.get("Рубин",0) >= 1.1: v.append("сцена и эмоции (впечатления, проявленность)")
    if scores.get("Шунгит",0) >= 1.1: v.append("тело и энергия (движение, выносливость)")
    if scores.get("Янтарь",0) >= 1.4: v.append("структура и система (порядок, регламенты, процессы)")
    return v[:6]

# =========================
# State
# =========================
def init_state():
    st.session_state.setdefault("session_id", str(uuid.uuid4()))
    st.session_state.setdefault("q_index", 0)
    st.session_state.setdefault("answers", {})
    st.session_state.setdefault("event_log", [])
    st.session_state.setdefault("master_authed", False)

    # UI temp: чтобы ответ НЕ переносился на следующий вопрос
    st.session_state.setdefault("tmp_text", "")
    st.session_state.setdefault("tmp_single", None)
    st.session_state.setdefault("tmp_multi", [])

def reset_diagnostic():
    st.session_state["session_id"] = str(uuid.uuid4())
    st.session_state["q_index"] = 0
    st.session_state["answers"] = {}
    st.session_state["event_log"] = []

    st.session_state["tmp_text"] = ""
    st.session_state["tmp_single"] = None
    st.session_state["tmp_multi"] = []

def build_payload(answers: dict, event_log: list, session_id: str):
    scores, evidence = score_all(answers)
    meta = {
        "schema": "ai-neo.master_report.v7",
        "app_version": APP_VERSION,
        "timestamp": utcnow_iso(),
        "session_id": session_id,
        "name": str(answers.get("intake.ask_name","") or "").strip(),
        "request": str(answers.get("intake.ask_request","") or "").strip(),
        "contact": str(answers.get("intake.contact","") or "").strip(),
        "question_count": len(question_plan()),
        "answered_count": len(event_log),
    }
    return {
        "meta": meta,
        "answers": answers,
        "scores": scores,
        "evidence": evidence,
        "event_log": event_log,
    }

# =========================
# Render Question
# =========================
def render_question(q):
    st.markdown(f"### {q['text']}")
    st.caption("Отвечай коротко и конкретно. Можно 1–5 предложений.")

    qtype = q["type"]
    options = q.get("options", [])

    if qtype == "single":
        # если options пустые — fallback на text
        if not options:
            return st.text_input("Ответ:", value=st.session_state["tmp_text"])
        # контролируем tmp_single
        default_index = 0
        if st.session_state["tmp_single"] in options:
            default_index = options.index(st.session_state["tmp_single"])
        choice = st.radio("Выбери один вариант:", options, index=default_index)
        return choice

    if qtype == "multi":
        if not options:
            return st.text_area("Ответ:", height=120, value=st.session_state["tmp_text"])
        selected = st.multiselect(
            "Выбери 1–4:",
            options,
            default=st.session_state["tmp_multi"] if isinstance(st.session_state["tmp_multi"], list) else []
        )
        return selected

    # text
    return st.text_area("Ответ:", height=140, value=st.session_state["tmp_text"])

def is_nonempty(q, ans):
    if q["type"] == "multi":
        return isinstance(ans, list) and len(ans) > 0
    return bool(str(ans or "").strip())

# =========================
# Client mini report (no labels)
# =========================
def build_client_mini_report(payload: dict) -> str:
    a = payload["answers"]
    scores = payload["scores"]
    vectors = vectors_without_labels(scores)

    name = payload["meta"].get("name") or "тебя"
    req = payload["meta"].get("request") or "самореализация"
    goal = a.get("intake.goal_3m", "—")
    leak = a.get("antipattern.energy_leak", "—")
    fill = a.get("now.energy_fill", [])
    if isinstance(fill, list):
        fill_txt = ", ".join(fill)
    else:
        fill_txt = str(fill or "—")

    strong = []
    if a.get("now.easy_tasks"): strong.append("ты легко видишь ход/план и думаешь на шаги вперёд")
    if a.get("now.praise_for"): strong.append("люди отмечают твою поддержку и способность вдохновлять")
    if a.get("now.best_result_example"): strong.append("ты умеешь организовать людей и довести до результата")

    # мягко продающий CTA
    cta = "Если хочешь — мастер сделает полный разбор (реализация/деньги/смещения) и даст план на 6 недель."

    lines = []
    lines.append(f"**Имя:** {name}")
    lines.append(f"**Запрос:** {req}")
    lines.append(f"**Как ты видишь результат за 3 месяца:** {goal}")
    lines.append("")
    if vectors:
        lines.append("**Твои ведущие векторы (без ярлыков):**")
        for v in vectors:
            lines.append(f"• {v}")
        lines.append("")
    if strong:
        lines.append("**Сильные стороны по твоим ответам:**")
        for s in strong[:4]:
            lines.append(f"• {s}")
        lines.append("")
    lines.append(f"**Что наполняет:** {fill_txt}")
    lines.append(f"**Что сильнее всего сливает энергию:** {leak}")
    lines.append("")
    lines.append("**3 шага на ближайшие 7 дней (минимум):**")
    lines.append("1) Выбери 1 тему/нишу и 1 продукт-черновик (что продаёшь/кому/за сколько).")
    lines.append("2) Сделай 5 коротких постов/рилсов «проблема → мысль → вывод» и 1 оффер.")
    lines.append("3) Один созвон/интервью с человеком из ЦА: что болит, за что готовы платить.")
    lines.append("")
    lines.append(f"**Следующий шаг:** {cta}")
    return "\n".join(lines)

# =========================
# AI report generation (master panel)
# =========================
def build_ai_payload(payload: dict) -> dict:
    meta = payload.get("meta", {})
    answers = payload.get("answers", {})
    scores = payload.get("scores", {})
    vectors = vectors_without_labels(scores)

    important_keys = [
        "intake.ask_request",
        "intake.current_state",
        "intake.goal_3m",
        "intake.priority_area",
        "now.easy_tasks",
        "now.praise_for",
        "now.best_result_example",
        "now.energy_fill",
        "behavior.group_role_now",
        "behavior.decision_style",
        "antipattern.hate_task",
        "antipattern.energy_leak",
    ]
    excerpt = {k: answers.get(k) for k in important_keys if k in answers}

    return {
        "meta": meta,
        "vectors_no_labels": vectors,
        "scores_hint": scores,     # мастеру можно
        "answers_excerpt": excerpt
    }

def call_openai_reports(model: str, data: dict):
    client = get_openai_client()
    if client is None:
        return None, None, "OpenAI API key не настроен (OPENAI_API_KEY)."

    model = safe_model_name(model)

    sys = (
        "Ты — эксперт по диагностике потенциалов.\n"
        "Сгенерируй JSON с двумя полями: client_report и master_report.\n"
        "client_report: 12–18 строк, без названий камней, векторно, конкретно: сильные стороны, что наполняет, что сливает, 3 шага на 7 дней + CTA.\n"
        "master_report: структурно и честно: ТОП-3 камня (гипотеза) + аргументы; возможные смещения/конфликты; 5 уточняющих вопросов; рекомендации по реализации/монетизации.\n"
        "Пиши по-русски. Без воды. Не упоминай, что ты ИИ."
    )

    try:
        resp = client.responses.create(
            model=model,
            input=[
                {"role": "system", "content": sys},
                {"role": "user", "content": json.dumps(data, ensure_ascii=False)}
            ],
            response_format={"type": "json_object"},
        )

        # надежно достаем текст ответа
        out_text = ""
        try:
            out_text = resp.output_text
        except Exception:
            # fallback
            try:
                out_text = resp.output[0].content[0].text
            except Exception:
                out_text = ""

        if not out_text:
            return None, None, "Пустой ответ от модели."

        obj = json.loads(out_text)
        return obj.get("client_report", ""), obj.get("master_report", ""), None

    except Exception as e:
        return None, None, f"Ошибка OpenAI: {e}"

# =========================
# MASTER PANEL AUTH
# =========================
def render_master_panel():
    st.subheader("🔐 Мастер-панель")

    if not st.session_state.get("master_authed", False):
        if not MASTER_PASSWORD:
            st.error("MASTER_PASSWORD не задан. Добавь в secrets или env.")
            return

        pwd = st.text_input("Пароль мастера", type="password")
        if st.button("Войти в мастер-панель"):
            if pwd == MASTER_PASSWORD:
                st.session_state["master_authed"] = True
                st.success("Ок, доступ открыт.")
                st.rerun()
            else:
                st.error("Неверный пароль.")
        return

    # внутри мастер-панели
    sessions = list_sessions()
    if not sessions:
        st.info("Пока нет сохранённых сессий.")
        return

    # список
    labels = []
    sid_map = {}
    for s in sessions:
        m = s.get("meta", {})
        sid = m.get("session_id", "—")
        nm = (m.get("name") or "—").strip()
        req = (m.get("request") or "—").strip()
        ts = m.get("timestamp", "")
        label = f"{ts} | {nm} | {req} | {sid[:8]}"
        labels.append(label)
        sid_map[label] = sid

    choice = st.selectbox("Выбери сессию:", labels)
    sid = sid_map.get(choice)

    sdata = load_session(sid)
    if not sdata:
        st.error("Не удалось загрузить сессию.")
        return

    meta = sdata.get("meta", {})
    st.markdown("**Карточка клиента:**")
    st.write({
        "name": meta.get("name"),
        "request": meta.get("request"),
        "contact": meta.get("contact"),
        "timestamp": meta.get("timestamp"),
        "session_id": meta.get("session_id"),
        "answered_count": meta.get("answered_count"),
    })

    st.download_button(
        "⬇️ Скачать JSON (сессия)",
        data=json.dumps(sdata, ensure_ascii=False, indent=2),
        file_name=f"{meta.get('session_id','session')}.json",
        mime="application/json",
    )

    st.divider()
    st.markdown("### 🤖 AI-отчёт (из мастер-панели)")

    model_input = st.text_input("Модель (оставь как есть)", value=DEFAULT_MODEL)

    if st.button("Сгенерировать AI-отчёт"):
        ai_data = build_ai_payload(sdata)
        client_rep, master_rep, err = call_openai_reports(model_input, ai_data)
        if err:
            st.error(err)
        else:
            # сохраняем в сессию, чтобы не терялось
            sdata["ai_client_report"] = client_rep
            sdata["ai_master_report"] = master_rep
            save_session(sdata)
            st.success("Готово. Отчёты сохранены в сессию.")

    # показать сохраненные
    if sdata.get("ai_client_report"):
        st.markdown("**Client report (для клиента):**")
        st.text_area("", value=sdata["ai_client_report"], height=240)

    if sdata.get("ai_master_report"):
        st.markdown("**Master report (внутренний):**")
        st.text_area("", value=sdata["ai_master_report"], height=320)

    with st.expander("Показать ответы (для проверки)"):
        st.json(sdata.get("answers", {}))

# =========================
# MAIN UI
# =========================
init_state()

st.title("NEO Диагностика потенциалов (MVP)")

tab1, tab2 = st.tabs(["🧑‍💼 Клиент", "🛠️ Мастер"])

with tab1:
    plan = question_plan()
    total = len(plan)

    # определяем done по индексу, а не по “флагу”, чтобы не застревало на “завершено”
    done = st.session_state["q_index"] >= total

    colA, colB = st.columns([1, 1])
    with colA: 
        st.caption(f"Ход: вопрос {min(st.session_state['q_index']+1, total)} из {total} | "
            f"фаза: {plan[min(st.session_state['q_index'], total-1)]['stage'] if total else '—'}"
        )

    with colB:
        if st.button("🔄 Сбросить диагностику"):
            reset_diagnostic()
            st.rerun()

    if not done:
        q = plan[st.session_state["q_index"]]

        # очищаем временные поля при переходе на новый вопрос
        idx_key = f"_last_q_index_{st.session_state['session_id']}"
        if st.session_state.get(idx_key) != st.session_state["q_index"]:
            st.session_state[idx_key] = st.session_state["q_index"]
            st.session_state["tmp_text"] = ""
            st.session_state["tmp_single"] = None
            st.session_state["tmp_multi"] = []

        ans = render_question(q)

        # синхроним tmp значения (чтобы не переносилось и было стабильно при rerun)
        if q["type"] == "single":
            st.session_state["tmp_single"] = ans
        elif q["type"] == "multi":
            st.session_state["tmp_multi"] = ans
        else:
            st.session_state["tmp_text"] = ans

        c1, c2 = st.columns([1, 1])
        with c1:
            if st.button("Далее ➜", use_container_width=True):
                if not is_nonempty(q, ans):
                    st.warning("Заполни ответ.")
                else:
                    # сохраняем ответ
                    st.session_state["answers"][q["id"]] = ans
                    st.session_state["event_log"].append({
                        "timestamp": utcnow_iso(),
                        "question_id": q["id"],
                        "question_text": q["text"],
                        "answer_type": q["type"],
                        "answer": ans
                    })

                    st.session_state["q_index"] += 1

                    # если дошли до конца — сохраняем сессию
                    if st.session_state["q_index"] >= total:
                        payload = build_payload(
                            st.session_state["answers"],
                            st.session_state["event_log"],
                            st.session_state["session_id"]
                        )
                        save_session(payload)

                    st.rerun()

        with c2:
            if st.button("Завершить сейчас", use_container_width=True):
                # сохраняем то, что уже есть
                payload = build_payload(
                    st.session_state["answers"],
                    st.session_state["event_log"],
                    st.session_state["session_id"]
                )
                save_session(payload)

                # форсируем конец
                st.session_state["q_index"] = total
                st.rerun()

    else:
        # финальный экран
        payload = build_payload(
            st.session_state["answers"],
            st.session_state["event_log"],
            st.session_state["session_id"]
        )

        # на всякий случай — ещё раз сохранить
        try:
            save_session(payload)
        except Exception:
            pass

        st.success("Диагностика завершена ✅")
        st.markdown("## Мини-отчёт (предварительный)")
        st.markdown(build_client_mini_report(payload))

        with st.expander("Показать мои ответы (для проверки)"):
            st.json(payload.get("answers", {}))

with tab2:
    render_master_panel()
