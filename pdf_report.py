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

from reportlab.lib.styles import ParagraphStyle
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

# -------------------------------------------------
# PATHS
# -------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGOS_DIR = os.path.join(ASSETS_DIR, "logos")

# -------------------------------------------------
# COLORS (под фон логотипа)
# -------------------------------------------------
PAGE_BG = colors.HexColor("#FAF8F6")      # мягкий off-white
TEXT = colors.HexColor("#1C1C1C")
MUTED = colors.HexColor("#6F6F6F")
ACCENT = colors.HexColor("#5B2B6C")       # фирменный фиолетовый
LINE = colors.HexColor("#D6CEDB")

# -------------------------------------------------
# FONTS (Unicode safe)
# -------------------------------------------------
def register_fonts():
    pdfmetrics.registerFont(
        TTFont("Body", os.path.join(FONTS_DIR, "DejaVuSans.ttf"))
    )
    pdfmetrics.registerFont(
        TTFont("Body-Bold", os.path.join(FONTS_DIR, "DejaVuSans-Bold.ttf"))
    )

# -------------------------------------------------
# BACKGROUND
# -------------------------------------------------
def draw_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()

# -------------------------------------------------
# MAIN BUILDER
# -------------------------------------------------
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str,
    request: str,
    brand_name: str = "Personal Potentials",
) -> bytes:

    register_fonts()

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=22 * mm,
        rightMargin=22 * mm,
        topMargin=22 * mm,
        bottomMargin=22 * mm,
    )

    # ---------------- STYLES ----------------
    body = ParagraphStyle(
        "body",
        fontName="Body",
        fontSize=11.5,
        leading=18,
        textColor=TEXT,
        spaceAfter=10,
    )

    header = ParagraphStyle(
        "header",
        fontName="Body-Bold",
        fontSize=13.5,
        leading=18,
        textColor=ACCENT,
        spaceBefore=14,
        spaceAfter=6,
    )

    title = ParagraphStyle(
        "title",
        fontName="Body-Bold",
        fontSize=16,
        textColor=ACCENT,
        alignment=TA_CENTER,
        spaceAfter=6,
    )

    meta = ParagraphStyle(
        "meta",
        fontName="Body",
        fontSize=10.5,
        textColor=MUTED,
        alignment=TA_CENTER,
        spaceAfter=4,
    )

    story = []

    # -------------------------------------------------
    # PAGE 1 — FIXED
    # -------------------------------------------------
    cover_blocks = []

    logo_path = os.path.join(LOGOS_DIR, "logo_mark.png")
    if os.path.exists(logo_path):
        logo = Image(logo_path, width=28 * mm, height=28 * mm)
        logo.hAlign = "CENTER"
        cover_blocks.append(logo)

    cover_blocks += [
        Spacer(1, 8),
        Paragraph("Personal Potentials", title),
        Paragraph("Индивидуальный отчёт по системе потенциалов человека 3×3", meta),
        Spacer(1, 10),
        Paragraph(f"Для: {client_name}", meta),
        Paragraph(f"Запрос: {request}", meta),
        Paragraph(f"Дата: {date.today().strftime('%d.%m.%Y')}", meta),
        Spacer(1, 14),

        Paragraph("Введение", header),
        Paragraph(
            "Этот отчёт — результат индивидуальной диагностики, направленной на выявление природного способа мышления, мотивации и реализации.
            Он не описывает качества характера и не даёт оценок личности.
            Его задача — показать, как именно у тебя устроен внутренний механизм, через который ты принимаешь решения, расходуешь энергию и достигаешь результата.

            Практическая ценность отчёта в том, что он:
        	•	помогает точнее понимать себя и свои реакции;
        	•	снижает внутренние конфликты между «хочу», «надо» и «делаю»;
        	•	даёт ясность, где стоит держать фокус, а где — не перегружать себя.
            ",
            body,
        ),

        Paragraph("Структура внимания и распределение энергии", header),
        Paragraph(
            "Структура внимания и распределение энергии

            В основе интерпретации лежит матрица потенциалов 3×3, где каждый ряд выполняет свою функцию.
            
            В твоей системе распределение внимания выглядит следующим образом:
        	1 ряд — 60% фокуса внимания
            Основа личности, способ реализации и создания ценности.
            Именно здесь находится твой главный вектор развития и устойчивости.
            2 ряд — 30% фокуса внимания
            Источник энергии, восстановления и живого контакта с людьми.
            Этот уровень поддерживает первый, но не должен его подменять.
        	3 ряд — 10% фокуса внимания
            Зоны риска и перегруза.
            Эти функции не предназначены для постоянного использования и лучше осознавать их как вспомогательные.

            Такое распределение позволяет сохранить внутренний баланс и не тратить ресурс на задачи, которые не соответствуют твоей природе.",
            body,
        ),
    ]

    story.append(KeepTogether(cover_blocks))
    story.append(PageBreak())

    # -------------------------------------------------
    # MAIN CONTENT (без разрывов)
    # -------------------------------------------------
    clean_text = re.sub(r"\n{2,}", "\n\n", client_report_text.strip())

    for block in clean_text.split("\n\n"):
        block = block.strip()
        if not block:
            continue

        if block.isupper():
            story.append(Paragraph(block, header))
        else:
            story.append(Paragraph(block.replace("\n", "<br/>"), body))

    # -------------------------------------------------
    # NOTES
    # -------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("Заметки", header))
    for _ in range(10):
        story.append(Spacer(1, 14))
        story.append(Paragraph("______________________________", body))

    story.append(
        Paragraph(
            "Этот отчёт предназначен для личного использования. "
            "Рекомендуется возвращаться к нему по мере изменений и принятия решений.",
            ParagraphStyle(
                "note",
                fontName="Body",
                fontSize=9.5,
                textColor=MUTED,
                spaceBefore=20,
            ),
        )
    )

    # -------------------------------------------------
    # METHODOLOGY + AUTHOR
    # -------------------------------------------------
    story.append(PageBreak())
    story.append(Paragraph("О методологии", header))
    story.append(Paragraph(
        "В основе данного отчёта лежит методология Системы Потенциалов Человека (СПЧ) — прикладной аналитический подход к изучению природы мышления, мотивации и способов реализации человека. Методология СПЧ рассматривает человека не через типы личности или поведенческие роли, а через внутренние механизмы восприятия информации, включения в действие и удержания результата. Ключевой принцип системы — каждый человек реализуется наиболее эффективно, когда опирается на свои природные способы мышления и распределяет внимание между уровнями реализации осознанно.
        Первоначально СПЧ разрабатывалась как офлайн-метод для глубинных разборов и практической работы с людьми. 
        
        В рамках данной диагностики методология адаптирована в формат онлайн-анализа с сохранением логики системы, структуры интерпретации и фокуса на прикладную ценность результата. 
        Важно: СПЧ не является психометрическим тестом в классическом понимании и не претендует на медицинскую или клиническую диагностику.
        Это карта внутренних механизмов, позволяющая точнее выстраивать решения, развитие и профессиональную реализацию без насилия над собой.
",
        body,
    ))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Об авторе", header))
    story.append(Paragraph(
        "Asselya Zhanybek — эксперт в области оценки и развития человеческого капитала, с профессиональным фокусом на проектах оценки компетенций и развития управленческих команд в национальных компаниях и европейском консалтинге, с применением психометрических инструментов.

        Имеет академическую подготовку в области международного развития.
        Практика сфокусирована на анализе человеческих способностей, потенциалов и механизмов реализации в профессиональном и жизненном контексте.

        В работе используется методология Системы Потенциалов Человека (СПЧ) как аналитическая основа для диагностики индивидуальных способов мышления, мотивации и действий. Методология адаптирована в формат онлайн-диагностики и персональных разборов с фокусом на прикладную ценность и устойчивые результаты.",
        body,
    ))

    # -------------------------------------------------
    doc.build(
        story,
        onFirstPage=draw_background,
        onLaterPages=draw_background,
    )

    return buffer.getvalue()