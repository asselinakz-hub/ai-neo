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
)

# ------------------------
# Paths
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGOS_DIR = os.path.join(ASSETS_DIR, "logos")

# FIX: define BRAND_DIR to avoid "name 'BRAND_DIR' is not defined"
# (минимально: у тебя лого лежат в assets/logos)
BRAND_DIR = LOGOS_DIR

# allow finding logos in dev env / streamlit / container
EXTRA_BRAND_DIRS = [
    BRAND_DIR,
    BASE_DIR,
    "/mnt/data",
]

# ------------------------
# Colors (calm, premium)
# ------------------------
C_TEXT = colors.HexColor("#121212")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")
C_ACCENT = colors.HexColor("#5B2B6C")
C_ACCENT_2 = colors.HexColor("#8C4A86")
C_SOFT_BG = colors.HexColor("#F7F5FB")
C_GRID = colors.HexColor("#E6E2F0")

# Background to reduce "вклейка" effect (soft off-white)
PAGE_BG = colors.HexColor("#FAF8F6")

# ------------------------
# Fonts (Cyrillic-safe)
#   - Body: DejaVuSans (sans)
#   - Headings: DejaVuSerif (serif) if available, else fallback to DejaVuSans
# ------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    sans = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    if not os.path.exists(sans):
        raise RuntimeError(f"Font not found: {sans}")
    if os.path.getsize(sans) < 10_000:
        raise RuntimeError(f"Font file looks corrupted: {sans}")

    serif = os.path.join(FONT_DIR, "DejaVuSerif.ttf")
    serif_use = serif if os.path.exists(serif) else sans
    if os.path.getsize(serif_use) < 10_000:
        raise RuntimeError(f"Font file looks corrupted: {serif_use}")

    pdfmetrics.registerFont(TTFont("PP-Sans", sans))
    pdfmetrics.registerFont(TTFont("PP-Serif", serif_use))

    _FONTS_REGISTERED = True

# ------------------------
# Background
# ------------------------
def _draw_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()

# ------------------------
# Logos
# ------------------------
def _find_logo(*names: str) -> str | None:
    for n in names:
        if not n:
            continue

        # absolute path
        if os.path.isabs(n) and os.path.exists(n):
            return n

        # try in known dirs
        for d in EXTRA_BRAND_DIRS:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p

    return None

# ------------------------
# Text cleanup: NO BOLD in descriptive body
# (оставляем только заголовки стилями, а не тегами)
# ------------------------
_MD_BOLD_RE = re.compile(r"(\*\*|__)(.+?)(\*\*|__)", re.DOTALL)
_B_TAG_RE = re.compile(r"</?b>", re.IGNORECASE)

def _clean_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("```", "")
    s = s.replace("\t", "    ")
    s = _B_TAG_RE.sub("", s)
    s = _MD_BOLD_RE.sub(lambda m: m.group(2), s)
    # убираем любые html-теги (кроме <br/>, который мы сами вставляем ниже)
    s = re.sub(r"</?[^>]+>", "", s)
    return s.strip()

def _paragraphs_1to1(text: str) -> list[str]:
    """
    1:1 разбиение: сохраняем переносы и смысл.
    Разделяем только по пустым строкам.
    """
    text = (text or "").strip()
    if not text:
        return []
    # normalize newlines
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", text)
    return [b.strip() for b in blocks if b.strip()]

# ------------------------
# Extract methodology/author from engine text (to avoid duplication)
# ------------------------
def _split_engine_for_last_page(engine_text: str) -> tuple[str, str, str]:
    """
    Returns: (main_text_without_method_author, methodology_text, author_text)
    If not found -> empty strings for those sections.
    """
    t = _clean_text(engine_text or "")
    if not t:
        return "", "", ""

    t = t.replace("\r\n", "\n").replace("\r", "\n")

    # locate headings (case-insensitive)
    m_meth = re.search(r"^.*О методологии.*$", t, flags=re.IGNORECASE | re.MULTILINE)
    m_auth = re.search(r"^.*Об авторе.*$", t, flags=re.IGNORECASE | re.MULTILINE)

    if not m_meth and not m_auth:
        return t, "", ""

    # Determine order and slicing
    idx_m = m_meth.start() if m_meth else None
    idx_a = m_auth.start() if m_auth else None

    # main ends at first of (meth/auth)
    cut_points = [i for i in [idx_m, idx_a] if i is not None]
    main_end = min(cut_points) if cut_points else len(t)
    main_text = t[:main_end].strip()

    methodology = ""
    author = ""

    if m_meth:
        meth_start = m_meth.start()
        meth_end = len(t)
        if m_auth and idx_a is not None and idx_a > meth_start:
            meth_end = idx_a
        methodology = t[meth_start:meth_end].strip()

    if m_auth:
        auth_start = m_auth.start()
        auth_end = len(t)
        author = t[auth_start:auth_end].strip()

    # remove extracted parts from main_text if somehow duplicated
    for part in (methodology, author):
        if part and main_text:
            main_text = main_text.replace(part, "").strip()

    return main_text, methodology, author

# ------------------------
# Footer
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials"):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Sans", 9)
    canvas.drawString(doc.leftMargin, y + 2, brand_name)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Sans", 9)
    canvas.drawRightString(A4[0] - doc.rightMargin, y + 2, str(doc.page))

    canvas.restoreState()

