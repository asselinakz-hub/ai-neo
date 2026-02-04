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
    Flowable,
)

# ------------------------
# Paths (ВАЖНО: под твой проект)
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGO_DIR = os.path.join(ASSETS_DIR, "logos")   # <-- у тебя так

# ------------------------
# Colors (calm, premium)
# ------------------------
C_PAPER = colors.HexColor("#FFFFFF")   # можно заменить на #F7F6F3 если хочешь "как у лого"
C_TEXT  = colors.HexColor("#141414")
C_MUTED = colors.HexColor("#666666")
C_LINE  = colors.HexColor("#D8D2E6")
C_ACCENT = colors.HexColor("#5B2B6C")

# ------------------------
# Fonts
# ------------------------
_FONTS_REGISTERED = False

def _pick_first_existing(*paths: str) -> str | None:
    for p in paths:
        if p and os.path.exists(p) and os.path.getsize(p) > 10_000:
            return p
    return None

def _register_fonts():
    """
    Body: sans (Inter/Lato/SourceSans/DejaVuSans fallback)
    Headings: serif (Playfair/Coromorant/LibreBaskerville/DejaVuSerif fallback)
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    # --- BODY (sans)
    body_font = _pick_first_existing(
        os.path.join(FONT_DIR, "Inter-Regular.ttf"),
        os.path.join(FONT_DIR, "Lato-Regular.ttf"),
        os.path.join(FONT_DIR, "SourceSans3-Regular.ttf"),
        os.path.join(FONT_DIR, "DejaVuSans.ttf"),
    )
    if not body_font:
        raise RuntimeError("No body font found in assets/fonts (need at least DejaVuSans.ttf)")

    # --- HEADINGS (serif, regular only)
    heading_font = _pick_first_existing(
        os.path.join(FONT_DIR, "PlayfairDisplay-Regular.ttf"),
        os.path.join(FONT_DIR, "CormorantGaramond-Regular.ttf"),
        os.path.join(FONT_DIR, "LibreBaskerville-Regular.ttf"),
        os.path.join(FONT_DIR, "DejaVuSerif.ttf"),
        body_font,  # fallback to body if nothing else exists
    )

    pdfmetrics.registerFont(TTFont("PP-Body", body_font))
    pdfmetrics.registerFont(TTFont("PP-Head", heading_font))

    _FONTS_REGISTERED = True


# ------------------------
# Small Flowable: horizontal rule (вместо символа ⸻)
# ------------------------
class HR(Flowable):
    def __init__(self, width=None, thickness=0.7, color=C_LINE, space_before=6, space_after=10):
        super().__init__()
        self.width = width
        self.thickness = thickness
        self.color = color
        self.space_before = space_before
        self.space_after = space_after
        self.height = self.space_before + self.space_after + 1

    def wrap(self, availWidth, availHeight):
        self._w = availWidth if self.width is None else min(self.width, availWidth)
        return self._w, self.height

    def draw(self):
        c = self.canv
        c.saveState()
        c.setStrokeColor(self.color)
        c.setLineWidth(self.thickness)
        y = self.space_after
        c.line(0, y, self._w, y)
        c.restoreState()


# ------------------------
# Helpers
# ------------------------
def _safe_logo_path(filename: str) -> str | None:
    p = os.path.join(LOGO_DIR, filename)
    return p if os.path.exists(p) else None

def _clean_text(s: str) -> str:
    """
    - убираем markdown ** (чтобы не было случайного bold)
    - убираем символ ⸻ (мы рисуем линию отдельно)
    - нормализуем точки/разделители
    """
    if not s:
        return ""
    s = s.replace("```", "")
    s = s.replace("\t", "    ")
    s = re.sub(r"</?[^>]+>", "", s)

    # убрать markdown bold
    s = s.replace("**", "")

    # заменить "·" на обычную точку (если вдруг квадратики)
    s = s.replace("·", "•")

    # убрать символ-разделитель — заменим на HR
    s = s.replace("⸻", "\n[HR]\n")
    return s.strip()

def _split_blocks(text: str) -> list[str]:
    """
    Разделяем на смысловые блоки по пустым строкам, но сохраняем списки.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n+", text)
    return [b.strip() for b in blocks if b.strip()]

def _extract_matrix_table(text: str):
    """
    Ищем матрицу в виде таблицы/колонок.
    Поддержка:
      - markdown таблица с |
      - либо "Ряд\nВосприятие\n..." + строки "1 (60%)\nРубин\n..."
    """
    # 1) markdown style
    md_rows = [l.strip() for l in text.splitlines() if "|" in l]
    if md_rows:
        parsed = []
        for r in md_rows:
            if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", r):
                continue
            parts = [c.strip() for c in r.strip("|").split("|")]
            parsed.append(parts)
        if parsed:
            return parsed

    # 2) "Ряд Восприятие Мотивация Инструмент" as spaced table (heuristic)
    m = re.search(r"(Твоя матрица потенциалов|Матрица потенциалов).*?(Ряд\s+Восприятие\s+Мотивация\s+Инструмент)(.*?)(?:\n\s*\n|$)", text, re.S | re.I)
    if m:
        tail = m.group(3).strip()
        # take next up to 3 lines that start with 1/2/3
        lines = [l.strip() for l in tail.splitlines() if l.strip()]
        rows = []
        for l in lines:
            if re.match(r"^(1|2|3)\b", l):
                rows.append(re.split(r"\s{2,}|\t| +", l))
            if len(rows) >= 3:
                break
        if rows:
            header = ["Ряд", "Восприятие", "Мотивация", "Инструмент"]
            return [header] + rows

    return None

