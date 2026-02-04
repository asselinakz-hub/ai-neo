# pdf_report.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from io import BytesIO
from datetime import date

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
    KeepTogether,
)

# ------------------------
# Paths
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
BRAND_DIR = os.path.join(ASSETS_DIR, "brand")

# ------------------------
# Colors (calm, premium)
# ------------------------
C_BG = colors.HexColor("#FFFFFF")
C_TEXT = colors.HexColor("#121212")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")     # soft lavender-gray
C_ACCENT = colors.HexColor("#5B2B6C")   # deep plum
C_ACCENT_2 = colors.HexColor("#8C4A86") # muted mauve
C_TABLE_BG = colors.HexColor("#F7F5FB")

# ------------------------
# Fonts (Cyrillic safe)
#   Headings: serif (regular/medium, NOT bold)
#   Body: sans (regular)
# ------------------------
_FONTS_REGISTERED = False

def _pick_first_existing(*paths: str) -> str | None:
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None

def _register_fonts():
    """
    Required: Body sans with Cyrillic
      - assets/fonts/DejaVuSans.ttf  (recommended)
    Optional: Headings serif (regular)
      - PlayfairDisplay-Regular.ttf
      - CormorantGaramond-Regular.ttf
      - LibreBaskerville-Regular.ttf
      - DejaVuSerif.ttf
    Fallback: use DejaVuSans for headings if no serif available.
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    sans_regular = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    if not os.path.exists(sans_regular):
        raise RuntimeError(f"Font not found: {sans_regular}")
    if os.path.getsize(sans_regular) < 10_000:
        raise RuntimeError(f"Font file looks corrupted (too small): {sans_regular}")

    serif_regular = _pick_first_existing(
        os.path.join(FONT_DIR, "PlayfairDisplay-Regular.ttf"),
        os.path.join(FONT_DIR, "CormorantGaramond-Regular.ttf"),
        os.path.join(FONT_DIR, "LibreBaskerville-Regular.ttf"),
        os.path.join(FONT_DIR, "DejaVuSerif.ttf"),
    )
    if serif_regular and os.path.getsize(serif_regular) < 10_000:
        serif_regular = None  # corruption guard

    pdfmetrics.registerFont(TTFont("PP-Sans", sans_regular))
    if serif_regular:
        pdfmetrics.registerFont(TTFont("PP-Serif", serif_regular))
    else:
        # fallback: headings will also use sans
        pdfmetrics.registerFont(TTFont("PP-Serif", sans_regular))

    _FONTS_REGISTERED = True


# ------------------------
# Helpers
# ------------------------
def _strip_md(md: str) -> str:
    if not md:
        return ""
    md = md.replace("```", "")
    md = md.replace("\t", "    ")
    md = re.sub(r"</?[^>]+>", "", md)  # remove html tags
    md = md.replace("**", "")          # remove markdown bold markers
    md = md.replace("__", "")
    return md.strip()

def _safe_logo_path(filename: str) -> str | None:
    p = os.path.join(BRAND_DIR, filename)
    return p if os.path.exists(p) else None

def _para_lines(text: str) -> list[str]:
    """
    Splits into short paragraphs:
    - preserves empty lines as separators
    - tries to avoid very long 'wall of text' by respecting existing line breaks
    """
    t = _strip_md(text or "")
    blocks = re.split(r"\n\s*\n", t)
    out = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        out.append(b)
    return out

def _is_heading(line: str) -> bool:
    """
    Treats ALL CAPS / explicit markers as headings.
    """
    s = line.strip()
    if not s:
        return False
    if s.startswith("#"):
        return True
    # common section markers
    if "—" in s and len(s) < 90 and s.upper() == s:
        return True
    if s.upper() == s and 4 <= len(s) <= 80:
        return True
    # starts with "Введение", "О методологии", etc.
    starters = (
        "Введение",
        "Структура",
        "Твоя матрица",
        "ПЕРВЫЙ РЯД",
        "ВТОРОЙ РЯД",
        "ТРЕТИЙ РЯД",
        "Итоговая картина",
        "О методологии",
        "Об авторе",
        "Заметки",
        "Ключевые выводы",
    )
    return any(s.startswith(x) for x in starters)

def _normalize_bullets(text: str) -> str:
    """
    Converts '• ' bullet lines into simple line breaks with a subtle bullet glyph.
    ReportLab supports '•' fine with DejaVu.
    """
    lines = [l.rstrip() for l in (text or "").splitlines()]
    out = []
    for l in lines:
        ls = l.strip()
        if ls.startswith("•"):
            out.append("• " + ls.lstrip("•").strip())
        else:
            out.append(l)
    return "\n".join(out).strip()


# ------------------------
# Default potential library (YOU can override per project)
# Each potential contains 3 role-templates:
#   perception / motivation / tool
# The report will pick by role based on matrix position.
# ------------------------
DEFAULT_POTENTIAL_LIBRARY: dict[str, dict[str, str]] = {
    # Example texts (short, neutral, no bold). Replace/expand as you need.
    "Рубин": {
        "perception": """Твоё восприятие настроено на эмоционально-телесный отклик.
