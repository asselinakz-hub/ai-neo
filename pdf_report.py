# pdf_report.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from io import BytesIO
from typing import Dict, List

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
    Image,
)

# ------------------------
# Paths (как в твоём предыдущем коде)
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
BRAND_DIR = os.path.join(ASSETS_DIR, "brand")

# ------------------------
# Colors (calm, premium — как в предыдущем коде)
# ------------------------
C_BG = colors.HexColor("#FFFFFF")
C_TEXT = colors.HexColor("#121212")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")     # soft lavender-gray
C_ACCENT = colors.HexColor("#5B2B6C")   # deep plum
C_ACCENT_2 = colors.HexColor("#8C4A86") # muted mauve

# ------------------------
# Fonts (Cyrillic safe)
# ------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    """
    Uses repo fonts:
      - assets/fonts/DejaVuSans.ttf
      - assets/fonts/DejaVuLGCSans-Bold.ttf
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    regular = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    bold = os.path.join(FONT_DIR, "DejaVuLGCSans-Bold.ttf")
    bold_alt = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

    if not os.path.exists(regular):
        raise RuntimeError(f"Font not found: {regular}")

    if os.path.exists(bold_alt):
        bold = bold_alt
    elif not os.path.exists(bold):
        bold = regular  # fallback

    # quick corruption guard
    if os.path.getsize(regular) < 10_000:
        raise RuntimeError(f"Font file looks corrupted (too small): {regular}")
    if os.path.getsize(bold) < 10_000:
        raise RuntimeError(f"Bold font file looks corrupted (too small): {bold}")

    pdfmetrics.registerFont(TTFont("PP-Regular", regular))
    pdfmetrics.registerFont(TTFont("PP-Bold", bold))
    _FONTS_REGISTERED = True


# ------------------------
# Helpers
# ------------------------
def _strip_html(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\t", "    ")
    text = re.sub(r"</?[^>]+>", "", text)
    return text.strip()

def _p(text: str, style: ParagraphStyle) -> Paragraph:
    # reportlab Paragraph understands basic tags like <b>, <br/>
    return Paragraph(_strip_html(text).replace("\n", "<br/>"), style)

def _safe_logo_path(filename: str) -> str | None:
    p = os.path.join(BRAND_DIR, filename)
    return p if os.path.exists(p) else None


# ------------------------
# Footer (как в предыдущем коде)
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "PERSONAL POTENTIALS"):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    logo_path = _safe_logo_path("logo_horizontal.png") or _safe_logo_path("logo_mark.png")
    x = doc.leftMargin
    if logo_path:
        try:
            canvas.drawImage(
                logo_path, x, y - 2,
                width=30 * mm, height=10 * mm,
                mask='auto', preserveAspectRatio=True, anchor='sw'
            )
            x += 34 * mm
        except Exception:
            pass

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Regular", 9)
    canvas.drawString(x, y + 2, brand_name)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Regular", 9)
    canvas.drawRightString(A4[0] - doc.rightMargin, y + 2, str(doc.page))

    canvas.restoreState()


