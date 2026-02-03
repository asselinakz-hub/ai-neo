# pdf_report.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import os
import re
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    PageBreak,
    Table,
    TableStyle,
)

from reportlab.platypus import Flowable

class _LineFlowable(Flowable):
    """
    Горизонтальная линия-разделитель.
    Использование: story.append(_LineFlowable(color=..., thickness=..., space_before=..., space_after=...))
    """
    def __init__(self, color, thickness=1.0, space_before=0, space_after=0):
        super().__init__()
        self.color = color
        self.thickness = thickness
        self.space_before = space_before
        self.space_after = space_after
        self.width = 0
        self.height = 0

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        # высота = толщина + отступы
        self.height = self.thickness + self.space_before + self.space_after
        return self.width, self.height

    def draw(self):
        c = self.canv
        w = getattr(self, "width", 0) or 0
        if w <= 0:
            return

        c.saveState()
        c.setStrokeColor(self.color)
        c.setLineWidth(self.thickness)

        # линия рисуется внутри доступной области,
        # учитываем space_before/after
        y = self.space_after  # снизу отступ
        c.line(0, y, w, y)

        c.restoreState()

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader


# ------------------------------------------------------------
# Paths
# ------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FONT_DIR = os.path.join(BASE_DIR, "assets", "fonts")
BRAND_DIR = os.path.join(BASE_DIR, "assets", "branding")

LOGO_COVER = os.path.join(BRAND_DIR, "logo_cover.png")
LOGO_FOOTER = os.path.join(BRAND_DIR, "logo_footer.png")


# ------------------------------------------------------------
# Fonts (Cyrillic)
# ------------------------------------------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    """
    Регистрирует кириллические шрифты.
    Используем твои реальные имена файлов из assets/fonts.
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    regular = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    bold = os.path.join(FONT_DIR, "DejaVuLGCSans-Bold.ttf")  # твой bold по скрину

    # fallback: если когда-то добавишь обычный DejaVuSans-Bold.ttf
    bold_alt = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")
    if os.path.exists(bold_alt):
        bold = bold_alt

    if not os.path.exists(regular):
        raise RuntimeError(f"Не найден шрифт: {regular}")

    if not os.path.exists(bold):
        # если bold нет — используем regular
        bold = regular

    # защита от битого файла (когда бинарник загрузили как текст)
    if os.path.getsize(regular) < 10_000:
        raise RuntimeError(f"Шрифт выглядит повреждённым/слишком маленький: {regular}")
    if os.path.getsize(bold) < 10_000:
        raise RuntimeError(f"Bold-шрифт выглядит повреждённым/слишком маленький: {bold}")

    pdfmetrics.registerFont(TTFont("SPCH-Regular", regular))
    pdfmetrics.registerFont(TTFont("SPCH-Bold", bold))

    _FONTS_REGISTERED = True


# ------------------------------------------------------------
# Helpers
# ------------------------------------------------------------
def _strip_md(md: str) -> str:
    """Мягкая чистка markdown -> текст для Paragraph (без HTML-тегов)."""
    if not md:
        return ""
    md = md.replace("```", "")
    md = md.replace("\t", "    ")
    md = re.sub(r"</?[^>]+>", "", md)
    return md.strip()


def _md_table_to_data(matrix_md: str):
    """
    Превращает markdown-таблицу (| a | b |) в data для reportlab.Table.
    Работает с матрицей 3×3.
    """
    text = _strip_md(matrix_md)
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


def _safe_image_reader(path: str):
    """Аккуратно читаем картинку, чтобы не падать, если файла нет."""
    try:
        if path and os.path.exists(path) and os.path.getsize(path) > 1000:
            return ImageReader(path)
    except Exception:
        return None
    return None


# ------------------------------------------------------------
# Footer / Header drawing
# ------------------------------------------------------------
def _draw_footer(canvas, doc, brand_name="Personal Potentials"):
    """
    Логотип внизу каждой страницы + тонкая линия.
    Без даты.
    """
    canvas.saveState()

    w, h = A4
    margin = 18 * mm
    y = 10 * mm

    # тонкая линия над футером
    canvas.setStrokeColor(colors.HexColor("#D6D6DB"))
    canvas.setLineWidth(0.6)
    canvas.line(margin, y + 10 * mm, w - margin, y + 10 * mm)

    # логотип (центр)
    logo = _safe_image_reader(LOGO_FOOTER)
    if logo:
        # высота логотипа — нежно, без крика
        logo_h = 7.5 * mm
        # ширину подберём пропорционально: используем фиксированную ширину
        logo_w = 40 * mm
        x = (w - logo_w) / 2
        canvas.drawImage(
            logo,
            x,
            y + 1.5 * mm,
            width=logo_w,
            height=logo_h,
            mask="auto",
            preserveAspectRatio=True,
            anchor="c",
        )
    else:
        # если лого нет — просто бренд текстом
        canvas.setFont("SPCH-Regular", 9)
        canvas.setFillColor(colors.HexColor("#6B6B72"))
        canvas.drawCentredString(w / 2, y + 4 * mm, brand_name)

    canvas.restoreState()