Ты считываешь происходящее через внутреннюю реакцию: подъём, интерес, напряжение или отторжение.

Это помогает быстро чувствовать, где процесс «живой», а где формальный, и где энергия действительно есть.""",
        "motivation": """Если Рубин стоит в мотивации, тебя запускает сильное проживание жизни и ощущение интенсивности.
Энергия приходит, когда есть движение, эмоция и ощутимый импульс «хочу».""",
        "tool": """Если Рубин стоит в инструменте, ты влияешь через состояние и «заряд» процесса.
Ты умеешь включать людей и создавать динамику, когда это уместно."""
    },
    "Аметист": {
        "perception": """Ты воспринимаешь мир через смысл и скрытые причины.
Важны логика, внутренние механизмы, точные формулировки и понимание «почему так».

Ты тонко чувствуешь, где в идее есть глубина, а где — только оболочка.""",
        "motivation": """Твоя мотивация связана с владением глубиной и пониманием механизмов.
Тебя включает сложная информация, первоисточники и возможность разобраться до сути.""",
        "tool": """Твой инструмент — смысл, слово и мышление.
Ты умеешь развязывать узлы, прояснять позиции и строить понятную логическую траекторию к решению."""
    },
    "Цитрин": {
        "perception": """Ты видишь процессы через структуру действий и результат.
Считываешь, где система работает, а где распадается, и что нужно сделать, чтобы стало управляемо.""",
        "motivation": """Тебя мотивирует практический эффект и измеримый результат.
Энергия появляется, когда есть ясные шаги и понятная цель.""",
        "tool": """Твой способ реализации — управление действиями и системами.
Ты превращаешь сложное в структурированное и доводишь идеи до практического результата."""
    },
    "Гранат": {
        "perception": """Ты тонко улавливаешь эмоциональные состояния людей и атмосферу.
Даже без специального фокуса считываешь напряжение, невысказанное и истинную вовлечённость.""",
        "motivation": """Тебя запускает эмоция, проявление и ощущение живой выразительности.
Энергия приходит, когда можно быть видимым и создавать впечатление.""",
        "tool": """Через Гранат ты влияешь состоянием, образом и выразительной подачей.
Это инструмент вовлечения и контакта."""
    },
    "Янтарь": {
        "perception": """Ты видишь, где нарушена опора: в системе, в процессе, в теле или в структуре действий.
Есть способность возвращать устойчивость и порядок.""",
        "motivation": """Энергия включается, когда есть практическая польза, стабильность и ощущение надёжности.
Тебя мотивирует опора и то, что действительно работает.""",
        "tool": """Твой инструмент — системность и восстановление устойчивости.
Ты умеешь упрощать сложное и возвращать опору через порядок."""
    },
    "Шунгит": {
        "perception": """Ты воспринимаешь через факты, труд, практику и повторяемость.
