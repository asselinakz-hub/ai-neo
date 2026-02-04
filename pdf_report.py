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
# Paths (optional)
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
      - assets/fonts/DejaVuLGCSans-Bold.ttf (or DejaVuSans-Bold.ttf)
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
_BOLD_TAG_RE = re.compile(r"</?b>", flags=re.IGNORECASE)

def _strip_md(md: str) -> str:
    """
    - removes code fences
    - removes HTML tags
    - normalizes tabs
    """
    if not md:
        return ""
    md = md.replace("```", "")
    md = md.replace("\t", "    ")
    md = re.sub(r"</?[^>]+>", "", md)  # remove html tags
    return md.strip()

def _sanitize_inline_bold(text: str) -> str:
    """
    Ensures bold is not used in body text.
    Headings stay bold via styles, not tags.
    """
    if not text:
        return ""
    return _BOLD_TAG_RE.sub("", text)

def _md_table_to_data(matrix_md: str):
    """
    Parses markdown-like pipe tables.
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

def _first_existing_path(paths: list[str | None]) -> str | None:
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None

def _safe_brand_logo(
    filename: str,
    absolute_override: str | None = None
) -> str | None:
    """
    If absolute_override is provided and exists -> use it.
    Else fallback to assets/brand/filename.
    """
    if absolute_override and os.path.exists(absolute_override):
        return absolute_override
    p = os.path.join(BRAND_DIR, filename)
    return p if os.path.exists(p) else None


# ------------------------
# Footer (logo + brand)
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials", footer_logo_path: str | None = None):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    x = doc.leftMargin

    if footer_logo_path and os.path.exists(footer_logo_path):
        try:
            canvas.drawImage(
                footer_logo_path,
                x, y - 2,
                width=30*mm, height=10*mm,
                mask='auto',
                preserveAspectRatio=True,
                anchor='sw'
            )
            x += 34 * mm
        except Exception:
            pass

    canvas.setFillColor(C_MUTED)
    canvas.setFont("PP-Regular", 9)
    canvas.drawString(x, y + 2, brand_name)

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
    # NEW: absolute logo paths (optional). If None -> uses assets/brand fallback.
    cover_logo_path: str | None = None,   # e.g. "/mnt/data/logo_main.png" or "/mnt/data/logo_main.jpg"
    footer_logo_path: str | None = None,  # e.g. "/mnt/data/logo_horizontal.png" or "/mnt/data/logo_mark.png"
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
    # COVER (KeepTogether to avoid “blank first page” issues)
    # ------------------------
    # cover logo selection (absolute override -> fallback to assets)
    cover_logo = _first_existing_path([
        cover_logo_path,
        _safe_brand_logo("logo_main.jpg"),
        _safe_brand_logo("logo_main.png"),
        _safe_brand_logo("logo_mark.png"),
    ])

    cover_parts = []
    cover_parts.append(Spacer(1, 14*mm))

    if cover_logo:
        try:
            img = Image(cover_logo)
            img._restrictSize(95*mm, 70*mm)
            img.hAlign = "CENTER"
            cover_parts.append(img)
            cover_parts.append(Spacer(1, 10*mm))
        except Exception:
            cover_parts.append(Spacer(1, 10*mm))

    cover_parts.append(Paragraph(brand_name, title_center))
    cover_parts.append(Paragraph("by Asselya Zhanybek", byline))

    cover_parts.append(Spacer(1, 6*mm))

    # IMPORTANT: no <b> tags (user asked remove bold in body text)
    cover_parts.append(Paragraph(f"Для: {client_name}", base))
    if request:
        cover_parts.append(Paragraph(f"Запрос: {request}", base))
    cover_parts.append(Paragraph(f"Дата: {date.today().strftime('%d.%m.%Y')}", base))

    cover_parts.append(Spacer(1, 10*mm))

    story.append(KeepTogether(cover_parts))
    story.append(PageBreak())

    # ------------------------
    # BODY
    # ------------------------
    raw_text = _strip_md(client_report_text or "")
    raw_text = _sanitize_inline_bold(raw_text)

    # Split out "end blocks" (methodology & about) if user includes them in text.
    # We will still append our own professional blocks at the end (below).
    # If your generator already includes those headings, they will just appear earlier;
    # so лучше НЕ включать их в client_report_text, а держать отдельными параметрами.
    text = raw_text

    # Matrix table (if present)
    table_data = _md_table_to_data(text)

    story.append(Paragraph("Твоя матрица потенциалов 3×3", h2))
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

    # Render body blocks, treat separators
    blocks = re.split(r"\n\s*\n", text)
    for block in blocks:
        b = block.strip()
        if not b:
            continue

        # Skip matrix blocks if already rendered
        if table_data and "|" in b and len(b.splitlines()) <= 10:
            continue

        # Visual separators from your text (⸻)
        if b.strip("—").strip() == "⸻" or "⸻" == b.strip():
            story.append(Spacer(1, 4*mm))
            continue

        # Headings (markdown-style)
        if b.startswith("###") or b.startswith("##") or b.startswith("#"):
            story.append(Paragraph(b.lstrip("#").strip(), h2))
            continue

        story.append(Paragraph(b.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2*mm))

    # ------------------------
    # END: About (3rd person) + Methodology (moved to end)
    # ------------------------
    story.append(PageBreak())

    story.append(Paragraph("Об авторе", h2))
    story.append(Paragraph(
        "Asselya Zhanybek — практик на стыке личной реализации и системного подхода. "
        "Её профессиональный бэкграунд включает многолетний опыт в HR, корпоративном консалтинге "
        "и развитии людей в организациях, где важны не формулировки, а измеримые изменения в мышлении, "
        "действиях и результате. "
        "Asselya адаптировала методику школы в онлайн-диагностику и платформенное сопровождение, "
        "чтобы человек мог увидеть природные механизмы, собрать ясные цели и выстроить путь достижения "
        "через сильные стороны — без постоянного «ломания себя».",
        base
    ))

    story.append(Spacer(1, 6*mm))
    story.append(Paragraph("О методологии диагностики", h2))
    story.append(Paragraph(
        "Диагностика основана на принципах системного анализа внутренних мотиваций: "
        "это не «типология ради типологии», а карта механизмов, через которые человек воспринимает мир, "
        "включается в действие и удерживает результат. "
        "В работе используется структурированный опрос (вопросы на мотивацию, восприятие и стиль действий), "
        "интерпретация ответов через матрицу 3×3, проверка согласованности связок между рядами "
        "и выявление возможных внутренних конфликтов и зон перегруза. "
        "Диагностика — это первый этап; далее (по желанию) выстраивается персональная система "
        "«цели → стратегия → действия → поддержка» в своём стиле, чтобы результат становился устойчивым.",
        base
    ))

    story.append(Spacer(1, 8*mm))
    story.append(Paragraph("Заметки", h2))
    # “lined page” imitation: a few soft lines
    for _ in range(14):
        story.append(Paragraph("______________________________________________", ParagraphStyle(
            "line",
            parent=subtle,
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#D0CBDD"),
            spaceAfter=2
        )))

    # footer logo selection
    footer_logo = _first_existing_path([
        footer_logo_path,
        _safe_brand_logo("logo_horizontal.png"),
        _safe_brand_logo("logo_main.png"),
        _safe_brand_logo("logo_mark.png"),
    ])

    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name, footer_logo_path=footer_logo),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name, footer_logo_path=footer_logo),
    )

    return buf.getvalue()