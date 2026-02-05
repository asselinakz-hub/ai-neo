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
from reportlab.lib.utils import ImageReader

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
# Paths
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGOS_DIR = os.path.join(ASSETS_DIR, "logos")

# brand dir fix (раньше падало из-за BRAND_DIR)
BRAND_DIR = LOGOS_DIR

# allow finding assets in dev env / streamlit / container
EXTRA_BRAND_DIRS = [
    LOGOS_DIR,
    BRAND_DIR,
    ASSETS_DIR,
    BASE_DIR,
    "/mnt/data",
]

# ------------------------
# Colors / Background
# ------------------------
C_PAGE_BG = colors.HexColor("#FAF8F6")  # фон как у лого (мягкий off-white)

C_TEXT = colors.HexColor("#121212")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")

C_ACCENT = colors.HexColor("#5B2B6C")
C_ACCENT_2 = colors.HexColor("#8C4A86")

C_SOFT_BG = colors.HexColor("#F4F1F7")
C_GRID = colors.HexColor("#E3DDEA")

# ------------------------
# Fonts (based on your actual files)
# ------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    body_regular = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    body_bold = os.path.join(FONT_DIR, "DejaVuLGCSans-Bold.ttf")  # <-- есть у тебя
    playfair = os.path.join(FONT_DIR, "Playfair-Display-Regular.ttf")  # <-- есть у тебя

    if not os.path.exists(body_regular):
        raise RuntimeError(f"Font not found: {body_regular}")
    if not os.path.exists(body_bold):
        # fallback to regular if bold missing
        body_bold = body_regular

    # Playfair optional
    if not os.path.exists(playfair):
        playfair = body_regular

    # corruption guards
    for p in [body_regular, body_bold, playfair]:
        if os.path.exists(p) and os.path.getsize(p) < 10_000:
            raise RuntimeError(f"Font file looks corrupted: {p}")

    pdfmetrics.registerFont(TTFont("PP-Body", body_regular))
    pdfmetrics.registerFont(TTFont("PP-Body-Bold", body_bold))
    pdfmetrics.registerFont(TTFont("PP-Head", playfair))

    _FONTS_REGISTERED = True

# ------------------------
# Background painter
# ------------------------
def _draw_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_PAGE_BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()

# ------------------------
# Footer (no logo, only brand + page)
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials"):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Body", 9)
    canvas.drawString(doc.leftMargin, y + 2, brand_name)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Body", 9)
    canvas.drawRightString(A4[0] - doc.rightMargin, y + 2, str(doc.page))

    canvas.restoreState()

def _on_page(canvas, doc, brand_name: str):
    _draw_background(canvas, doc)
    _draw_footer(canvas, doc, brand_name=brand_name)

# ------------------------
# Logo finder + safe image (keep ratio)
# ------------------------
def _find_asset(*names: str) -> str | None:
    for n in names:
        if not n:
            continue
        if os.path.isabs(n) and os.path.exists(n):
            return n
        for d in EXTRA_BRAND_DIRS:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p
    return None

def _img_keep_ratio(path: str, target_w_mm: float) -> Image:
    ir = ImageReader(path)
    w_px, h_px = ir.getSize()
    target_w = target_w_mm * mm
    target_h = target_w * (h_px / float(w_px))
    img = Image(path, width=target_w, height=target_h)
    img.hAlign = "CENTER"
    return img

# ------------------------
# Preserve bold from engine:
# - keep <b>..</b>
# - convert **..** to <b>..</b>
# - minimal sanitation for ReportLab Paragraph
# ------------------------
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)

def _escape_for_paragraph(s: str) -> str:
    # keep reportlab markup tags <b> <br/> only
    s = s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    # restore allowed tags
    s = s.replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>")
    s = s.replace("&lt;br/&gt;", "<br/>").replace("&lt;br&gt;", "<br/>")
    return s

def _engine_to_paragraph_html(raw: str) -> str:
    if not raw:
        return ""

    t = raw.replace("\r\n", "\n").replace("\r", "\n")

    # normalize bullets: keep as lines
    # convert markdown bold to <b>
    t = _MD_BOLD_RE.sub(lambda m: f"<b>{m.group(1).strip()}</b>", t)

    # allow <b> tags from engine; later we escape and restore allowed tags
    # convert blank lines to paragraph separators outside
    # convert single line breaks to <br/>
    t = t.strip()
    t = t.replace("\t", "    ")

    # keep line breaks
    t = t.replace("\n", "<br/>")
    t = _escape_for_paragraph(t)
    return t

