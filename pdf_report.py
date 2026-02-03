# pdf_report.py
from io import BytesIO
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak
from reportlab.lib import colors


def _escape(s: str) -> str:
    # reportlab Paragraph умеет немного html-like, поэтому экранируем
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _md_to_flowables(md_text: str, styles):
    """
    Очень простой конвертер markdown-подобного текста в Paragraph/Spacer.
    Поддержка:
    - строки начинающиеся с "###", "##", "#" как заголовки
    - пустые строки как отступ
    - остальное как обычный абзац
    """
    flow = []
    lines = (md_text or "").splitlines()

    for raw in lines:
        line = raw.strip()
        if not line:
            flow.append(Spacer(1, 4 * mm))
            continue

        if line.startswith("### "):
            flow.append(Paragraph(_escape(line[4:]), styles["H3"]))
            flow.append(Spacer(1, 2.5 * mm))
        elif line.startswith("## "):
            flow.append(Paragraph(_escape(line[3:]), styles["H2"]))
            flow.append(Spacer(1, 3 * mm))
        elif line.startswith("# "):
            flow.append(Paragraph(_escape(line[2:]), styles["H1"]))
            flow.append(Spacer(1, 3.5 * mm))
        else:
            # буллеты - оставим как текст с маркером
            if line.startswith(("-", "•")):
                txt = "• " + _escape(line.lstrip("-• ").strip())
                flow.append(Paragraph(txt, styles["Body"]))
            else:
                flow.append(Paragraph(_escape(line), styles["Body"]))
    return flow


def build_client_report_pdf_bytes(
    client_report_text: str,
    *,
    client_name: str = "Клиент",
    request: str = "",
    brand_title: str = "NEO — Диагностика потенциалов",
) -> bytes:
    """
    Возвращает PDF как bytes.
    """
    buf = BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title="Отчёт СПЧ",
        author="NEO",
    )

    base = getSampleStyleSheet()

    styles = {
        "CoverTitle": ParagraphStyle(
            "CoverTitle",
            parent=base["Title"],
            fontSize=22,
            leading=26,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111111"),
            spaceAfter=10 * mm,
        ),
        "CoverSub": ParagraphStyle(
            "CoverSub",
            parent=base["Normal"],
            fontSize=11,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#333333"),
        ),
        "H1": ParagraphStyle("H1", parent=base["Heading1"], fontSize=16, leading=20, spaceBefore=6*mm, spaceAfter=3*mm),
        "H2": ParagraphStyle("H2", parent=base["Heading2"], fontSize=13, leading=17, spaceBefore=5*mm, spaceAfter=2*mm),
        "H3": ParagraphStyle("H3", parent=base["Heading3"], fontSize=11.5, leading=15, spaceBefore=4*mm, spaceAfter=1.5*mm),
        "Body": ParagraphStyle("Body", parent=base["BodyText"], fontSize=10.5, leading=14),
        "Small": ParagraphStyle("Small", parent=base["BodyText"], fontSize=9.5, leading=12, textColor=colors.HexColor("#444444")),
    }

    today = datetime.now().strftime("%Y-%m-%d")

    story = []

    # ---- Cover ----
    story.append(Paragraph(_escape(brand_title), styles["CoverTitle"]))
    story.append(Paragraph(_escape("Клиентский отчёт по системе потенциалов человека (СПЧ)"), styles["CoverSub"]))
    story.append(Spacer(1, 6 * mm))

    story.append(Paragraph(_escape(f"<b>Имя:</b> {client_name}"), styles["CoverSub"]))
    if request:
        story.append(Spacer(1, 2 * mm))
        story.append(Paragraph(_escape(f"<b>Запрос:</b> {request}"), styles["CoverSub"]))
    story.append(Spacer(1, 3 * mm))
    story.append(Paragraph(_escape(f"<b>Дата:</b> {today}"), styles["CoverSub"]))

    story.append(Spacer(1, 14 * mm))
    story.append(Paragraph(_escape(
        "Этот отчёт помогает увидеть, как устроена твоя внутренняя система: "
        "где сила, где ресурс, а где лучше не тащить всё на себе."
    ), styles["Small"]))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(_escape(
        "Как работать с отчётом: прочитай целиком, затем вернись к 1 ряду "
        "и отметь, что отзывается. 2 ряд — твой «топливный бак», 3 ряд — зоны, "
        "которые лучше закрывать через людей/системы."
    ), styles["Small"]))

    story.append(PageBreak())

    # ---- Main report ----
    story.extend(_md_to_flowables(client_report_text, styles))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
