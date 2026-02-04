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
)

# ------------------------
# Paths
# ------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
FONT_DIR = os.path.join(ASSETS_DIR, "fonts")
BRAND_DIR = os.path.join(ASSETS_DIR, "brand")

# allow finding logos in dev env / streamlit / container
EXTRA_BRAND_DIRS = [
    BRAND_DIR,
    BASE_DIR,
    "/mnt/data",
]

# ------------------------
# Colors (calm, premium)
# ------------------------
C_TEXT = colors.HexColor("#121212")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")
C_ACCENT = colors.HexColor("#5B2B6C")
C_ACCENT_2 = colors.HexColor("#8C4A86")
C_SOFT_BG = colors.HexColor("#F7F5FB")
C_GRID = colors.HexColor("#E6E2F0")

# ------------------------
# Fonts (Cyrillic-safe)
#   - Body: DejaVuSans (sans)
#   - Headings: DejaVuSerif (serif) if available, else fallback to DejaVuSans
# ------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    sans = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    if not os.path.exists(sans):
        raise RuntimeError(f"Font not found: {sans}")
    if os.path.getsize(sans) < 10_000:
        raise RuntimeError(f"Font file looks corrupted: {sans}")

    serif = os.path.join(FONT_DIR, "DejaVuSerif.ttf")
    serif_use = serif if os.path.exists(serif) else sans
    if os.path.getsize(serif_use) < 10_000:
        raise RuntimeError(f"Font file looks corrupted: {serif_use}")

    pdfmetrics.registerFont(TTFont("PP-Sans", sans))
    pdfmetrics.registerFont(TTFont("PP-Serif", serif_use))

    _FONTS_REGISTERED = True

# ------------------------
# Logos
# ------------------------
def _find_logo(*names: str) -> str | None:
    for n in names:
        if not n:
            continue

        # absolute path
        if os.path.isabs(n) and os.path.exists(n):
            return n

        # try in known dirs
        for d in EXTRA_BRAND_DIRS:
            p = os.path.join(d, n)
            if os.path.exists(p):
                return p

    return None

# ------------------------
# Text cleanup: NO BOLD in descriptive body
# ------------------------
_MD_BOLD_RE = re.compile(r"(\*\*|__)(.+?)(\*\*|__)", re.DOTALL)
_B_TAG_RE = re.compile(r"</?b>", re.IGNORECASE)

def _clean_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("```", "")
    s = s.replace("\t", "    ")
    s = _B_TAG_RE.sub("", s)
    s = _MD_BOLD_RE.sub(lambda m: m.group(2), s)
    s = re.sub(r"</?[^>]+>", "", s)  # remove other html tags
    return s.strip()

def _md_table_to_data(text: str):
    """
    Finds first markdown-like table (pipes).
    Returns parsed rows or None.
    """
    lines = [l.rstrip() for l in text.splitlines()]

    table_lines = []
    started = False
    for l in lines:
        if "|" in l:
            table_lines.append(l.strip())
            started = True
        elif started:
            break

    if not table_lines:
        return None

    parsed = []
    for r in table_lines:
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", r):
            continue
        parts = [c.strip() for c in r.strip("|").split("|")]
        if len(parts) >= 2:
            parsed.append(parts)

    return parsed if parsed else None

