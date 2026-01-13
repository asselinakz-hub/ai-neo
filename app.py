# app.py — ai-neo (Streamlit) vNext (TOP-3 per position + reasons)
# ✅ Клиент: Топ-3 overall + Позиции 1–3 (ТОП-1) без сырого лога
# ✅ Мастер (PIN): Матрица 1–9, В КАЖДОЙ ПОЗИЦИИ показываем TOP-3 + "почему" (по evidence)
# ✅ Фиксы: не залипает, поля очищаются, лишнее скрыто от клиента

import json
from datetime import datetime
import streamlit as st

# -----------------------------
# CONFIG
# -----------------------------
APP_TITLE = "NEO Диагностика (MVP)"
MASTER_PIN_DEFAULT = "1234"  # лучше задать в secrets: MASTER_PIN
MAX_QUESTIONS_DEFAULT = 30

POTENTIALS = [
    "Янтарь", "Шунгит", "Цитрин",
    "Изумруд", "Рубин", "Гранат",
    "Сапфир", "Гелиодор", "Аметист"
]

ROWS = {"row1": "СИЛЫ", "row2": "ЭНЕРГИЯ", "row3": "СЛАБОСТИ"}
COLS = {"col1": "ВОСПРИЯТИЕ", "col2": "МОТИВАЦИЯ", "col3": "ИНСТРУМЕНТ"}

KEYWORDS = {
    "Янтарь": ["порядок", "структур", "система", "организац", "регламент", "детал", "схем", "документ", "процесс"],
    "Шунгит": ["движ", "спорт", "тело", "рук", "физ", "вынослив", "качалк", "актив"],
    "Цитрин": ["деньг", "результ", "быстр", "эффектив", "выгод", "цифр", "сделк", "доход", "оптим"],
    "Изумруд": ["красот", "уют", "гармон", "эстет", "дизайн", "стиль", "атмосфер", "вкус"],
    "Рубин": ["драйв", "адренал", "эмоц", "сцена", "путешеств", "новые места", "перезагруз", "трансформац"],
    "Гранат": ["люд", "команд", "общен", "близк", "семь", "забот", "поддерж", "отношен", "гости"],
    "Сапфир": ["смысл", "иде", "почему", "философ", "глубин", "мировоззр", "концепц"],
    "Гелиодор": ["знан", "уч", "обуч", "объясн", "настав", "курс", "развит", "учиться", "преподав"],
    "Аметист": ["цель", "стратег", "план", "управ", "лидер", "координац", "вектор", "проект"]
}

SHIFT_TRIGGERS = ["надо", "должен", "должна", "ради семьи", "так принято", "некогда", "вынужден", "обязан"]