# ------------------------------------------------------------
# Main builder
# ------------------------------------------------------------
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
    brand_name: str = "Personal Potentials",
    author_name: str = "Asselya Zhanybek",
) -> bytes:
    """
    Спокойный, профессиональный PDF:
    - обложка с логотипом
    - без коробок/карточек
    - мягкая палитра
    - логотип/подпись внизу каждой страницы
    - блок "обо мне" (коротко, профессионально)
    """
    _register_fonts()

    buf = BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=22 * mm,  # чуть больше, чтобы футер не давил текст
        title=f"{brand_name} — Report",
        author=author_name,
    )

    styles = getSampleStyleSheet()

    # нейтральная палитра (очень мягкая)
    C_TEXT = colors.HexColor("#1C1C1F")
    C_MUTED = colors.HexColor("#6B6B72")
    C_ACCENT = colors.HexColor("#5A3A7A")   # спокойный фиолетовый
    C_LINE = colors.HexColor("#D6D6DB")

    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="SPCH-Regular",
        fontSize=11,
        leading=16,
        textColor=C_TEXT,
        spaceAfter=6,
    )

    title = ParagraphStyle(
        "title",
        parent=base,
        fontName="SPCH-Bold",
        fontSize=22,
        leading=26,
        textColor=C_TEXT,
        alignment=TA_LEFT,
        spaceAfter=10,
    )

    subtitle = ParagraphStyle(
        "subtitle",
        parent=base,
        fontName="SPCH-Regular",
        fontSize=12,
        leading=16,
        textColor=C_MUTED,
        spaceAfter=10,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="SPCH-Bold",
        fontSize=14,
        leading=18,
        textColor=C_TEXT,
        spaceBefore=12,
        spaceAfter=6,
    )

    small = ParagraphStyle(
        "small",
        parent=base,
        fontSize=9.5,
        leading=13,
        textColor=C_MUTED,
        spaceAfter=6,
    )

    quote = ParagraphStyle(
        "quote",
        parent=base,
        fontName="SPCH-Regular",
        fontSize=11,
        leading=16,
        textColor=C_TEXT,
        leftIndent=6 * mm,
        borderPadding=0,
        spaceBefore=6,
        spaceAfter=6,
    )

    story = []

    # -----------------------------
    # Cover
    # -----------------------------
    cover_logo = _safe_image_reader(LOGO_COVER)
    if cover_logo:
        # аккуратный логотип наверху
        story.append(Spacer(1, 8 * mm))
        story.append(_LogoFlowable(cover_logo, width=55*mm, height=18*mm, center=False))
        story.append(Spacer(1, 8 * mm))
    else:
        story.append(Spacer(1, 18 * mm))

    story.append(Paragraph("Персональный отчёт", title))

    # тонкая линия
    story.append(_LineFlowable(color=C_LINE, thickness=0.8, space_before=3*mm, space_after=8*mm))

    story.append(Paragraph(f"для: <b>{client_name}</b>", subtitle))
    if request:
        story.append(Paragraph(f"запрос: {request}", subtitle))

    # новый слоган (без “прочитай/лучше” и без “не типология ради типологии”)
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph(
        f"<b>{brand_name}</b> — это мягкая карта твоей природы: "
        "как ты воспринимаешь мир, что тебя по-настоящему движет и "
        "какой путь возвращает тебя к себе — без насилия и бесконечного «надо».",
        base
    ))

    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph(
        "Отчёт помогает увидеть свою опору, распознать внутренние конфликты "
        "и выбрать стиль действий, который даёт рост без выгорания.",
        base
    ))

    # мини-инструкция — без карточек и без коробок
    story.append(Spacer(1, 10 * mm))
    story.append(Paragraph("Как работать с отчётом", h2))
    story.append(_BulletList([
        "Сначала прочитай <b>1 ряд</b> — это твой «родной стиль» реализации.",
        "Затем <b>2 ряд</b> — где берётся энергия и как складывается контакт с людьми.",
        "<b>3 ряд</b> — зона риска: что лучше упрощать и не тащить на себе.",
        "В конце выпиши: <b>3 инсайта</b> и <b>1 действие</b> на ближайшую неделю.",
    ], base, bullet_color=C_ACCENT))

    # про автора (коротко, профессионально)
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Об авторе и методе", h2))
    story.append(Paragraph(
        f"Диагностика адаптирована и переведена в онлайн-формат <b>{author_name}</b>. "
        "Я опираюсь на методологию школы СПЧ, но упаковала её в практический инструмент: "
        "понятный отчёт + дальнейшее сопровождение, чтобы человек мог вернуться к себе и выстроить свою систему действий.",
        base
    ))
    story.append(Paragraph(
        "Мой бэкграунд — многолетний опыт в HR, обучении и развитии людей, "
        "корпоративном консалтинге и внедрении систем (в том числе международных). "
        "В этой работе я соединяю глубину человека и здравый прагматизм реализации.",
        base
    ))

    story.append(PageBreak())

    # -----------------------------
    # Body
    # -----------------------------
    text = _strip_md(client_report_text or "")

    # Матрица таблицей (если найдётся markdown)
    table_data = _md_table_to_data(text)

    story.append(Paragraph("Твоя матрица потенциалов", h2))
    story.append(_LineFlowable(color=C_LINE, thickness=0.6, space_before=2*mm, space_after=6*mm))

    if table_data:
        tbl = Table(table_data, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "SPCH-Regular"),
            ("FONTSIZE", (0, 0), (-1, -1), 10.7),
            ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F5F5F7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_TEXT),
            ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#E1E1E6")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8 * mm))

    # Текст отчёта — без коробок, но с аккуратными заголовками
    story.append(Paragraph("Интерпретация", h2))
    story.append(_LineFlowable(color=C_LINE, thickness=0.6, space_before=2*mm, space_after=6*mm))

    # Умная разбивка на блоки
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue

        # если блок похож на таблицу — пропустим (мы уже показали матрицу)
        if "|" in b and len(b.splitlines()) <= 8:
            continue

        # markdown заголовки -> h2
        if b.startswith("#"):
            t = b.lstrip("#").strip()
            story.append(Paragraph(t, h2))
            story.append(_LineFlowable(color=C_LINE, thickness=0.6, space_before=2*mm, space_after=6*mm))
            continue

        # выделение важных абзацев как "цитаты" (по ключевым словам)
        if ("Почему" in b and "не получа" in b) or ("Проблема" in b and "не" in b):
            story.append(Paragraph(b.replace("\n", "<br/>"), quote))
            story.append(Spacer(1, 2 * mm))
            continue

        story.append(Paragraph(b.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2 * mm))

    # Последняя строка — брендовая подпись, аккуратно
    story.append(Spacer(1, 6 * mm))
    story.append(_LineFlowable(color=C_LINE, thickness=0.6, space_before=2*mm, space_after=6*mm))
    story.append(Paragraph(
        f"<b>{brand_name}</b> — когда ты узнаёшь себя, становится проще выбирать путь и действовать из своей природы.",
        small
    ))

    # Build with footer
    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
    )

    return buf.getvalue()


