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

from reportlab.lib.utils import ImageReader
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

# Streamlit/Container safe search dirs (НЕ ТРЕБУЕТ BRAND_DIR)
EXTRA_BRAND_DIRS = [
    LOGOS_DIR,
    ASSETS_DIR,
    BASE_DIR,
    "/mnt/data",
]

# ------------------------
# Colors (фон под лого)
# ------------------------
C_PAGE_BG = colors.HexColor("#FAF8F6")   # мягкий фон как у лого
C_TEXT = colors.HexColor("#121212")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")
C_ACCENT = colors.HexColor("#5B2B6C")
C_GRID = colors.HexColor("#E6E2F0")
C_SOFT_BG = colors.HexColor("#F7F5FB")

# ------------------------
# Fonts (Cyrillic-safe)
# ВАЖНО: у тебя в папке Bold = DejaVuLGCSans-Bold.ttf (не DejaVuSans-Bold.ttf)
# ------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    sans = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    bold = os.path.join(FONT_DIR, "DejaVuLGCSans-Bold.ttf")
    serif = os.path.join(FONT_DIR, "Playfair-Display-Regular.ttf")  # есть у тебя

    if not os.path.exists(sans):
        raise RuntimeError(f"Font not found: {sans}")
    if not os.path.exists(bold):
        raise RuntimeError(f"Font not found: {bold}")

    pdfmetrics.registerFont(TTFont("PP-Sans", sans))
    pdfmetrics.registerFont(TTFont("PP-Sans-Bold", bold))

    # Serif: пытаемся Playfair, если вдруг не откроется — fallback на sans
    try:
        if os.path.exists(serif):
            pdfmetrics.registerFont(TTFont("PP-Serif", serif))
        else:
            pdfmetrics.registerFont(TTFont("PP-Serif", sans))
    except Exception:
        pdfmetrics.registerFont(TTFont("PP-Serif", sans))

    _FONTS_REGISTERED = True

# ------------------------
# Background
# ------------------------
def _draw_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_PAGE_BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()

# ------------------------
# Footer (без лого)
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
# Logo finder
# ------------------------
def _find_logo(*names: str) -> str | None:
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

def _scaled_image(path: str, target_width_mm: float) -> Image:
    """
    Image without stretching: keep aspect ratio.
    """
    ir = ImageReader(path)
    iw, ih = ir.getSize()
    target_w = target_width_mm * mm
    scale = target_w / float(iw)
    target_h = ih * scale
    img = Image(path, width=target_w, height=target_h)
    img.hAlign = "CENTER"
    return img

# ------------------------
# Markdown helpers: keep bold from engine
# ------------------------
_END_TOKEN_RE = re.compile(r"<<<?\s*END_CLIENT_REPORT\s*>>>?", re.IGNORECASE)
_MD_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)

def _clean_engine_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\r\n", "\n")
    s = _END_TOKEN_RE.sub("", s)        # убрать END marker
    s = s.replace("```", "")
    return s.strip()

def _md_inline_to_rl(text: str) -> str:
    """
    Minimal markdown inline:
      **bold** -> <b>bold</b>
      newlines -> <br/>
    """
    if not text:
        return ""
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = _MD_BOLD_RE.sub(r"<b>\1</b>", text)
    text = text.replace("\n", "<br/>")
    return text