# ------------------------
# Main builder: собирает отчёт строго по твоему шаблону
# ------------------------
def build_client_report_pdf_bytes(
    client_name: str,
    request: str,
    matrix_3x3: List[List[str]],           # [[p1,p2,p3],[p4,p5,p6],[p7,p8,p9]]
    potentials_texts: Dict[str, str],      # {"Сапфир": "...", "Гранат":"...", ...}
    brand_name: str = "PERSONAL POTENTIALS",
) -> bytes:
    """
    matrix_3x3 example:
    [
      ["Сапфир","Гранат","Аметист"],
      ["Янтарь","Изумруд","Цитрин"],
      ["Шунгит","Рубин","Гелиодор"],
    ]

    potentials_texts: dictionary with ready texts for each potential name.
    """
    _register_fonts()

    if len(matrix_3x3) != 3 or any(len(r) != 3 for r in matrix_3x3):
        raise ValueError("matrix_3x3 must be exactly 3 rows x 3 columns")

    # unpack for readability
    p1, p2, p3 = matrix_3x3[0]
    p4, p5, p6 = matrix_3x3[1]
    p7, p8, p9 = matrix_3x3[2]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{brand_name} Report",
        author="Asselya Zhanybek",
    )

    styles = getSampleStyleSheet()

    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Regular",
        fontSize=11,
        leading=16,
        textColor=C_TEXT,
        spaceAfter=6,
        alignment=TA_LEFT,
    )

    h1 = ParagraphStyle(
        "h1",
        parent=base,
        fontName="PP-Bold",
        fontSize=22,
        leading=28,
        textColor=C_ACCENT,
        spaceAfter=10,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="PP-Bold",
        fontSize=14,
        leading=18,
        textColor=C_ACCENT,
        spaceBefore=10,
        spaceAfter=6,
    )

    h3 = ParagraphStyle(
        "h3",
        parent=base,
        fontName="PP-Bold",
        fontSize=12,
        leading=16,
        textColor=C_TEXT,
        spaceBefore=8,
        spaceAfter=4,
    )

    subtle = ParagraphStyle(
        "subtle",
        parent=base,
        fontSize=10,
        leading=14,
        textColor=C_MUTED,
    )

    title_center = ParagraphStyle(
        "title_center",
        parent=h1,
        alignment=TA_CENTER,
    )

    cover_sub = ParagraphStyle(
        "cover_sub",
        parent=base,
        fontName="PP-Regular",
        fontSize=13,
        leading=18,
        textColor=C_ACCENT_2,
        alignment=TA_CENTER,
        spaceAfter=16,
    )

    story: List = []

    # ========================
    # COVER (строго по шаблону)
    # ========================
    cover_logo = (
        _safe_logo_path("logo_main.png")   # полный логотип с кружочком (как ты просила)
        or _safe_logo_path("logo_main.jpg")
        or _safe_logo_path("logo_light.png")
    )

    story.append(Spacer(1, 10 * mm))

    if cover_logo:
        try:
            img = Image(cover_logo)
            img._restrictSize(95 * mm, 70 * mm)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 10 * mm))
        except Exception:
            story.append(Spacer(1, 16 * mm))
    else:
        story.append(Spacer(1, 16 * mm))

    story.append(_p(brand_name, title_center))
    story.append(_p("Персональный отчёт", cover_sub))

    story.append(_p(f"<b>для:</b> {client_name}", base))
    story.append(_p(f"<b>запрос:</b> {request}", base))

    story.append(Spacer(1, 6 * mm))
    story.append(_p("Вводная", h2))

    # Вводная — ровно твой текст (без изменений)
    story.append(_p(
        "Есть моменты, когда ты вроде бы стараешься — но ощущение, что живёшь “не своим способом”.\n"
        "Эта диагностика помогает сделать очень простую, но сильную вещь: увидеть свой природный механизм — "
        "как ты воспринимаешь мир, что тебя по-настоящему зажигает и через какой стиль действий ты достигаешь результата без насилия над собой.\n\n"
        "После такой диагностики обычно происходит одно из трёх:\n"
        "• становится легче принимать решения (появляется внутреннее “да/нет” без тревоги);\n"
        "• появляется ясность, где именно ты теряешь энергию и почему буксуешь;\n"
        "• появляется ощущение “я понял(а) себя” — и из этого уже проще строить цели, работу, отношения и стиль жизни.",
        base
    ))

    story.append(PageBreak())

    # ========================
    # MATRIX (строго по шаблону)
    # ========================
    story.append(_p("Твоя матрица потенциалов 3×3", h2))
    story.append(Spacer(1, 2 * mm))

    table_data = [
        ["Ряд", "Восприятие", "Мотивация", "Инструмент"],
        ["1", p1, p2, p3],
        ["2", p4, p5, p6],
        ["3", p7, p8, p9],
    ]

    tbl = Table(table_data, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "PP-Regular"),
        ("FONTSIZE", (0, 0), (-1, -1), 10.5),
        ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F4FA")),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_ACCENT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, C_LINE),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E6E2F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(tbl)
    story.append(Spacer(1, 6 * mm))

    story.append(_p(
        "Важно: матрица — это не оценка и не “уровень развития”.\n"
        "Это карта твоего естественного устройства:\n"
        "• 1 ряд — твой базовый стиль реализации (как ты создаёшь ценность).\n"
        "• 2 ряд — ресурс, энергия и взаимодействие с людьми (чем подпитываешься).\n"
        "• 3 ряд — зона риска (где легче перегрузиться; что лучше упрощать/делегировать).",
        base
    ))

    story.append(PageBreak())

    # ========================
    # ROW 1 (строго по шаблону)
    # ========================
    story.append(_p("1 РЯД — ОСНОВА ТВОЕЙ РЕАЛИЗАЦИИ", h2))
    story.append(_p(
        "Твой фундамент — это сочетание тонкого внутреннего восприятия, эмоциональной мотивации и силы слова/смысла.\n"
        "Ты не про “делать больше”, ты про “попадать точно”. Когда ты в своём стиле — появляется ощущение ясности, красоты и внутренней правды. "
        "Когда не в своём — много шума, сомнений и усталости.",
        base
    ))

    story.append(_p(f"1 потенциал: твой потенциал {p1}", h3))
    story.append(_p(potentials_texts.get(p1, "—"), base))

    story.append(_p(f"2 потенциал: твой потенциал {p2}", h3))
    story.append(_p(potentials_texts.get(p2, "—"), base))

    story.append(_p(f"3 потенциал: твой потенциал {p3}", h3))
    story.append(_p(potentials_texts.get(p3, "—"), base))

    story.append(_p("Связка 1 ряда:", h3))
    story.append(_p(
        f"{p1} даёт тонкость и глубину → {p2} даёт живое проявление и энергию → {p3} превращает это в ясную мысль и результат.",
        base
    ))

    story.append(PageBreak())

    # ========================
    # ROW 2 (строго по шаблону)
    # ========================
    story.append(_p("2 РЯД — ЭНЕРГИЯ, РЕСУРС И ВЗАИМОДЕЙСТВИЕ С ЛЮДЬМИ", h2))
    story.append(_p(
        "Этот ряд — про то, где ты выдыхаешь, чем питаешься и за что тебя ценят люди.\n"
        "Он не должен становиться “обязанностью”, но когда он включён правильно — он поддерживает твой 1 ряд и делает реализацию устойчивой.",
        base
    ))

    story.append(_p(f"4 потенциал: твой потенциал {p4}", h3))
    story.append(_p(potentials_texts.get(p4, "—"), base))

    story.append(_p(f"5 потенциал: твой потенциал {p5}", h3))
    story.append(_p(potentials_texts.get(p5, "—"), base))

    story.append(_p(f"6 потенциал: твой потенциал {p6}", h3))
    story.append(_p(potentials_texts.get(p6, "—"), base))

    story.append(PageBreak())

    # ========================
    # ROW 3 (строго по шаблону)
    # ========================
    story.append(_p("3 РЯД — ЗОНА РИСКА (ГДЕ МОЖНО ПЕРЕГРУЗИТЬСЯ)", h2))
    story.append(_p(
        "Третий ряд часто проявляется не сразу. Он показывает:\n"
        "• где ты можешь “тащить лишнее”;\n"
        "• где включаются крайности (перегруз, контроль, рывок, выгорание);\n"
        "• что лучше упрощать/делегировать.\n\n"
        f"В твоей матрице: {p7} — {p8} — {p9}.\n"
        "Пока это выглядит гармонично, но требует подтверждения жизненными примерами — обычно это делается на мастер-сессии.",
        base
    ))

    story.append(PageBreak())

    # ========================
    # WHY NOT (строго по шаблону, но названия потенциалов — динамически из 1 ряда)
    # ========================
    story.append(_p("ПОЧЕМУ ИНОГДА НЕ ПОЛУЧАЕТСЯ (ДАЖЕ ЕСЛИ ПОТЕНЦИАЛ ЕСТЬ)", h2))
    story.append(_p(
        "Чаще всего проблема не в лени и не в “слабой силе воли”.\n"
        "Обычно происходит одно из этих смещений:\n"
        f"• {p1}у нужен внутренний покой, но внешняя спешка и шум сбивают настройку — появляется сомнение, расфокус.\n"
        f"• {p2}у нужна эмоция и проявление, но если ты начинаешь “держать себя”, чтобы быть правильной/рациональной, — мотивация гаснет.\n"
        f"• {p3} умеет вести к результату, но если ты пытаешься стартовать без внутреннего “звучит”, появляется сопротивление и стопор.\n\n"
        "Когда 2 ряд становится обязанностью (помогать всем, держать всё, быть опорой), энергия уходит туда — и первый ряд перестаёт звучать.",
        base
    ))

    story.append(PageBreak())

    # ========================
    # EXERCISE (строго по шаблону)
    # ========================
    story.append(_p("УПРАЖНЕНИЕ: 3 ИНСАЙТА + 1 ДЕЙСТВИЕ", h2))
    story.append(_p(
        "Это упражнение переводит отчёт из текста в движение — мягко, без рывка.\n"
        "1. Что в этом отчёте “попало в точку”? (1–2 фразы)\n"
        "2. Где ты чаще всего пытаешься жить не своим способом?\n"
        "3. Что ты готов(а) перестать делать на этой неделе, чтобы стало легче?\n"
        "4. Одно действие на неделю (очень конкретно): ______________________",
        base
    ))

    story.append(PageBreak())

    # ========================
    # NOTES (строго по шаблону)
    # ========================
    story.append(_p("ЗАМЕТКИ", h2))
    story.append(_p(
        "Подсказка: сюда можно выписывать идеи, наблюдения, “где я узнаю себя”, вопросы к сессии, инсайты про работу/отношения/деньги/проявленность.",
        subtle
    ))
    story.append(Spacer(1, 4 * mm))

    lines = 22
    notes_data = [[""] for _ in range(lines)]
    notes_tbl = Table(notes_data, colWidths=[A4[0] - doc.leftMargin - doc.rightMargin])
    notes_tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#E6E2F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(notes_tbl)

    story.append(PageBreak())

    # ========================
    # ABOUT (строго по шаблону, без изменений)
    # ========================
    story.append(_p("ОБО МНЕ", h2))
    story.append(_p(
        "Asselya Zhanybek — практик и эксперт на стыке личной реализации и системного подхода.\n"
        "Мой профессиональный бэкграунд — многолетний опыт в HR, корпоративном консалтинге и работе с развитием людей в организациях, где важны не красивые слова, "
        "а реальные изменения в мышлении, действиях и результате.\n\n"
        "Я адаптировала методику школы (на базе системного подхода к личности) в онлайн-диагностику и платформенное сопровождение, чтобы человек мог:\n"
        "1. увидеть свои природные механизмы,\n"
        "2. собрать понятные цели,\n"
        "3. выстроить путь достижения через свои сильные стороны — без постоянного “ломания себя”.",
        base
    ))

    story.append(Spacer(1, 4 * mm))

    # ========================
    # METHODOLOGY (строго по шаблону, без изменений)
    # ========================
    story.append(_p("О МЕТОДОЛОГИИ ДИАГНОСТИКИ", h2))
    story.append(_p(
        "Диагностика основана на принципах векторной психологии и системного анализа внутренних мотиваций "
        "(не “типология ради типологии”, а карта механизмов).\n"
        "Мы используем:\n"
        "• структурированный опрос (вопросы на мотивацию, восприятие, стиль действий),\n"
        "• интерпретацию ответов через матрицу 3×3,\n"
        "• проверку согласованности (логика связок между рядами),\n"
        "• выявление возможных внутренних конфликтов и зон перегруза.\n\n"
        "Диагностика — это первый этап.\n"
        "Дальше, при желании, человек выстраивает свою систему: цели → стратегия → действия → поддержка (в своём стиле), чтобы результат становился устойчивым.",
        base
    ))

    # build
    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
    )

    return buf.getvalue()