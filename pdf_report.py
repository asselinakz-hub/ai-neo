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

# Extra fallback dir (works in notebooks / sandboxes)
FALLBACK_DIRS = [
    BRAND_DIR,
    "/mnt/data",  # <- your uploaded logos are here
]

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

def _safe_asset_path(filename: str) -> str | None:
    for d in FALLBACK_DIRS:
        p = os.path.join(d, filename)
        if os.path.exists(p):
            return p
    return None

def _hr(story, height_mm: float = 6):
    # soft divider imitation (spacing + thin line via table)
    t = Table([[""]], colWidths=[A4[0] - 36*mm], rowHeights=[0.6])
    t.setStyle(TableStyle([
        ("LINEABOVE", (0,0), (-1,-1), 0.6, C_LINE),
        ("LINEBELOW", (0,0), (-1,-1), 0.0, C_LINE),
    ]))
    story.append(Spacer(1, 2*mm))
    story.append(t)
    story.append(Spacer(1, height_mm*mm))

# ------------------------
# Footer (logo + brand)
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials"):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    # prefer horizontal logo in footer; fallback mark
    logo_path = _safe_asset_path("logo_horizontal.png") or _safe_asset_path("logo_mark.png")
    x = doc.leftMargin
    if logo_path:
        try:
            canvas.drawImage(
                logo_path,
                x, y - 2,
                width=32*mm, height=10*mm,
                mask='auto',
                preserveAspectRatio=True,
                anchor='sw'
            )
            x += 36 * mm
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
    report_date: str | None = None,
) -> bytes:
    _register_fonts()

    if report_date is None:
        report_date = date.today().strftime("%d.%m.%Y")

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
        spaceAfter=12,
    )

    bullet = ParagraphStyle(
        "bullet",
        parent=base,
        leftIndent=10,
        bulletIndent=0,
        spaceBefore=2,
        spaceAfter=2,
    )

    story = []

    # ------------------------
    # COVER (FIXED)
    # ------------------------
    # Prefer big “main” image; fallback to mark (oval)
    cover_logo = (
        _safe_asset_path("logo_main.jpg")
        or _safe_asset_path("logo_main.png")
        or _safe_asset_path("logo_mark.png")
    )

    cover_block = []

    cover_block.append(Spacer(1, 10*mm))

    if cover_logo:
        try:
            img = Image(cover_logo)
            img.hAlign = "CENTER"
            img._restrictSize(120*mm, 70*mm)  # safe size to avoid pushing off-page
            cover_block.append(img)
            cover_block.append(Spacer(1, 10*mm))
        except Exception:
            cover_block.append(Spacer(1, 8*mm))

    cover_block.append(Paragraph(brand_name, title_center))
    cover_block.append(Paragraph("by Asselya Zhanybek", byline))

    cover_block.append(Spacer(1, 4*mm))
    cover_block.append(Paragraph(f"<b>Для:</b> {client_name}", base))
    if request:
        cover_block.append(Paragraph(f"<b>Запрос:</b> {request}", base))
    cover_block.append(Paragraph(f"<b>Дата:</b> {report_date}", base))

    _hr(cover_block, height_mm=5)

    # Intro from your NEW text (short, premium, human)
    cover_block.append(Paragraph(
        "Есть моменты, когда ты вроде бы стараешься — но ощущение, что живёшь “не своим способом”. "
        "Эта диагностика помогает увидеть твой природный механизм: как ты воспринимаешь мир, "
        "что тебя по-настоящему зажигает и через какой стиль действий ты достигаешь результата без насилия над собой.",
        base
    ))

    cover_block.append(Spacer(1, 3*mm))
    # bullets
    cover_block.append(Paragraph("После такой диагностики обычно происходит одно из трёх:", base))
    cover_block.append(Paragraph("становится легче принимать решения (появляется внутреннее “да/нет” без тревоги);", bullet, bulletText="•"))
    cover_block.append(Paragraph("появляется ясность, где именно ты теряешь энергию и почему буксуешь;", bullet, bulletText="•"))
    cover_block.append(Paragraph("появляется ощущение “я понял(а) себя” — и из этого уже проще строить цели, работу, отношения и стиль жизни.", bullet, bulletText="•"))

    _hr(cover_block, height_mm=4)

    # "Asselya Zhanybek" block — WITHOUT header "Обо мне"
    cover_block.append(Paragraph(
        "<b>Asselya Zhanybek</b> — практик на стыке личной реализации и системного подхода. "
        "Мой профессиональный бэкграунд — многолетний опыт в HR, корпоративном консалтинге и развитии людей в организациях, "
        "где важны не красивые слова, а реальные изменения в мышлении, действиях и результате.",
        base
    ))

    cover_block.append(Spacer(1, 3*mm))
    cover_block.append(Paragraph(
        "Я адаптировала методику школы в онлайн-диагностику и платформенное сопровождение, чтобы человек мог: "
        "1) увидеть свои природные механизмы, 2) собрать понятные цели, 3) выстроить путь достижения через свои сильные стороны — "
        "без постоянного “ломания себя”.",
        base
    ))

    _hr(cover_block, height_mm=4)

    # Methodology block — must be present
    cover_block.append(Paragraph("<b>О методологии диагностики</b>", h2))
    cover_block.append(Paragraph(
        "Диагностика основана на принципах системного анализа внутренних мотиваций — это не “типология ради типологии”, "
        "а карта механизмов. Мы используем: структурированный опрос (вопросы на мотивацию, восприятие и стиль действий), "
        "интерпретацию ответов через матрицу 3×3, проверку согласованности связок между рядами и выявление возможных "
        "внутренних конфликтов и зон перегруза. Диагностика — это первый этап; дальше (по желанию) выстраивается система: "
        "цели → стратегия → действия → поддержка (в своём стиле), чтобы результат становился устойчивым.",
        base
    ))

    story.append(KeepTogether(cover_block))
    story.append(PageBreak())

    # ------------------------
    # BODY
    # ------------------------
    text = _strip_md(client_report_text or "")

    # Replace divider symbol with blank lines to split blocks cleanly
    text = text.replace("⸻", "\n\n---\n\n")

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
        story.append(Spacer(1, 6*mm))
    else:
        story.append(Paragraph(
            "Матрица не распознана как таблица. Это не ошибка — отчёт всё равно будет читаться корректно.",
            subtle
        ))
        story.append(Spacer(1, 6*mm))

    # Render remaining content
    for block in re.split(r"\n\s*\n", text):
        b = block.strip()
        if not b:
            continue

        # skip small matrix blocks if we already rendered table
        if table_data and "|" in b and len(b.splitlines()) <= 10:
            continue

        # divider
        if b.strip() == "---":
            _hr(story, height_mm=5)
            continue

        # markdown headings
        if b.startswith("###") or b.startswith("##") or b.startswith("#"):
            story.append(Paragraph(b.lstrip("#").strip(), h2))
            continue

        # bullet lines starting with "•"
        lines = b.splitlines()
        if all(l.strip().startswith("•") for l in lines if l.strip()):
            for l in lines:
                l = l.strip()
                if not l:
                    continue
                story.append(Paragraph(l.lstrip("•").strip(), bullet, bulletText="•"))
            story.append(Spacer(1, 2*mm))
            continue

        story.append(Paragraph(b.replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2*mm))

    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
    )

    return buf.getvalue()