def _md_table_to_data(text: str):
    """
    Finds first markdown table (pipes) and returns rows,
    plus removes that table block from text by returning (data, text_without_table).
    """
    lines = text.splitlines()

    # find first run of lines containing "|"
    start = None
    end = None
    for i, ln in enumerate(lines):
        if "|" in ln:
            start = i
            break
    if start is None:
        return None, text

    # continue until lines stop having "|"
    for j in range(start, len(lines)):
        if "|" in lines[j]:
            end = j
        else:
            break
    if end is None or end < start:
        return None, text

    table_lines = [l.strip() for l in lines[start:end+1] if l.strip()]
    parsed = []
    for r in table_lines:
        # skip separator row like |---|---|
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", r):
            continue
        parts = [c.strip() for c in r.strip("|").split("|")]
        if len(parts) >= 2:
            parsed.append(parts)

    if not parsed:
        return None, text

    # remove that table from text
    new_lines = lines[:start] + lines[end+1:]
    new_text = "\n".join(new_lines).strip()

    return parsed, new_text

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

    # Air (общий стиль текста)
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Sans",
        fontSize=11.7,
        leading=19.5,
        textColor=C_TEXT,
        spaceAfter=12,
        alignment=TA_LEFT,
    )

    # (оставляю, вдруг пригодится дальше; сейчас не используем)
    meta = ParagraphStyle(
        "meta",
        parent=base,
        fontSize=10.6,
        leading=16.5,
        textColor=C_MUTED,
        alignment=TA_CENTER,
        spaceAfter=6,
    )

    # Фиолетовый жирный для "Твоя таблица потенциалов"
    h_purple_bold = ParagraphStyle(
        "h_purple_bold",
        parent=base,
        fontName="PP-Sans-Bold",
        fontSize=12.8,
        leading=18.5,
        textColor=C_ACCENT,
        spaceBefore=6,
        spaceAfter=10,
    )

    # Фиолетовые жирные заголовки движка (### ...)
    h_bold = ParagraphStyle(
        "h_bold",
        parent=base,
        fontName="PP-Sans-Bold",
        fontSize=13.3,
        leading=18.5,
        textColor=C_ACCENT,
        spaceBefore=8,
        spaceAfter=6,
    )

    story = []

    # ------------------------
    # PAGE 1: LOGO + TABLE + ENGINE REPORT (1:1)
    # ------------------------
    logo_main = _find_logo("logo_main.png", "logo_main.PNG")
    if logo_main:
        story.append(Spacer(1, 2 * mm))
        story.append(_scaled_image(logo_main, target_width_mm=70))
        story.append(Spacer(1, 6 * mm))

    engine_raw = _clean_engine_text(client_report_text or "")

    # Заголовок над таблицей
    story.append(Paragraph("Твоя таблица потенциалов", h_purple_bold))

    # Table: если есть — рисуем красиво, а из текста удаляем
    table_data, engine_wo_table = _md_table_to_data(engine_raw)

    if table_data:
        tbl = Table(table_data, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "PP-Sans"),
            ("FONTSIZE", (0, 0), (-1, -1), 11.2),
            ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),

            ("BACKGROUND", (0, 0), (-1, 0), C_SOFT_BG),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_ACCENT),

            ("GRID", (0, 0), (-1, -1), 0.4, C_GRID),

            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8 * mm))
    else:
        engine_wo_table = engine_raw

    # Печатаем текст движка абзацами (чтобы первая часть выглядела как весь остальной текст)
    lines = engine_wo_table.splitlines()

    para_buf = []

    def flush_paragraph():
        nonlocal para_buf
        if not para_buf:
            return
        txt = "\n".join(para_buf).strip()
        if txt:
            story.append(Paragraph(_md_inline_to_rl(txt), base))
        para_buf = []

    for ln in lines:
        raw = ln.rstrip()

        # пустая строка = конец абзаца
        if not raw.strip():
            flush_paragraph()
            story.append(Spacer(1, 3 * mm))
            continue

        # УБИРАЕМ "По отдельности:"
        if raw.strip().lower().startswith("по отдельности"):
            continue

        # Заголовки движка
        if raw.lstrip().startswith("###"):
            flush_paragraph()
            title_text = raw.lstrip("#").strip()
            story.append(Paragraph(_md_inline_to_rl(title_text), h_bold))
            continue

        # разделитель
        if raw.strip() in ("---", "⸻"):
            flush_paragraph()
            t = Table([[""]], colWidths=[(A4[0] - doc.leftMargin - doc.rightMargin)], rowHeights=[1])
            t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, C_LINE)]))
            story.append(Spacer(1, 2 * mm))
            story.append(t)
            story.append(Spacer(1, 4 * mm))
            continue

        # обычная строка — копим в текущий абзац
        para_buf.append(raw)

    flush_paragraph()

    # ------------------------
    # PAGE 2: METHODOLOGY + AUTHOR (static)
    # ------------------------
    story.append(PageBreak())

    story.append(Paragraph("О методологии", h_bold))
    story.append(Paragraph(_md_inline_to_rl(
        "В основе данного отчёта лежит методология Системы Потенциалов Человека (СПЧ) — прикладной аналитический подход к изучению природы мышления, мотивации и способов реализации человека.\n\n"
        "Методология СПЧ рассматривает человека не через типы личности или поведенческие роли, а через внутренние механизмы восприятия информации, включения в действие и удержания результата.\n"
        "Ключевой принцип системы — каждый человек реализуется наиболее эффективно, когда опирается на свои природные способы мышления и распределяет внимание между уровнями реализации осознанно.\n\n"
        "Первоначально СПЧ разрабатывалась как офлайн-метод для глубинных разборов и практической работы с людьми.\n"
        "В рамках данной диагностики методология адаптирована в формат онлайн-анализа с сохранением логики системы, структуры интерпретации и фокуса на прикладную ценность результата.\n\n"
        "Важно: СПЧ не является психометрическим тестом в классическом понимании и не претендует на медицинскую или клиническую диагностику.\n"
        "Это карта внутренних механизмов, позволяющая точнее выстраивать решения, развитие и профессиональную реализацию без насилия над собой."
    ), base))

    story.append(Spacer(1, 8 * mm))

    story.append(Paragraph("Интерпретация и адаптация методологии в онлайн формат", h_bold))
    story.append(Paragraph(_md_inline_to_rl(
        "Asselya Zhanybek — эксперт в области оценки и развития человеческого капитала, с профессиональным фокусом на проектах оценки компетенций и развития управленческих команд в национальных компаниях и европейском консалтинге, с применением психометрических инструментов.\n\n"
        "Имеет академическую подготовку в области международного развития.\n"
        "Практика сфокусирована на анализе человеческих способностей, потенциалов и механизмов реализации в профессиональном и жизненном контексте.\n\n"
    ), base))

    # ------------------------
    # Build
    # ------------------------
    doc.build(
        story,
        onFirstPage=lambda c, d: (_draw_background(c, d), _draw_footer(c, d, brand_name=brand_name)),
        onLaterPages=lambda c, d: (_draw_background(c, d), _draw_footer(c, d, brand_name=brand_name)),
    )

    return buf.getvalue()