# ------------------------
# Markdown table parser (pipes)
# ------------------------
def _md_table_to_data(text: str):
    if not text:
        return None

    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # grab first contiguous block with pipes
    table_lines = []
    started = False
    for l in lines:
        if "|" in l:
            table_lines.append(l)
            started = True
        elif started:
            break

    if not table_lines:
        return None

    parsed = []
    for r in table_lines:
        # skip separator rows
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", r):
            continue
        parts = [c.strip() for c in r.strip("|").split("|")]
        if len(parts) >= 2:
            parsed.append(parts)

    # require header-ish row and at least 2 rows
    return parsed if len(parsed) >= 2 else None

def _build_matrix_table(table_data: list[list[str]], base_style: ParagraphStyle) -> Table:
    cell_style = ParagraphStyle(
        "cell",
        parent=base_style,
        fontName="PP-Body",
        fontSize=11,
        leading=17,
        spaceAfter=0,
    )
    head_style = ParagraphStyle(
        "head_cell",
        parent=cell_style,
        textColor=C_ACCENT,
    )

    cells = []
    for r_i, row in enumerate(table_data):
        new_row = []
        for c in row:
            txt = (c or "").strip()
            # allow bold inside cells too
            html = _engine_to_paragraph_html(txt)
            new_row.append(Paragraph(html, head_style if r_i == 0 else cell_style))
        cells.append(new_row)

    usable_w = A4[0] - (18*mm + 18*mm)  # margins below in doc
    # if 4 cols, use nice proportions; else equal widths
    if cells and len(cells[0]) == 4:
        col_widths = [0.14*usable_w, 0.29*usable_w, 0.29*usable_w, 0.28*usable_w]
    else:
        n = len(cells[0]) if cells else 3
        col_widths = [usable_w / float(n)] * n

    tbl = Table(cells, colWidths=col_widths, hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), C_SOFT_BG),
        ("GRID", (0, 0), (-1, -1), 0.45, C_GRID),

        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
    ]))
    return tbl

# ------------------------
# Static methodology + author (your exact text)
# ------------------------
METHODOLOGY_AND_AUTHOR_TEXT = """О методологии

В основе данного отчёта лежит методология Системы Потенциалов Человека (СПЧ) — прикладной аналитический подход к изучению природы мышления, мотивации и способов реализации человека.

Методология СПЧ рассматривает человека не через типы личности или поведенческие роли, а через внутренние механизмы восприятия информации, включения в действие и удержания результата.
Ключевой принцип системы — каждый человек реализуется наиболее эффективно, когда опирается на свои природные способы мышления и распределяет внимание между уровнями реализации осознанно.

Первоначально СПЧ разрабатывалась как офлайн-метод для глубинных разборов и практической работы с людьми.
В рамках данной диагностики методология адаптирована в формат онлайн-анализа с сохранением логики системы, структуры интерпретации и фокуса на прикладную ценность результата.

Важно: СПЧ не является психометрическим тестом в классическом понимании и не претендует на медицинскую или клиническую диагностику.
Это карта внутренних механизмов, позволяющая точнее выстраивать решения, развитие и профессиональную реализацию без насилия над собой.

⸻

Об авторе

Asselya Zhanybek — эксперт в области оценки и развития человеческого капитала, с профессиональным фокусом на проектах оценки компетенций и развития управленческих команд в национальных компаниях и европейском консалтинге, с применением психометрических инструментов.

Имеет академическую подготовку в области международного развития.
Практика сфокусирована на анализе человеческих способностей, потенциалов и механизмов реализации в профессиональном и жизненном контексте.

В работе используется методология Системы Потенциалов Человека (СПЧ) как аналитическая основа для диагностики индивидуальных способов мышления, мотивации и действий. Методология адаптирована в формат онлайн-диагностики и персональных разборов с фокусом на прикладную ценность и устойчивые результаты.
"""