Важно «пощупать» реальность и увидеть, что работает на деле.""",
        "motivation": """Тебя мотивирует движение, тренировка навыка и понятная физическая/практическая нагрузка.
Энергия растёт через регулярность и дисциплину без драматизации.""",
        "tool": """Результат твоего влияния — устойчивые связи, команда и совместное действие.
Ты умеешь объединять людей вокруг практики и реального опыта."""
    },
    "Изумруд": {
        "perception": """Ты считываешь мир через гармонию, красоту и эмоциональный баланс.
Видишь, где «перекосило», и что нужно, чтобы вернуть равновесие.""",
        "motivation": """Тебя мотивирует ощущение внутренней гармонии и «мне можно быть собой».
Энергия появляется, когда есть мягкость и восстановление.""",
        "tool": """Ты влияешь через тонкое восстановление и эмоциональное выравнивание.
Это инструмент поддержки и возвращения ресурса."""
    },
    "Сапфир": {
        "perception": """У тебя тонкий «внутренний слух» к смыслу и точности идеи.
Ты чувствуешь, звучит ли решение как «моё», и где нарушена логика или глубина.""",
        "motivation": """Тебя мотивирует чистота смысла и ощущение внутренней правды.
Когда идея звучит точно, появляется спокойная сила и ясность.""",
        "tool": """Твой инструмент — точность, глубина и смысловая настройка.
Ты умеешь делать идеи чище, яснее и сильнее."""
    },
    "Гелиодор": {
        "perception": """Ты воспринимаешь через перспективу, идеи и «зачем».
Важно видеть направление и смысловой вектор.""",
        "motivation": """Тебя мотивирует рост, расширение и ощущение перспективы.
Энергия приходит, когда есть горизонт и смысл будущего.""",
        "tool": """Через Гелиодор ты влияешь вдохновением и направлением.
Это инструмент стратегии, смысла и ориентиров."""
    },
}

# ------------------------
# Footer
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials"):
    canvas.saveState()

    y = 12 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.6)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    logo_path = (
        _safe_logo_path("logo_horizontal.png")
        or _safe_logo_path("logo_main.png")
        or _safe_logo_path("logo_mark.png")
    )

    x = doc.leftMargin
    if logo_path:
        try:
            canvas.drawImage(
                logo_path,
                x,
                y - 1,
                width=28 * mm,
                height=10 * mm,
                mask="auto",
                preserveAspectRatio=True,
                anchor="sw",
            )
            x += 32 * mm
        except Exception:
            pass

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Sans", 9)
    canvas.drawString(x, y + 2, brand_name)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Sans", 9)
    canvas.drawRightString(A4[0] - doc.rightMargin, y + 2, str(doc.page))

    canvas.restoreState()


# ------------------------
# Dynamic section builders
# ------------------------
def _get_potential_text(potential: str, role: str, library: dict[str, dict[str, str]]) -> str:
    pot = (potential or "").strip()
    if not pot:
        return "Описание не задано."
    data = library.get(pot)
    if not data:
        return "Описание для этого потенциала пока не добавлено в базу."
    return (data.get(role) or "Описание для этого потенциала пока не добавлено в базу.").strip()

def _compose_row_section(row_label: str, triplet: list[str], library: dict[str, dict[str, str]]) -> list[tuple[str, str]]:
    """
    Returns list of (heading, paragraph_text) blocks.
    triplet = [perception, motivation, tool]
    """
    p, m, t = [(x or "").strip() for x in triplet]
    blocks: list[tuple[str, str]] = []

    blocks.append((row_label, ""))

    blocks.append((f"Восприятие — {p}", _get_potential_text(p, "perception", library)))
    blocks.append((f"Мотивация — {m}", _get_potential_text(m, "motivation", library)))
    blocks.append((f"Инструмент — {t}", _get_potential_text(t, "tool", library)))

    blocks.append(("Связка ряда", _normalize_bullets(f"""Твоя сила проявляется, когда:
• внутренний механизм ({p})
• соединяется с мотивацией ({m})
• и переводится в действие через ({t}).

