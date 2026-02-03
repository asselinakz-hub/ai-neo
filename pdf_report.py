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
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
import os

# ---------- Fonts (Cyrillic) ----------
_FONTS_REGISTERED = False

def _register_fonts():
    """
    Регистрирует кириллические шрифты.
    Берём из репо ./assets/fonts с твоими именами файлов.
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    here = os.path.dirname(os.path.abspath(__file__))

    # ✅ реальные имена из твоей папки (по скрину)
    regular = os.path.join(here, "assets", "fonts", "DejaVuSans.ttf")
    bold = os.path.join(here, "assets", "fonts", "DejaVuLGCSans-Bold.ttf")

    # fallback (если ты потом добавишь обычный bold под именем DejaVuSans-Bold.ttf)
    bold_alt = os.path.join(here, "assets", "fonts", "DejaVuSans-Bold.ttf")

    if not os.path.exists(regular):
        raise RuntimeError(
            f"Не найден шрифт: {regular}. "
            "Проверь assets/fonts/DejaVuSans.ttf"
        )

    if os.path.exists(bold_alt):
        bold = bold_alt
    elif not os.path.exists(bold):
        # bold не критичен — используем regular, но лучше иметь bold
        bold = regular

    # защита от “текстового” файла (когда залили через Edit)
    if os.path.getsize(regular) < 10_000:
        raise RuntimeError(f"Шрифт выглядит повреждённым (слишком маленький): {regular}")
    if os.path.getsize(bold) < 10_000:
        raise RuntimeError(f"Bold-шрифт выглядит повреждённым (слишком маленький): {bold}")

    pdfmetrics.registerFont(TTFont("SPCH-Regular", regular))
    pdfmetrics.registerFont(TTFont("SPCH-Bold", bold))

    _FONTS_REGISTERED = True

# ---------- Helpers ----------
def _strip_md(md: str) -> str:
    """Очень мягкая чистка markdown -> текст для Paragraph (без HTML-тегов)."""
    if not md:
        return ""
    # убираем маркеры кода
    md = md.replace("```", "")
    # заменим двойные пробелы/табуляции
    md = md.replace("\t", "    ")
    # убираем лишние html-теги (на всякий)
    md = re.sub(r"</?[^>]+>", "", md)
    return md.strip()


def _md_table_to_data(matrix_md: str):
    """
    Превращает markdown-таблицу (| a | b |) в data для reportlab.Table.
    Работает с твоей матрицей 3×3.
    """
    text = _strip_md(matrix_md)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # берём только строки, которые похожи на таблицу
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

    # иногда в markdown-таблице есть шапка + линия-разделитель уже пропущена — ок
    return parsed if parsed else None


def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
) -> bytes:
    """
    Делает красивый PDF:
    - обложка
    - краткая инструкция
    - сам отчёт (текст + матрица как таблица, если найдётся)
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
        spaceAfter=10,
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
    story.append(Paragraph("NEO — Диагностика потенциалов", h1))
    story.append(Paragraph(f"Персональный отчёт для: <b>{client_name}</b>", base))
    if request:
        story.append(Paragraph(f"Запрос: {request}", base))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Дата: {date.today().isoformat()}", small))
    story.append(Spacer(1, 50 * mm))

    story.append(Paragraph("Зачем нужен этот отчёт", h2))
    story.append(Paragraph(
        "Он помогает увидеть твой природный способ мышления, мотивации и реализации — "
        "без оценок и «правильно/неправильно». Это карта: где твоя сила, где ресурс, "
        "и что лучше не тащить на себе.",
        base
    ))

    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("Как читать и как использовать", h2))
    story.append(Paragraph(
        "1) Сначала посмотри на 1 ряд — это фундамент реализации.<br/>"
        "2) Затем 2 ряд — откуда берётся энергия и контакт с людьми (его нельзя превращать в обязаловку).<br/>"
        "3) 3 ряд — зона риска: что лучше делегировать или делать минимально.<br/>"
        "4) После чтения выпиши 3 инсайта и 1 действие на неделю — этого достаточно, чтобы отчёт «заработал».",
        base
    ))

    story.append(PageBreak())

    # ---------- Report body ----------
    text = client_report_text or ""
    text = _strip_md(text)

    # Попробуем вытащить матрицу как таблицу (если внутри есть markdown-таблица)
    table_data = _md_table_to_data(text)

    story.append(Paragraph("Отчёт", h2))
    story.append(Spacer(1, 2 * mm))

    if table_data:
        # рисуем таблицу матрицы красиво
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

    # основной текст — построчно, но аккуратно
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue
        # если блок — это таблица, мы уже её отрисовали, пропустим
        if "|" in b and len(b.splitlines()) <= 6:
            continue
        # Заголовки markdown (#, ##) преобразуем в h2
        if b.startswith("#"):
            title = b.lstrip("#").strip()
            story.append(Paragraph(title, h2))
            continue
        story.append(Paragraph(b.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2 * mm))

    doc.build(story)
    return buf.getvalue()