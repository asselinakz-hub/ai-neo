# app.py
# Streamlit MVP: HYBRID диагностика (ИИ генерирует вопросы + варианты, но маршрут ведём мы)
# ✅ без банка вопросов
# ✅ без "почему-почему-почему" по кругу
# ✅ вопросы меняются по ответам, нет повторов
# ✅ в конце: клиентский мини-отчет + мастерский сырой лог

import os, json, re, time
from datetime import datetime
from typing import Dict, Any, List, Optional

import streamlit as st

# -----------------------------
# 0) БАЗОВЫЕ НАСТРОЙКИ
# -----------------------------
st.set_page_config(page_title="NEO Диагностика (Hybrid)", page_icon="🧠", layout="centered")

DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.2-mini")  # можно поменять в переменных окружения
API_KEY = os.getenv("OPENAI_API_KEY", "")

# Если у тебя openai>=1.0 установлен — используем.
# Если нет — приложение не упадёт: включится "локальный режим" (простые вопросы без ИИ).
OPENAI_AVAILABLE = True
try:
    from openai import OpenAI
    client = OpenAI(api_key=API_KEY) if API_KEY else None
except Exception:
    OPENAI_AVAILABLE = False
    client = None

# -----------------------------
# 1) СПРАВОЧНИК (минимум для скоринга)
# -----------------------------
POTENTIALS = [
    "Янтарь", "Шунгит", "Цитрин",
    "Изумруд", "Рубин", "Гранат",
    "Сапфир", "Гелиодор", "Аметист"
]

# ⚠️ Ты можешь подстроить слова под свои файлы positions/shifts позже.
KEYWORDS: Dict[str, List[str]] = {
    "Янтарь": ["порядок", "структур", "система", "организац", "регламент", "документ", "детал", "схем", "разлож"],
    "Шунгит": ["движ", "тело", "спорт", "физ", "вынослив", "прогул", "актив", "качал", "руками"],
    "Цитрин": ["деньг", "доход", "результ", "быстро", "эффектив", "оптимиз", "сделк", "продаж", "скорост"],
    "Изумруд": ["красот", "гармон", "уют", "эстет", "дизайн", "стиль", "атмосфер"],
    "Рубин": ["драйв", "адреналин", "путешеств", "новые места", "перезагруз", "эмоц", "трансформац", "приключ"],
    "Гранат": ["люди", "команд", "общен", "близк", "родств", "забот", "поддерж", "отношен"],
    "Сапфир": ["смысл", "идея", "концепц", "философ", "мировоззрен", "глубин", "ценност"],
    "Гелиодор": ["знан", "изуч", "обуч", "объясн", "настав", "курс", "развит", "учиться"],
    "Аметист": ["цель", "стратег", "управ", "лидер", "план", "координац", "проект", "вектор"]
}

SHIFT_TRIGGERS = [
    "надо", "должен", "должна", "ради семьи", "так принято", "не могу", "стыдно", "вина", "страшно"
]

# -----------------------------
# 2) УПРАВЛЕНИЕ ДИАЛОГОМ (маршрут)
# -----------------------------
STAGES = [
    "stage0_intake",     # имя + запрос + критерий успеха
    "stage1_now",        # текущая ситуация, что забирает/даёт энергию
    "stage2_behavior",   # реальное поведение: время/деньги/роль в группе/антипаттерны
    "stage3_childhood",  # детство 7–12: игры/что легко/за что хвалили
    "stage4_hypothesis", # проверка 2–3 лидирующих потенциалов (короткие проверки)
    "stage5_shifts",     # 1–2 вопроса на смещения, если есть триггеры/противоречия
    "stage6_wrap"        # мини-отчет клиенту + лог мастеру
]

# Сколько ходов на каждый этап (примерно)
STAGE_BUDGET = {
    "stage0_intake": 2,
    "stage1_now": 3,
    "stage2_behavior": 4,
    "stage3_childhood": 3,
    "stage4_hypothesis": 5,
    "stage5_shifts": 2,
    "stage6_wrap": 1
}

