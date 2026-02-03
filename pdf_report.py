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
from reportlab.lib.enums import TA_CENTER, TA_LEFT

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

# --------------------
# Paths
# --------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGO_DIR = os.path.join(ASSETS_DIR, "logos")

# --------------------
# Brand colors
# --------------------
BRAND_PURPLE = colors.HexColor("#6B2E7A")
BRAND_DARK = colors.HexColor("#2B0F33")
BRAND_PINK = colors.HexColor("#C85A8A")
BRAND_ORANGE = colors.HexColor("#F2A23A")

BG_LAVENDER = colors.HexColor("#F7F1FB")
BG_PINK = colors.HexColor("#FFF3F8")
BG_ORANGE = colors.HexColor("#FFF3E6")

LINE_SOFT = colors.HexColor("#E6D7EF")
TEXT_MAIN = colors.HexColor("#111111")
TEXT_MUTED = colors.HexColor("#3A3A3A")

# --------------------
# Fonts (Cyrillic)
# --------------------
_FONTS_REGISTERED = False


def _register_fonts() -> None:
    """
    Регистрирует кириллические шрифты из репо.
    ОЖИДАЕМЫЕ ФАЙЛЫ:
      assets/fonts/DejaVuSans.ttf
      assets/fonts/DejaVuLGCSans-Bold.ttf
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    regular = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    bold = os.path.join(FONT_DIR, "DejaVuLGCSans-Bold.ttf")

    if not os.path.exists(regular):
        raise RuntimeError(f"Не найден шрифт: {regular}")

    if not os.path.exists(bold):
        bold = regular  # fallback

    # защита от «повреждённого» файла (если бинарник залили через Edit)
    if os.path.getsize(regular) < 10_000:
        raise RuntimeError(
            f"Шрифт повреждён/слишком маленький: {regular}. Перезалей через Upload."
        )
    if os.path.getsize(bold) < 10_000:
        raise RuntimeError(
            f"Bold-шрифт повреждён/слишком маленький: {bold}. Перезалей через Upload."
        )

    pdfmetrics.registerFont(TTFont("SPCH-Regular", regular))
    pdfmetrics.registerFont(TTFont("SPCH-Bold", bold))

    _FONTS_REGISTERED = True


# --------------------
# Logos
# --------------------
def _get_logo(name: str) -> str | None:
    path = os.path.join(LOGO_DIR, name)
    return path if os.path.exists(path) else None


# --------------------
# Helpers
# --------------------
def _strip_md(md: str) -> str:
    if not md:
        return ""
    md = md.replace("```", "")
    md = md.replace("\t", "    ")
    md = re.sub(r"</?[^>]+>", "", md)
    return md.strip()


def _md_table_to_data(text: str):
    text = _strip_md(text)
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


def _divider(height_mm: float = 1.2, color=LINE_SOFT):
    """Тонкий цветной разделитель как Table (стабильно в ReportLab)."""
    t = Table([[""]], colWidths=[A4[0] - 36 * mm], rowHeights=[height_mm * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _card(title: str, body_html: str, *, accent=BRAND_PURPLE, bg=BG_LAVENDER,
          title_style=None, body_style=None):
    """
    Карточка-блок: заголовок + текст внутри «плашки».
    """
    title_style = title_style
    body_style = body_style

    # Внутренняя таблица — самый надёжный способ
    content = [
        [Paragraph(f"<b>{title}</b>", title_style)],
        [Paragraph(body_html, body_style)],
    ]
    t = Table(content, colWidths=[A4[0] - 36 * mm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.8, accent),
        ("LINEBEFORE", (0, 0), (0, -1), 5, accent),  # акцентная полоса слева
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
    ]))
    return t


# --------------------
# Page decor
# --------------------
def _draw_gradient_band(canvas, x, y, w, h, colors_list):
    """
    Простой «градиент» полоской: рисуем много тонких прямоугольников.
    Работает везде и даёт вау-эффект.
    """
    steps = 60
    for i in range(steps):
        t = i / (steps - 1)
        # интерполяция между 3 цветами
        if t < 0.5:
            t2 = t / 0.5
            c1, c2 = colors_list[0], colors_list[1]
        else:
            t2 = (t - 0.5) / 0.5
            c1, c2 = colors_list[1], colors_list[2]

        r = c1.red + (c2.red - c1.red) * t2
        g = c1.green + (c2.green - c1.green) * t2
        b = c1.blue + (c2.blue - c1.blue) * t2

        canvas.setFillColor(colors.Color(r, g, b))
        canvas.setStrokeColor(colors.Color(r, g, b))
        canvas.rect(x + (w * i / steps), y, w / steps + 0.5, h, stroke=0, fill=1)


def _inner_header_footer(brand_title: str):
    logo_mark = _get_logo("logo_mark.png")

    def _draw(canvas, doc):
        canvas.saveState()

        # Лента слева (брендовый штрих)
        canvas.setFillColor(BG_LAVENDER)
        canvas.rect(0, 0, 8 * mm, A4[1], stroke=0, fill=1)

        # Три точки-акцента (фиолет/розовый/оранж) сверху справа
        y = A4[1] - 18 * mm
        x = A4[0] - 22 * mm
        canvas.setFillColor(BRAND_PURPLE)
        canvas.circle(x, y, 2.2, stroke=0, fill=1)
        canvas.setFillColor(BRAND_PINK)
        canvas.circle(x + 7 * mm, y, 2.2, stroke=0, fill=1)
        canvas.setFillColor(BRAND_ORANGE)
        canvas.circle(x + 14 * mm, y, 2.2, stroke=0, fill=1)

        # Маленькая логомарка слева сверху
        if logo_mark:
            try:
                canvas.drawImage(
                    logo_mark,
                    x=18 * mm,
                    y=A4[1] - 22 * mm,
                    width=14 * mm,
                    height=14 * mm,
                    mask="auto",
                )
            except Exception:
                pass

        # Футер
        canvas.setFillColor(BRAND_PURPLE)
        canvas.setFont("SPCH-Regular", 8.5)
        footer_left = brand_title
        footer_right = f"{date.today().isoformat()} · стр. {doc.page}"
        canvas.drawString(18 * mm, 12 * mm, footer_left)
        canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, footer_right)

        canvas.restoreState()

    return _draw


def _cover_decor(brand_title: str):
    def _draw(canvas, doc):
        canvas.saveState()

        # верхняя градиентная полоска
        _draw_gradient_band(
            canvas,
            x=0,
            y=A4[1] - 22 * mm,
            w=A4[0],
            h=22 * mm,
            colors_list=[BRAND_PURPLE, BRAND_PINK, BRAND_ORANGE],
        )

        # лёгкая подложка снизу (чтобы выглядело «дизайнерски»)
        canvas.setFillColor(colors.HexColor("#FBF7FD"))
        canvas.rect(0, 0, A4[0], A4[1] - 22 * mm, stroke=0, fill=1)

        # футер на обложке
        canvas.setFillColor(BRAND_PURPLE)
        canvas.setFont("SPCH-Regular", 8.5)
        canvas.drawString(18 * mm, 12 * mm, brand_title)

        canvas.restoreState()

    return _draw


# --------------------
# Main builder
# --------------------
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
    brand_title: str = "Personal Potentials by Asselya Zhanybek",
) -> bytes:
    """
    Брендированный PDF:
    - обложка с градиентом + логотип
    - вау-карточки
    - отчёт + матрица
    - упражнение и заметки
    """
    _register_fonts()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=24 * mm,
        bottomMargin=18 * mm,
        title="Personal Potentials Report",
        author="Asselya Zhanybek",
    )

    # Styles
    base = ParagraphStyle(
        "base",
        fontName="SPCH-Regular",
        fontSize=11,
        leading=15,
        textColor=TEXT_MAIN,
        spaceAfter=6,
    )

    h1 = ParagraphStyle(
        "h1",
        fontName="SPCH-Bold",
        fontSize=22,
        leading=26,
        textColor=BRAND_DARK,
        spaceAfter=8,
    )

    h2 = ParagraphStyle(
        "h2",
        fontName="SPCH-Bold",
        fontSize=14,
        leading=18,
        textColor=BRAND_DARK,
        spaceBefore=10,
        spaceAfter=6,
    )

    small = ParagraphStyle(
        "small",
        fontName="SPCH-Regular",
        fontSize=9.5,
        leading=13,
        textColor=TEXT_MUTED,
        spaceAfter=4,
    )

    card_title = ParagraphStyle(
        "card_title",
        fontName="SPCH-Bold",
        fontSize=11.2,
        leading=14,
        textColor=BRAND_DARK,
        alignment=TA_LEFT,
        spaceAfter=4,
    )

    card_body = ParagraphStyle(
        "card_body",
        fontName="SPCH-Regular",
        fontSize=10.7,
        leading=14.5,
        textColor=TEXT_MAIN,
        alignment=TA_LEFT,
    )

    centered = ParagraphStyle(
        "centered",
        parent=base,
        alignment=TA_CENTER,
        textColor=BRAND_PURPLE
    )

    # Logos
    logo_main = _get_logo("logo_main.png")
    logo_horizontal = _get_logo("logo_horizontal.png")
    logo_light = _get_logo("logo_light.png")

    story = []

    # --------------------
    # Cover
    # --------------------
    story.append(Spacer(1, 18 * mm))

    cover_logo = logo_horizontal or logo_main
    if cover_logo:
        try:
            story.append(Image(cover_logo, width=120 * mm, height=120 * mm))
            story.append(Spacer(1, 6 * mm))
        except Exception:
            pass

    story.append(Paragraph("Персональный отчёт", h1))
    story.append(_divider(1.2, LINE_SOFT))
    story.append(Spacer(1, 4 * mm))

    story.append(Paragraph(f"для: <b>{client_name}</b>", base))
    if request:
        story.append(Paragraph(f"Запрос: {request}", base))
    story.append(Paragraph(f"Дата: {date.today().isoformat()}", small))

    story.append(Spacer(1, 10 * mm))

    # WOW cards on cover
    story.append(_card(
        "Зачем нужен этот отчёт",
        "Это не «типология ради типологии». Это карта твоей естественной реализации: "
        "как ты воспринимаешь мир, что тебя по-настоящему мотивирует и какой механизм "
        "помогает тебе двигаться без насилия над собой.",
        accent=BRAND_PURPLE,
        bg=BG_LAVENDER,
        title_style=card_title,
        body_style=card_body,
    ))
    story.append(Spacer(1, 6 * mm))

    story.append(_card(
        "Как получить максимум (2–5 минут)",
        "1) Прочитай <b>1 ряд</b> — фундамент и твой «родной стиль».<br/>"
        "2) Затем <b>2 ряд</b> — энергия и контакт с людьми (не превращай в обязаловку).<br/>"
        "3) <b>3 ряд</b> — зона риска: что лучше упростить/делегировать.<br/>"
        "4) Сделай упражнение «3 инсайта + 1 действие» — и отчёт начнёт работать в жизни.",
        accent=BRAND_PINK,
        bg=BG_PINK,
        title_style=card_title,
        body_style=card_body,
    ))

    story.append(PageBreak())

    # --------------------
    # Report body
    # --------------------
    text = _strip_md(client_report_text or "")

    story.append(Paragraph("Твой отчёт", h2))
    story.append(_divider(1.0, LINE_SOFT))
    story.append(Spacer(1, 4 * mm))

    # Optional “quick summary” card (universal)
    story.append(_card(
        "Быстрый ориентир",
        "Если ты сейчас в сомнениях или застое — это часто не «лень». "
        "Это конфликт между твоей природой и тем, <i>как ты пытаешься достигать</i>. "
        "Смысл отчёта — вернуть тебя в свой механизм.",
        accent=BRAND_ORANGE,
        bg=BG_ORANGE,
        title_style=card_title,
        body_style=card_body,
    ))
    story.append(Spacer(1, 6 * mm))

    # Table (matrix) if present
    table_data = _md_table_to_data(text)
    if table_data:
        tbl = Table(table_data, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "SPCH-Regular"),
            ("FONTSIZE", (0, 0), (-1, -1), 10.5),
            ("BACKGROUND", (0, 0), (-1, 0), BG_LAVENDER),
            ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_DARK),
            ("GRID", (0, 0), (-1, -1), 0.5, LINE_SOFT),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 6 * mm))

    # Render main text by blocks
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue

        if "|" in b and len(b.splitlines()) <= 8:
            continue

        if b.startswith("#"):
            title = b.lstrip("#").strip()
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(title, h2))
            story.append(_divider(0.9, LINE_SOFT))
            story.append(Spacer(1, 3 * mm))
            continue

        story.append(Paragraph(b.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2 * mm))

    # --------------------
    # Worksheet page
    # --------------------
    story.append(PageBreak())
    story.append(Paragraph("Упражнение: 3 инсайта + 1 действие", h2))
    story.append(_divider(1.0, LINE_SOFT))
    story.append(Spacer(1, 4 * mm))

    story.append(_card(
        "Зачем это нужно",
        "Ты можешь быть «очень сильным человеком» и всё равно буксовать, "
        "если действуешь не своим способом. Это упражнение переводит отчёт "
        "из текста в движение.",
        accent=BRAND_PURPLE,
        bg=BG_LAVENDER,
        title_style=card_title,
        body_style=card_body,
    ))
    story.append(Spacer(1, 6 * mm))

    ws_data = [
        ["1) Что в отчёте прям «попало в точку»? (1–2 фразы)", ""],
        ["2) Где ты обычно пытаешься «ломать себя», вместо того чтобы действовать своим способом?", ""],
        ["3) Что ты готов(а) перестать делать на этой неделе, чтобы стало легче?", ""],
        ["4) 1 действие на неделю (очень конкретно):", ""],
    ]
    ws = Table(ws_data, colWidths=[65 * mm, 110 * mm])
    ws.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "SPCH-Regular"),
        ("FONTSIZE", (0, 0), (-1, -1), 10.5),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TEXTCOLOR", (0, 0), (-1, -1), TEXT_MAIN),
        ("GRID", (0, 0), (-1, -1), 0.5, LINE_SOFT),
        ("BACKGROUND", (0, 0), (-1, 0), BG_PINK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
    ]))
    story.append(ws)

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "Подсказка: выбери одно маленькое действие. Система строится шагами — не рывком.",
        small
    ))

    # --------------------
    # Notes page
    # --------------------
    story.append(PageBreak())
    story.append(Paragraph("Заметки", h2))
    story.append(_divider(1.0, LINE_SOFT))
    story.append(Spacer(1, 4 * mm))

    story.append(_card(
        "Что сюда писать",
        "Примеры из жизни, вопросы к сессии, «где я узнаю себя», идеи для контента, "
        "любые мысли, которые пришли во время чтения.",
        accent=BRAND_ORANGE,
        bg=BG_ORANGE,
        title_style=card_title,
        body_style=card_body,
    ))
    story.append(Spacer(1, 6 * mm))

    for _ in range(18):
        story.append(Paragraph("<font color='#C7B3D1'>______________________________________________________________</font>", small))

    # --------------------
    # Closing
    # --------------------
    story.append(Spacer(1, 10 * mm))
    if logo_light:
        try:
            story.append(Image(logo_light, width=48 * mm, height=48 * mm))
            story.append(Spacer(1, 3 * mm))
        except Exception:
            pass

    story.append(Paragraph(
        "Personal Potentials — не про «стать лучше». Это про «вернуться к себе».",
        centered
    ))

    # Build with decor
    doc.build(
        story,
        onFirstPage=_cover_decor(brand_title),
        onLaterPages=_inner_header_footer(brand_title),
    )

    return buf.getvalue()