В этом состоянии решения принимаются легче, а движение ощущается естественным.
При нарушении связки могут появляться сомнения, пустота или избыточный контроль.""")))

    return blocks

def _build_key_takeaways(row1_triplet: list[str], row2_triplet: list[str]) -> str:
    """
    Simple dynamic takeaways page. No bold.
    """
    r1 = " · ".join([x for x in row1_triplet if x])
    r2 = " · ".join([x for x in row2_triplet if x])
    return _normalize_bullets(f"""Ключевые выводы

1) Твой главный вектор — первый ряд (60%).
Это зона, где важно держать фокус и строить решения: {r1}.

2) Второй ряд (30%) — источник подпитки.
Он поддерживает первый ряд, но не должен становиться обязанностью: {r2}.

3) Третий ряд (10%) — зона риска.
Лучше относиться к нему как к вспомогательному режиму: эпизодически, дозировано.

4) Если появляется ощущение «стараюсь, но не еду» — чаще всего причина не в силе воли,
а в смещении фокуса: слишком много задач не из первого ряда или перегруз во втором/третьем.""").strip()


# ------------------------
# Main builder
# ------------------------
def build_client_report_pdf_bytes(
    client_name: str,
    request: str,
    matrix_rows: list[list[str]],
    # dynamic texts (can be overridden)
    potential_library: dict[str, dict[str, str]] | None = None,
    # metadata / brand
    brand_name: str = "PERSONAL POTENTIALS",
    subtitle: str = "Индивидуальный отчёт по системе потенциалов человека 3×3",
    author_name: str = "Asselya Zhanybek",
    report_date: date | None = None,
) -> bytes:
    """
    matrix_rows format (required):
      [
        ["1 (60%)", perception, motivation, tool],
        ["2 (30%)", perception, motivation, tool],
        ["3 (10%)", perception, motivation, tool],
      ]

    IMPORTANT: This report is fully dynamic:
      - Matrix is printed from matrix_rows
      - Row sections are generated from matrix_rows + potential_library texts
    """
    _register_fonts()
    lib = potential_library or DEFAULT_POTENTIAL_LIBRARY
    report_date = report_date or date.today()

    # validate matrix
    if not matrix_rows or len(matrix_rows) != 3:
        raise ValueError("matrix_rows must contain exactly 3 rows: 1st/2nd/3rd.")
    for r in matrix_rows:
        if len(r) < 4:
            raise ValueError("Each matrix row must have 4 columns: label, perception, motivation, tool.")

    row1_triplet = [matrix_rows[0][1], matrix_rows[0][2], matrix_rows[0][3]]
    row2_triplet = [matrix_rows[1][1], matrix_rows[1][2], matrix_rows[1][3]]
    row3_triplet = [matrix_rows[2][1], matrix_rows[2][2], matrix_rows[2][3]]

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{brand_name} Report",
        author=author_name,
    )

    styles = getSampleStyleSheet()

    # Body text: premium readable (1.55–1.6)
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Sans",
        fontSize=11.5,
        leading=18,            # ~1.56
        textColor=C_TEXT,
        spaceAfter=9,          # more air between paragraphs
        alignment=TA_LEFT,
    )

    # Headings: serif, regular (NOT bold)
    h1 = ParagraphStyle(
        "h1",
        parent=base,
        fontName="PP-Serif",
        fontSize=24,
        leading=30,
        textColor=C_ACCENT,
        spaceAfter=10,
        spaceBefore=0,
        alignment=TA_CENTER,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="PP-Serif",
        fontSize=16,
        leading=22,
        textColor=C_ACCENT,
        spaceBefore=6,
        spaceAfter=8,
    )

    h3 = ParagraphStyle(
        "h3",
        parent=base,
        fontName="PP-Serif",
        fontSize=13.5,
        leading=19,
        textColor=C_ACCENT,
        spaceBefore=6,
        spaceAfter=6,
    )

    subtle = ParagraphStyle(
        "subtle",
        parent=base,
        fontName="PP-Sans",
        fontSize=10,
        leading=15,
        textColor=C_MUTED,
        spaceAfter=8,
    )

    # Narrow text (for About author page: 60–70% width)
    narrow_left_pad = 0
    narrow_right_pad = int((A4[0] - doc.leftMargin - doc.rightMargin) * 0.30)

    story = []

    # ------------------------
    # COVER (clean, never empty)
    # ------------------------
    cover_logo = (
        _safe_logo_path("logo_main.jpg")
        or _safe_logo_path("logo_main.png")
        or _safe_logo_path("logo_mark.png")
    )

    cover_blocks = []
    cover_blocks.append(Spacer(1, 6 * mm))

    if cover_logo:
        img = Image(cover_logo)
        img._restrictSize(70 * mm, 70 * mm)
        img.hAlign = "CENTER"
        cover_blocks.append(Spacer(1, 12 * mm))
        cover_blocks.append(img)
        cover_blocks.append(Spacer(1, 10 * mm))
    else:
        cover_blocks.append(Spacer(1, 26 * mm))

    cover_blocks.append(Paragraph(brand_name, h1))
    cover_blocks.append(Paragraph(subtitle, ParagraphStyle(
        "subtitle",
        parent=subtle,
        alignment=TA_CENTER,
        textColor=C_ACCENT_2,
        fontSize=11,
        leading=16,
        spaceAfter=14,
    )))

    # meta lines (no bold)
    meta_style = ParagraphStyle(
        "meta",
        parent=base,
        alignment=TA_CENTER,
        spaceAfter=6,
    )
    cover_blocks.append(Spacer(1, 4 * mm))
    cover_blocks.append(Paragraph(f"Для: {client_name}", meta_style))
    cover_blocks.append(Paragraph(f"Запрос: {request}", meta_style))
    cover_blocks.append(Paragraph(f"Дата: {report_date.strftime('%d.%m.%Y')}", meta_style))

    cover_blocks.append(Spacer(1, 20 * mm))
    cover_blocks.append(Paragraph(" ", subtle))

    story.append(KeepTogether(cover_blocks))
    story.append(PageBreak())

    # ------------------------
    # INTRODUCTION (page)
    # ------------------------
    story.append(Paragraph("Введение", h2))
    intro_text = _normalize_bullets("""Этот отчёт — результат индивидуальной диагностики, направленной на выявление природного способа мышления, мотивации и реализации.
