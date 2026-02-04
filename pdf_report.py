# pdf_report.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
from io import BytesIO
from datetime import date, datetime

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
# Paths (repo structure)
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
C_LINE = colors.HexColor("#D8D2E6")      # soft lavender-gray
C_ACCENT = colors.HexColor("#5B2B6C")    # deep plum
C_ACCENT_2 = colors.HexColor("#8C4A86")  # muted mauve

# ------------------------
# Typography targets
#   Headings: Serif Regular
#   Body: Sans
# ------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    """
    Registers:
      - Body sans: DejaVuSans.ttf (Cyrillic-safe)
      - Head serif: DejaVuSerif.ttf (if present), else fallback to DejaVuSans

    You can add these files to assets/fonts:
      - DejaVuSans.ttf
      - DejaVuSans-Bold.ttf (optional)
      - DejaVuSerif.ttf (recommended)
      - DejaVuSerif-Italic.ttf (optional)
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    # Body font (sans)
    sans_regular = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    sans_bold = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
    if not os.path.exists(sans_regular):
        raise RuntimeError(f"Font not found: {sans_regular}")
    if os.path.getsize(sans_regular) < 10_000:
        raise RuntimeError(f"Font file looks corrupted: {sans_regular}")

    pdfmetrics.registerFont(TTFont("PP-Body", sans_regular))

    # "Bold" is not used for body, but keep registered for safety if needed
    if os.path.exists(sans_bold) and os.path.getsize(sans_bold) > 10_000:
        pdfmetrics.registerFont(TTFont("PP-Body-Bold", sans_bold))
    else:
        pdfmetrics.registerFont(TTFont("PP-Body-Bold", sans_regular))

    # Headings (serif)
    serif_regular = os.path.join(FONT_DIR, "DejaVuSerif.ttf")
    if os.path.exists(serif_regular) and os.path.getsize(serif_regular) > 10_000:
        pdfmetrics.registerFont(TTFont("PP-Head", serif_regular))
    else:
        # fallback to sans if serif not available
        pdfmetrics.registerFont(TTFont("PP-Head", sans_regular))

    _FONTS_REGISTERED = True


# ------------------------
# Helpers
# ------------------------
def _strip_rich(text: str) -> str:
    """
    Removes markdown code fences, tabs, and HTML tags (<b>, etc.)
    because you requested no bold in body text.
    """
    if not text:
        return ""
    text = text.replace("```", "")
    text = text.replace("\t", "    ")
    text = re.sub(r"</?[^>]+>", "", text)  # remove html tags
    return text.strip()

def _safe_brand_logo(brand_logo_path: str | None = None) -> str | None:
    """
    Finds logo in:
      1) explicit absolute path (if provided)
      2) assets/brand common filenames
    """
    if brand_logo_path and os.path.exists(brand_logo_path):
        return brand_logo_path

    candidates = [
        "logo_main.png", "logo_main.jpg", "logo_main.jpeg",
        "logo_horizontal.png", "logo_horizontal.jpg", "logo_horizontal.jpeg",
        "logo_light.png", "logo_light.jpg", "logo_light.jpeg",
        "logo_mark.png", "logo_mark.jpg", "logo_mark.jpeg",
    ]
    for fn in candidates:
        p = os.path.join(BRAND_DIR, fn)
        if os.path.exists(p):
            return p
    return None

def _format_date(d: date | datetime | None) -> str:
    if d is None:
        return date.today().strftime("%d.%m.%Y")
    if isinstance(d, datetime):
        d = d.date()
    return d.strftime("%d.%m.%Y")

def _split_paragraphs(text: str) -> list[str]:
    """
    Enforces “premium воздух”: break into smaller paragraphs,
    avoid walls of text. We treat blank lines as paragraph breaks.
    """
    text = _strip_rich(text)
    blocks = [b.strip() for b in re.split(r"\n\s*\n", text) if b.strip()]
    return blocks

def _maybe_bullets(block: str) -> list[str] | None:
    """
    Detects bullet-like lines: "• " or "- " or "— "
    Returns list of bullet strings without marker.
    """
    lines = [l.strip() for l in block.splitlines() if l.strip()]
    bullet = []
    for l in lines:
        if l.startswith("• "):
            bullet.append(l[2:].strip())
        elif l.startswith("- "):
            bullet.append(l[2:].strip())
        elif l.startswith("— "):
            bullet.append(l[2:].strip())
        else:
            # if mixed, not a bullet block
            if bullet:
                return None
            else:
                return None
    return bullet if bullet else None