# ------------------------
# Main builder
# ------------------------
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
    brand_name: str = "Personal Potentials",
    report_date: date | str | None = None,
) -> bytes:
    _register_fonts()

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

    # Airy body
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Body",
        fontSize=11.5,
        leading=20,           # больше воздуха
        textColor=C_TEXT,
        spaceAfter=12,
        alignment=TA_LEFT,
    )

    small = ParagraphStyle(
        "small",
        parent=base,
        fontSize=10.5,
        leading=18,
        textColor=C_MUTED,
        spaceAfter=10,
    )

    h_title = ParagraphStyle(
        "h_title",
        parent=base,
        fontName="PP-Head",
        fontSize=18,
        leading=24,
        textColor=C_ACCENT,
        alignment=TA_CENTER,
        spaceAfter=6,
    )

    h_meta = ParagraphStyle(
        "h_meta",
        parent=base,
        fontName="PP-Body",
        fontSize=10.5,
        leading=16,
        textColor=C_MUTED,
        alignment=TA_CENTER,
        spaceAfter=4,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="PP-Body-Bold",
        fontSize=13.5,
        leading=18,
        textColor=C_ACCENT,
        spaceBefore=10,
        spaceAfter=6,
    )

    story = []

    # =========================================================
    # PAGE 1: LOGO + META + ENGINE REPORT (no custom intro)
    # =========================================================
    logo_main = _find_asset("logo_main.png", "logo_main.PNG", os.path.join(LOGOS_DIR, "logo_main.png"))
    if logo_main:
        # bigger, keep ratio (no stretching)
        story.append(Spacer(1, 4 * mm))
        story.append(_img_keep_ratio(logo_main, target_w_mm=80))
        story.append(Spacer(1, 6 * mm))
    else:
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(brand_name, h_title))
        story.append(Spacer(1, 4 * mm))

    story.append(Paragraph("Индивидуальный отчёт по системе потенциалов человека 3×3", h_meta))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(f"Для: {client_name}", h_meta))
    if request:
        story.append(Paragraph(f"Запрос: {request}", h_meta))

    if report_date is None:
        date_str = date.today().strftime("%d.%m.%Y")
    elif isinstance(report_date, date):
        date_str = report_date.strftime("%d.%m.%Y")
    else:
        date_str = str(report_date)

    story.append(Paragraph(f"Дата: {date_str}", h_meta))
    story.append(Spacer(1, 8 * mm))

    engine_text = (client_report_text or "").strip()

    # Render matrix table nicely IF engine contains markdown table
    table_data = _md_table_to_data(engine_text)
    if table_data:
        story.append(Paragraph("Твоя матрица потенциалов", h2))
        story.append(Spacer(1, 2 * mm))
        story.append(_build_matrix_table(table_data, base))
        story.append(Spacer(1, 10 * mm))

        # Remove the table block from printed text to avoid duplication:
        # remove contiguous pipe-lines block
        lines = engine_text.splitlines()
        out_lines = []
        in_tbl = False
        started = False
        for ln in lines:
            if "|" in ln:
                in_tbl = True
                started = True
                continue
            if started and in_tbl and ln.strip() == "":
                in_tbl = False
                continue
            if not in_tbl:
                out_lines.append(ln)
        engine_text_no_table = "\n".join(out_lines).strip()
    else:
        engine_text_no_table = engine_text

    # Print engine text as-is (preserve **bold** and <b>)
    # Split into paragraphs by blank lines
    blocks = re.split(r"\n\s*\n", engine_text_no_table)
    for b in blocks:
        b = b.strip()
        if not b:
            continue

        # Simple heuristic: headings in engine often uppercase or start with digits/keywords.
        # But we do NOT rewrite content, only style if it looks like a heading.
        is_heading = (
            len(b) < 90
            and (b.isupper() or b.startswith("1 РЯД") or b.startswith("2 РЯД") or b.startswith("3 РЯД")
                 or b.startswith("ПЕРВ") or b.startswith("ВТОР") or b.startswith("ТРЕТ")
                 or b.startswith("Итоговая") or b.startswith("ИТОГ"))
        )

        if is_heading:
            story.append(Paragraph(_engine_to_paragraph_html(b), h2))
        else:
            story.append(Paragraph(_engine_to_paragraph_html(b), base))

    # =========================================================
    # LAST PAGE: METHODOLOGY + AUTHOR (static)
    # =========================================================
    story.append(PageBreak())
    # print static text with same formatting (bold preserved if any)
    for b in re.split(r"\n\s*\n", METHODOLOGY_AND_AUTHOR_TEXT.strip()):
        b = b.strip()
        if not b:
            continue
        # headings
        if b in ["О методологии", "Об авторе"]:
            story.append(Paragraph(_engine_to_paragraph_html(b), h2))
        else:
            story.append(Paragraph(_engine_to_paragraph_html(b), base))

    doc.build(
        story,
        onFirstPage=lambda c, d: _on_page(c, d, brand_name),
        onLaterPages=lambda c, d: _on_page(c, d, brand_name),
    )

    return buf.getvalue()