# -----------------------------
# QUESTIONS (гибрид)
# -----------------------------
QUESTION_FLOW = [
    {"id": "intake.ask_name", "type": "text", "label": "Как мне к тебе обращаться? (имя/как удобно)"},
    {"id": "intake.ask_request", "type": "text", "label": "С каким запросом ты пришёл(пришла) на диагностику? Что хочешь понять/изменить? (1–2 фразы)"},
    {"id": "intake.current_state", "type": "text", "label": "Если коротко: что сейчас в жизни больше всего НЕ устраивает или забирает энергию?"},
    {"id": "intake.goal_3m", "type": "text", "label": "Представь: прошло 3 месяца и стало лучше. Что изменилось бы в первую очередь?"},
    {"id": "intake.priority_area", "type": "single", "label": "Что важнее всего прояснить сегодня?",
     "options": ["Деньги/реализация", "Отношения", "Здоровье/энергия", "Смысл/направление", "Смешанное"]},

    {"id": "now.easy_tasks", "type": "text", "label": "Какие задачи тебе обычно даются легко (как будто само получается)?"},
    {"id": "now.praise_for", "type": "text", "label": "За что тебя чаще всего хвалят люди? (1–3 пункта)"},
    {"id": "now.time_flow", "type": "text", "label": "В какой деятельности ты теряешь счёт времени?"},
    {"id": "now.attention_first", "type": "single", "label": "Когда попадаешь в новую ситуацию, что ты замечаешь первым?",
     "options": ["Порядок/структуру/детали", "Людей/отношения/настроение", "Деньги/выгоду/результат", "Красоту/атмосферу",
                 "Смысл/идею/почему так", "Цели/стратегию/куда идём", "Другое (напишу)"]},
    {"id": "now.attention_first_other", "type": "text_optional", "label": "Если выбрал(а) 'Другое' — что именно?"},
    {"id": "now.best_result_example", "type": "text", "label": "Дай 1 конкретный пример из жизни: ситуация → что ты сделал(а) → результат (то, что у тебя получается лучше большинства)."},
    {"id": "now.motivation_trigger", "type": "single", "label": "Что сильнее всего тебя заводит/включает?",
     "options": ["Драйв/сцена/эмоции", "Цель/стратегия/вектор", "Деньги/выгода/результат", "Знания/обучение/рост",
                 "Люди/команда/родство", "Красота/уют/гармония", "Тело/движение/спорт", "Порядок/система/структура"]},
    {"id": "now.stress_pattern", "type": "single", "label": "Когда стресс/давление, что происходит чаще всего?",
     "options": ["Ускоряюсь и становлюсь резкой(им)", "Ухожу в тишину/анализ", "Начинаю всё контролировать и структурировать",
                 "Ищу поддержку у людей", "Срываюсь эмоционально", "Застываю/прокрастинация", "Падаю в тело/движение"]},
    {"id": "now.energy_fill", "type": "multi", "label": "Что тебя реально наполняет (выбери 1–3)?",
     "options": ["Красивые места/эстетика/уют", "Тишина/чтение/мысли", "Общение и близкие люди",
                 "Драйв/новые места/приключения", "Планирование/цели/стратегии", "Спорт/движение/тело",
                 "Деньги/сделки/результат", "Порядок/организация/система", "Учёба/обучение/новые знания"]},

    {"id": "childhood.child_play", "type": "multi", "label": "В детстве (примерно 6–12) что любил(а) больше всего? (1–4 варианта)",
     "options": ["Выступать/быть заметным(ой)", "Организовывать/командовать", "Строить/собирать/конструкторы", "Рисовать/создавать красиво",
                 "Читать/фантазировать/придумывать", "Бегать/двигаться/спорт", "Учить других/играть в школу",
                 "Играть в бизнес/деньги/магазин", "Объединять друзей/душа компании"]},
    {"id": "childhood.teen_dream", "type": "text", "label": "Подростком (12–16) кем хотелось быть или чем заниматься?"},
    {"id": "childhood.first_success", "type": "text", "label": "Какое раннее достижение/сильная сторона вспоминается первым?"},
    {"id": "childhood.family_role", "type": "single", "label": "В семье/классе ты чаще был(а) кем?",
     "options": ["Душа компании/коммуникатор", "Тихий мыслитель/наблюдатель", "Организатор/контролёр порядка", "Лидер/стратег",
                 "Творец красоты/атмосферы", "Исполнитель/делатель", "Учитель/помогал объяснять", "Добытчик/про деньги/выгоду"]},
    {"id": "childhood.child_aversion", "type": "text", "label": "А что в детстве/школе было прям тяжело/не хотелось и ты избегал(а)? (1–2 вещи)"},
    {"id": "childhood.parent_expect", "type": "text", "label": "Что от тебя ‘ожидали’ взрослые (каким(ой) надо быть)? И как ты к этому относился(лась)?"},
    {"id": "childhood.child_energy", "type": "text", "label": "Где ты чувствовал(а) себя ‘живым(ой)’ в детстве сильнее всего?"},

    {"id": "behavior.free_time", "type": "text", "label": "Если есть свободные 2 часа без обязательств — что ты чаще всего делаешь?"},
    {"id": "behavior.money_spend", "type": "multi", "label": "На что ты импульсивно тратишь деньги/силы? (1–3)",
     "options": ["На красоту/одежду/дом/уют", "На людей/подарки/семью", "На обучение/курсы/информацию",
                 "На спорт/здоровье/тело", "На путешествия/адреналин/впечатления", "На проекты/инструменты/работу",
                 "На инвест/доход/выгоду"]},
    {"id": "behavior.group_role_now", "type": "single", "label": "В группе/команде ты обычно кто?",
     "options": ["Объединяю людей", "Зажигаю/даю энергию", "Строю систему/порядок", "Даю знания/обучаю",
                 "Двигаю к результату/ускоряю", "Стратег/направление", "Спокойный исполнитель"]},
    {"id": "behavior.decision_style", "type": "single", "label": "Как ты принимаешь решения чаще всего?",
     "options": ["Через смысл/идею", "Через выгоду/цифры", "Через ощущения/эмоции", "Через структуру/правила",
                 "Через долгосрочную цель", "Через людей/совет"]},
    {"id": "behavior.long_focus", "type": "text", "label": "На что ты можешь удерживать внимание долго и без насилия над собой?"},
    {"id": "behavior.fast_win", "type": "text", "label": "Что ты умеешь делать быстро и качественно, когда надо ‘собраться и сделать’? (1–3 примера)"},

    {"id": "antipattern.avoid", "type": "text", "label": "Какие задачи ты стабильно откладываешь (и прямо внутренне сопротивляешься)?"},
    {"id": "antipattern.hate_task", "type": "single", "label": "Что для тебя самое ‘нелюбимое’ из списка?",
     "options": ["Рутина/порядок/регламенты", "Публичность/сцена/быть на виду", "Физическая нагрузка/спорт",
                 "Долгий анализ/теория", "Обучение/учиться/инструкции", "Общение/тусоваться", "Деньги/цифры/учёт", "Ничего из этого"]},
    {"id": "antipattern.energy_leak", "type": "text", "label": "Где ты сильнее всего ‘сливаешь’ энергию сейчас? (люди/дела/мысли/тело/хаос/контроль — как у тебя)"},

    {"id": "shifts.shift_1", "type": "single", "label": "Бывает ли так: результат есть, а удовольствия почти нет?",
     "options": ["Да, часто", "Иногда", "Редко", "Нет"]},
    {"id": "shifts.shift_2", "type": "single", "label": "Чаще ты делаешь ‘по внутреннему хочу’ или ‘надо/должен/ради…’?",
     "options": ["Больше ‘хочу’", "50/50", "Больше ‘надо’"]},
]