Он не описывает качества характера и не даёт оценок личности.
Его задача — показать, как именно у тебя устроен внутренний механизм, через который ты принимаешь решения, расходуешь энергию и достигаешь результата.

Практическая ценность отчёта в том, что он:
• помогает точнее понимать себя и свои реакции;
• снижает внутренние конфликты между «хочу», «надо» и «делаю»;
• даёт ясность, где стоит держать фокус, а где — не перегружать себя.""")
    for block in _para_lines(intro_text):
        story.append(Paragraph(block.replace("\n", "<br/>"), base))

    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph("Структура внимания и распределение энергии", h2))
    energy_text = _normalize_bullets("""В основе интерпретации лежит матрица потенциалов 3×3, где каждый ряд выполняет свою функцию.

В твоей системе распределение внимания выглядит следующим образом:
• 1 ряд — 60% фокуса внимания
Основа личности, способ реализации и создания ценности.
Именно здесь находится твой главный вектор развития и устойчивости.
• 2 ряд — 30% фокуса внимания
Источник энергии, восстановления и живого контакта с людьми.
Этот уровень поддерживает первый, но не должен его подменять.
• 3 ряд — 10% фокуса внимания
Зоны риска и перегруза.
Эти функции не предназначены для постоянного использования и лучше осознавать их как вспомогательные.