MAX_TURNS = 20
MAX_FOLLOWUPS_ON_SAME_TOPIC = 2


# -----------------------------
# 3) STATE
# -----------------------------
def init_state():
    st.session_state.setdefault("turn", 0)
    st.session_state.setdefault("stage", "stage0_intake")
    st.session_state.setdefault("stage_turns", {s: 0 for s in STAGES})
    st.session_state.setdefault("history", [])  # list of dict: {q, a, meta...}
    st.session_state.setdefault("asked_fingerprints", set())  # защита от повторов
    st.session_state.setdefault("profile", {"name": "", "request": "", "success": ""})
    st.session_state.setdefault("scores", {p: 0.0 for p in POTENTIALS})
    st.session_state.setdefault("evidence", {p: [] for p in POTENTIALS})
    st.session_state.setdefault("shift_flags", [])  # найденные триггеры
    st.session_state.setdefault("current_q", None)  # dict question payload from generator
    st.session_state.setdefault("topic_depth", 0)   # сколько уточнений подряд по одному смыслу
    st.session_state.setdefault("last_topic", "")


def fingerprint(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def detect_shifts_in_text(text: str) -> List[str]:
    t = (text or "").lower()
    hits = [w for w in SHIFT_TRIGGERS if w in t]
    return hits


def add_score_from_text(text: str, weight: float = 1.0, note_prefix: str = ""):
    t = (text or "").lower()
    for pot, words in KEYWORDS.items():
        if any(w in t for w in words):
            st.session_state["scores"][pot] += 0.6 * weight
            st.session_state["evidence"][pot].append(f"{note_prefix}текст→{pot}")


def add_score_from_options(selected: List[str], option_map: Dict[str, Dict[str, float]], weight: float, note_prefix: str):
    if not selected:
        return
    per = 1.0 / max(1, len(selected))
    for ans in selected:
        if ans in option_map:
            for pot, w in option_map[ans].items():
                st.session_state["scores"][pot] += float(w) * float(weight) * per
                st.session_state["evidence"][pot].append(f"{note_prefix}{ans}→{pot}")


def top_potentials(n=3) -> List[str]:
    items = sorted(st.session_state["scores"].items(), key=lambda x: x[1], reverse=True)
    return [p for p, _ in items[:n]]


def should_move_stage() -> bool:
    stage = st.session_state["stage"]
    # если бюджет этапа исчерпан — идём дальше
    if st.session_state["stage_turns"][stage] >= STAGE_BUDGET.get(stage, 3):
        return True
    return False


def next_stage(stage: str) -> str:
    idx = STAGES.index(stage)
    return STAGES[min(idx + 1, len(STAGES) - 1)]


def should_stop() -> bool:
    if st.session_state["turn"] >= MAX_TURNS:
        return True
    if st.session_state["stage"] == "stage6_wrap":
        return True
    return False


# -----------------------------
# 4) ИНТЕНТЫ (что мы хотим узнать на этом шаге)
# -----------------------------
def pick_intent() -> Dict[str, Any]:
    stage = st.session_state["stage"]
    leader = top_potentials(3)

    # базовое: на старте не лезем "в лоб" про уверенность/вдохновение
    if stage == "stage0_intake":
        intents = [
            {"id": "collect_name", "goal": "Получить имя клиента и как к нему обращаться."},
            {"id": "collect_request", "goal": "Уточнить запрос: что сейчас не так и зачем пришёл."},
            {"id": "collect_success", "goal": "Сформулировать критерий успеха: что будет считаться хорошим результатом диагностики."}
        ]
        # первые 2 хода: имя + запрос
        if not st.session_state["profile"]["name"]:
            return intents[0]
        if not st.session_state["profile"]["request"]:
            return intents[1]
        return intents[2]

    if stage == "stage1_now":
        return {"id": "now_state", "goal": "Понять текущую ситуацию: что забирает энергию, где застревание, что хочется изменить."}

    if stage == "stage2_behavior":
        # чередуем: время/деньги/роль/антипаттерны
        options = [
            {"id": "behavior_time", "goal": "Выявить реальное распределение времени (в ресурсном состоянии)."},
            {"id": "behavior_money", "goal": "Выявить импульсивные траты и приоритеты денег."},
            {"id": "behavior_role", "goal": "Уточнить естественную роль в группе/семье."},
            {"id": "behavior_avoid", "goal": "Выявить антипаттерны: что устойчиво избегает/откладывает."}
        ]
        return options[st.session_state["stage_turns"][stage] % len(options)]

    if stage == "stage3_childhood":
        options = [
            {"id": "child_play", "goal": "Детство 7–12: во что мог играть/заниматься часами."},
            {"id": "child_praise", "goal": "За что чаще хвалили и что получалось легко."},
            {"id": "child_dream", "goal": "Кем хотел стать/что тянуло в подростковом возрасте."}
        ]
        return options[st.session_state["stage_turns"][stage] % len(options)]

    if stage == "stage4_hypothesis":
        return {
            "id": "confirm_leaders",
            "goal": "Проверить гипотезы по 2–3 лидирующим потенциалам через удовольствие/поведение/контекст.",
            "leaders": leader
        }

    if stage == "stage5_shifts":
        return {"id": "shift_probe", "goal": "Проверить смещения/соц.адаптацию: 'надо/должен' vs 'хочу/заряжает'."}

    return {"id": "wrap", "goal": "Собрать мини-вывод и завершить."}


# -----------------------------
# 5) ГЕНЕРАЦИЯ ВОПРОСА (ИИ или локально)
# -----------------------------
SYSTEM_PROMPT = """Ты — NEO-диагност (мягко, точно, по делу).
Твоя задача: задавать ОДИН следующий вопрос, который логично следует из предыдущих ответов.
Формат ответа СТРОГО JSON, без текста вокруг.

Правила:
- Не повторяй уже заданные вопросы (ориентируйся на историю).
- Не задавай "почему" больше 1 раза подряд.
- Максимум 2 уточнения на одну тему — затем меняй ось (эмоция→поведение, поведение→детство, детство→текущая реальность).
- Вопросы должны ощущаться как беседа, не как анкета.
- Варианты ответов: 4–8, если тип choice. Всегда добавляй "Другое (напишу сам/сама)".
- Можно использовать типы: "text", "single", "multi".
- Если видишь противоречие/социальную адаптацию — задай уточнение МЯГКО.

JSON-схема:
{
  "id": "q_<timestamp>",
  "topic": "короткая тема (1-3 слова)",
  "type": "text|single|multi",
  "question": "текст вопроса",
  "options": ["..."] ,                 // если type single/multi
  "option_map": { "опция": {"Потенциал": число} }, // опционально
  "weight": 1.0,
  "note": "для системы: зачем этот вопрос"
}
"""

def call_llm(payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not (OPENAI_AVAILABLE and client and API_KEY):
        return None

    try:
        # Используем Responses API (openai>=1.0). Если у тебя другая версия — просто поменяешь.
        resp = client.responses.create(
            model=DEFAULT_MODEL,
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}
            ],
            response_format={"type": "json_object"}
        )
        text = resp.output_text
        data = json.loads(text)
        return data
    except Exception as e:
        st.session_state.setdefault("errors", [])
        st.session_state["errors"].append(str(e))
        return None