def _remove_duplicate_intro(engine_text: str) -> str:
    """
    Если движок уже возвращает "Введение" + "Структура внимания..." —
    мы их вырезаем, потому что на первой странице они будут статично.
    НИЧЕГО НЕ ПЕРЕФОРМУЛИРУЕМ — только удаляем дубли.
    """
    t = engine_text

    # вырезаем кусок от "Введение" до "Твоя матрица потенциалов" (если найден)
    pat = r"Введение.*?(?=(Твоя матрица потенциалов|ПЕРВЫЙ РЯД|Первый ряд))"
    t2 = re.sub(pat, "", t, flags=re.S | re.I)

    # вырезаем кусок "Структура внимания..." если он остался отдельно
    pat2 = r"Структура внимания.*?(?=(Твоя матрица потенциалов|ПЕРВЫЙ РЯД|Первый ряд))"
    t2 = re.sub(pat2, "", t2, flags=re.S | re.I)

    return t2.strip()


# ------------------------
# Footer (только текст, без лого)
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
    canvas.drawRightString(A4[0] - doc.rightMargin, y + 2, str(doc.page))

    canvas.restoreState()


# ------------------------
# Optional page background (если захочешь "как у лого")
# ------------------------
def _draw_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_PAPER)
    canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canvas.restoreState()


