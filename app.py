# app.py
import streamlit as st
import json
import os
import uuid
from pathlib import Path
from datetime import datetime, timezone

# -----------------------------
# Config
# -----------------------------
CONFIG_PATH = "configs/diagnosis_config.json"
SESSIONS_DIR = Path("data/sessions")
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

POTENTIALS = ["Янтарь","Шунгит","Цитрин","Изумруд","Рубин","Гранат","Сапфир","Гелиодор","Аметист"]

# -----------------------------
# Helpers
# -----------------------------
def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def load_cfg(path=CONFIG_PATH):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def safe_text(x):
    if x is None:
        return ""
    if isinstance(x, (list, dict)):
        return json.dumps(x, ensure_ascii=False)
    return str(x)
    
def get_any(answers: dict, keys: list, default=""):
    for k in keys:
        v = answers.get(k)
        if v is None:
            continue
        s = safe_text(v).strip()
        if s and s != "[]":
            return v
    return default
    
def session_new_id():
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

def save_session(payload: dict) -> Path:
    sid = payload.get("meta", {}).get("session_id") or session_new_id()
    payload.setdefault("meta", {})
    payload["meta"]["session_id"] = sid
    out = SESSIONS_DIR / f"{sid}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return out

def list_sessions():
    if not SESSIONS_DIR.exists():
        return []
    files = sorted(SESSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    items = []
    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            meta = data.get("meta", {})
            items.append({
                "path": p,
                "session_id": meta.get("session_id", p.stem),
                "timestamp": meta.get("timestamp", ""),
                "name": meta.get("name", ""),
                "request": meta.get("request", ""),
                "phone": meta.get("phone", ""),
                "email": meta.get("email", ""),
                "question_count": meta.get("question_count", ""),
            })
        except Exception:
            continue
    return items

def try_get_secret(key: str, default=None):
    try:
        return st.secrets.get(key, default)
    except Exception:
        return os.environ.get(key, default)

# -----------------------------
# Scoring (MVP)
# -----------------------------
def init_state(cfg):
    st.session_state.setdefault("asked", [])
    st.session_state.setdefault("answers", {})        # qid -> answer
    st.session_state.setdefault("event_log", [])      # list of dict
    st.session_state.setdefault("scores", {p: 0.0 for p in POTENTIALS})
    st.session_state.setdefault("evidence", {p: [] for p in POTENTIALS})
    st.session_state.setdefault("turn", 0)
    st.session_state.setdefault("current_qid", None)
    st.session_state.setdefault("done", False)

    # meta fields
    st.session_state.setdefault("client_name", "")
    st.session_state.setdefault("client_request", "")
    st.session_state.setdefault("client_phone", "")
    st.session_state.setdefault("client_email", "")
    st.session_state.setdefault("session_id", session_new_id())

def add_score(p, val, note):
    st.session_state["scores"][p] = float(st.session_state["scores"].get(p, 0.0)) + float(val)
    st.session_state["evidence"].setdefault(p, []).append(note)

def keyword_hits(text: str, keywords: dict):
    t = (text or "").lower()
    hits = {p: 0 for p in POTENTIALS}
    for p, words in keywords.items():
        for w in words:
            if w.lower() in t:
                hits[p] += 1
    return hits

def apply_scoring(question, answer, cfg):
    """
    Uses:
      - question.option_map (option-> {potential: weight})
      - cfg.mapping.options_to_potentials keywords
      - cfg.scoring.question_weights (if present)
    """
    qid = question.get("id", "")
    qtext = question.get("text", "")
    qtype = question.get("type", "text")
    base_w = float(question.get("weight", 1.0))

    # option_map scoring
    option_map = question.get("option_map", {})
    if qtype == "single" and isinstance(answer, str):
        if answer in option_map:
            for pot, w in option_map[answer].items():
                add_score(pot, base_w * float(w), f"{qid}: {answer}")
    elif qtype == "multi" and isinstance(answer, list) and len(answer) > 0:
        per = 1.0 / len(answer)
        for a in answer:
            if a in option_map:
                for pot, w in option_map[a].items():
                    add_score(pot, base_w * float(w) * per, f"{qid}: {a}")

    # text keywords scoring (soft)
    keywords = cfg.get("mapping", {}).get("options_to_potentials", {})
    if qtype == "text":
        hits = keyword_hits(safe_text(answer), keywords)
        for pot, cnt in hits.items():
            if cnt > 0:
                # мягкий буст за конкретику
                add_score(pot, base_w * (0.20 + 0.10 * min(cnt, 3)), f"{qid}: текстовые маркеры ({cnt})")

    # antipattern penalty
    tags = set(question.get("tags", []))
    if "antipattern" in tags:
        # если ответ явно про "не люблю/не хочу/рутина/регламенты" — штраф к Янтарю и частично к Цитрину
        t = safe_text(answer).lower()
        if any(x in t for x in ["рутина", "регламент", "порядок", "документы", "бумаги", "система", "структур"]):
            add_score("Янтарь", -0.45 * base_w, f"{qid}: антипаттерн штраф (янтарь)")
        if any(x in t for x in ["цифры", "финансы", "учёт", "таблиц", "отчёт"]):
            add_score("Цитрин", -0.20 * base_w, f"{qid}: антипаттерн штраф (цитрин)")

def pick_next_question(cfg):
    bank = cfg.get("question_bank", [])
    asked = set(st.session_state["asked"])
    # строго: следующий не заданный по порядку (чтобы не прыгало и не повторялось)
    for q in bank:
        if q.get("id") not in asked:
            return q
    return None

def record_event(question, answer):
    st.session_state["event_log"].append({
        "timestamp": now_iso(),
        "question_id": question.get("id"),
        "question_text": question.get("text"),
        "answer_type": question.get("type"),
        "answer": answer
    })

def should_stop(cfg):
    max_q = int(cfg.get("diagnosis", {}).get("hard_stop_at_questions", 30) or 30)
    if st.session_state["turn"] >= max_q:
        return True
    # если вопросов в банке закончились
    if st.session_state["current_qid"] is None:
        q = pick_next_question(cfg)
        if q is None:
            return True
    return False

# -----------------------------
# Report (client + master)
# -----------------------------
def top_potentials(scores: dict, n=3):
    items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    return items[:n]

def infer_vectors(answers: dict, scores: dict):
    """
    Возвращает словесный вектор без названий потенциалов.
    """
    # смысл/идея -> смысловой вектор
    att = answers.get("now.attention_first", "")
    want = safe_text(answers.get("intake.priority_area", "")).lower()
    flow = safe_text(answers.get("now.time_flow", "")).lower()
    easy = safe_text(answers.get("now.easy_tasks", "")).lower()
    energy_fill = answers.get("now.energy_fill", [])

    vectors = []

    if "смысл" in safe_text(att).lower() or "почему" in safe_text(att).lower():
        vectors.append("Смысловой вектор: ты видишь идею/суть и ищешь «почему так устроено».")

    if any(k in easy for k in ["план", "стратег", "вектор", "координ", "управлен"]):
        vectors.append("Стратегический вектор: сильна способность видеть маршрут и собирать людей/задачи в план.")

    if any(k in flow for k in ["продукт", "как устроен", "система", "план", "стратег"]):
        vectors.append("Конструкторский вектор: нравится «собирать» продукт/систему и продумывать устройство.")

    if "деньги" in want or "реализац" in want:
        vectors.append("Результативный вектор: важна монетизация и ощущение «это приносит результат».")

    if isinstance(energy_fill, list) and any("люди" in x.lower() for x in energy_fill):
        vectors.append("Социальный вектор: энергия приходит через людей, близость, объединение.")

    if isinstance(energy_fill, list) and any("красив" in x.lower() or "уют" in x.lower() for x in energy_fill):
        vectors.append("Эстетический вектор: подпитывает красота, атмосфера, «сделать красиво».")

    # коротко: если пусто, fallback
    if not vectors:
        vectors.append("Вектор пока не до конца проявился — нужно больше фактов/примеров, но уже видно стремление к смыслу и реализации.")

    return vectors[:5]

def client_mini_report(answers: dict, scores: dict):
    name = answers.get("intake.ask_name", "тебя")
    req  = safe_text(answers.get("intake.ask_request", "")).strip()
    state = safe_text(answers.get("intake.current_state", "")).strip()
    goal  = safe_text(answers.get("intake.goal_3m", "")).strip()

    vectors = infer_vectors(answers, scores)
    fills = answers.get("now.energy_fill", [])
    fills_txt = ""
    if isinstance(fills, list) and fills:
        fills_txt = " • " + "\n • ".join(fills)

    # next steps (без потенциалов)
    next_steps = [
        "Сформулируй одну конкретную гипотезу реализации на 14 дней (одна тема/один продукт/один формат).",
        "Выбери 1 метрику результата (например: 10 коротких публикаций/2 созвона/1 прототип).",
        "Запланируй 3 «энерго-слота» в неделю (красота/тишина/люди — из твоего списка).",
    ]

    # риск «слива энергии»
    leak = safe_text(answers.get("antipattern.energy_leak", "")).lower()
    leak_note = ""
    if leak:
        leak_note = "Триггер выгорания у тебя связан с ощущением «впустую» и «без смысла/результата». Поэтому тебе критично заранее ставить критерий полезности задачи: *что должно измениться после этого действия?*"

    return f"""
### Мини-отчёт (предварительный)

**{name}**, запрос: **{req or "самореализация"}**  
Что сейчас забирает энергию: *{state or "—"}*  
Ожидаемый сдвиг за 3 месяца: *{goal or "—"}*

#### Твой текущий вектор (без ярлыков)
{chr(10).join([f"- {v}" for v in vectors])}

#### Что тебя наполняет (это важно держать в системе)
{fills_txt if fills_txt else "Пока не отмечено."}

#### 3 шага, которые дадут движение уже на этой неделе
- {next_steps[0]}
- {next_steps[1]}
- {next_steps[2]}

#### Важное наблюдение
{leak_note or "—"}

> Это предварительная картина по ответам. Полный разбор (с глубокой реализацией и денежной стратегией) делает мастер на основе твоего транскрипта.
""".strip()

def master_full_report_template(payload: dict):
    """
    Шаблонный мастер-отчет (если нет AI ключа).
    """
    answers = payload.get("answers", {})
    scores = payload.get("scores", {})
    top = top_potentials(scores, 5)

    lines = []
    lines.append("# Мастер-отчёт (шаблон)")
    lines.append("")
    lines.append(f"Имя: {answers.get('intake.ask_name','')}")
    lines.append(f"Запрос: {answers.get('intake.ask_request','')}")
    lines.append("")
    lines.append("## Топ-гипотезы (по скорингу)")
    for p, s in top:
        lines.append(f"- {p}: {round(s, 3)}")
    lines.append("")
    lines.append("## Ключевые цитаты клиента")
    for k in ["now.easy_tasks","now.time_flow","now.best_result_example","antipattern.energy_leak","childhood.first_success"]:
        if k in answers and safe_text(answers[k]).strip():
            lines.append(f"- **{k}**: {safe_text(answers[k])}")
    lines.append("")
    lines.append("## Риски/смещения (гипотезы)")
    lines.append("- Проверить, нет ли «надо/должен» и ориентации на ожидания вместо истинного выбора.")
    lines.append("- Проверить, есть ли разрыв: результат есть, удовольствия нет.")
    lines.append("")
    lines.append("## Рекомендованные уточнения мастера (5–7 минут)")
    lines.append("1) Где ты реально получаешь удовольствие, даже если никто не видит?")
    lines.append("2) Какие задачи ты делаешь ради результата, но они тебя опустошают?")
    lines.append("3) Если убрать деньги и оценку — что ты бы делал(а) как деятельность?")
    lines.append("")
    return "\n".join(lines)

def ai_generate_master_report(payload: dict):
    """
    Если есть OPENAI_API_KEY, можно подключить реальную AI-генерацию.
    Если ключа нет — вернем шаблон.
    """
    api_key = try_get_secret("OPENAI_API_KEY", None)
    if not api_key:
        return master_full_report_template(payload), False

    # Безопасно: если библиотека openai не установлена — тоже fallback
    try:
        from openai import OpenAI
    except Exception:
        return master_full_report_template(payload), False

    client = OpenAI(api_key=api_key)

    # Сжимаем payload (без мусора)
    compact = {
        "meta": payload.get("meta", {}),
        "answers": payload.get("answers", {}),
        "scores": payload.get("scores", {}),
        "evidence": payload.get("evidence", {}),
        "shift_risk": payload.get("shift_risk", None),
    }

    system = """Ты — ассистент мастера по диагностике NEO Потенциалов.
Задача: по транскрипту и скорингу сформировать МАСТЕР-ОТЧЕТ: гипотезы, подтверждения, риски смещений, рекомендации по реализации и деньгам.
Стиль: профессионально, структурно, без воды. Пиши по-русски.
Не выдумывай факты, опирайся только на данные из JSON.
Формат:
1) Резюме профиля (3–5 строк)
2) Матрица: Ряд1/Ряд2/Ряд3 (если данных мало — честно укажи)
3) Потенциалы топ-5: проявления + как монетизировать + как наполняться + чего избегать/делегировать
4) Смещения: признаки, гипотезы, как проверить (2 вопроса на каждое)
5) Следующий шаг: что предложить клиенту (upsell: расширенный отчет/консультация/программа 3 мес)
"""

    user = f"JSON клиента:\n{json.dumps(compact, ensure_ascii=False)}"

    resp = client.chat.completions.create(
        model=try_get_secret("OPENAI_MODEL", "gpt-5"),
        messages=[
            {"role":"system","content":system},
            {"role":"user","content":user}
        ],
        temperature=0.3
    )

    text = resp.choices[0].message.content
    return text, True

# -----------------------------
# UI: Master auth
# -----------------------------
def master_gate():
    st.sidebar.markdown("## 🔒 Мастер-панель")
    pw_required = try_get_secret("MASTER_PASSWORD", "neo")
    entered = st.sidebar.text_input("Пароль мастера", type="password")
    ok = (entered == pw_required) and (entered != "")
    if ok:
        st.sidebar.success("Доступ открыт")
    else:
        st.sidebar.info("Введите пароль, чтобы открыть мастер-панель")
    return ok

# -----------------------------
# Main App
# -----------------------------
st.set_page_config(page_title="NEO Диагностика", layout="wide")

cfg = load_cfg()
init_state(cfg)

st.title("NEO Диагностика потенциалов (MVP)")

# ---- CLIENT FLOW ----
colA, colB = st.columns([1.2, 0.8], gap="large")

with colA:
    st.markdown("### Клиентская часть")

    # pick question
    if st.session_state["done"] or should_stop(cfg):
        st.session_state["done"] = True
    else:
        if st.session_state["current_qid"] is None:
            q = pick_next_question(cfg)
            if q is None:
                st.session_state["done"] = True
            else:
                st.session_state["current_qid"] = q["id"]

    if not st.session_state["done"]:
        bank = cfg.get("question_bank", [])
        q = next((x for x in bank if x.get("id") == st.session_state["current_qid"]), None)
        if q is None:
            st.session_state["done"] = True
        else:
            st.markdown(f"**Вопрос {st.session_state['turn']+1} из {cfg.get('diagnosis',{}).get('hard_stop_at_questions',30)}**")
            st.markdown(f"#### {q.get('text','')}")

            qtype = q.get("type","text")
            answer_key = f"ans_{q.get('id')}"
            # IMPORTANT: reset input on next question
            if f"__last_qid" not in st.session_state:
                st.session_state["__last_qid"] = q.get("id")
            if st.session_state["__last_qid"] != q.get("id"):
                # wipe old field value to avoid "answer carries over"
                if answer_key in st.session_state:
                    del st.session_state[answer_key]
                st.session_state["__last_qid"] = q.get("id")

            answer = None
            if qtype == "single":
                answer = st.radio("Выберите вариант:", q.get("options", []), key=answer_key)
            elif qtype == "multi":
                answer = st.multiselect("Выберите варианты:", q.get("options", []), key=answer_key)
            else:
                answer = st.text_area("Ответ:", key=answer_key, height=120, placeholder="Можно коротко. Пример: ...")

            c1, c2 = st.columns([0.7, 0.3])
            with c1:
                if st.button("Далее ➜", use_container_width=True):
                    qid = q.get("id")
                    st.session_state["asked"].append(qid)
                    st.session_state["answers"][qid] = answer
                    record_event(q, answer)
                    apply_scoring(q, answer, cfg)

                    # meta capture
                    if qid == "intake.ask_name":
                        st.session_state["client_name"] = safe_text(answer).strip()
                    if qid == "intake.ask_request":
                        st.session_state["client_request"] = safe_text(answer).strip()
                    if qid == "intake.ask_phone":
                        st.session_state["client_phone"] = safe_text(answer).strip()
                    if qid == "intake.ask_email":
                        st.session_state["client_email"] = safe_text(answer).strip()

                    st.session_state["turn"] += 1
                    st.session_state["current_qid"] = None
                    st.rerun()

            with c2:
                if st.button("Сброс", use_container_width=True):
                    for k in list(st.session_state.keys()):
                        del st.session_state[k]
                    st.rerun()

    # ---- FINISH CLIENT ----
    if st.session_state["done"]:
        # Build payload, save session
        payload = {
            "meta": {
                "schema": "ai-neo.master_report.v3",
                "timestamp": now_iso(),
                "session_id": st.session_state["session_id"],
                "name": st.session_state.get("client_name") or safe_text(st.session_state["answers"].get("intake.ask_name","")),
                "request": st.session_state.get("client_request") or safe_text(st.session_state["answers"].get("intake.ask_request","")),
                "phone": st.session_state.get("client_phone") or safe_text(st.session_state["answers"].get("intake.ask_phone","")),
                "email": st.session_state.get("client_email") or safe_text(st.session_state["answers"].get("intake.ask_email","")),
                "question_count": st.session_state.get("turn", 0),
            },
            "answers": st.session_state["answers"],
            "scores": st.session_state["scores"],
            "evidence": st.session_state["evidence"],
            "event_log": st.session_state["event_log"],
        }
        saved_path = save_session(payload)

        st.success("Диагностика завершена ✅")
        st.markdown(client_mini_report(payload["answers"], payload["scores"]))

        # CTA
        st.markdown("---")
        st.markdown("### Хочешь следующий шаг?")
        st.markdown(
            "Полный разбор включает: реализация + деньги (канал монетизации), зоны наполнения, риски смещений и персональный план на 4–6 недель."
        )
        st.info("Скажи мастеру: «Хочу полный отчёт и план реализации».")
        st.caption(f"Сессия сохранена: {saved_path.name}")

# ---- MASTER PANEL ----
with colB:
    st.markdown("### Панель мастера")
    authed = master_gate()

    if not authed:
        st.stop()

    tabs = st.tabs(["Сессии", "Открыть JSON", "Сгенерировать отчёт", "Настройки"])

    with tabs[0]:
        st.markdown("#### Список клиентов (локально сохранённые)")
        items = list_sessions()
        if not items:
            st.info("Пока нет сохранённых сессий. Пройди диагностику как клиент — и она появится здесь.")
        else:
            pick = st.selectbox(
                "Выбери сессию",
                options=list(range(len(items))),
                format_func=lambda i: f"{items[i]['timestamp']} — {items[i]['name']} — {items[i]['request']}",
            )
            chosen = items[pick]
            st.write(f"**Session ID:** {chosen['session_id']}")
            st.write(f"**Имя:** {chosen['name']}")
            st.write(f"**Запрос:** {chosen['request']}")
            if chosen.get("phone"):
                st.write(f"**Телефон:** {chosen['phone']}")
            if chosen.get("email"):
                st.write(f"**Email:** {chosen['email']}")

            if st.button("Скачать JSON (сессия)", use_container_width=True):
                with open(chosen["path"], "r", encoding="utf-8") as f:
                    data = f.read()
                st.download_button(
                    "Download",
                    data=data,
                    file_name=chosen["path"].name,
                    mime="application/json",
                    use_container_width=True
                )

    with tabs[1]:
        st.markdown("#### Загрузить JSON вручную (если пришёл откуда-то)")
        up = st.file_uploader("JSON файл", type=["json"])
        if up:
            try:
                data = json.load(up)
                st.session_state["__master_loaded"] = data
                st.success("JSON загружен")
                st.json(data.get("meta", {}))
            except Exception as e:
                st.error(f"Не смог прочитать JSON: {e}")

    with tabs[2]:
        st.markdown("#### Генерация мастер-отчёта")
        source = st.radio("Источник данных", ["Последняя сохранённая сессия", "Загруженный JSON"], horizontal=True)

        payload = None
        if source == "Последняя сохранённая сессия":
            items = list_sessions()
            if items:
                with open(items[0]["path"], "r", encoding="utf-8") as f:
                    payload = json.load(f)
                st.caption(f"Используется: {items[0]['path'].name}")
            else:
                st.warning("Нет сохранённых сессий.")
        else:
            payload = st.session_state.get("__master_loaded")

        if payload:
            st.markdown("**Meta**")
            st.json(payload.get("meta", {}))

            # IMPORTANT: avoid error — always produce something
            if st.button("🧠 Сгенерировать отчёт (AI/шаблон)", use_container_width=True):
                try:
                    report, used_ai = ai_generate_master_report(payload)
                    st.session_state["__master_report_text"] = report
                    st.session_state["__master_report_used_ai"] = used_ai
                    st.success("Отчёт готов")
                except Exception as e:
                    st.error(f"Ошибка генерации отчёта: {e}")

            report_txt = st.session_state.get("__master_report_text")
            if report_txt:
                used_ai = st.session_state.get("__master_report_used_ai", False)
                st.caption("AI использован ✅" if used_ai else "AI не подключён — сгенерирован шаблон ✅")

                st.text_area("Текст отчёта", value=report_txt, height=420)

                st.download_button(
                    "Скачать отчёт (.md)",
                    data=report_txt,
                    file_name=f"{payload.get('meta',{}).get('session_id','report')}_master_report.md",
                    mime="text/markdown",
                    use_container_width=True
                )

                st.markdown("---")
                st.markdown("##### Куда отправлять отчёт (пока вручную)")
                st.write("Телефон/Email клиента можно хранить в meta (intake.ask_phone / intake.ask_email). Отправку в Telegram/Email подключим следующим шагом.")

    with tabs[3]:
        st.markdown("#### Настройки")
        st.write("Пароль мастера берётся из `st.secrets['MASTER_PASSWORD']` или переменной окружения `MASTER_PASSWORD`.")
        st.write("AI-генерация отчёта включается, если задан `OPENAI_API_KEY` (и установлен пакет `openai`).")
        st.code("""
# .streamlit/secrets.toml
MASTER_PASSWORD="your_password"
OPENAI_API_KEY="sk-..."
OPENAI_MODEL="gpt-5"
""".strip())