def local_question_fallback(intent: Dict[str, Any]) -> Dict[str, Any]:
    """Если нет ключа/модели — задаём нормальные вопросы без ИИ, чтобы приложение работало."""
    now = int(time.time())
    iid = intent["id"]

    if iid == "collect_name":
        return {"id": f"q_{now}", "topic": "имя", "type": "text",
                "question": "Как вас зовут? Как к вам обращаться?",
                "weight": 1.0, "note": "intake"}

    if iid == "collect_request":
        return {"id": f"q_{now}", "topic": "запрос", "type": "text",
                "question": "С каким запросом вы пришли? Что сейчас не так или что хочется изменить?",
                "weight": 1.0, "note": "intake"}

    if iid == "collect_success":
        return {"id": f"q_{now}", "topic": "результат", "type": "text",
                "question": "Что для вас будет хорошим результатом после диагностики? (1–2 предложения)",
                "weight": 1.0, "note": "intake"}

    if iid == "now_state":
        return {"id": f"q_{now}", "topic": "сейчас", "type": "text",
                "question": "Опишите последний месяц: что больше всего забирает энергию, и что хоть немного её возвращает?",
                "weight": 1.1, "note": "now"}

    if iid == "behavior_time":
        return {"id": f"q_{now}", "topic": "время", "type": "text",
                "question": "Если у вас внезапно появился свободный вечер, на что вы реально тратите время в первую очередь?",
                "weight": 1.1, "note": "behavior"}

    if iid == "behavior_money":
        return {"id": f"q_{now}", "topic": "деньги", "type": "text",
                "question": "На что вы охотнее тратите свободные деньги (когда не надо)? Что покупаете “для себя”?",
                "weight": 1.1, "note": "behavior"}

    if iid == "behavior_role":
        return {"id": f"q_{now}", "topic": "роль", "type": "single",
                "question": "В компании/на работе вы чаще…",
                "options": [
                    "Собираю и объединяю людей, создаю тепло",
                    "Объясняю и обучаю, доношу сложное просто",
                    "Навожу порядок, структуру, держу процессы",
                    "Делаю быстрее и результативнее, ускоряю",
                    "Даю драйв/эмоцию/заряжаю",
                    "Думаю концептуально, ищу смысл и идеи",
                    "Руковожу, задаю направление, стратегирую",
                    "Другое (напишу сам/сама)"
                ],
                "weight": 1.15, "note": "role"}

    if iid == "behavior_avoid":
        return {"id": f"q_{now}", "topic": "избегание", "type": "text",
                "question": "Какие задачи вы устойчиво откладываете или делаете через силу (даже если “надо”)?",
                "weight": 1.2, "note": "antipattern"}

    if iid == "child_play":
        return {"id": f"q_{now}", "topic": "детство", "type": "text",
                "question": "В 7–12 лет: чем вы могли заниматься часами без принуждения? Во что играли?",
                "weight": 1.2, "note": "childhood"}

    if iid == "child_praise":
        return {"id": f"q_{now}", "topic": "хвалили", "type": "text",
                "question": "За что вас чаще всего хвалили в детстве/школе? Что “само получалось”?",
                "weight": 1.2, "note": "childhood"}

    if iid == "child_dream":
        return {"id": f"q_{now}", "topic": "мечта", "type": "text",
                "question": "В подростковом возрасте: кем хотелось стать или чем тянуло заниматься? Что казалось “моим”?",
                "weight": 1.1, "note": "childhood"}

    if iid == "confirm_leaders":
        leaders = intent.get("leaders", [])[:3]
        return {"id": f"q_{now}", "topic": "проверка", "type": "text",
                "question": f"Похоже, у вас могут быть сильны: {', '.join(leaders)}. Какая из этих тем больше всего 'включает' вас — и в каких реальных ситуациях это проявляется?",
                "weight": 1.25, "note": "hypothesis"}

    if iid == "shift_probe":
        return {"id": f"q_{now}", "topic": "смещение", "type": "text",
                "question": "Где у вас чаще звучит 'надо/должен', но внутри нет энергии? И наоборот — где 'хочу', но вы себе это не разрешаете?",
                "weight": 1.25, "note": "shift"}

    return {"id": f"q_{now}", "topic": "финал", "type": "text",
            "question": "Если коротко: что вы поняли о себе за этот разговор?",
            "weight": 1.0, "note": "wrap"}


