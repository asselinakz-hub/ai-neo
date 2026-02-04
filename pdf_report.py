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
)

# ------------------------
# Paths
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")

# ВАЖНО: у тебя папка logos, не brand
LOGO_DIR = os.path.join(ASSETS_DIR, "logos")

# ------------------------
# Colors (calm, premium)
# ------------------------
# Мягкий off-white, чтобы не было эффекта "вклейки" логотипа
C_BG = colors.HexColor("#F7F6F2")     # можно вернуть #FFFFFF если захочешь
C_TEXT = colors.HexColor("#121212")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")   # soft lavender-gray
C_ACCENT = colors.HexColor("#5B2B6C") # deep plum

# ------------------------
# Fonts (body: Cyrillic safe)
# ------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    """
    Body font: DejaVuSans (Cyrillic safe)
    Headings: built-in Times-Roman (serif), no bold
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    regular = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    if not os.path.exists(regular):
        raise RuntimeError(f"Font not found: {regular}")

    if os.path.getsize(regular) < 10_000:
        raise RuntimeError(f"Font file looks corrupted: {regular}")

    pdfmetrics.registerFont(TTFont("PP-Body", regular))
    _FONTS_REGISTERED = True


# ------------------------
# Helpers
# ------------------------
def _safe_logo_path(filename: str) -> str | None:
    p = os.path.join(LOGO_DIR, filename)
    return p if os.path.exists(p) else None

def _strip_md(s: str) -> str:
    if not s:
        return ""
    s = s.replace("```", "")
    s = s.replace("\t", "    ")
    s = re.sub(r"</?[^>]+>", "", s)     # remove html tags
    # убираем "лишние" разделители из движка
    s = re.sub(r"^\s*---\s*$", "", s, flags=re.MULTILINE)
    s = re.sub(r"^\s*###\s*$", "", s, flags=re.MULTILINE)
    return s.strip()

def _normalize_spaces(s: str) -> str:
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def _format_date_ru(d: date | None) -> str:
    if not d:
        d = date.today()
    try:
        return d.strftime("%d.%m.%Y")
    except Exception:
        return str(d)

def _parse_matrix_from_text(text: str):
    """
    Поддержка 2 форматов:
    1) markdown pipe-table: | Ряд | ... |
    2) простой вид:
       Ряд Восприятие Мотивация Инструмент
       1 Рубин Аметист Цитрин
       2 Гранат Янтарь Шунгит
       3 Изумруд Сапфир Гелиодор
    Возвращает list[list[str]] или None
    """
    t = _strip_md(text)

    # 1) markdown table
    lines = [l.strip() for l in t.splitlines() if l.strip()]
    pipe_lines = [l for l in lines if "|" in l]
    if pipe_lines:
        parsed = []
        for r in pipe_lines:
            if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", r):
                continue
            parts = [c.strip() for c in r.strip("|").split("|")]
            if len(parts) >= 4:
                parsed.append(parts[:4])
        if parsed:
            return parsed

    # 2) простая таблица
    # ищем блок после "Твоя матрица потенциалов"
    m = re.search(r"Твоя матрица потенциалов\s*(.+?)(?:\n\s*\n|$)", t, flags=re.S)
    block = m.group(1) if m else ""
    block_lines = [l.strip() for l in block.splitlines() if l.strip()]
    # если в pdf-стиле: "Ряд Восприятие Мотивация Инструмент" + 3 строки
    if block_lines and len(block_lines) >= 4:
        header = block_lines[0]
        if "Ряд" in header and "Восприятие" in header and "Мотивация" in header and "Инструмент" in header:
            rows = []
            rows.append(["Ряд", "Восприятие", "Мотивация", "Инструмент"])
            for l in block_lines[1:4]:
                parts = l.split()
                if len(parts) >= 4:
                    rows.append([parts[0], parts[1], parts[2], parts[3]])
            if len(rows) == 4:
                return rows

    return None

def _extract_section(text: str, start_keys: list[str], end_keys: list[str]) -> str:
    """
    Берёт кусок текста между start_keys и ближайшим end_keys.
    Если не найдено — возвращает "".
    """
    t = _normalize_spaces(_strip_md(text))
    start_pos = -1
    start_key_found = None
    for k in start_keys:
        p = t.lower().find(k.lower())
        if p != -1 and (start_pos == -1 or p < start_pos):
            start_pos = p
            start_key_found = k

    if start_pos == -1:
        return ""

    # отрезаем до конца заголовка (до следующей строки)
    sub = t[start_pos:]
    # ищем конец по end_keys
    end_pos = None
    sub_lower = sub.lower()
    for ek in end_keys:
        p = sub_lower.find(ek.lower())
        if p != -1 and p > 0:
            end_pos = p if end_pos is None else min(end_pos, p)

    content = sub if end_pos is None else sub[:end_pos]
    # убираем сам заголовок, если он в начале
    # например: "Второй ряд\nВторой ряд — ..."
    content = re.sub(r"^\s*(" + "|".join([re.escape(k) for k in start_keys]) + r")\s*\n", "", content, flags=re.I)
    return content.strip()

