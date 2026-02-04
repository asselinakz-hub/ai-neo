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
    KeepTogether,
)

# ------------------------
# Paths
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
LOGO_DIR = os.path.join(ASSETS_DIR, "logos")  # <-- FIX: у тебя assets/logos

# ------------------------
# Colors (calm, premium)
# ------------------------
C_BG = colors.HexColor("#FFFFFF")
C_TEXT = colors.HexColor("#151515")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")     # soft lavender-gray
C_ACCENT = colors.HexColor("#5B2B6C")   # deep plum
C_ACCENT_2 = colors.HexColor("#8C4A86") # muted mauve
C_SOFT = colors.HexColor("#F6F4FA")

# ------------------------
# Fonts
# Заголовки: serif regular (без bold)
# Текст: sans regular
#
# ВАЖНО: Я не могу гарантировать наличие Playfair/Inter у тебя.
# Поэтому делаю "если есть — используем", иначе fallback на DejaVu.
# ------------------------
_FONTS_REGISTERED = False

def _pick_first_existing(*paths: str) -> str | None:
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None

def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    # Sans (body)
    sans_regular = _pick_first_existing(
        os.path.join(FONT_DIR, "Inter-Regular.ttf"),
        os.path.join(FONT_DIR, "SourceSans3-Regular.ttf"),
        os.path.join(FONT_DIR, "Lato-Regular.ttf"),
        os.path.join(FONT_DIR, "DejaVuSans.ttf"),
    )
    sans_bold = _pick_first_existing(
        os.path.join(FONT_DIR, "Inter-SemiBold.ttf"),
        os.path.join(FONT_DIR, "Inter-Bold.ttf"),
        os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"),
        os.path.join(FONT_DIR, "DejaVuLGCSans-Bold.ttf"),
        sans_regular,
    )

    # Serif (headings) — regular / medium, НЕ bold
    serif_regular = _pick_first_existing(
        os.path.join(FONT_DIR, "PlayfairDisplay-Regular.ttf"),
        os.path.join(FONT_DIR, "CormorantGaramond-Regular.ttf"),
        os.path.join(FONT_DIR, "LibreBaskerville-Regular.ttf"),
    )
    # если serif нет — fallback на DejaVuSans (чтобы не падало)
    if not serif_regular:
        serif_regular = sans_regular

    if not sans_regular:
        raise RuntimeError(f"No body font found in {FONT_DIR}. Add DejaVuSans.ttf at least.")

    # регистрация
    pdfmetrics.registerFont(TTFont("PP-Body", sans_regular))
    pdfmetrics.registerFont(TTFont("PP-BodyBold", sans_bold))
    pdfmetrics.registerFont(TTFont("PP-Head", serif_regular))

    _FONTS_REGISTERED = True


# ------------------------
# Helpers
# ------------------------
def _strip_md(md: str) -> str:
    if not md:
        return ""
    md = md.replace("```", "")
    md = md.replace("\t", "    ")
    md = re.sub(r"</?[^>]+>", "", md)  # remove html tags
    return md.strip()

def _safe_logo_path(filename: str) -> str | None:
    p = os.path.join(LOGO_DIR, filename)
    return p if os.path.exists(p) else None

def _md_table_to_data(matrix_md: str):
    """
    Парсит markdown-таблицу вида:
    | Ряд | ... |
    |---|---|
    | 1 | ... |
    """
    text = _strip_md(matrix_md)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows = [l for l in lines if "|" in l]
    if not rows:
        return None

    parsed = []
    for r in rows:
        # skip separators like |---|---|
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", r):
            continue
        parts = [c.strip() for c in r.strip("|").split("|")]
        parsed.append(parts)

    return parsed if parsed else None