def generate_question() -> Dict[str, Any]:
    intent = pick_intent()

    # ограничитель на бесконечные уточнения
    last_topic = st.session_state["last_topic"]
    topic_depth = st.session_state["topic_depth"]
    if topic_depth >= MAX_FOLLOWUPS_ON_SAME_TOPIC and intent["id"] in ("now_state", "confirm_leaders"):
        # принудительно меняем ось на поведение/детство
        if st.session_state["stage"] in ("stage1_now", "stage4_hypothesis"):
            intent = {"id": "behavior_avoid", "goal": "Сменить ось: от эмоций к поведению."}

    payload = {
        "stage": st.session_state["stage"],
        "intent": intent,
        "profile": st.session_state["profile"],
        "top_potentials": top_potentials(3),
        "scores_snapshot": st.session_state["scores"],
        "shift_flags": st.session_state["shift_flags"],
        "recent_history": st.session_state["history"][-6:],  # последние 6 ходов
        "asked_fingerprints": list(st.session_state["asked_fingerprints"])[-25:]
    }

    q = call_llm(payload)
    if not q:
        q = local_question_fallback(intent)

    # валидация и защита от повторов
    q.setdefault("type", "text")
    q.setdefault("options", [])
    q.setdefault("option_map", {})
    q.setdefault("weight", 1.0)
    q.setdefault("topic", intent.get("id", ""))
    q.setdefault("note", intent.get("goal", ""))

    fp = fingerprint(q.get("question", ""))
    if fp in st.session_state["asked_fingerprints"]:
        # если повтор — слегка переформулируем в локальном режиме
        q = local_question_fallback(intent)

    st.session_state["asked_fingerprints"].add(fingerprint(q.get("question", "")))
    return q