# ------------------------
# Dynamic section parsing from engine text
# ------------------------
def _extract_sections(engine_text: str) -> dict:
    """
    Tries to split engine report into sections by headings that usually exist.
    Works with:
      - 'ПЕРВЫЙ РЯД'
      - 'ВТОРОЙ РЯД'
      - 'ТРЕТИЙ РЯД'
      - 'Итоговая картина'
      - 'ПОЧЕМУ ИНОГДА НЕ ПОЛУЧАЕТСЯ' etc.
      - 'ЗАМЕТКИ'
      - 'О методологии' / 'Об авторе'
    Returns dict with keys:
      first_row, second_row, third_row, final_misc, methodology, author, notes
    """
    t = _clean_text(engine_text)
    if not t:
        return {
            "first_row": "",
            "second_row": "",
            "third_row": "",
            "final_misc": "",
            "methodology": "",
            "author": "",
            "notes": "",
            "full": "",
        }

    # Normalize separators
    t = t.replace("\r\n", "\n")

    # Helper: find block between headings
    def grab(start_pat: str, end_pats: list[str]) -> str:
        m = re.search(start_pat, t, flags=re.IGNORECASE | re.MULTILINE)
        if not m:
            return ""
        start = m.start()
        # find nearest end
        end = len(t)
        for ep in end_pats:
            m2 = re.search(ep, t[m.end():], flags=re.IGNORECASE | re.MULTILINE)
            if m2:
                end = min(end, m.end() + m2.start())
        return t[start:end].strip()

    first = grab(r"^.*ПЕРВ(ЫЙ|ЫИ)\s+РЯД.*$", [r"^.*ВТОР(ОЙ|ОИ)\s+РЯД.*$", r"^.*ТРЕТ(ИЙ|ИИ)\s+РЯД.*$", r"^.*Итоговая картина.*$"])
    second = grab(r"^.*ВТОР(ОЙ|ОИ)\s+РЯД.*$", [r"^.*ТРЕТ(ИЙ|ИИ)\s+РЯД.*$", r"^.*Итоговая картина.*$"])
    third = grab(r"^.*ТРЕТ(ИЙ|ИИ)\s+РЯД.*$", [r"^.*Итоговая картина.*$", r"^.*О методологии.*$", r"^.*Об авторе.*$", r"^.*ЗАМЕТКИ.*$"])

    final_misc = grab(r"^.*Итоговая картина.*$", [r"^.*О методологии.*$", r"^.*Об авторе.*$", r"^.*ЗАМЕТКИ.*$"])
    # If there are extra blocks like "ПОЧЕМУ..." and "УПРАЖНЕНИЕ..." but no "Итоговая картина",
    # we'll take everything after third row as misc.
    if not final_misc and third:
        # take everything after third block
        idx = t.lower().find(third.lower())
        if idx != -1:
            after_third = t[idx + len(third):].strip()
            final_misc = after_third

    methodology = grab(r"^.*О методологии.*$", [r"^.*Об авторе.*$", r"^.*ЗАМЕТКИ.*$"])
    author = grab(r"^.*Об авторе.*$", [r"^.*ЗАМЕТКИ.*$"])
    notes = grab(r"^.*ЗАМЕТКИ.*$", [])

    # Remove methodology/author from misc if they are embedded there
    for x in [methodology, author, notes]:
        if x and final_misc:
            final_misc = final_misc.replace(x, "").strip()

    return {
        "first_row": first,
        "second_row": second,
        "third_row": third,
        "final_misc": final_misc,
        "methodology": methodology,
        "author": author,
        "notes": notes,
        "full": t,
    }

def _paragraphs_from_text(text: str) -> list[str]:
    """
    Splits into short-ish paragraphs to avoid 'wall of text'.
    Keeps bullet lines '• ' on separate paragraphs.
    """
    text = (text or "").strip()
    if not text:
        return []

    # keep bullets: split by blank lines first
    blocks = re.split(r"\n\s*\n", text)
    out = []
    for b in blocks:
        b = b.strip()
        if not b:
            continue

        # If block contains bullets, split them
        if "•" in b:
            lines = [x.strip() for x in b.splitlines() if x.strip()]
            for ln in lines:
                out.append(ln)
            continue

        # Otherwise keep as one paragraph, but wrap long text by sentence
        # (soft split)
        if len(b) > 520:
            parts = re.split(r"(?<=[\.\!\?])\s+", b)
            cur = ""
            for s in parts:
                if not s:
                    continue
                if len(cur) + len(s) + 1 <= 520:
                    cur = (cur + " " + s).strip()
                else:
                    if cur:
                        out.append(cur)
                    cur = s.strip()
            if cur:
                out.append(cur)
        else:
            out.append(b)

    return out

# ------------------------
# Footer
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
# Small visual helpers
# ------------------------
def _title(story, text: str, style_title: ParagraphStyle):
    story.append(Paragraph(text, style_title))
    # thin line under heading
    t = Table([[""]], colWidths=[160 * mm], rowHeights=[1])
    t.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, -1), 0.8, C_LINE)]))
    story.append(Spacer(1, 2 * mm))
    story.append(t)
    story.append(Spacer(1, 6 * mm))