# -----------------------------
# HELPERS
# -----------------------------
def now_ts() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def normalize_text(s: str) -> str:
    return (s or "").strip().lower()


def detect_shift_risk(text: str) -> float:
    t = normalize_text(text)
    hits = sum(1 for w in SHIFT_TRIGGERS if w in t)
    return min(0.18, hits * 0.06)


def keyword_counts(text: str) -> dict:
    t = normalize_text(text)
    counts = {p: 0.0 for p in POTENTIALS}
    if not t:
        return counts
    for pot, words in KEYWORDS.items():
        for w in words:
            if w in t:
                counts[pot] += 1.0
    return counts


def add_evidence(pot: str, points: float, note: str):
    st.session_state.scores[pot] = st.session_state.scores.get(pot, 0.0) + float(points)
    st.session_state.evidence.setdefault(pot, []).append(note)


def score_answer(q: dict, answer):
    qid = q["id"]
    qtype = q["type"]

    if qtype in ("single", "multi"):
        combined = " ; ".join(answer) if isinstance(answer, list) else str(answer or "")
        counts = keyword_counts(combined)
        for pot, v in counts.items():
            if v > 0:
                add_evidence(pot, 0.35 * v, f"{qid}: «{combined}»")
        return

    if qtype in ("text", "text_optional"):
        text = str(answer or "")
        counts = keyword_counts(text)
        for pot, v in counts.items():
            if v > 0:
                add_evidence(pot, 0.25 * v, f"{qid}: {text[:120]}")

        # бонус за конкретику (пример)
        if qid == "now.best_result_example" and len(text) >= 40:
            for pot in ["Аметист", "Янтарь", "Цитрин"]:
                add_evidence(pot, 0.15, f"{qid}: бонус за конкретику")
        return


def should_ask_optional_other(qid: str) -> bool:
    if qid == "now.attention_first_other":
        return st.session_state.answers.get("now.attention_first") == "Другое (напишу)"
    return True


def current_question():
    i = st.session_state.q_index
    while i < len(QUESTION_FLOW):
        q = QUESTION_FLOW[i]
        if q.get("type") == "text_optional" and not should_ask_optional_other(q["id"]):
            i += 1
            st.session_state.q_index = i
            continue
        return q
    return None


