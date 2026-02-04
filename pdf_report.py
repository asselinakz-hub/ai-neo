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
def _strip_md(md: str) -> str:
    if not md:
        return ""
    md = md.replace("```", "")
    md = md.replace("\t", "    ")
    md = re.sub(r"</?[^>]+>", "", md)  # remove html tags
    # remove markdown bold markers just in case (**text**)
    md = re.sub(r"\*\*(.+?)\*\*", r"\1", md)
    return md.strip()

def _md_table_to_data(matrix_md: str):
    text = _strip_md(matrix_md)
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    rows = [l for l in lines if "|" in l]
    if not rows:
        return None

    parsed = []
    for r in rows:
        if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?", r):
            continue
        parts = [c.strip() for c in r.strip("|").split("|")]
        parsed.append(parts)

    return parsed if parsed else None

def _safe_brand(*filenames: str) -> str | None:
    for fn in filenames:
        p = os.path.join(BRAND_DIR, fn)
        if os.path.exists(p):
            return p
    return None

def _escape_para(s: str) -> str:
    """ReportLab Paragraph is XML-ish; escape bare ampersands etc."""
    if not s:
        return ""
    s = s.replace("&", "&amp;")
    s = s.replace("<", "&lt;").replace(">", "&gt;")
    return s


# ------------------------
# Footer (logo + brand)
# ------------------------
def _draw_footer(canvas, doc, brand_name: str = "Personal Potentials"):
    canvas.saveState()

    y = 14 * mm
    canvas.setStrokeColor(C_LINE)
    canvas.setLineWidth(0.7)
    canvas.line(doc.leftMargin, y + 8, A4[0] - doc.rightMargin, y + 8)

    # small logo in footer (subtle)
    logo_path = _safe_brand("logo_horizontal.png", "logo_light.png", "logo_mark.png")
    x = doc.leftMargin
    if logo_path:
        try:
            canvas.drawImage(
                logo_path, x, y - 2,
                width=30*mm, height=10*mm,
                mask='auto', preserveAspectRatio=True, anchor='sw'
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
# Tail blocks (professional, end of doc)
# ------------------------
def _append_end_blocks(story, h2, base, subtle):
    story.append(PageBreak())

    story.append(Paragraph("Об авторе", h2))
    story.append(Paragraph(
        _escape_para(
            "Asselya Zhanybek — практик на стыке личной реализации и системного подхода. "
            "Профессиональный бэкграунд включает многолетний опыт в HR, корпоративном консалтинге "
            "и развитии людей в организациях, где важны не формулировки, а измеримые изменения "
            "в мышлении, действиях и результате. "
            "Asselya адаптировала методику школы в онлайн-диагностику и платформенное сопровождение, "
            "чтобы человек мог увидеть природные механизмы, собрать ясные цели и выстроить путь "
            "достижения через сильные стороны — без постоянного «ломания себя»."
        ),
        base
    ))

    story.append(Spacer(1, 4*mm))
    story.append(Paragraph("Методология диагностики", h2))
    story.append(Paragraph(
        _escape_para(
            "Диагностика основана на принципах системного анализа внутренних мотиваций: "
            "это не «типология ради типологии», а карта механизмов, через которые человек воспринимает мир, "
            "включается в действие и удерживает результат. "
            "В работе используется структурированный опрос (вопросы на мотивацию, восприятие и стиль действий), "
            "интерпретация ответов через матрицу 3×3, проверка согласованности связок между рядами "
            "и выявление возможных внутренних конфликтов и зон перегруза. "
            "Диагностика — это первый этап; далее (по желанию) выстраивается персональная система "
            "«цели → стратегия → действия → поддержка» в своём стиле, чтобы результат становился устойчивым."
        ),
        base
    ))

    story.append(PageBreak())
    story.append(Paragraph("Заметки", h2))
    lines = "<br/>".join(["______________________________________________"] * 16)
    story.append(Paragraph(lines, subtle))


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

    byline = ParagraphStyle(
        "byline",
        parent=subtle,
        alignment=TA_CENTER,
        fontName="PP-Regular",
        fontSize=11,
        textColor=C_ACCENT_2,
        spaceAfter=10,
    )

    story = []

    # ------------------------
    # COVER (KeepTogether to prevent blank first page)
    # ------------------------
    cover = []

    # logo mark (oval PP) preferred
    cover_logo = _safe_brand("logo_mark.png", "logo_main.png", "logo_main.jpg", "logo_horizontal.png")
    if cover_logo:
        img = Image(cover_logo)
        # critical: restrict so it never overflows the frame
        img._restrictSize(55*mm, 55*mm)
        img.hAlign = "CENTER"
        cover.append(Spacer(1, 12*mm))
        cover.append(img)
        cover.append(Spacer(1, 8*mm))
    else:
        cover.append(Spacer(1, 22*mm))

    cover.append(Paragraph(_escape_para(brand_name), title_center))
    cover.append(Paragraph("by Asselya Zhanybek", byline))
    cover.append(Spacer(1, 6*mm))

    # No bold labels (per request)
    cover.append(Paragraph(_escape_para(f"Для: {client_name}"), base))
    if request:
        cover.append(Paragraph(_escape_para(f"Запрос: {request}"), base))
    cover.append(Paragraph(_escape_para(f"Дата: {date.today().strftime('%d.%m.%Y')}"), base))

    cover.append(Spacer(1, 10*mm))

    cover.append(Paragraph("Введение", h2))
    cover.append(Paragraph(
        _escape_para(
            "Есть моменты, когда ты вроде бы стараешься — но ощущение, что живёшь «не своим способом». "
            "Эта диагностика помогает увидеть природный механизм: как ты воспринимаешь мир, "
            "что тебя по-настоящему зажигает и через какой стиль действий ты достигаешь результата без насилия над собой."
        ),
        base
    ))

    cover.append(Spacer(1, 4*mm))
    cover.append(Paragraph(
        _escape_para(
            "После такой диагностики обычно становится легче принимать решения, появляется ясность, "
            "где утекает энергия и почему возникает «буксование», и появляется ощущение: «я понял(а) себя»."
        ),
        base
    ))

    story.append(KeepTogether(cover))
    story.append(PageBreak())

    # ------------------------
    # BODY
    # ------------------------
    text = _strip_md(client_report_text or "")

    # If your text already contains "Об авторе" / "Методология" — we will remove them from body
    # because we append a professional version at the end.
    def _remove_tail_sections(t: str) -> str:
        patterns = [
            r"\n?Об авторе\s*\n.*?(?=\n[A-ZА-ЯЁ0-9][^\n]{0,60}\n|$)",
            r"\n?О методологии.*?\n.*?(?=\n[A-ZА-ЯЁ0-9][^\n]{0,60}\n|$)",
        ]
        for pat in patterns:
            t = re.sub(pat, "\n", t, flags=re.IGNORECASE | re.DOTALL)
        return t.strip()

    body_text = _remove_tail_sections(text)

    # matrix table (if present)
    table_data = _md_table_to_data(body_text)

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
        story.append(Paragraph("Матрица не распознана как таблица — текст будет выведен ниже.", subtle))
        story.append(Spacer(1, 4*mm))

    # Render blocks: headings regular, body without bold markup
    for block in re.split(r"\n\s*\n", body_text):
        b = block.strip()
        if not b:
            continue

        # skip small matrix blocks if table already rendered
        if table_data and "|" in b and len(b.splitlines()) <= 10:
            continue

        # treat lines with dashes as separators
        if re.fullmatch(r"[-–—]{3,}", b):
            story.append(Spacer(1, 2*mm))
            continue

        # markdown headings
        if b.startswith(("###", "##", "#")):
            story.append(Paragraph(_escape_para(b.lstrip("#").strip()), h2))
            continue

        # remove accidental <b> tags if any slipped in
        b = re.sub(r"</?b>", "", b, flags=re.IGNORECASE)

        story.append(Paragraph(_escape_para(b).replace("\n", "<br/>"), base))
        story.append(Spacer(1, 2*mm))

    # ------------------------
    # END: author + methodology + notes (moved to the end)
    # ------------------------
    _append_end_blocks(story, h2, base, subtle)

    doc.build(
        story,
        onFirstPage=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
        onLaterPages=lambda c, d: _draw_footer(c, d, brand_name=brand_name),
    )

    return buf.getvalue()