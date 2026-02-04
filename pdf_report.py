# pdf_report.py
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
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
    Image,
)

# ------------------------
# Paths
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGOS_DIR = os.path.join(ASSETS_DIR, "logos")

EXTRA_LOGO_DIRS = [
    LOGOS_DIR,
    BASE_DIR,
    "/mnt/data",
]

# ------------------------
# Colors (фон как у логотипа)
# ------------------------
PAGE_BG = colors.HexColor("#F7F5FB")
TEXT = colors.HexColor("#121212")
MUTED = colors.HexColor("#5A5A5A")

# ------------------------
# Fonts
# ------------------------
def register_fonts():
    pdfmetrics.registerFont(
        TTFont("Body", os.path.join(FONT_DIR, "DejaVuSans.ttf"))
    )
    pdfmetrics.registerFont(
        TTFont("Body-Bold", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))
    )

# ------------------------
# Background
# ------------------------
def draw_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PAGE_BG)
    canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
    canvas.restoreState()

# ------------------------
# Logo finder
# ------------------------
def find_logo(name: str) -> str | None:
    for d in EXTRA_LOGO_DIRS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None

# ------------------------
# Builder
# ------------------------
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
    brand_name: str = "Personal Potentials",
) -> bytes:

    register_fonts()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()

    body = ParagraphStyle(
        "body",
        parent=styles["Normal"],
        fontName="Body",
        fontSize=11.5,
        leading=18,
        textColor=TEXT,
        spaceAfter=10,
        alignment=TA_LEFT,
    )

    note = ParagraphStyle(
        "note",
        parent=body,
        fontSize=9.5,
        leading=14,
        textColor=MUTED,
        spaceBefore=14,
        spaceAfter=0,
    )

    story = []

    # ------------------------
    # LOGO (увеличенный)
    # ------------------------
    logo_path = find_logo("logo_main.png")
    if logo_path:
        logo = Image(logo_path, width=70 * mm, height=70 * mm)
        logo.hAlign = "CENTER"
        story.append(logo)
        story.append(Spacer(1, 12))

    # ------------------------
    # ENGINE REPORT (1:1)
    # ------------------------
    for block in (client_report_text or "").split("\n\n"):
        block = block.strip()
        if not block:
            continue
        story.append(Paragraph(block.replace("\n", "<br/>"), body))

    # ------------------------
    # LAST PAGE: METHODOLOGY + AUTHOR (твой текст 1:1)
    # ------------------------
    story.append(PageBreak())

    story.append(Paragraph("<b>О методологии</b>", body))
    story.append(Spacer(1, 6))

    methodology_text = (
        "В основе данного отчёта лежит методология Системы Потенциалов Человека (СПЧ) — "
        "прикладной аналитический подход к изучению природы мышления, мотивации и способов реализации человека.<br/><br/>"

        "Методология СПЧ рассматривает человека не через типы личности или поведенческие роли, "
        "а через внутренние механизмы восприятия информации, включения в действие и удержания результата.<br/>"
        "Ключевой принцип системы — каждый человек реализуется наиболее эффективно, когда опирается "
        "на свои природные способы мышления и распределяет внимание между уровнями реализации осознанно.<br/><br/>"

        "Первоначально СПЧ разрабатывалась как офлайн-метод для глубинных разборов и практической работы с людьми.<br/>"
        "В рамках данной диагностики методология адаптирована в формат онлайн-анализа с сохранением логики системы, "
        "структуры интерпретации и фокуса на прикладную ценность результата.<br/><br/>"

        "Важно: СПЧ не является психометрическим тестом в классическом понимании и не претендует "
        "на медицинскую или клиническую диагностику.<br/>"
        "Это карта внутренних механизмов, позволяющая точнее выстраивать решения, развитие и профессиональную "
        "реализацию без насилия над собой."
    )
    story.append(Paragraph(methodology_text, body))

    story.append(Spacer(1, 14))
    story.append(Paragraph("<b>Об авторе</b>", body))
    story.append(Spacer(1, 6))

    author_text = (
        "Asselya Zhanybek — эксперт в области оценки и развития человеческого капитала, "
        "с профессиональным фокусом на проектах оценки компетенций и развития управленческих команд "
        "в национальных компаниях и европейском консалтинге, с применением психометрических инструментов.<br/><br/>"

        "Имеет академическую подготовку в области международного развития.<br/>"
        "Практика сфокусирована на анализе человеческих способностей, потенциалов и механизмов реализации "
        "в профессиональном и жизненном контексте.<br/><br/>"

        "В работе используется методология Системы Потенциалов Человека (СПЧ) как аналитическая основа "
        "для диагностики индивидуальных способов мышления, мотивации и действий. "
        "Методология адаптирована в формат онлайн-диагностики и персональных разборов с фокусом "
        "на прикладную ценность и устойчивые результаты."
    )
    story.append(Paragraph(author_text, body))

    # (по твоей просьбе) "отчёт предназначен..." — сюда, в конец методологии/автора
    story.append(Paragraph(
        "Этот отчёт предназначен для личного использования. Рекомендуется возвращаться к нему по мере изменений и принятия решений.",
        note
    ))

    doc.build(
        story,
        onFirstPage=draw_background,
        onLaterPages=draw_background,
    )

    return buf.getvalue()