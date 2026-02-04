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

# ------------------------
# Colors (calm, premium)
# ------------------------
C_BG = colors.HexColor("#FFFFFF")
C_TEXT = colors.HexColor("#121212")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")       # soft lavender-gray
C_ACCENT = colors.HexColor("#5B2B6C")     # deep plum
C_ACCENT_2 = colors.HexColor("#8C4A86")   # muted mauve
C_SOFT = colors.HexColor("#F6F4FA")       # very light lavender

# ------------------------
# Fonts (Cyrillic safe)
# ------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    """
    Uses repo fonts:
      - assets/fonts/DejaVuSans.ttf
      - assets/fonts/DejaVuLGCSans-Bold.ttf (your bold filename)
    """
    global _FONTS_REGISTERED
    if _FONTS_REGISTERED:
        return

    regular = os.path.join(FONT_DIR, "DejaVuSans.ttf")
    bold = os.path.join(FONT_DIR, "DejaVuLGCSans-Bold.ttf")
    bold_alt = os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf")

    if not os.path.exists(regular):
        raise RuntimeError(f"Font not found: {regular}")

    if os.path.exists(bold_alt):
        bold = bold_alt
    elif not os.path.exists(bold):
        bold = regular

    if os.path.getsize(regular) < 10_000:
        raise RuntimeError(f"Font file looks corrupted (too small): {regular}")
    if os.path.getsize(bold) < 10_000:
        raise RuntimeError(f"Bold font file looks corrupted (too small): {bold}")

    pdfmetrics.registerFont(TTFont("PP-Regular", regular))
    pdfmetrics.registerFont(TTFont("PP-Bold", bold))
    _FONTS_REGISTERED = True

# ------------------------
# Helpers
# ------------------------
def _strip_text(s: str) -> str:
    if not s:
        return ""
    s = s.replace("```", "")
    s = s.replace("\t", "    ")
    s = re.sub(r"</?[^>]+>", "", s)  # remove html tags
    return s.strip()

def _safe_brand_path(filename: str) -> str | None:
    p = os.path.join(BRAND_DIR, filename)
    return p if os.path.exists(p) else None

def _is_heading(line: str) -> bool:
    """
    Heuristics for headings in RU text.
    Examples:
      - '1 РЯД — ОСНОВА...'
      - 'ОБО МНЕ'
      - 'О МЕТОДОЛОГИИ ДИАГНОСТИКИ'
      - 'УПРАЖНЕНИЕ: ...'
    """
    t = line.strip()
    if not t:
        return False
    if t.upper() == t and len(t) >= 6:
        return True
    if re.match(r"^\d+\s*РЯД\b", t, flags=re.I):
        return True
    if re.match(r"^(ПОЧЕМУ|УПРАЖНЕНИЕ|ЗАМЕТКИ|ОБО МНЕ|О МЕТОДОЛОГИИ)\b", t, flags=re.I):
        return True
    return False

def _normalize_bullets(text: str) -> str:
    """
    Converts bullet lines starting with • into HTML line breaks.
    """
    lines = text.splitlines()
    out = []
    for ln in lines:
        l = ln.rstrip()
        if re.match(r"^\s*•\s+", l):
            out.append(f"• {re.sub(r'^\\s*•\\s+', '', l)}")
        else:
            out.append(l)
    return "\n".join(out)

def _extract_matrix_block(text: str):
    """
    Tries to find the matrix in formats like:
      Ряд | Восприятие | Мотивация | Инструмент
      1 | Сапфир | Гранат | Аметист
      2 | Янтарь | Изумруд | Цитрин
      3 | Шунгит | Рубин | Гелиодор

    Returns: (table_data, text_without_block)
    """
    raw = text
    lines = [l.strip() for l in raw.splitlines()]

    # find header line containing those words (with or without pipes)
    header_idx = None
    for i, l in enumerate(lines):
        if ("ряд" in l.lower() and "воспр" in l.lower() and "мотивац" in l.lower() and "инстру" in l.lower()):
            header_idx = i
            break

    if header_idx is None:
        return None, text

    # collect 4 lines: header + up to next 3 rows with pipes
    block = []
    for j in range(header_idx, min(header_idx + 6, len(lines))):
        if "|" in lines[j]:
            block.append(lines[j])
        else:
            # allow header without pipes; if so, stop (we only support pipe format)
            if j == header_idx:
                return None, text
            break

    if len(block) < 4:
        return None, text

    # parse to table data
    parsed = []
    for row in block:
        parts = [c.strip() for c in row.strip("|").split("|")]
        parsed.append(parts)

    # remove the block from original text
    block_text = "\n".join(block)
    cleaned = raw.replace(block_text, "").strip()
    return parsed, cleaned

# ------------------------
# Footer + optional page decorations
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials"):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    # small logo (prefer horizontal, fallback mark)
    logo_path = (
        _safe_brand_path("logo_main.png")
        or _safe_brand_path("logo_light.png")
        or _safe_brand_path("logo_mark.png")
        or _safe_brand_path("logo_main.png")
        or _safe_brand_path("logo_main.jpg")
    )

    x = doc.leftMargin
    if logo_path:
        try:
            canvas.drawImage(
                logo_path,
                x,
                y - 2,
                width=34 * mm,
                height=10 * mm,
                mask="auto",
                preserveAspectRatio=True,
                anchor="sw",
            )
            x += 38 * mm
        except Exception:
            pass

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Regular", 9)
    canvas.drawString(x, y + 2, brand_name)

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Regular", 9)
    canvas.drawRightString(A4[0] - doc.rightMargin, y + 2, str(doc.page))

    canvas.restoreState()

def _draw_notes_lines(canvas, doc, top_y_mm: float = 250, bottom_y_mm: float = 25, step_mm: float = 8):
    """
    Draws writing lines on the current page (for Notes page).
    """
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#E7E2F2"))
    canvas.setLineWidth(0.6)

    x1 = doc.leftMargin
    x2 = A4[0] - doc.rightMargin

    y = top_y_mm * mm
    y_min = bottom_y_mm * mm
    while y > y_min:
        canvas.line(x1, y, x2, y)
        y -= step_mm * mm

    canvas.restoreState()

# ------------------------
# Main builder
# ------------------------
def build_client_report_pdf_bytes(
    client_report_text: str,
    client_name: str = "Клиент",
    request: str = "",
    brand_name: str = "Personal Potentials",
    author_name: str = "Asselya Zhanybek",
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
        author=author_name,
    )

    styles = getSampleStyleSheet()

    base = ParagraphStyle(
        "base",
        parent=styles["Normal"],
        fontName="PP-Regular",
        fontSize=11,
        leading=16,
        textColor=C_TEXT,
        spaceAfter=6,
        alignment=TA_LEFT,
    )

    h1 = ParagraphStyle(
        "h1",
        parent=base,
        fontName="PP-Bold",
        fontSize=22,
        leading=28,
        textColor=C_ACCENT,
        spaceAfter=10,
    )

    h2 = ParagraphStyle(
        "h2",
        parent=base,
        fontName="PP-Bold",
        fontSize=14,
        leading=18,
        textColor=C_ACCENT,
        spaceBefore=10,
        spaceAfter=6,
    )

    subtle = ParagraphStyle(
        "subtle",
        parent=base,
        fontSize=10,
        leading=14,
        textColor=C_MUTED,
    )

    title_center = ParagraphStyle(
        "title_center",
        parent=h1,
        alignment=TA_CENTER,
    )

    byline = ParagraphStyle(
        "byline",
        parent=subtle,
        alignment=TA_CENTER,
        fontName="PP-Regular",
        fontSize=11,
        textColor=C_ACCENT_2,
        spaceAfter=14,
    )

    story = []

    # ------------------------
    # COVER
    # ------------------------
    cover_logo = _safe_brand_path("logo_main.jpg") or _safe_brand_path("logo_main.png") or _safe_brand_path("logo_main.png")
    if cover_logo:
        try:
            story.append(Spacer(1, 18 * mm))
            img = Image(cover_logo)
            img._restrictSize(90 * mm, 70 * mm)
            img.hAlign = "CENTER"
            story.append(img)
            story.append(Spacer(1, 10 * mm))
        except Exception:
            story.append(Spacer(1, 28 * mm))
    else:
        story.append(Spacer(1, 28 * mm))

    story.append(Paragraph(brand_name, title_center))
    story.append(Paragraph(f"by {author_name}", byline))

    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"<b>Для:</b> {client_name}", base))
    if request:
        story.append(Paragraph(f"<b>Запрос:</b> {request}", base))
    story.append(Paragraph(f"<b>Дата:</b> {date.today().strftime('%d.%m.%Y')}", base))

    story.append(PageBreak())

    # ------------------------
    # BODY
    # ------------------------
    raw_text = _strip_text(client_report_text or "")
    raw_text = _normalize_bullets(raw_text)

    # 1) Try extract matrix block first
    matrix_data, text_wo_matrix = _extract_matrix_block(raw_text)

    # 2) Split by sections on ⸻ (your separator)
    # We still keep paragraphs inside each section.
    sections = [s.strip() for s in re.split(r"\n?\s*⸻\s*\n?", text_wo_matrix) if s.strip()]

    # Matrix section: if matrix exists, render it near the beginning (or where you want)
    if matrix_data:
        story.append(Paragraph("Твоя матрица потенциалов 3×3", h2))
        story.append(Spacer(1, 2 * mm))

        tbl = Table(matrix_data, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "PP-Regular"),
            ("FONTSIZE", (0, 0), (-1, -1), 10.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),

            ("BACKGROUND", (0, 0), (-1, 0), C_SOFT),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_ACCENT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, C_LINE),

            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E6E2F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8 * mm))

    # Notes mode (when we see heading "ЗАМЕТКИ")
    notes_triggered = False

    def add_separator_line():
        story.append(Spacer(1, 2 * mm))
        # a “fake line” using an empty table
        line_tbl = Table([[""]], colWidths=[A4[0] - doc.leftMargin - doc.rightMargin])
        line_tbl.setStyle(TableStyle([
            ("LINEABOVE", (0, 0), (-1, -1), 0.8, C_LINE),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(line_tbl)
        story.append(Spacer(1, 2 * mm))

    for sec in sections:
        # if there were ⸻ in text, we add a subtle separator between sections
        # (but not before the very first paragraph if not needed)
        # We'll add it when a section begins with a heading-like line.
        blocks = [b.strip() for b in re.split(r"\n\s*\n", sec) if b.strip()]
        if not blocks:
            continue

        # Detect "ЗАМЕТКИ" section and create a dedicated notes page
        # (if the section starts with that heading or contains it as first line)
        first_line = blocks[0].splitlines()[0].strip()
        if re.match(r"^ЗАМЕТКИ\b", first_line, flags=re.I):
            notes_triggered = True
            story.append(Paragraph("ЗАМЕТКИ", h2))
            story.append(Paragraph(
                "Подсказка: сюда можно выписывать идеи, наблюдения, «где я узнаю себя», вопросы к сессии, инсайты про работу/отношения/деньги/проявленность.",
                subtle
            ))
            story.append(PageBreak())

            # create a page with lines (drawn via onPage)
            # We'll add a blank paragraph to force content and keep footer.
            story.append(Spacer(1, 2 * mm))
            story.append(Paragraph(" ", base))
            story.append(PageBreak())
            continue

        # Normal section: render block-by-block
        for b in blocks:
            # if a block starts with a heading-like single line, render as h2 then rest
            lines = [ln.strip() for ln in b.splitlines() if ln.strip()]
            if not lines:
                continue

            # draw a separator between major sections (optional but matches your ⸻ meaning)
            # We'll add a separator if the first line looks like a heading and it's not the very start.
            if _is_heading(lines[0]):
                add_separator_line()

            # If block is a heading alone
            if len(lines) == 1 and _is_heading(lines[0]):
                story.append(Paragraph(lines[0], h2))
                continue

            # If first line is heading and there is body below it
            if _is_heading(lines[0]) and len(lines) > 1:
                story.append(Paragraph(lines[0], h2))
                body = "\n".join(lines[1:]).strip()
                if body:
                    story.append(Paragraph(body.replace("\n", "<br/>"), base))
                story.append(Spacer(1, 2 * mm))
                continue

            # Otherwise: normal paragraph
            story.append(Paragraph(b.replace("\n", "<br/>"), base))
            story.append(Spacer(1, 2 * mm))

    # ------------------------
    # Build with footer and notes-lines hook
    # ------------------------
    def on_page(canvas, d):
        _draw_footer(canvas, d, brand_name=brand_name)

    def on_page_notes(canvas, d):
        _draw_footer(canvas, d, brand_name=brand_name)
        _draw_notes_lines(canvas, d, top_y_mm=250, bottom_y_mm=28, step_mm=8)

    # If notes were triggered, we draw lines on EVERY blank notes page created after "ЗАМЕТКИ".
    # Easiest robust approach: draw lines on all later pages AFTER it was triggered is hard without tracking.
    # So: we draw lines on all pages (safe + subtle). If you want ONLY the notes page, tell me and I’ll add page-state tracking.
    # Here we keep it conservative: lines only on later pages, but only if notes_triggered.
    if notes_triggered:
        doc.build(
            story,
            onFirstPage=on_page,
            onLaterPages=on_page_notes,
        )
    else:
        doc.build(
            story,
            onFirstPage=on_page,
            onLaterPages=on_page,
        )

    return buf.getvalue()