Такое распределение позволяет сохранить внутренний баланс и не тратить ресурс на задачи, которые не соответствуют твоей природе.""")
    for block in _para_lines(energy_text):
        story.append(Paragraph(block.replace("\n", "<br/>"), base))

    story.append(PageBreak())

    # ------------------------
    # MATRIX (separate page)
    # ------------------------
    story.append(Paragraph("Твоя матрица потенциалов", h2))
    story.append(Spacer(1, 2 * mm))

    table_data = [
        ["Ряд", "Восприятие", "Мотивация", "Инструмент"],
        [matrix_rows[0][0], matrix_rows[0][1], matrix_rows[0][2], matrix_rows[0][3]],
        [matrix_rows[1][0], matrix_rows[1][1], matrix_rows[1][2], matrix_rows[1][3]],
        [matrix_rows[2][0], matrix_rows[2][1], matrix_rows[2][2], matrix_rows[2][3]],
    ]

    tbl = Table(table_data, hAlign="LEFT", colWidths=[26*mm, 48*mm, 48*mm, 48*mm])
    tbl.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "PP-Sans"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),

        ("BACKGROUND", (0, 0), (-1, 0), C_TABLE_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), C_ACCENT),

        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E6E2F0")),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, C_LINE),

        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),

        # subtle row shading (1st row slightly more visible)
        ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FAF8FD")),
        ("BACKGROUND", (0, 2), (-1, 2), colors.HexColor("#FFFFFF")),
        ("BACKGROUND", (0, 3), (-1, 3), colors.HexColor("#FFFFFF")),
    ]))
    story.append(tbl)
    story.append(PageBreak())

    # ------------------------
    # KEY TAKEAWAYS (separate page)
    # ------------------------
    takeaways_text = _build_key_takeaways(row1_triplet, row2_triplet)
    lines = _para_lines(takeaways_text)
    # first block "Ключевые выводы" as heading
    story.append(Paragraph("Ключевые выводы", h2))
    for b in lines[1:]:
        story.append(Paragraph(b.replace("\n", "<br/>"), base))
    story.append(PageBreak())

    # ------------------------
    # ROW 1 (separate page)
    # ------------------------
    blocks = _compose_row_section("Первый ряд — основа личности и реализации (60%)", row1_triplet, lib)
    story.append(Paragraph("Первый ряд — основа личности и реализации (60%)", h2))
    story.append(Spacer(1, 2 * mm))
    for head, text in blocks[1:]:
        story.append(Paragraph(head, h3))
        for b in _para_lines(_normalize_bullets(text)):
            story.append(Paragraph(b.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2 * mm))
        # thin accent line between sub-blocks
        story.append(Spacer(1, 1 * mm))
    story.append(PageBreak())

    # ------------------------
    # ROW 2 (separate page)
    # ------------------------
    blocks = _compose_row_section("Второй ряд — энергия и взаимодействие (30%)", row2_triplet, lib)
    story.append(Paragraph("Второй ряд — энергия и взаимодействие (30%)", h2))
    story.append(Spacer(1, 2 * mm))
    for head, text in blocks[1:]:
        story.append(Paragraph(head, h3))
        for b in _para_lines(_normalize_bullets(text)):
            story.append(Paragraph(b.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2 * mm))
    story.append(PageBreak())

    # ------------------------
    # ROW 3 (separate page)
    # ------------------------
    story.append(Paragraph("Третий ряд — зоны риска (10%)", h2))
    story.append(Spacer(1, 2 * mm))

    row3_label = " · ".join([x for x in row3_triplet if x])
    third_text = _normalize_bullets(f"""Этот ряд не предназначен для постоянной реализации.
Он включается эпизодически — как поддержка или дополнение.

В твоей матрице: {row3_label}

Перегрузка третьего ряда может приводить к:
• эмоциональной расфокусировке;
• избыточному анализу;
• потере ясности в целях.

Осознанное отношение к этим зонам позволяет сохранить ресурс и не распыляться.""")
    for b in _para_lines(third_text):
        story.append(Paragraph(b.replace("\n", "<br/>"), base))
    story.append(PageBreak())

    # ------------------------
    # FINAL PICTURE (separate page)
    # ------------------------
    story.append(Paragraph("Итоговая картина", h2))
    final_text = _normalize_bullets(f"""Твоя система устроена вокруг первого ряда: { " · ".join([x for x in row1_triplet if x]) }.
