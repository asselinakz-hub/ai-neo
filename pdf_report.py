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
BRAND_DIR = os.path.join(ASSETS_DIR, "brand")

# ------------------------
# Colors (calm, premium)
# ------------------------
C_BG = colors.HexColor("#FFFFFF")
C_TEXT = colors.HexColor("#121212")
C_MUTED = colors.HexColor("#5A5A5A")
C_LINE = colors.HexColor("#D8D2E6")     # soft lavender-gray
C_ACCENT = colors.HexColor("#5B2B6C")   # deep plum
C_ACCENT_2 = colors.HexColor("#8C4A86") # muted mauve

# ------------------------
# Fonts (Cyrillic safe)
# ------------------------
_FONTS_REGISTERED = False

def _register_fonts():
    """
    Uses repo fonts:
      - assets/fonts/DejaVuSans.ttf
      - assets/fonts/DejaVuLGCSans-Bold.ttf   (your bold filename)
    Fallback: tries DejaVuSans-Bold.ttf if you add later.
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
        bold = regular  # fallback

    # quick corruption guard
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
def _strip_md(md: str) -> str:
    if not md:
        return ""
    md = md.replace("```", "")
    md = md.replace("\t", "    ")
    md = re.sub(r"</?[^>]+>", "", md)  # remove html tags
    return md.strip()

def _md_table_to_data(matrix_md: str):
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

def _safe_logo_path(filename: str) -> str | None:
    p = os.path.join(BRAND_DIR, filename)
    return p if os.path.exists(p) else None


# ------------------------
# Footer (logo + brand)
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials"):
    canvas.saveState()

    # footer line
    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    # small logo (prefer horizontal, fallback mark)
    logo_path = _safe_logo_path("logo_horizontal.png") or _safe_logo_path("logo_mark.png")
    x = doc.leftMargin
    if logo_path:
        try:
            # keep subtle size
            canvas.drawImage(logo_path, x, y - 2, width=30*mm, height=10*mm, mask='auto', preserveAspectRatio=True, anchor='sw')
            x += 34 * mm
        except Exception:
            pass

    # brand text
    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Regular", 9)
    canvas.drawString(x, y + 2, brand_name)

    # page number (right)
    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Regular", 9)
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
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"{brand_name} Report",
        author="Asselya Zhanybek",
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

    story = []

    # ------------------------
    # COVER
    # ------------------------
    # top thin accent line
    story.append(Spacer(1, 2*mm))

    cover_logo = _safe_logo_path("logo_main.jpg") or _safe_logo_path("logo_light.png")
    if cover_logo:
        try:
            img = Image(cover_logo)
            img._restrictSize(90*mm, 60*mm)
            img.hAlign = "CENTER"
            story.append(Spacer(1, 18*mm))
            story.append(img)
            story.append(Spacer(1, 10*mm))
        except Exception:
            story.append(Spacer(1, 22*mm))
    else:
        story.append(Spacer(1, 28*mm))

    story.append(Paragraph(brand_name, title_center))
    story.append(Paragraph("by Asselya Zhanybek", ParagraphStyle(
        "byline",
        parent=subtle,
        alignment=TA_CENTER,
        fontName="PP-Regular",
        fontSize=11,
        textColor=C_ACCENT_2,
        spaceAfter=14,
    )))

    story.append(Spacer(1, 6*mm))
    story.append(Paragraph(f"<b>Для:</b> {client_name}", base))
    if request:
        story.append(Paragraph(f"<b>Запрос:</b> {request}", base))

    story.append(Spacer(1, 10*mm))

    # short positioning (professional, not “AI-ish”)
    story.append(Paragraph("О чём этот отчёт", h2))
    story.append(Paragraph(
        "Это персональная карта твоих внутренних механизмов: как ты принимаешь решения, "
        "что тебя по-настоящему запускает и через что у тебя получается реализовываться без насилия над собой. "
        "Отчёт помогает вернуть ясность, опору и направление — особенно когда ты много стараешься, "
        "а движение всё равно идёт тяжело.",
        base
    ))

    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("Кто автор интерпретации", h2))
    story.append(Paragraph(
        "Аселя Жаныбек — практик и эксперт в HR и трансформации людей и команд, "
        "с опытом в корпоративной среде и международном консалтинге. "
        "Эта диагностика — адаптация методики школы потенциалов в современный онлайн-формат: "
        "быстро, понятно и применимо к жизни, карьере и проявленности.",
        base
    ))

    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Как использовать (коротко)", h2))
    story.append(Paragraph(
        "Прочитай 1 ряд — это твой «родной стиль» реализации. Затем 2 ряд — где берётся энергия и контакт с людьми. "
        "3 ряд — что лучше упростить или делегировать. После чтения выпиши 3 инсайта и 1 действие на неделю — "
        "и отчёт начнёт работать в реальности.",
        base
    ))

    story.append(PageBreak())

    # ------------------------
    # BODY
    # ------------------------
    text = _strip_md(client_report_text or "")

    # Matrix table (if present)
    table_data = _md_table_to_data(text)

    story.append(Paragraph("Твоя матрица", h2))
    story.append(Spacer(1, 2*mm))

    if table_data:
        tbl = Table(table_data, hAlign="LEFT")
        tbl.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), "PP-Regular"),
            ("FONTSIZE", (0, 0), (-1, -1), 10.5),
            ("TEXTCOLOR", (0, 0), (-1, -1), C_TEXT),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F6F4FA")),
            ("TEXTCOLOR", (0, 0), (-1, 0), C_ACCENT),
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, C_LINE),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E6E2F0")),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(tbl)
        story.append(Spacer(1, 8*mm))
    else:
        story.append(Paragraph(
            "Матрица не распознана как таблица. Это не ошибка — отчёт всё равно будет читаться корректно.",
            subtle
        ))
        story.append(Spacer(1, 6*mm))

    # Clean pass: split into paragraphs and keep headings
    # We avoid “boxes”; only typography + spacing.
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue

        # skip small matrix blocks if we already rendered table
        if table_data and "|" in b and len(b.splitlines()) <= 8:
            continue

        # markdown headings
        if b.startswith("###"):
            story.append(Paragraph(b.lstrip("#").strip(), h2))
            continue
        if b.startswith("##"):
            story.append(Paragraph(b.lstrip("#").strip(), h2))
            continue
        if b.startswith("#"):
            story.append(Paragraph(b.lstrip("#").strip(), h2))
            continue

        story.append(Paragraph(b.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2*mm))

    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
    )

    return buf.getvalue()