def _extract_matrix_from_text(text: str) -> list[list[str]] | None:
    """
    Fallback: if you still pass a text that contains markdown-like table.
    Expected header includes "Ряд" and 3 rows after.
    """
    t = _strip_rich(text)
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    table_lines = [l for l in lines if "|" in l]
    if len(table_lines) < 4:
        return None

    rows = []
    for l in table_lines:
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", l):
            continue
        parts = [c.strip() for c in l.strip("|").split("|")]
        rows.append(parts)

    if len(rows) < 4:
        return None

    header_idx = None
    for i, r in enumerate(rows):
        if len(r) >= 4 and r[0].lower().startswith("ряд"):
            header_idx = i
            break
    if header_idx is None:
        return None

    data = rows[header_idx + 1: header_idx + 4]
    if len(data) != 3:
        return None

    out = []
    for r in data:
        if len(r) < 4:
            return None
        out.append([r[0], r[1], r[2], r[3]])
    return out


# ------------------------
# Footer
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "PERSONAL POTENTIALS", brand_logo_path: str | None = None):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    # small logo
    logo = _safe_brand_logo(brand_logo_path)
    x = doc.leftMargin
    if logo:
        try:
            canvas.drawImage(
                logo,
                x, y - 2,
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
    canvas.setFont("PP-Body", 9)
    canvas.drawString(x, y + 2, brand_name)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Body", 9)
    canvas.drawRightString(A4[0] - doc.rightMargin, y + 2, str(doc.page))

    canvas.restoreState()


# ------------------------
# Content blocks (RU text templates)
# ------------------------
INTRO_TEXT = """Этот отчёт — результат индивидуальной диагностики, направленной на выявление природного способа мышления, мотивации и реализации.
Он не описывает качества характера и не даёт оценок личности.
Его задача — показать, как именно у тебя устроен внутренний механизм, через который ты принимаешь решения, расходуешь энергию и достигаешь результата.

Практическая ценность отчёта в том, что он:
• помогает точнее понимать себя и свои реакции;
• снижает внутренние конфликты между «хочу», «надо» и «делаю»;
• даёт ясность, где стоит держать фокус, а где — не перегружать себя.
"""

ENERGY_DIST_TEXT = """В основе интерпретации лежит матрица потенциалов 3×3, где каждый ряд выполняет свою функцию.

В твоей системе распределение внимания выглядит следующим образом:
• 1 ряд — 60% фокуса внимания. Основа личности, способ реализации и создания ценности.
• 2 ряд — 30% фокуса внимания. Источник энергии, восстановления и живого контакта с людьми.
• 3 ряд — 10% фокуса внимания. Зоны риска и перегруза.

Такое распределение позволяет сохранить внутренний баланс и не тратить ресурс на задачи, которые не соответствуют твоей природе.
"""

METHODOLOGY_TEXT = """В основе данного отчёта лежит методология Системы Потенциалов Человека (СПЧ) — прикладной аналитический подход к изучению природы мышления, мотивации и способов реализации человека.

Методология СПЧ рассматривает человека не через типы личности или поведенческие роли, а через внутренние механизмы восприятия информации, включения в действие и удержания результата.
Ключевой принцип системы — каждый человек реализуется наиболее эффективно, когда опирается на свои природные способы мышления и распределяет внимание между уровнями реализации осознанно.

Первоначально СПЧ разрабатывалась как офлайн-метод для глубинных разборов и практической работы с людьми.
В рамках данной диагностики методология адаптирована в формат онлайн-анализа с сохранением логики системы, структуры интерпретации и фокуса на прикладную ценность результата.

Важно: СПЧ не является психометрическим тестом в классическом понимании и не претендует на медицинскую или клиническую диагностику.
Это карта внутренних механизмов, позволяющая точнее выстраивать решения, развитие и профессиональную реализацию без насилия над собой.
"""

AUTHOR_TEXT_3P = """Asselya Zhanybek — эксперт в области оценки и развития человеческого капитала, с профессиональным фокусом на проектах оценки компетенций и развития управленческих команд в национальных компаниях и европейском консалтинге, с применением психометрических инструментов.

Имеет академическую подготовку в области международного развития.
Практика сфокусирована на анализе человеческих способностей, потенциалов и механизмов реализации в профессиональном и жизненном контексте.

В работе используется методология Системы Потенциалов Человека (СПЧ) как аналитическая основа для диагностики индивидуальных способов мышления, мотивации и действий. Методология адаптирована в формат онлайн-диагностики и персональных разборов с фокусом на прикладную ценность и устойчивые результаты.
"""

NOTES_FOOTER_LINE = "Этот отчёт предназначен для личного использования. Возвращайтесь к нему по мере изменений и принятия решений."


# ------------------------
# Dynamic content helpers
# ------------------------
def _default_potential_library() -> dict:
    """
    Optional: you can pass your own library from app,
    where each potential key maps to dict with 'title' and 'text'.
    """
    return {}

def _get_potential_block(potential_name: str, library: dict | None) -> tuple[str, str]:
    """
    Returns (heading, body) for a potential.
    If not found, returns minimal placeholder without bold.
    """
    lib = library or {}
    item = lib.get(potential_name) or lib.get(potential_name.lower()) or None
    if isinstance(item, dict):
        title = item.get("title") or potential_name
        body = item.get("text") or ""
        return title.strip(), _strip_rich(body)
    # fallback
    return potential_name, ""


# ------------------------
# Main builder (backward compatible)
# ------------------------
def build_client_report_pdf_bytes(
    client_report_text: str = "",
    client_name: str = "Клиент",
    request: str = "",
    brand_name: str = "PERSONAL POTENTIALS",
    subtitle: str = "Индивидуальный отчёт по системе потенциалов человека 3×3",
    report_date: date | datetime | None = None,
    matrix_rows: list[list[str]] | None = None,
    potential_library: dict | None = None,
    brand_logo_path: str | None = None,
) -> bytes:
    """
    Backward compatible:
      - old call: build_client_report_pdf_bytes(cr, client_name=..., request=..., brand_name=...)
      - new dynamic: pass matrix_rows from online diagnostics.

    matrix_rows format:
      [
        ["1 (60%)", "Рубин", "Аметист", "Цитрин"],
        ["2 (30%)", "Гранат", "Янтарь", "Шунгит"],
        ["3 (10%)", "Изумруд", "Сапфир", "Гелиодор"],
      ]
    """
    _register_fonts()

    # If matrix is not provided, try to parse from text
    if matrix_rows is None:
        matrix_rows = _extract_matrix_from_text(client_report_text)

    # If still none, we can still build report (but matrix page will show notice)
    lib = potential_library or _default_potential_library()

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

    # Body (sans)
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Body",
        fontSize=11.5,     # чуть больше среднего
        leading=18,        # ~1.55
        textColor=C_TEXT,
        spaceAfter=9,      # воздух между абзацами
        alignment=TA_LEFT,
    )

    subtle = ParagraphStyle(
        "subtle",
        parent=base,
        fontSize=10.5,
        leading=16,
        textColor=C_MUTED,
    )

    # Headings (serif regular, NOT bold)
    h1 = ParagraphStyle(
        "h1",
        parent=base,
        fontName="PP-Head",
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
        fontName="PP-Head",
        fontSize=16,
        leading=22,
        textColor=C_ACCENT,
        spaceBefore=6,
        spaceAfter=8,
    )

    h3 = ParagraphStyle(
        "h3",
        parent=base,
        fontName="PP-Head",
        fontSize=13.5,
        leading=19,
        textColor=C_ACCENT,
        spaceBefore=4,
        spaceAfter=6,
    )

    # Thin line under headings (visual accent)
    def heading_with_line(text: str, level_style: ParagraphStyle):
        return KeepTogether([
            Paragraph(text, level_style),
            Spacer(1, 1.5 * mm),
            Table([[""]], colWidths=[A4[0] - doc.leftMargin - doc.rightMargin], rowHeights=[0.6]),
        ])

    story = []

    # ------------------------
    # COVER
    # ------------------------
    logo = _safe_brand_logo(brand_logo_path)
    story.append(Spacer(1, 8 * mm))

    if logo:
        try:
            img = Image(logo)
            img._restrictSize(85 * mm, 55 * mm)
            img.hAlign = "CENTER"
            story.append(Spacer(1, 10 * mm))
            story.append(img)
            story.append(Spacer(1, 10 * mm))
        except Exception:
            # even if image fails, cover won't be blank
            story.append(Spacer(1, 8 * mm))

    story.append(Paragraph(_strip_rich(brand_name), h1))
    story.append(Paragraph(_strip_rich(subtitle), ParagraphStyle(
        "subtitle",
        parent=subtle,
        alignment=TA_CENTER,
        fontName="PP-Body",
        fontSize=11,
        textColor=C_ACCENT_2,
        spaceAfter=14,
    )))

    meta = f"Для: {client_name}<br/>"
    if request:
        meta += f"Запрос: {request}<br/>"
    meta += f"Дата: {_format_date(report_date)}"
    story.append(Paragraph(meta, base))

    story.append(PageBreak())

    # ------------------------
    # INTRO
    # ------------------------
    story.append(Paragraph("Введение", h2))
    story.append(Spacer(1, 1 * mm))
    for b in _split_paragraphs(INTRO_TEXT):
        bullets = _maybe_bullets(b)
        if bullets:
            for it in bullets:
                story.append(Paragraph(f"• {it}", base))
            story.append(Spacer(1, 2 * mm))
        else:
            story.append(Paragraph(b.replace("\n", "<br/>"), base))

    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph("Структура внимания и распределение энергии", h2))
    for b in _split_paragraphs(ENERGY_DIST_TEXT):
        bullets = _maybe_bullets(b)
        if bullets:
            for it in bullets:
                story.append(Paragraph(f"• {it}", base))
            story.append(Spacer(1, 2 * mm))
        else:
            story.append(Paragraph(b.replace("\n", "<br/>"), base))

    story.append(PageBreak())

    # ------------------------
    # MATRIX (separate page)
    # ------------------------
    story.append(Paragraph("Твоя матрица потенциалов", h2))
    story.append(Spacer(1, 4 * mm))

    if matrix_rows and len(matrix_rows) == 3:
        table_data = [
            ["Ряд", "Восприятие", "Мотивация", "Инструмент"],
            matrix_rows[0],
            matrix_rows[1],
            matrix_rows[2],
        ]
        tbl = Table(table_data, hAlign="LEFT", colWidths=[28*mm, 45*mm, 45*mm, 45*mm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "PP-Body"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),

            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F4FA")),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_ACCENT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, C_LINE),

            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E6E2F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),

            # subtle row shading for 1st row (data row index 1)
            ("BACKGROUND", (0, 1), (-1, 1), colors.HexColor("#FBFAFD")),
        ]))
        story.append(tbl)
    else:
        story.append(Paragraph(
            "Матрица не передана в генератор. Передай matrix_rows из результатов диагностики, чтобы отчёт был динамичным.",
            subtle
        ))

    story.append(PageBreak())

    # ------------------------
    # KEY TAKEAWAYS (1 page)
    # ------------------------
    story.append(Paragraph("Ключевые выводы", h2))

    if matrix_rows and len(matrix_rows) == 3:
        r1 = matrix_rows[0]
        r2 = matrix_rows[1]
        r3 = matrix_rows[2]
        # concise, non-bold, premium
        takeaways = [
            f"Твой основной фокус — первый ряд ({r1[0]}): именно здесь находится основной вектор реализации.",
            f"Энергия и восстановление поддерживаются через второй ряд ({r2[0]}), но он не должен подменять первый.",
            f"Третий ряд ({r3[0]}) важно держать как вспомогательный: перегруз здесь чаще всего ведёт к расфокусу и усталости.",
        ]
        for t in takeaways:
            story.append(Paragraph(f"• {t}", base))
    else:
        story.append(Paragraph("Передай матрицу, и здесь появятся персональные выводы.", subtle))

    story.append(PageBreak())

    # ------------------------
    # ROW SECTIONS (dynamic)
    # ------------------------
    def add_row_section(title: str, row: list[str], percent_label: str):
        # row = [row_label, perception, motivation, tool]
        story.append(Paragraph(f"{title} ({percent_label})", h2))
        story.append(Spacer(1, 2 * mm))

        row_label, p, m, t = row[0], row[1], row[2], row[3]

        # Perception
        story.append(Paragraph(f"Восприятие — {p}", h3))
        p_title, p_text = _get_potential_block(p, lib)
        if p_text:
            for b in _split_paragraphs(p_text):
                story.append(Paragraph(b.replace("\n", "<br/>"), base))
        else:
            story.append(Paragraph("Описание этого потенциала подставляется из библиотеки интерпретаций.", subtle))

        story.append(Spacer(1, 2 * mm))

        # Motivation
        story.append(Paragraph(f"Мотивация — {m}", h3))
        m_title, m_text = _get_potential_block(m, lib)
        if m_text:
            for b in _split_paragraphs(m_text):
                story.append(Paragraph(b.replace("\n", "<br/>"), base))
        else:
            story.append(Paragraph("Описание этого потенциала подставляется из библиотеки интерпретаций.", subtle))

        story.append(Spacer(1, 2 * mm))

        # Tool
        story.append(Paragraph(f"Инструмент — {t}", h3))
        t_title, t_text = _get_potential_block(t, lib)
        if t_text:
            for b in _split_paragraphs(t_text):
                story.append(Paragraph(b.replace("\n", "<br/>"), base))
        else:
            story.append(Paragraph("Описание этого потенциала подставляется из библиотеки интерпретаций.", subtle))

        story.append(PageBreak())

    if matrix_rows and len(matrix_rows) == 3:
        add_row_section("ПЕРВЫЙ РЯД — ОСНОВА ЛИЧНОСТИ И РЕАЛИЗАЦИИ", matrix_rows[0], "60%")
        add_row_section("ВТОРОЙ РЯД — ЭНЕРГИЯ И ВЗАИМОДЕЙСТВИЕ", matrix_rows[1], "30%")

        # Third row: shorter, risk zone
        story.append(Paragraph("ТРЕТИЙ РЯД — ЗОНЫ РИСКА (10%)", h2))
        story.append(Spacer(1, 2 * mm))
        third = matrix_rows[2]
        story.append(Paragraph(f"{third[1]} · {third[2]} · {third[3]}", h3))
        story.append(Paragraph(
            "Этот ряд не предназначен для постоянной реализации. Он включается эпизодически — как поддержка или дополнение. "
            "Осознанное отношение к этим зонам помогает сохранить ресурс и не распыляться.",
            base
        ))
        story.append(PageBreak())

        # Summary picture
        story.append(Paragraph("Итоговая картина", h2))
        story.append(Paragraph(
            "Твоя система устроена вокруг твоего первого ряда — там находятся основная устойчивость и стиль реализации. "
            "Второй ряд поддерживает ресурс и контакт, а третий лучше держать как вспомогательный, чтобы избегать перегруза.",
            base
        ))
        story.append(PageBreak())
    else:
        story.append(Paragraph("Нет матрицы — невозможно собрать динамические блоки рядов.", subtle))
        story.append(PageBreak())

    # ------------------------
    # Methodology (end)
    # ------------------------
    story.append(Paragraph("О методологии", h2))
    for b in _split_paragraphs(METHODOLOGY_TEXT):
        story.append(Paragraph(b.replace("\n", "<br/>"), base))
    story.append(PageBreak())

    # ------------------------
    # About author (end, 60-70% width feel)
    # ------------------------
    story.append(Paragraph("Об авторе", h3))
    # make narrower block via a table with two columns: text + empty space
    about_paras = _split_paragraphs(AUTHOR_TEXT_3P)
    about_flow = []
    for b in about_paras:
        about_flow.append(Paragraph(b.replace("\n", "<br/>"), base))
    about_table = Table([[about_flow, ""]], colWidths=[120*mm, (A4[0]-doc.leftMargin-doc.rightMargin-120*mm)])
    about_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(Spacer(1, 3 * mm))
    story.append(about_table)
    story.append(PageBreak())

    # ------------------------
    # Notes (last page not empty)
    # ------------------------
    story.append(Paragraph("Заметки", h2))
    story.append(Spacer(1, 4 * mm))

    # draw lines for notes using a 1-col table with repeated empty rows
    lines = [[""] for _ in range(18)]
    notes_tbl = Table(lines, colWidths=[A4[0] - doc.leftMargin - doc.rightMargin])
    notes_tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, colors.HexColor("#E6E2F0")),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(notes_tbl)
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(NOTES_FOOTER_LINE, subtle))

    # Build PDF
    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name, brand_logo_path=brand_logo_path),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name, brand_logo_path=brand_logo_path),
    )

    return buf.getvalue()