def _split_paragraphs(text: str) -> list[str]:
    """
    Делит текст на короткие абзацы (чтобы не было 'стены').
    Уважает пустые строки.
    """
    text = _strip_md(text)
    blocks = re.split(r"\n\s*\n", text)
    out = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue
        # если внутри блока слишком много строк — чуть дробим по строкам
        lines = [x.strip() for x in b.splitlines() if x.strip()]
        if len(lines) >= 6:
            # делим на маленькие смысловые куски по 2-3 строки
            chunk = []
            for ln in lines:
                chunk.append(ln)
                if len(chunk) >= 3:
                    out.append(" ".join(chunk))
                    chunk = []
            if chunk:
                out.append(" ".join(chunk))
        else:
            out.append(" ".join(lines))
    return out

def _extract_sections(client_report_text: str) -> dict:
    """
    Достаёт из текста движка ключевые части, если они есть.
    Если нет — просто вернём всё целиком.
    Ориентируемся на заголовки (чтобы было динамично).
    """
    t = _strip_md(client_report_text or "")
    return {"raw": t}


# ------------------------
# Footer (logo + brand)
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials"):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    # small logo (prefer horizontal, fallback light)
    logo_path = _safe_logo_path("logo_horizontal.png") or _safe_logo_path("logo_light.png")
    x = doc.leftMargin
    if logo_path:
        try:
            canvas.drawImage(
                logo_path, x, y - 2,
                width=36*mm, height=10*mm,
                mask='auto', preserveAspectRatio=True, anchor='sw'
            )
            x += 40 * mm
        except Exception:
            pass

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Body", 9)
    canvas.drawString(x, y + 2, brand_name)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Body", 9)
    canvas.drawRightString(A4[0] - doc.rightMargin, y + 2, str(doc.page))

    canvas.restoreState()