def log_event(q: dict, answer):
    st.session_state.event_log.append({
        "timestamp": now_ts(),
        "question_id": q["id"],
        "question_text": q.get("label"),
        "answer_type": q.get("type"),
        "answer": answer,
    })


def top_potentials(scores: dict, n=3):
    return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:n]


def evidence_reasons_for(pot: str, max_items: int = 4):
    """Коротко 'почему': берем последние/самые частые evidence записи по потенциалу."""
    notes = st.session_state.evidence.get(pot, [])
    if not notes:
        return []
    # подсчёт по question_id (до двоеточия)
    freq = {}
    for n in notes:
        qid = n.split(":")[0].strip()
        freq[qid] = freq.get(qid, 0) + 1

    # сортируем qid по частоте
    top_qids = sorted(freq.items(), key=lambda x: x[1], reverse=True)[:max_items]
    chosen = []
    for qid, _ in top_qids:
        # берём 1–2 примера заметок по этому qid
        examples = [n for n in notes if n.startswith(qid + ":")][:2]
        chosen.extend(examples)
        if len(chosen) >= max_items:
            break
    return chosen[:max_items]


# ---------- FULL row/col scoring (для позиции 1–9) ----------
def full_column_scores() -> dict:
    col_scores = {c: {p: 0.0 for p in POTENTIALS} for c in COLS.values()}

    # ВОСПРИЯТИЕ
    for key in ["now.attention_first", "now.attention_first_other", "behavior.decision_style", "behavior.long_focus"]:
        val = st.session_state.answers.get(key, "")
        text = " ; ".join(val) if isinstance(val, list) else str(val or "")
        counts = keyword_counts(text)
        for p, v in counts.items():
            col_scores["ВОСПРИЯТИЕ"][p] += v

    # МОТИВАЦИЯ
    for key in ["now.motivation_trigger", "now.energy_fill", "now.time_flow", "intake.goal_3m"]:
        val = st.session_state.answers.get(key, "")
        text = " ; ".join(val) if isinstance(val, list) else str(val or "")
        counts = keyword_counts(text)
        for p, v in counts.items():
            col_scores["МОТИВАЦИЯ"][p] += v

    # ИНСТРУМЕНТ
    for key in ["now.easy_tasks", "now.praise_for", "now.best_result_example", "behavior.fast_win"]:
        val = st.session_state.answers.get(key, "")
        text = str(val or "")
        counts = keyword_counts(text)
        for p, v in counts.items():
            col_scores["ИНСТРУМЕНТ"][p] += v

    return col_scores


def full_row_scores() -> dict:
    row_scores = {r: {p: 0.0 for p in POTENTIALS} for r in ROWS.values()}

    # СИЛЫ
    for key in ["now.energy_fill", "now.time_flow", "now.easy_tasks", "behavior.free_time", "childhood.child_energy"]:
        val = st.session_state.answers.get(key, "")
        text = " ; ".join(val) if isinstance(val, list) else str(val or "")
        counts = keyword_counts(text)
        for p, v in counts.items():
            row_scores["СИЛЫ"][p] += v

    # ЭНЕРГИЯ
    for key in ["behavior.money_spend", "now.energy_fill"]:
        val = st.session_state.answers.get(key, "")
        text = " ; ".join(val) if isinstance(val, list) else str(val or "")
        counts = keyword_counts(text)
        for p, v in counts.items():
            row_scores["ЭНЕРГИЯ"][p] += v

    # СЛАБОСТИ
    for key in ["antipattern.avoid", "antipattern.hate_task", "antipattern.energy_leak", "childhood.child_aversion"]:
        val = st.session_state.answers.get(key, "")
        text = " ; ".join(val) if isinstance(val, list) else str(val or "")
        counts = keyword_counts(text)
        for p, v in counts.items():
            row_scores["СЛАБОСТИ"][p] += v

    return row_scores