# -----------------------------
# 6) ОБРАБОТКА ОТВЕТА
# -----------------------------
def apply_answer(q: Dict[str, Any], answer: Any):
    # 1) сохраняем профиль
    if st.session_state["stage"] == "stage0_intake":
        if not st.session_state["profile"]["name"]:
            st.session_state["profile"]["name"] = (answer or "").strip()
        elif not st.session_state["profile"]["request"]:
            st.session_state["profile"]["request"] = (answer or "").strip()
        elif not st.session_state["profile"]["success"]:
            st.session_state["profile"]["success"] = (answer or "").strip()

    # 2) shift flags
    if isinstance(answer, str):
        st.session_state["shift_flags"].extend(detect_shifts_in_text(answer))

    # 3) scoring
    w = float(q.get("weight", 1.0))
    option_map = q.get("option_map", {}) or {}
    if q.get("type") in ("single", "multi"):
        selected = []
        if q["type"] == "single":
            selected = [answer] if answer else []
        else:
            selected = list(answer or [])
        add_score_from_options(selected, option_map, w, note_prefix=f"{q.get('id','')}: ")
        # если есть "Другое" — просим текстом дополнить (но не сейчас)
    else:
        add_score_from_text(answer or "", weight=w, note_prefix=f"{q.get('id','')}: ")

    # 4) topic depth (от повторов)
    topic = (q.get("topic") or "").strip().lower()
    if topic and topic == st.session_state["last_topic"]:
        st.session_state["topic_depth"] += 1
    else:
        st.session_state["topic_depth"] = 0
        st.session_state["last_topic"] = topic

    # 5) лог
    st.session_state["history"].append({
        "ts": datetime.utcnow().isoformat(),
        "stage": st.session_state["stage"],
        "q": q,
        "a": answer
    })

    # 6) счетчики
    st.session_state["turn"] += 1
    st.session_state["stage_turns"][st.session_state["stage"]] += 1

    # 7) переход этапа
    if should_move_stage():
        # если в процессе накопились shift триггеры — позже включим stage5_shifts
        if st.session_state["stage"] == "stage4_hypothesis":
            if st.session_state["shift_flags"]:
                # гарантируем, что shifts пройдём
                pass
        st.session_state["stage"] = next_stage(st.session_state["stage"])