# ------------------------
# Main builder
# ------------------------
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
    brand_name: str = "Personal Potentials",
    report_date: str | None = None,  # можно передавать из app.py
) -> bytes:
    _register_fonts()

    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=f"{brand_name} Report",
        author="Asselya Zhanybek",
    )

    styles = getSampleStyleSheet()

    # Body (sans), easy reading
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Body",
        fontSize=11.3,
        leading=18,          # ~1.6
        textColor=C_TEXT,
        spaceAfter=10,       # воздух
        alignment=TA_LEFT,
    )

    # Headings (serif), regular (НЕ bold)
    h1 = ParagraphStyle(
        "h1",
        parent=base,
        fontName="PP-Head",
        fontSize=22,
        leading=28,
        textColor=C_ACCENT,
        spaceAfter=10,
        alignment=TA_CENTER,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="PP-Head",
        fontSize=14.5,
        leading=20,
        textColor=C_ACCENT,
        spaceBefore=10,
        spaceAfter=8,
    )

    subtle = ParagraphStyle(
        "subtle",
        parent=base,
        fontSize=10,
        leading=15,
        textColor=C_MUTED,
    )

    # ---- дата
    if report_date:
        dt_str = report_date
    else:
        dt_str = date.today().strftime("%d.%m.%Y")

    story = []

    # ========================
    # PAGE 1 (СТАТИЧНАЯ)
    # ========================
    # background (optional)
    # (если хочешь фон "как у лого", поменяй C_PAPER и оставь)
    story.append(Spacer(1, 2*mm))

    # ЛОГО: проще и чище использовать logo_main.png (в нём уже кружок + надпись)
    cover_logo = _safe_logo_path("logo_main.png") or _safe_logo_path("logo_main.jpg")
    if cover_logo:
        img = Image(cover_logo)
        img._restrictSize(70*mm, 45*mm)  # уменьшили, чтобы текст точно влезал
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 4*mm))

    story.append(Paragraph(brand_name.upper(), h1))
    story.append(Paragraph("Индивидуальный отчёт по системе потенциалов человека 3×3", ParagraphStyle(
        "subtitle",
        parent=subtle,
        alignment=TA_CENTER,
        fontName="PP-Body",
        fontSize=11,
        textColor=C_MUTED,
        spaceAfter=10,
    )))

    # реквизиты
    story.append(Paragraph(f"Для: {client_name}", base))
    if request:
        story.append(Paragraph(f"Запрос: {request}", base))
    story.append(Paragraph(f"Дата: {dt_str}", base))

    story.append(HR())

    # Введение (строго твой текст — без жирного)
    story.append(Paragraph("Введение", h2))
    intro_text = (
        "Этот отчёт — результат индивидуальной диагностики, направленной на выявление природного способа мышления, мотивации и реализации.\n"
        "Он не описывает качества характера и не даёт оценок личности.\n"
        "Его задача — показать, как именно у тебя устроен внутренний механизм, через который ты принимаешь решения, расходуешь энергию и достигаешь результата.\n\n"
        "Практическая ценность отчёта в том, что он:\n"
        "• помогает точнее понимать себя и свои реакции;\n"
        "• снижает внутренние конфликты между «хочу», «надо» и «делаю»;\n"
        "• даёт ясность, где стоит держать фокус, а где — не перегружать себя."
    )
    story.append(Paragraph(intro_text.replace("\n", "<br/>"), base))

    story.append(HR())

    story.append(Paragraph("Структура внимания и распределение энергии", h2))
    structure_text = (
        "В основе интерпретации лежит матрица потенциалов 3×3, где каждый ряд выполняет свою функцию.\n\n"
        "В твоей системе распределение внимания выглядит следующим образом:\n"
        "• 1 ряд — 60% фокуса внимания\n"
        "Основа личности, способ реализации и создания ценности.\n"
        "Именно здесь находится твой главный вектор развития и устойчивости.\n"
        "• 2 ряд — 30% фокуса внимания\n"
        "Источник энергии, восстановления и живого контакта с людьми.\n"
        "Этот уровень поддерживает первый, но не должен его подменять.\n"
        "• 3 ряд — 10% фокуса внимания\n"
        "Зоны риска и перегруза.\n"
        "Эти функции не предназначены для постоянного использования и лучше осознавать их как вспомогательные.\n\n"
        "Такое распределение позволяет сохранить внутренний баланс и не тратить ресурс на задачи, которые не соответствуют твоей природе."
    )
    story.append(Paragraph(structure_text.replace("\n", "<br/>"), base))

    story.append(PageBreak())

    # ========================
    # ДАЛЬШЕ — ДИНАМИКА ИЗ ДВИЖКА (APP.PY)
    # ========================
    engine_text = _clean_text(client_report_text or "")
    engine_text = _remove_duplicate_intro(engine_text)

    # 1) Матрица: если в тексте есть таблица — рисуем красиво
    story.append(Paragraph("Твоя матрица потенциалов", h2))

    matrix_data = _extract_matrix_table(engine_text)
    if matrix_data:
        tbl = Table(matrix_data, hAlign="LEFT", colWidths=[22*mm, 48*mm, 48*mm, 48*mm])
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "PP-Body"),
            ("FONTSIZE", (0, 0), (-1, -1), 10.8),
            ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),

            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F4FA")),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_ACCENT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, C_LINE),

            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E6E2F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(Spacer(1, 2*mm))
        story.append(tbl)
        story.append(Spacer(1, 6*mm))
    else:
        story.append(Paragraph("Матрица не распознана как таблица — продолжение отчёта ниже.", subtle))
        story.append(Spacer(1, 4*mm))

    # 2) Основной текст из движка — без искусственных PageBreak между рядами
    blocks = _split_blocks(engine_text)

    # чтобы не дублировать матрицу как текст, если она рядом
    def _looks_like_matrix_block(b: str) -> bool:
        if "Ряд" in b and "Восприятие" in b and "Мотивация" in b and "Инструмент" in b:
            return True
        if "|" in b and len(b.splitlines()) <= 10:
            return True
        return False

    for b in blocks:
        if matrix_data and _looks_like_matrix_block(b):
            continue

        # HR marker -> line
        if b.strip() == "[HR]":
            story.append(HR())
            continue

        # Заголовки (если движок отдаёт их капсом/с двоеточиями — ловим мягко)
        if re.match(r"^(ПЕРВЫЙ РЯД|ВТОРОЙ РЯД|ТРЕТИЙ РЯД|Итоговая картина|Почему может не получаться|Заметки|О методологии|Об авторе)\b", b, flags=re.I):
            story.append(HR())
            story.append(Paragraph(b.strip(), h2))
            continue

        # если в блоке есть [HR] внутри — разрежем
        if "[HR]" in b:
            parts = [p.strip() for p in b.split("[HR]") if p.strip()]
            for i, part in enumerate(parts):
                story.append(Paragraph(part.replace("\n", "<br/>"), base))
                if i != len(parts) - 1:
                    story.append(HR())
            continue

        story.append(Paragraph(b.replace("\n", "<br/>"), base))

    # ========================
    # NOTES + METHODOLOGY/AUTHOR — отдельными страницами
    # (если движок их уже отдал в тексте — они останутся там;
    # но “лишнюю пустую страницу” с фразой мы не делаем)
    # ========================
    # Финальная строка (не отдельной страницей)
    story.append(Spacer(1, 4*mm))
    story.append(HR())
    story.append(Paragraph(
        "Этот отчёт предназначен для личного использования. Возвращайтесь к нему по мере изменений и принятия решений.",
        subtle
    ))

    doc.build(
        story,
        onFirstPage=lambda c, d: (_draw_background(c, d), _draw_footer(c, d, brand_name=brand_name)),
        onLaterPages=lambda c, d: (_draw_background(c, d), _draw_footer(c, d, brand_name=brand_name)),
    )

    return buf.getvalue()