def compute_positions_matrix_top3():
    """
    Возвращает:
      grid[pos] = {
        row, col,
        top3: [(pot, score), ...],
        best: pot
      }
    """
    overall = st.session_state.scores
    row_scores = full_row_scores()
    col_scores = full_column_scores()

    mapping = [
        (1, "СИЛЫ", "ВОСПРИЯТИЕ"),
        (2, "СИЛЫ", "МОТИВАЦИЯ"),
        (3, "СИЛЫ", "ИНСТРУМЕНТ"),
        (4, "ЭНЕРГИЯ", "ВОСПРИЯТИЕ"),
        (5, "ЭНЕРГИЯ", "МОТИВАЦИЯ"),
        (6, "ЭНЕРГИЯ", "ИНСТРУМЕНТ"),
        (7, "СЛАБОСТИ", "ВОСПРИЯТИЕ"),
        (8, "СЛАБОСТИ", "МОТИВАЦИЯ"),
        (9, "СЛАБОСТИ", "ИНСТРУМЕНТ"),
    ]

    grid = {}
    for pos, r, c in mapping:
        scored = []
        for p in POTENTIALS:
            cell_val = (0.55 * float(overall.get(p, 0.0))) + (0.25 * float(row_scores[r].get(p, 0.0))) + (0.20 * float(col_scores[c].get(p, 0.0)))
            scored.append((p, cell_val))
        scored.sort(key=lambda x: x[1], reverse=True)
        top3 = scored[:3]
        grid[pos] = {
            "row": r,
            "col": c,
            "top3": top3,
            "best": top3[0][0] if top3 else None
        }

    return {"grid": grid, "row_scores": row_scores, "col_scores": col_scores}


def build_client_report():
    name = st.session_state.answers.get("intake.ask_name", "—")
    request = st.session_state.answers.get("intake.ask_request", "—")
    pos_pack = compute_positions_matrix_top3()
    grid = pos_pack["grid"]
    return {
        "name": name,
        "request": request,
        "top3_overall": top_potentials(st.session_state.scores, 3),
        "pos_1_3_best": {k: grid[k]["best"] for k in [1, 2, 3]},
        "shift_risk": st.session_state.shift_risk,
    }