# -----------------------------
# 7) ОТЧЕТЫ
# -----------------------------
def client_report() -> str:
    name = st.session_state["profile"]["name"] or "друг"
    tops = top_potentials(3)
    # ряд/столбцы тут упрощенно: на MVP даём "3 силы" + "ресурс/риски"
    txt = []
    txt.append(f"**{name}, мини-результат диагностики (черновик):**\n")
    txt.append(f"**Ваши ведущие потенциалы (гипотеза):** {', '.join(tops)}.\n")
    txt.append("**Что это означает (очень коротко):**")
    bullets = {
        "Янтарь": "опора на порядок, систему, структуру, доведение до ясности.",
        "Шунгит": "опора на тело/движение/реальные действия, включение через физическую жизнь.",
        "Цитрин": "опора на результат, эффективность, деньги, скорость, 'сделать и получить'.",
        "Изумруд": "опора на гармонию, красоту, атмосферу, эстетический вкус.",
        "Рубин": "опора на драйв, эмоцию, перезагрузку, новые впечатления и трансформации.",
        "Гранат": "опора на людей, близость, поддержку, команду, отношения.",
        "Сапфир": "опора на смысл, идеи, глубину, мировоззрение.",
        "Гелиодор": "опора на знания, обучение, объяснение, рост компетенций.",
        "Аметист": "опора на цель, стратегию, управление, лидерство."
    }
    for p in tops:
        txt.append(f"- **{p}:** {bullets.get(p,'')}")
    txt.append("\n**Следующий шаг:** если хотите полный разбор (реализация/деньги/риски/смещения) — мастер формирует расширенный отчет в панели мастера.")
    return "\n".join(txt)


def master_dump() -> Dict[str, Any]:
    return {
        "profile": st.session_state["profile"],
        "top_potentials": top_potentials(5),
        "scores": st.session_state["scores"],
        "shift_flags": list(sorted(set(st.session_state["shift_flags"]))),
        "history": st.session_state["history"]
    }


# -----------------------------
# 8) UI
# -----------------------------
init_state()

st.title("🧠 NEO Диагностика (Hybrid MVP)")
st.caption("ИИ задаёт вопросы как мастер (в диалоге). Маршрут ведёт система. В конце — мини-отчет клиенту + лог для мастера.")

with st.expander("⚙️ Статус (для тебя)", expanded=False):
    st.write("Model:", DEFAULT_MODEL, "| OpenAI available:", OPENAI_AVAILABLE, "| API key set:", bool(API_KEY))
    st.write("Stage:", st.session_state["stage"], "| Turn:", st.session_state["turn"])
    st.write("Top:", top_potentials(3))
    if st.session_state.get("errors"):
        st.warning("Ошибки API (последняя): " + st.session_state["errors"][-1])

# если закончили
if should_stop():
    st.success("Диагностика завершена ✅")
    st.markdown(client_report())
    st.divider()
    st.subheader("🧾 Лог мастера (сырой)")
    st.json(master_dump())
    st.stop()

# генерируем вопрос, если нет текущего
if st.session_state["current_q"] is None:
    st.session_state["current_q"] = generate_question()

q = st.session_state["current_q"]

st.subheader(q.get("question", ""))
answer = None

qtype = q.get("type", "text")

if qtype == "single":
    opts = q.get("options", []) or []
    if not opts:
        qtype = "text"
    else:
        answer = st.radio("Выберите один вариант:", opts, index=0)
elif qtype == "multi":
    opts = q.get("options", []) or []
    if not opts:
        qtype = "text"
    else:
        answer = st.multiselect("Можно выбрать несколько:", opts, default=[])
if qtype == "text":
    answer = st.text_area("Ваш ответ:", height=140, placeholder="Напишите кратко и по-человечески. Можно 3–6 предложений.")

col1, col2 = st.columns([1, 1])
with col1:
    if st.button("Далее ➜", use_container_width=True):
        apply_answer(q, answer)
        st.session_state["current_q"] = None
        st.rerun()

with col2:
    if st.button("Сбросить и начать заново", use_container_width=True):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()