Ты наиболее устойчив и эффективен, когда держишь фокус на первом ряду, подпитываешься через второй и не берёшь на себя лишнего из третьего.

Это не универсальный путь, а твой индивидуальный стиль реализации, при котором сохраняется энергия и появляется ощущение правильного движения.""")
    for b in _para_lines(final_text):
        story.append(Paragraph(b.replace("\n", "<br/>"), base))
    story.append(PageBreak())

    # ------------------------
    # METHODOLOGY (separate page) — moved to end as you asked
    # ------------------------
    story.append(Paragraph("О методологии", h2))
    methodology = _normalize_bullets("""В основе данного отчёта лежит методология Системы Потенциалов Человека (СПЧ) — прикладной аналитический подход к изучению природы мышления, мотивации и способов реализации человека.

Методология СПЧ рассматривает человека не через типы личности или поведенческие роли, а через внутренние механизмы восприятия информации, включения в действие и удержания результата.
Ключевой принцип системы — каждый человек реализуется наиболее эффективно, когда опирается на свои природные способы мышления и распределяет внимание между уровнями реализации осознанно.

Первоначально СПЧ разрабатывалась как офлайн-метод для глубинных разборов и практической работы с людьми.
В рамках данной диагностики методология адаптирована в формат онлайн-анализа с сохранением логики системы, структуры интерпретации и фокуса на прикладную ценность результата.

Важно: СПЧ не является психометрическим тестом в классическом понимании и не претендует на медицинскую или клиническую диагностику.
Это карта внутренних механизмов, позволяющая точнее выстраивать решения, развитие и профессиональную реализацию без насилия над собой.""")
    for b in _para_lines(methodology):
        story.append(Paragraph(b.replace("\n", "<br/>"), base))
    story.append(PageBreak())

    # ------------------------
    # ABOUT AUTHOR (separate page) — professional, 3rd person, narrower width
    # ------------------------
    story.append(Paragraph("Об авторе", h2))

    about = _normalize_bullets("""Asselya Zhanybek — эксперт в области оценки и развития человеческого капитала, с профессиональным фокусом на проектах оценки компетенций и развития управленческих команд в национальных компаниях и европейском консалтинге, с применением психометрических инструментов.

Имеет академическую подготовку в области международного развития.
Практика сфокусирована на анализе человеческих способностей, потенциалов и механизмов реализации в профессиональном и жизненном контексте.

В работе используется методология Системы Потенциалов Человека (СПЧ) как аналитическая основа для диагностики индивидуальных способов мышления, мотивации и действий.
Методология адаптирована в формат онлайн-диагностики и персональных разборов с фокусом на прикладную ценность и устойчивые результаты.""")
    # Create a "narrow" table to constrain width without visual borders
    about_tbl = Table(
        [[Paragraph(about.replace("\n", "<br/>"), base)]],
        colWidths=[A4[0] - doc.leftMargin - doc.rightMargin - narrow_right_pad],
        hAlign="LEFT",
    )
    about_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), narrow_left_pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(Spacer(1, 2 * mm))
    story.append(about_tbl)
    story.append(PageBreak())

    # ------------------------
    # NOTES (separate page) — not empty + small disclaimer line
    # ------------------------
    story.append(Paragraph("Заметки", h2))
    story.append(Spacer(1, 2 * mm))

    # simple lined area
    for _ in range(18):
        story.append(Paragraph("______________________________________________________________", ParagraphStyle(
            "line",
            parent=subtle,
            fontName="PP-Sans",
            fontSize=10,
            leading=16,
            textColor=colors.HexColor("#B7B2C6"),
            spaceAfter=4,
        )))

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(
        "Этот отчёт предназначен для личного использования. Возвращайтесь к нему по мере изменений и принятия решений.",
        subtle,
    ))

    # build
    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
    )

    return buf.getvalue()