def export_master_json():
    pos_pack = compute_positions_matrix_top3()
    payload = {
        "meta": {
            "schema": "ai-neo.master_report.v3",
            "timestamp": now_ts(),
            "name": st.session_state.answers.get("intake.ask_name"),
            "request": st.session_state.answers.get("intake.ask_request"),
            "question_count": st.session_state.q_index,
        },
        "answers": st.session_state.answers,
        "scores": st.session_state.scores,
        "evidence": st.session_state.evidence,
        "shift_risk": st.session_state.shift_risk,
        "positions_top3": {
            str(k): {
                "row": v["row"],
                "col": v["col"],
                "top3": v["top3"],
                "best": v["best"],
            } for k, v in pos_pack["grid"].items()
        },
        "row_scores_full": pos_pack["row_scores"],
        "col_scores_full": pos_pack["col_scores"],
        "event_log": st.session_state.event_log,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# -----------------------------
# STATE
# -----------------------------
def init_state():
    st.session_state.setdefault("q_index", 0)
    st.session_state.setdefault("answers", {})
    st.session_state.setdefault("scores", {p: 0.0 for p in POTENTIALS})
    st.session_state.setdefault("evidence", {})
    st.session_state.setdefault("event_log", [])
    st.session_state.setdefault("shift_risk", 0.0)
    st.session_state.setdefault("finished", False)
    st.session_state.setdefault("input_key", 0)  # очистка text_area


# -----------------------------
# UI
# -----------------------------
st.set_page_config(page_title=APP_TITLE, page_icon="🧠", layout="centered")
st.title("🧠 NEO Диагностика потенциалов (MVP)")

init_state()

with st.sidebar:
    st.markdown("### 🔒 Панель мастера")
    pin = st.text_input("PIN", type="password", value="", placeholder="Введите PIN")
    master_pin = st.secrets.get("MASTER_PIN", MASTER_PIN_DEFAULT)
    is_master = (pin == master_pin)

    if is_master:
        st.success("Доступ мастера открыт")
        master_json = export_master_json()
        st.download_button(
            "Скачать master_report.json",
            data=master_json.encode("utf-8"),
            file_name="master_report.json",
            mime="application/json",
            use_container_width=True
        )

# -------- FINISH PAGE --------
if st.session_state.finished:
    report = build_client_report()
    st.subheader(f"Готово, {report['name']} ✅")

    st.markdown("### Топ-3 потенциала (гипотеза)")
    for i, (p, _) in enumerate(report["top3_overall"], start=1):
        st.write(f"**{i}. {p}**")

    st.markdown("### Позиции 1–3 (СИЛЫ)")
    st.write(f"**Позиция 1 (Силы × Восприятие):** {report['pos_1_3_best'][1]}")
    st.write(f"**Позиция 2 (Силы × Мотивация):** {report['pos_1_3_best'][2]}")
    st.write(f"**Позиция 3 (Силы × Инструмент):** {report['pos_1_3_best'][3]}")

    st.info("Расширенный отчет с реализацией/деньгами/планом — формирует мастер на основе твоих ответов.")

    if is_master:
        st.divider()
        st.subheader("🧩 Мастер: полная матрица 1–9 (TOP-3 в каждой позиции)")
        pos_pack = compute_positions_matrix_top3()
        grid = pos_pack["grid"]

        st.markdown("**ВОСПРИЯТИЕ | МОТИВАЦИЯ | ИНСТРУМЕНТ**")

        def cell_str(pos):
            t3 = grid[pos]["top3"]
            return " / ".join([f"{p}" for p, _ in t3])

        st.write(f"**СИЛЫ:** {cell_str(1)} | {cell_str(2)} | {cell_str(3)}")
        st.write(f"**ЭНЕРГИЯ:** {cell_str(4)} | {cell_str(5)} | {cell_str(6)}")
        st.write(f"**СЛАБОСТИ:** {cell_str(7)} | {cell_str(8)} | {cell_str(9)}")

        st.markdown("### Почему так (коротко)")
        for pos in range(1, 10):
            row = grid[pos]["row"]
            col = grid[pos]["col"]
            top3 = grid[pos]["top3"]

            with st.expander(f"Позиция {pos}: {row} × {col}"):
                for rank, (pot, score) in enumerate(top3, start=1):
                    st.write(f"**{rank}. {pot}** (cell-score: {round(score, 3)})")
                    reasons = evidence_reasons_for(pot, max_items=4)
                    if reasons:
                        for r in reasons:
                            st.write(f"- {r}")
                    else:
                        st.write("- (пока мало явных маркеров в ответах)")

        st.divider()
        st.markdown("**Overall scores:**")
        st.json(st.session_state.scores)

        st.markdown("**Shift risk:**")
        st.write(round(st.session_state.shift_risk, 3))

    if st.button("Пройти заново"):
        for k in list(st.session_state.keys()):
            del st.session_state[k]
        st.rerun()

    st.stop()

# ---- QUESTION PAGE ----
q = current_question()
if q is None:
    st.session_state.finished = True
    st.rerun()

progress = min(1.0, st.session_state.q_index / float(MAX_QUESTIONS_DEFAULT))
st.progress(progress)

st.markdown(f"### Вопрос {st.session_state.q_index + 1} из {min(len(QUESTION_FLOW), MAX_QUESTIONS_DEFAULT)}")
st.write(q["label"])

with st.form(key=f"form_{st.session_state.q_index}"):
    answer = None

    if q["type"] == "single":
        answer = st.radio(
            "Выбери один вариант:",
            q["options"],
            index=0,
            key=f"single_{st.session_state.q_index}"
        )
    elif q["type"] == "multi":
        answer = st.multiselect(
            "Выбери 1–3 варианта:",
            q["options"],
            default=[],
            key=f"multi_{st.session_state.q_index}"
        )
    elif q["type"] in ("text", "text_optional"):
        answer = st.text_area(
            "Ответ (коротко, как чувствуешь):",
            value="",
            height=110,
            key=f"text_{st.session_state.input_key}"
        )

    submitted = st.form_submit_button("Далее ➜", use_container_width=True)

if submitted:
    st.session_state.answers[q["id"]] = answer
    log_event(q, answer)

    if isinstance(answer, str):
        st.session_state.shift_risk = min(0.18, st.session_state.shift_risk + detect_shift_risk(answer))

    score_answer(q, answer)

    st.session_state.q_index += 1
    st.session_state.input_key += 1

    if st.session_state.q_index >= min(len(QUESTION_FLOW), MAX_QUESTIONS_DEFAULT):
        st.session_state.finished = True

    st.rerun()