def _as_date_str(d: date | str | None) -> str:
    if not d:
        return date.today().strftime("%d.%m.%Y")
    if isinstance(d, date):
        return d.strftime("%d.%m.%Y")
    return str(d)

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

    # Body typography (premium, breathable)
    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Sans",
        fontSize=11.5,
        leading=18,            # ~1.55
        textColor=C_TEXT,
        spaceAfter=10,
        alignment=TA_LEFT,
    )

    small = ParagraphStyle(
        "small",
        parent=base,
        fontSize=10.5,
        leading=16,
        textColor=C_MUTED,
        spaceAfter=8,
    )

    # Headings: serif, NOT bold
    h1 = ParagraphStyle(
        "h1",
        parent=base,
        fontName="PP-Serif",
        fontSize=22,
        leading=28,
        textColor=C_ACCENT,
        alignment=TA_CENTER,
        spaceAfter=4,
    )

    h1_sub = ParagraphStyle(
        "h1_sub",
        parent=base,
        fontName="PP-Serif",
        fontSize=13.5,
        leading=20,
        textColor=C_ACCENT_2,
        alignment=TA_CENTER,
        spaceAfter=10,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="PP-Serif",
        fontSize=16,
        leading=22,
        textColor=C_ACCENT,
        spaceBefore=2,
        spaceAfter=2,
    )

    # -------- Parse engine content (dynamic!) --------
    cleaned_engine = _clean_text(client_report_text or "")
    sections = _extract_sections(cleaned_engine)
    table_data = _md_table_to_data(cleaned_engine)

    story = []

    # =========================================================
    # PAGE 1: COVER + INTRO + ATTENTION STRUCTURE
    # =========================================================
    logo_mark = _find_logo("logo_mark.png", "logo_mark.PNG")
    logo_light = _find_logo("logo_light.png", "logo_light.PNG")

    story.append(Spacer(1, 4 * mm))

    # Two logos stacked: mark (circle) then light (wordmark)
    # Even if missing, page still has text, so never blank.
    if logo_mark:
        try:
            img1 = Image(logo_mark)
            img1._restrictSize(22 * mm, 22 * mm)
            img1.hAlign = "CENTER"
            story.append(img1)
            story.append(Spacer(1, 4 * mm))
        except Exception:
            pass

    if logo_light:
        try:
            img2 = Image(logo_light)
            img2._restrictSize(95 * mm, 20 * mm)
            img2.hAlign = "CENTER"
            story.append(img2)
            story.append(Spacer(1, 8 * mm))
        except Exception:
            story.append(Spacer(1, 6 * mm))
    else:
        story.append(Spacer(1, 6 * mm))

    story.append(Paragraph("PERSONAL POTENTIALS", h1))
    story.append(Paragraph("Индивидуальный отчёт по системе потенциалов человека 3×3", h1_sub))

    info = [
        f"Для: {client_name}",
        f"Запрос: {request}" if request else None,
        f"Дата: {_as_date_str(report_date)}",
    ]
    for line in [x for x in info if x]:
        story.append(Paragraph(line, small))

    story.append(Spacer(1, 6 * mm))

    # Intro (static, as you wrote)
    _title(story, "Введение", h2)
    intro_text = (
        "Этот отчёт — результат индивидуальной диагностики, направленной на выявление природного способа мышления, мотивации и реализации.<br/>"
        "Он не описывает качества характера и не даёт оценок личности.<br/>"
        "Его задача — показать, как именно у тебя устроен внутренний механизм, через который ты принимаешь решения, расходуешь энергию и достигаешь результата.<br/><br/>"
        "Практическая ценность отчёта в том, что он:<br/>"
        "• помогает точнее понимать себя и свои реакции;<br/>"
        "• снижает внутренние конфликты между «хочу», «надо» и «делаю»;<br/>"
        "• даёт ясность, где стоит держать фокус, а где — не перегружать себя."
    )
    story.append(Paragraph(intro_text, base))

    _title(story, "Структура внимания и распределение энергии", h2)
    attention_text = (
        "В основе интерпретации лежит матрица потенциалов 3×3, где каждый ряд выполняет свою функцию.<br/><br/>"
        "• 1 ряд — 60% фокуса внимания. Основа личности, способ реализации и создания ценности.<br/>"
        "• 2 ряд — 30% фокуса внимания. Источник энергии, восстановления и живого контакта с людьми.<br/>"
        "• 3 ряд — 10% фокуса внимания. Зоны риска и перегруза.<br/><br/>"
        "Такое распределение позволяет сохранить внутренний баланс и не тратить ресурс на задачи, которые не соответствуют твоей природе."
    )
    story.append(Paragraph(attention_text, base))

    story.append(PageBreak())

    # =========================================================
    # PAGE 2: MATRIX + FIRST ROW
    # =========================================================
    _title(story, "Твоя матрица потенциалов", h2)

    if table_data:
        # premium matrix table (no bold)
        tbl = Table(table_data, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "PP-Sans"),
            ("FONTSIZE", (0, 0), (-1, -1), 11),
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
        story.append(Paragraph(
            "Матрица не распознана как таблица в тексте движка. "
            "Если движок выводит матрицу в формате таблицы с символом “|”, она появится здесь автоматически.",
            small
        ))
        story.append(Spacer(1, 6 * mm))

    # First row (dynamic)
    if sections["first_row"].strip():
        for p in _paragraphs_from_text(sections["first_row"]):
            # keep bullets nicer
            if p.startswith("•"):
                story.append(Paragraph(p, base))
            else:
                story.append(Paragraph(p.replace("\n", " "), base))
    else:
        # fallback: print the beginning of engine text (after table)
        story.append(Paragraph(
            "Блок первого ряда не найден в тексте движка. Проверь, что в report_text есть заголовок «ПЕРВЫЙ РЯД».",
            small
        ))

    story.append(PageBreak())

    # =========================================================
    # PAGE 3: SECOND ROW
    # =========================================================
    if sections["second_row"].strip():
        # title is inside text; still add a clean header for page structure
        _title(story, "Второй ряд", h2)
        for p in _paragraphs_from_text(sections["second_row"]):
            story.append(Paragraph(p.replace("\n", " "), base))
    else:
        _title(story, "Второй ряд", h2)
        story.append(Paragraph(
            "Блок второго ряда не найден в тексте движка. Проверь, что в report_text есть заголовок «ВТОРОЙ РЯД».",
            small
        ))

    story.append(PageBreak())

    # =========================================================
    # PAGE 4: THIRD ROW + FINAL + INSIGHTS/WHY + NOTES (from engine)
    # =========================================================
    _title(story, "Третий ряд и итоговая картина", h2)

    # Third row
    if sections["third_row"].strip():
        for p in _paragraphs_from_text(sections["third_row"]):
            story.append(Paragraph(p.replace("\n", " "), base))
        story.append(Spacer(1, 4 * mm))

    # Final misc (everything else dynamic except methodology/author)
    if sections["final_misc"].strip():
        for p in _paragraphs_from_text(sections["final_misc"]):
            story.append(Paragraph(p.replace("\n", " "), base))

    # Notes area on same page (as you requested)
    story.append(Spacer(1, 6 * mm))
    _title(story, "Заметки", h2)
    story.append(Paragraph(
        "Запиши здесь главные инсайты, вопросы и наблюдения — то, к чему хочется вернуться.",
        base
    ))
    story.append(Spacer(1, 6 * mm))

    lines = [[""] for _ in range(12)]
    notes_tbl = Table(lines, colWidths=[170 * mm], rowHeights=[8 * mm] * len(lines))
    notes_tbl.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 0.35, C_GRID),
    ]))
    story.append(notes_tbl)

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(
        "Этот отчёт предназначен для личного использования. Возвращайтесь к нему по мере изменений и принятия решений.",
        small
    ))

    story.append(PageBreak())

    # =========================================================
    # PAGE 5: METHODOLOGY + AUTHOR (static fallback if not in engine)
    # =========================================================
    _title(story, "О методологии", h2)

    if sections["methodology"].strip():
        for p in _paragraphs_from_text(sections["methodology"]):
            story.append(Paragraph(p.replace("\n", " "), base))
    else:
        # fallback (your approved text)
        methodology_fallback = (
            "В основе данного отчёта лежит методология Системы Потенциалов Человека (СПЧ) — прикладной аналитический подход "
            "к изучению природы мышления, мотивации и способов реализации человека.<br/><br/>"
            "Методология СПЧ рассматривает человека не через типы личности или поведенческие роли, а через внутренние механизмы "
            "восприятия информации, включения в действие и удержания результата. Ключевой принцип системы — каждый человек реализуется "
            "наиболее эффективно, когда опирается на свои природные способы мышления и распределяет внимание между уровнями реализации осознанно.<br/><br/>"
            "Важно: СПЧ не является психометрическим тестом в классическом понимании и не претендует на медицинскую или клиническую диагностику. "
            "Это карта внутренних механизмов, позволяющая точнее выстраивать решения, развитие и профессиональную реализацию без насилия над собой."
        )
        story.append(Paragraph(methodology_fallback, base))

    story.append(Spacer(1, 8 * mm))
    _title(story, "Об авторе", h2)

    if sections["author"].strip():
        for p in _paragraphs_from_text(sections["author"]):
            story.append(Paragraph(p.replace("\n", " "), base))
    else:
        author_fallback = (
            "Asselya Zhanybek — эксперт в области оценки и развития человеческого капитала, с профессиональным фокусом на проектах "
            "оценки компетенций и развития управленческих команд в национальных компаниях и европейском консалтинге, с применением психометрических инструментов.<br/><br/>"
            "Практика сфокусирована на анализе человеческих способностей, потенциалов и механизмов реализации в профессиональном и жизненном контексте. "
            "Методология СПЧ адаптирована в формат онлайн-диагностики и персональных разборов с фокусом на прикладную ценность и устойчивые результаты."
        )
        story.append(Paragraph(author_fallback, base))

    # ------------------------
    # Build
    # ------------------------
    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
    )

    return buf.getvalue()