def _split_into_short_paragraphs(text: str, max_lines: int = 5) -> list[str]:
    """
    Делает "премиум воздух": дробит длинные абзацы.
    (Оценка по длине предложений, без идеальной лингвистики)
    """
    t = _normalize_spaces(_strip_md(text))
    if not t:
        return []

    # сохраняем списки
    blocks = re.split(r"\n\s*\n", t)
    out = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue

        # если это список
        if re.search(r"^\s*[•\-\*]\s+", b, flags=re.M):
            out.append(b)
            continue

        # если абзац очень длинный — режем по предложениям
        sentences = re.split(r"(?<=[\.\!\?])\s+", b)
        cur = ""
        line_count = 0
        for s in sentences:
            if not s:
                continue
            # грубо считаем "строки" через длину
            est_lines = max(1, len(s) // 90)
            if line_count + est_lines > max_lines and cur:
                out.append(cur.strip())
                cur = s
                line_count = est_lines
            else:
                cur = (cur + " " + s).strip()
                line_count += est_lines
        if cur.strip():
            out.append(cur.strip())
    return out


# ------------------------
# Page background + footer
# ------------------------
def _draw_background(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(C_BG)
    canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canvas.restoreState()

def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials"):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Body", 9)
    canvas.drawString(doc.leftMargin, y + 2, brand_name)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Body", 9)
    canvas.drawRightString(A4[0] - doc.rightMargin, y + 2, str(doc.page))

    canvas.restoreState()

def _on_page(canvas, doc, brand_name: str):
    _draw_background(canvas, doc)
    _draw_footer(canvas, doc, brand_name=brand_name)


# ------------------------
# Main builder
# ------------------------
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
    brand_name: str = "Personal Potentials",
    report_date: date | None = None,
    include_notes_page: bool = True,
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

    # Body (sans, readable, airy)
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Body",
        fontSize=11.5,
        leading=18,  # 1.55x
        textColor=C_TEXT,
        spaceAfter=10,   # воздух между абзацами
        alignment=TA_LEFT,
    )

    small = ParagraphStyle(
        "small",
        parent=base,
        fontSize=10.5,
        leading=16,
        textColor=C_MUTED,
    )

    # Headings: serif regular (no bold)
    h1 = ParagraphStyle(
        "h1",
        parent=base,
        fontName="Times-Roman",
        fontSize=22,
        leading=28,
        textColor=C_ACCENT,
        alignment=TA_CENTER,
        spaceAfter=10,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="Times-Roman",
        fontSize=15,
        leading=20,
        textColor=C_ACCENT,
        spaceBefore=12,
        spaceAfter=8,
    )

    # Smaller heading for end blocks (Methodology/Author)
    h3 = ParagraphStyle(
        "h3",
        parent=base,
        fontName="Times-Roman",
        fontSize=13,
        leading=18,
        textColor=C_ACCENT,
        spaceBefore=10,
        spaceAfter=6,
    )

    # Divider line as a thin table
    def divider():
        t = Table([[""]], colWidths=[A4[0] - doc.leftMargin - doc.rightMargin])
        t.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, -1), 0.8, C_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t

    story = []
    text = _normalize_spaces(_strip_md(client_report_text or ""))

    # ------------------------
    # PAGE 1 (STATIC COVER + INTRO + STRUCTURE)
    # ------------------------
    logo_mark = _safe_logo_path("logo_mark.png")
    logo_light = _safe_logo_path("logo_light.png")

    story.append(Spacer(1, 6 * mm))

    # Mark (circle) first
    if logo_mark:
        img = Image(logo_mark)
        img._restrictSize(34 * mm, 34 * mm)
        img.hAlign = "CENTER"
        story.append(img)
        story.append(Spacer(1, 6 * mm))

    # Light wordmark under
    if logo_light:
        img2 = Image(logo_light)
        img2._restrictSize(120 * mm, 18 * mm)
        img2.hAlign = "CENTER"
        story.append(img2)
        story.append(Spacer(1, 10 * mm))
    else:
        story.append(Paragraph(brand_name, h1))
        story.append(Spacer(1, 6 * mm))

    # Title block
    story.append(Paragraph("Индивидуальный отчёт по системе потенциалов человека 3×3", small))
    story.append(Spacer(1, 6 * mm))

    # Meta (NO bold)
    story.append(Paragraph(f"Для: {client_name}", base))
    if request:
        story.append(Paragraph(f"Запрос: {request}", base))
    story.append(Paragraph(f"Дата: {_format_date_ru(report_date)}", base))

    story.append(Spacer(1, 6 * mm))
    story.append(divider())

    # Intro (static, per твоим правкам)
    story.append(Paragraph("Введение", h2))
    intro_text = (
        "Этот отчёт — результат индивидуальной диагностики, направленной на выявление природного способа мышления, "
        "мотивации и реализации. Он не описывает качества характера и не даёт оценок личности. Его задача — показать, "
        "как именно у тебя устроен внутренний механизм, через который ты принимаешь решения, расходуешь энергию и достигаешь результата."
    )
    intro_value = (
        "Практическая ценность отчёта в том, что он помогает точнее понимать себя и свои реакции, "
        "снижает внутренние конфликты между «хочу», «надо» и «делаю», и даёт ясность, где стоит держать фокус, "
        "а где — не перегружать себя."
    )
    for p in _split_into_short_paragraphs(intro_text):
        story.append(Paragraph(p, base))
    for p in _split_into_short_paragraphs(intro_value):
        story.append(Paragraph(p, base))

    story.append(Paragraph("Структура внимания и распределение энергии", h2))
    structure_text = (
        "В основе интерпретации лежит матрица потенциалов 3×3, где каждый ряд выполняет свою функцию. "
        "В твоей системе распределение внимания выглядит следующим образом:"
        "<br/>• 1 ряд — 60% фокуса внимания. Основа личности, способ реализации и создания ценности."
        "<br/>• 2 ряд — 30% фокуса внимания. Источник энергии, восстановления и живого контакта с людьми."
        "<br/>• 3 ряд — 10% фокуса внимания. Зоны риска и перегруза."
        "<br/><br/>Такое распределение позволяет сохранить внутренний баланс и не тратить ресурс на задачи, которые не соответствуют твоей природе."
    )
    story.append(Paragraph(structure_text, base))

    story.append(PageBreak())

    # ------------------------
    # PAGE 2 (MATRIX + FIRST ROW)
    # ------------------------
    story.append(Paragraph("Твоя матрица потенциалов", h2))
    matrix = _parse_matrix_from_text(text)

    if matrix:
        tbl = Table(matrix, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "PP-Body"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
            ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),

            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F1EFF7")),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_ACCENT),

            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E3DEEF")),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8 * mm))
    else:
        story.append(Paragraph("Матрица не распознана в тексте движка. Проверь, что движок отдаёт блок «Твоя матрица потенциалов».", small))
        story.append(Spacer(1, 6 * mm))

    # First row section from engine
    first_row = _extract_section(
        text,
        start_keys=["Первый ряд", "ПЕРВЫЙ РЯД"],
        end_keys=["Второй ряд", "ВТОРОЙ РЯД", "Третий ряд", "ТРЕТИЙ РЯД", "Почему может", "Итоговая картина", "О методологии", "Об авторе", "Заметки", "В итоге"]
    )
    if first_row:
        story.append(Paragraph("Первый ряд", h2))
        for p in _split_into_short_paragraphs(first_row):
            story.append(Paragraph(p.replace("\n", "<br/>"), base))
    else:
        story.append(Paragraph("Первый ряд", h2))
        story.append(Paragraph("Движок не передал блок «Первый ряд». Проверь, что он присутствует в client_report_text.", small))

    story.append(PageBreak())

    # ------------------------
    # PAGE 3 (SECOND ROW)
    # ------------------------
    second_row = _extract_section(
        text,
        start_keys=["Второй ряд", "ВТОРОЙ РЯД"],
        end_keys=["Третий ряд", "ТРЕТИЙ РЯД", "Почему может", "Итоговая картина", "О методологии", "Об авторе", "Заметки", "В итоге"]
    )
    story.append(Paragraph("Второй ряд", h2))
    if second_row:
        for p in _split_into_short_paragraphs(second_row):
            story.append(Paragraph(p.replace("\n", "<br/>"), base))
    else:
        story.append(Paragraph("Движок не передал блок «Второй ряд».", small))

    story.append(PageBreak())

    # ------------------------
    # PAGE 4 (THIRD ROW + WHY + SUMMARY + INSIGHTS)
    # ------------------------
    third_row = _extract_section(
        text,
        start_keys=["Третий ряд", "ТРЕТИЙ РЯД"],
        end_keys=["Почему может", "Итоговая картина", "О методологии", "Об авторе", "Заметки", "В итоге"]
    )
    why_block = _extract_section(
        text,
        start_keys=["Почему может не получаться", "ПОЧЕМУ ИНОГДА НЕ ПОЛУЧАЕТСЯ", "Почему не получается"],
        end_keys=["Итоговая картина", "О методологии", "Об авторе", "Заметки", "В итоге"]
    )
    summary_block = _extract_section(
        text,
        start_keys=["Итоговая картина", "Итоговая картина"],
        end_keys=["О методологии", "Об авторе", "Заметки", "В итоге"]
    )
    insights_block = _extract_section(
        text,
        start_keys=["Главные инсайты", "УПРАЖНЕНИЕ", "3 инсайта"],
        end_keys=["О методологии", "Об авторе", "Заметки", "В итоге"]
    )

    if third_row:
        story.append(Paragraph("Третий ряд", h2))
        for p in _split_into_short_paragraphs(third_row):
            story.append(Paragraph(p.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 3 * mm))
        story.append(divider())

    if why_block:
        story.append(Paragraph("Почему может не получаться так, как хочется", h2))
        for p in _split_into_short_paragraphs(why_block):
            story.append(Paragraph(p.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 3 * mm))
        story.append(divider())

    if summary_block:
        story.append(Paragraph("Итоговая картина", h2))
        for p in _split_into_short_paragraphs(summary_block):
            story.append(Paragraph(p.replace("\n", "<br/>"), base))

    if insights_block:
        story.append(Spacer(1, 4 * mm))
        story.append(divider())
        story.append(Paragraph("Главные инсайты", h2))
        for p in _split_into_short_paragraphs(insights_block):
            story.append(Paragraph(p.replace("\n", "<br/>"), base))

    story.append(PageBreak())

    # ------------------------
    # PAGE 5 (METHODOLOGY + AUTHOR) — always separate
    # ------------------------
    methodology = _extract_section(
        text,
        start_keys=["О методологии", "О МЕТОДОЛОГИИ", "Методология"],
        end_keys=["Об авторе", "Обо мне", "Заметки", "В итоге"]
    )
    author = _extract_section(
        text,
        start_keys=["Об авторе", "Обо мне", "Asselya Zhanybek —"],
        end_keys=["Заметки", "В итоге"]
    )

    story.append(Paragraph("О методологии", h3))
    if methodology:
        for p in _split_into_short_paragraphs(methodology):
            story.append(Paragraph(p.replace("\n", "<br/>"), base))
    else:
        story.append(Paragraph(
            "В основе данного отчёта лежит методология Системы Потенциалов Человека (СПЧ) — прикладной аналитический подход к изучению "
            "природы мышления, мотивации и способов реализации человека. СПЧ не является медицинской или клинической диагностикой. "
            "Это карта внутренних механизмов, которая помогает точнее выстраивать решения и развитие без насилия над собой.",
            base
        ))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph("Об авторе", h3))
    # текст делаем визуально "подписью": уже, чем страница
    author_text = author.strip() if author else (
        "Asselya Zhanybek — эксперт в области оценки и развития человеческого капитала. Профессиональный фокус — проекты оценки компетенций "
        "и развития управленческих команд в национальных компаниях и европейском консалтинге с применением психометрических инструментов. "
        "Практика сфокусирована на анализе человеческих способностей, потенциалов и механизмов реализации в профессиональном и жизненном контексте."
    )
    # узкая колонка через таблицу
    author_tbl = Table([[Paragraph(author_text, base)]], colWidths=[120 * mm])
    author_tbl.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(author_tbl)

    # ------------------------
    # NOTES PAGE (optional, separate)
    # ------------------------
    if include_notes_page:
        story.append(PageBreak())
        story.append(Paragraph("Заметки", h2))
        story.append(Spacer(1, 4 * mm))

        for _ in range(14):
            line = Table([[""]], colWidths=[A4[0] - doc.leftMargin - doc.rightMargin])
            line.setStyle(TableStyle([
                ("LINEBELOW", (0, 0), (-1, -1), 0.6, colors.HexColor("#DDD7E8")),
                ("TOPPADDING", (0, 0), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ]))
            story.append(line)

        story.append(Spacer(1, 6 * mm))
        story.append(Paragraph(
            "Этот отчёт предназначен для личного использования. Возвращайтесь к нему по мере изменений и принятия решений.",
            small
        ))

    doc.build(
        story,
        onFirstPage=lambda c, d: _on_page(c, d, brand_name),
        onLaterPages=lambda c, d: _on_page(c, d, brand_name),
    )

    return buf.getvalue()