# ------------------------------------------------------------
# Small Flowables: line, bullets, logo
# ------------------------------------------------------------
from reportlab.platypus import Flowable

from reportlab.lib import colors

class RoundedCard(Flowable):
    """
    Универсальная «карточка/контейнер» с закруглением.
    Важно: ширина приходит в wrap(), а в draw() используем self.width.
    """
    def __init__(self, height=60, radius=10, stroke=1, fill_color=colors.white, stroke_color=colors.HexColor("#E6E0F0"), padding=10):
        super().__init__()
        self.card_height = height
        self.radius = radius
        self.stroke = stroke
        self.fill_color = fill_color
        self.stroke_color = stroke_color
        self.padding = padding
        self.width = 0
        self.height = self.card_height

    def wrap(self, availWidth, availHeight):
        # ✅ ReportLab вызывает wrap() и даёт доступную ширину
        self.width = availWidth
        self.height = self.card_height
        return self.width, self.height

    def draw(self):
        c = self.canv
        w = getattr(self, "width", 0) or 0
        h = getattr(self, "height", self.card_height) or self.card_height

        # ✅ если вдруг ширина не пришла — не падаем
        if w <= 0:
            return

        c.saveState()
        c.setLineWidth(self.stroke)
        c.setStrokeColor(self.stroke_color)
        c.setFillColor(self.fill_color)

        # Закругленный прямоугольник
        c.roundRect(0, 0, w, h, self.radius, stroke=1, fill=1)

        c.restoreState()
        
class _BulletList(Flowable):
    def __init__(self, items, base_style, bullet_color=colors.HexColor("#5A3A7A")):
        super().__init__()
        self.items = items
        self.base_style = base_style
        self.bullet_color = bullet_color

    def wrap(self, availWidth, availHeight):
        # высоту посчитаем приблизительно
        self._availWidth = availWidth
        return availWidth, 10 * mm + len(self.items) * 6 * mm

    def draw(self):
        c = self.canv
        c.saveState()

        x = 0
        y = self.height - 2 * mm

        for item in self.items:
            # bullet
            c.setFillColor(self.bullet_color)
            c.circle(x + 2.5 * mm, y - 3 * mm, 0.9 * mm, fill=1, stroke=0)

            # text
            # Пишем через Paragraph прямо в canvas (простая отрисовка)
            p = Paragraph(item, self.base_style)
            w, h = p.wrap(self._availWidth - 8 * mm, 200 * mm)
            p.drawOn(c, x + 7 * mm, y - h)

            y -= (h + 2.5 * mm)

        c.restoreState()


class _LogoFlowable(Flowable):
    def __init__(self, img_reader, width, height, center=True):
        super().__init__()
        self.img = img_reader
        self.w = width
        self.h = height
        self.center = center

    def wrap(self, availWidth, availHeight):
        self._availWidth = availWidth
        return availWidth, self.h

    def draw(self):
        c = self.canv
        x = (self._availWidth - self.w) / 2 if self.center else 0
        c.drawImage(
            self.img,
            x,
            0,
            width=self.w,
            height=self.h,
            mask="auto",
            preserveAspectRatio=True,
        )