# ------------------------
# Main builder
# ------------------------
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
    brand_name: str = "Personal Potentials",
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

    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Body",
        fontSize=11.5,
        leading=18,                 # 1.55–1.6 ощущения
        textColor=C_TEXT,
        spaceAfter=10,              # больше воздуха между абзацами
        alignment=TA_LEFT,
    )

    # Заголовки: serif regular, без bold
    h1 = ParagraphStyle(
        "h1",
        parent=base,
        fontName="PP-Head",
        fontSize=22,
        leading=28,
        textColor=C_ACCENT,
        spaceAfter=10,
        spaceBefore=2,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="PP-Head",
        fontSize=15,
        leading=20,
        textColor=C_ACCENT,
        spaceBefore=10,
        spaceAfter=8,
    )

    h3 = ParagraphStyle(
        "h3",
        parent=base,
        fontName="PP-Head",
        fontSize=13,
        leading=18,
        textColor=C_ACCENT,
        spaceBefore=10,
        spaceAfter=6,
    )

    subtle = ParagraphStyle(
        "subtle",
        parent=base,
        fontSize=10.5,
        leading=16,
        textColor=C_MUTED,
        spaceAfter=8,
    )

    title_center = ParagraphStyle(
        "title_center",
        parent=h1,
        alignment=TA_CENTER,
    )

    center = ParagraphStyle(
        "center",
        parent=base,
        alignment=TA_CENTER,
    )

    story = []

    # ------------------------
    # PAGE 1: COVER + Введение + Структура внимания
    # (чтобы НЕ было пустого листа)
    # ------------------------
    logo_mark = _safe_logo_path("logo_mark.png")
    logo_light = _safe_logo_path("logo_light.png")

    story.append(Spacer(1, 10*mm))

    # logo mark (кружочек)
    if logo_mark:
        try:
            img = Image(logo_mark)
            img._restrictSize(34*mm, 34*mm)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 6*mm))
        except Exception:
            story.append(Spacer(1, 10*mm))

    # logo light (надпись)
    if logo_light:
        try:
            img2 = Image(logo_light)
            img2._restrictSize(120*mm, 22*mm)
            img2.hAlign = "CENTER"
            story.append(img2)
            story.append(Spacer(1, 10*mm))
        except Exception:
            pass
    else:
        story.append(Paragraph(brand_name, title_center))
        story.append(Spacer(1, 6*mm))

    story.append(Paragraph("Индивидуальный отчёт по системе потенциалов человека 3×3", center))
    story.append(Spacer(1, 8*mm))

    # мета-блок (без жирного)
    today = date.today().strftime("%d.%m.%Y")
    meta_lines = [
        f"Для: {client_name}",
        f"Запрос: {request}" if request else "",
        f"Дата: {today}",
    ]
    meta_lines = [x for x in meta_lines if x]
    story.append(Paragraph("<br/>".join(meta_lines), subtle))

    # Введение (твой текст)
    story.append(Paragraph("Введение", h2))
    intro = (
        "Этот отчёт — результат индивидуальной диагностики, направленной на выявление природного способа мышления, "
        "мотивации и реализации. Он не описывает качества характера и не даёт оценок личности. "
        "Его задача — показать, как именно у тебя устроен внутренний механизм, через который ты принимаешь решения, "
        "расходуешь энергию и достигаешь результата."
    )
    story.append(Paragraph(intro, base))

    value = (
        "Практическая ценность отчёта в том, что он помогает точнее понимать себя и свои реакции, "
        "снижает внутренние конфликты между «хочу», «надо» и «делаю», "
        "и даёт ясность, где стоит держать фокус, а где — не перегружать себя."
    )
    story.append(Paragraph(value, base))

    # Структура внимания
    story.append(Paragraph("Структура внимания и распределение энергии", h2))
    struct = (
        "В основе интерпретации лежит матрица потенциалов 3×3, где каждый ряд выполняет свою функцию. "
        "В твоей системе распределение внимания выглядит следующим образом:"
    )
    story.append(Paragraph(struct, base))

    # список — аккуратно, без эмодзи, можно маркеры точками
    bullets = [
        "1 ряд — 60% фокуса внимания. Основа личности, способ реализации и создания ценности.",
        "2 ряд — 30% фокуса внимания. Источник энергии, восстановления и живого контакта с людьми.",
        "3 ряд — 10% фокуса внимания. Зоны риска и перегруза.",
    ]
    story.append(Paragraph("• " + "<br/>• ".join(bullets), base))

    tail = (
        "Такое распределение позволяет сохранить внутренний баланс и не тратить ресурс на задачи, "
        "которые не соответствуют твоей природе."
    )
    story.append(Paragraph(tail, base))

    story.append(PageBreak())

    # ------------------------
    # PAGE 2: Матрица + Первый ряд (динамично из движка)
    # ------------------------
    t = _strip_md(client_report_text or "")
    table_data = _md_table_to_data(t)

    story.append(Paragraph("Твоя матрица потенциалов", h2))
    story.append(Spacer(1, 2*mm))

    if table_data:
        tbl = Table(table_data, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "PP-Body"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),
            ("BACKGROUND", (0, 0), (-1, 0), C_SOFT),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_ACCENT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, C_LINE),
            ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#E6E2F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 10*mm))
    else:
        story.append(Paragraph(
            "Матрица не распознана как таблица в markdown. "
            "Проверь, что движок передаёт таблицу с символами | ... |.",
            subtle
        ))
        story.append(Spacer(1, 8*mm))

    # ВАЖНО: ниже мы НЕ “затираем” интерпретации.
    # Мы печатаем весь текст движка, но “странично”:
    # На стр.2 хотим, чтобы попал 1 ряд (если он есть), иначе просто первые блоки.
    story.append(Paragraph("Первый ряд", h2))

    # Простой механизм: возьмём кусок текста от "ПЕРВЫЙ РЯД" до "ВТОРОЙ РЯД", если найдено.
    def slice_between(src: str, start_kw: str, end_kw: str) -> str | None:
        s = src.find(start_kw)
        if s == -1:
            return None
        e = src.find(end_kw, s + len(start_kw))
        if e == -1:
            return src[s:].strip()
        return src[s:e].strip()

    first_row = slice_between(t, "ПЕРВЫЙ РЯД", "ВТОРОЙ РЯД") or slice_between(t, "Первый ряд", "Второй ряд")
    if not first_row:
        # fallback — первые 6–8 абзацев после таблицы
        paras = _split_paragraphs(t)
        first_row = "\n\n".join(paras[:8])

    for p in _split_paragraphs(first_row):
        story.append(Paragraph(p, base))

    story.append(PageBreak())

    # ------------------------
    # PAGE 3: Второй ряд
    # ------------------------
    story.append(Paragraph("Второй ряд", h2))
    second_row = slice_between(t, "ВТОРОЙ РЯД", "ТРЕТИЙ РЯД") or slice_between(t, "Второй ряд", "Третий ряд")
    if not second_row:
        # fallback — средняя часть
        paras = _split_paragraphs(t)
        second_row = "\n\n".join(paras[8:16]) if len(paras) > 10 else t

    for p in _split_paragraphs(second_row):
        story.append(Paragraph(p, base))

    story.append(PageBreak())

    # ------------------------
    # PAGE 4: Третий ряд + Итоги/инсайты/почему не получается/заметки (из движка)
    # ------------------------
    story.append(Paragraph("В итоге", h2))

    third_plus = slice_between(t, "ТРЕТИЙ РЯД", "О методологии") or slice_between(t, "Третий ряд", "О методологии")
    if not third_plus:
        # fallback — конец текста (кроме методологии/автора)
        third_plus = t

    # Если в движке реально нет третьего ряда — просто печатаем то, что есть (не выдумываем).
    for p in _split_paragraphs(third_plus):
        story.append(Paragraph(p, base))

    # Заметки (линии)
    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Заметки", h2))
    for _ in range(12):
        story.append(Spacer(1, 3*mm))
        story.append(Paragraph("______________________________________________________________", subtle))

    story.append(Spacer(1, 4*mm))
    story.append(Paragraph(
        "Этот отчёт предназначен для личного использования. Возвращайтесь к нему по мере изменений и принятия решений.",
        subtle
    ))

    story.append(PageBreak())

    # ------------------------
    # PAGE 5: Методология + Об авторе (в конец)
    # ------------------------
    story.append(Paragraph("О методологии", h2))

    methodology_block = slice_between(t, "О методологии", "Об авторе") or slice_between(t, "О МЕТОДОЛОГИИ", "ОБ АВТОРЕ")
    if not methodology_block:
        methodology_block = (
            "В основе данного отчёта лежит методология Системы Потенциалов Человека (СПЧ) — прикладной аналитический подход "
            "к изучению природы мышления, мотивации и способов реализации человека. "
            "СПЧ рассматривает человека не через типы личности или поведенческие роли, а через внутренние механизмы восприятия, "
            "включения в действие и удержания результата. "
            "Важно: СПЧ не является психометрическим тестом в классическом понимании и не претендует на медицинскую диагностику. "
            "Это карта внутренних механизмов, помогающая точнее выстраивать решения и развитие без насилия над собой."
        )

    for p in _split_paragraphs(methodology_block):
        story.append(Paragraph(p, base))

    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Об авторе", h2))

    author_block = slice_between(t, "Об авторе", "") or slice_between(t, "ОБ АВТОРЕ", "")
    if not author_block:
        author_block = (
            "Asselya Zhanybek — эксперт в области оценки и развития человеческого капитала. "
            "Профессиональный фокус — проекты оценки компетенций и развития управленческих команд в национальных компаниях "
            "и европейском консалтинге с применением психометрических инструментов. "
            "Практика сфокусирована на анализе человеческих способностей, потенциалов и механизмов реализации "
            "в профессиональном и жизненном контексте."
        )

    # чуть уже по ширине: делаем через большие боковые отступы в ParagraphStyle
    author_style = ParagraphStyle(
        "author",
        parent=base,
        leftIndent=12*mm,
        rightIndent=12*mm,
    )
    for p in _split_paragraphs(author_block):
        story.append(Paragraph(p, author_style))

    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
    )

    return buf.getvalue()