# ------------------------
# Small visual helper (title + line)
# ------------------------
def _title(story, text: str, style_title: ParagraphStyle):
    story.append(Paragraph(text, style_title))
    t = Table([[""]], colWidths=[160 * mm], rowHeights=[1])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, C_LINE)]))
    story.append(Spacer(1, 2 * mm))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

def _as_date_str(d: date | str | None) -> str:
    if not d:
        return date.today().strftime("%d.%m.%Y")
    if isinstance(d, date):
        return d.strftime("%d.%m.%Y")
    return str(d)

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

    # Body typography (premium, breathable) — no bold in content
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Sans",
        fontSize=11.5,
        leading=18,            # ~1.55
        textColor=C_TEXT,
        spaceAfter=10,
        alignment=TA_LEFT,
    )

    small = ParagraphStyle(
        "small",
        parent=base,
        fontSize=10.5,
        leading=16,
        textColor=C_MUTED,
        spaceAfter=8,
    )

    # Headings: serif, NOT bold
    h1_sub = ParagraphStyle(
        "h1_sub",
        parent=base,
        fontName="PP-Serif",
        fontSize=13.5,
        leading=20,
        textColor=C_ACCENT_2,
        alignment=TA_CENTER,
        spaceAfter=10,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="PP-Serif",
        fontSize=16,
        leading=22,
        textColor=C_ACCENT,
        spaceBefore=2,
        spaceAfter=2,
    )

    story = []

    # =========================
    # PAGE 1: FIXED (1:1 as you approved)
    # =========================
    story.append(Spacer(1, 2 * mm))

    # Logo MAIN (smaller)
    logo_main = _find_logo("logo_main.png", "logo_main.PNG", "logo_main.jpg", "logo_main.JPG")
    if logo_main:
        try:
            img = Image(logo_main)
            img._restrictSize(28 * mm, 28 * mm)  # уменьшено
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 4 * mm))
        except Exception:
            pass

    story.append(Paragraph("Индивидуальный отчёт по системе потенциалов человека", h1_sub))

    info = [
        f"Для: {client_name}",
        f"Запрос: {request}" if request else None,
        f"Дата: {_as_date_str(report_date)}",
    ]
    for line in [x for x in info if x]:
        story.append(Paragraph(line, small))

    story.append(Spacer(1, 4 * mm))

    _title(story, "Введение", h2)
    intro_text = (
        "Этот отчёт — результат индивидуальной диагностики, направленной на выявление природного способа мышления, мотивации и реализации.<br/>"
        "Он не описывает качества характера и не даёт оценок личности.<br/>"
        "Его задача — показать, как именно у тебя устроен внутренний механизм, через который ты принимаешь решения, расходуешь энергию и достигаешь результата.<br/><br/>"
        "Практическая ценность отчёта в том, что он:<br/>"
        "• помогает точнее понимать себя и свои реакции;<br/>"
        "• снижает внутренние конфликты между «хочу», «надо» и «делаю»;<br/>"
        "• даёт ясность, где стоит держать фокус, а где — не перегружать себя."
    )
    story.append(Paragraph(intro_text, base))

    _title(story, "Структура внимания и распределение энергии", h2)
    attention_text = (
        "В основе интерпретации лежит матрица потенциалов 3×3, где каждый ряд выполняет свою функцию.<br/><br/>"
        "• 1 ряд — 60% фокуса внимания. Основа личности, способ реализации и создания ценности.<br/>"
        "• 2 ряд — 30% фокуса внимания. Источник энергии, восстановления и живого контакта с людьми.<br/>"
        "• 3 ряд — 10% фокуса внимания. Зоны риска и перегруза.<br/><br/>"
        "Такое распределение позволяет сохранить внутренний баланс и не тратить ресурс на задачи, которые не соответствуют твоей природе."
    )
    story.append(Paragraph(attention_text, base))

    story.append(PageBreak())

    # =========================
    # MAIN CONTENT: 1:1 as engine (cr)
    # but remove methodology/author from the flow to avoid duplicates
    # =========================
    main_text, meth_text, author_text = _split_engine_for_last_page(client_report_text or "")
    main_blocks = _paragraphs_1to1(main_text)

    for block in main_blocks:
        # 1:1: keep line breaks inside a block
        story.append(Paragraph(block.replace("\n", "<br/>"), base))

    story.append(PageBreak())

    # =========================
    # LAST PAGE: Methodology + Author
    # + disclaimer moved here
    # =========================
    _title(story, "О методологии", h2)
    if meth_text.strip():
        for block in _paragraphs_1to1(meth_text):
            story.append(Paragraph(block.replace("\n", "<br/>"), base))

    _title(story, "Об авторе", h2)
    if author_text.strip():
        for block in _paragraphs_1to1(author_text):
            story.append(Paragraph(block.replace("\n", "<br/>"), base))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Этот отчёт предназначен для личного использования. Возвращайтесь к нему по мере изменений и принятия решений.",
        small
    ))

    # ------------------------
    # Build
    # ------------------------
    doc.build(
        story,
        onFirstPage=lambda c, d: (_draw_background(c, d), _draw_footer(c, d, brand_name=brand_name)),
        onLaterPages=lambda c, d: (_draw_background(c, d), _draw_footer(c, d, brand_name=brand_name)),
    )

    return buf.getvalue()