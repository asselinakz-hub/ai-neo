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
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


# =========================
# Fonts (Cyrillic) — YOUR FILE NAMES
# =========================
_FONTS_REGISTERED = False

def _register_fonts():
    """
    Регистрирует кириллические шрифты из ./assets/fonts
    Под твои имена файлов:
      - DejaVuSans.ttf
      - DejaVuLGCSans-Bold.ttf
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    here = os.path.dirname(os.path.abspath(__file__))
    font_dir = os.path.join(here, "assets", "fonts")

    regular = os.path.join(font_dir, "DejaVuSans.ttf")
    bold = os.path.join(font_dir, "DejaVuLGCSans-Bold.ttf")

    if not os.path.exists(regular):
        raise RuntimeError(f"Не найден шрифт: {regular}")

    if not os.path.exists(bold):
        # Bold не обязателен — используем regular
        bold = regular

    # регистрируем шрифты под внутренними именами
    pdfmetrics.registerFont(TTFont("SPCH-Regular", regular))
    pdfmetrics.registerFont(TTFont("SPCH-Bold", bold))

    _FONTS_REGISTERED = True


# =========================
# Helpers
# =========================
def _strip_md(md: str) -> str:
    """Мягкая чистка markdown -> текст для Paragraph."""
    if not md:
        return ""
    md = md.replace("```", "")
    md = md.replace("\t", "    ")
    md = re.sub(r"</?[^>]+>", "", md)  # убираем html-теги на всякий
    return md.strip()


def _md_table_to_data(text_md: str):
    """
    Превращает markdown-таблицу (| a | b |) в data для reportlab.Table.
    """
    text = _strip_md(text_md)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows = [l for l in lines if "|" in l]

    if not rows:
        return None

    parsed = []
    for r in rows:
        # пропускаем разделитель |---|
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", r):
            continue
        parts = [c.strip() for c in r.strip("|").split("|")]
        parsed.append(parts)

    return parsed if parsed else None


# =========================
# Main builder
# =========================
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
    brand_title: str = "NEO — Диагностика потенциалов",
) -> bytes:
    """
    Делает PDF:
    - обложка
    - краткая инструкция
    - отчёт (текст + матрица как таблица, если найдётся)
    """
    _register_fonts()

    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="SPCH Report",
        author="NEO Диагностика",
    )

    styles = getSampleStyleSheet()

    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="SPCH-Regular",
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#111111"),
        spaceAfter=6,
    )

    h1 = ParagraphStyle(
        "h1",
        parent=base,
        fontName="SPCH-Bold",
        fontSize=20,
        leading=24,
        alignment=TA_CENTER,
        spaceAfter=12,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="SPCH-Bold",
        fontSize=14,
        leading=18,
        spaceBefore=10,
        spaceAfter=6,
    )

    small = ParagraphStyle(
        "small",
        parent=base,
        fontSize=9.5,
        leading=13,
        textColor=colors.HexColor("#333333"),
    )

    story = []

    # ---------- Cover ----------
    story.append(Spacer(1, 18 * mm))
    story.append(Paragraph(brand_title, h1))
    story.append(Paragraph(f"Персональный отчёт для: <b>{client_name}</b>", base))
    if request:
        story.append(Paragraph(f"Запрос: {request}", base))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f"Дата: {date.today().isoformat()}", small))
    story.append(Spacer(1, 28 * mm))

    story.append(Paragraph("Зачем нужен этот отчёт", h2))
    story.append(Paragraph(
        "Он помогает увидеть твой природный способ мышления, мотивации и реализации — "
        "без оценок и «правильно/неправильно». Это карта: где твоя сила, где ресурс, "
        "и что лучше не тащить на себе.",
        base
    ))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Как читать и как использовать", h2))
    story.append(Paragraph(
        "1) Сначала посмотри на 1 ряд — это фундамент реализации.<br/>"
        "2) Затем 2 ряд — откуда берётся энергия и контакт с людьми (его нельзя превращать в обязаловку).<br/>"
        "3) 3 ряд — зона риска: что лучше делегировать или делать минимально.<br/>"
        "4) Выпиши 3 инсайта и 1 действие на неделю — этого достаточно, чтобы отчёт «заработал».",
        base
    ))

    story.append(PageBreak())

    # ---------- Report body ----------
    text = _strip_md(client_report_text or "")

    table_data = _md_table_to_data(text)

    story.append(Paragraph("Отчёт", h2))
    story.append(Spacer(1, 2 * mm))

    if table_data:
        tbl = Table(table_data, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "SPCH-Regular"),
            ("FONTSIZE", (0, 0), (-1, -1), 10.5),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F2F4F7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111111")),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D5DD")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 6 * mm))

    # основной текст
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue
        # если это таблица — мы её уже нарисовали
        if "|" in b and len(b.splitlines()) <= 10:
            continue
        # markdown headings
        if b.startswith("#"):
            title = b.lstrip("#").strip()
            story.append(Paragraph(title, h2))
            continue

        story.append(Paragraph(b.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2 * mm))

    doc.build(story)
    return buf.getvalue()