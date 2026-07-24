"""
Report builder — turns SQL aggregates into a polished PDF artifact (reportlab).

The PDF is written to reports/<id>.pdf and referenced by a download link.
We store the artifact and link to it; we never pass the bytes around in JSON.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

import data

REPORTS_DIR = Path(__file__).resolve().parent / "reports"
BRAND = colors.HexColor("#0e9f6e")
DARK = colors.HexColor("#111827")
LIGHT = colors.HexColor("#f3f4f6")


def _styles():
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle("H1", parent=styles["Title"], textColor=DARK, fontSize=24))
    styles.add(ParagraphStyle("H2", parent=styles["Heading2"], textColor=BRAND, spaceBefore=16))
    styles.add(ParagraphStyle("Muted", parent=styles["Normal"], textColor=colors.grey, fontSize=9))
    return styles


def _kpi_table(summary: dict) -> Table:
    cells = [
        ["Pages audited", "Avg SEO score", "Total issues", "Best", "Worst"],
        [
            str(summary["total"]),
            str(summary["avg_score"]),
            str(summary["total_issues"]),
            str(summary["best"]),
            str(summary["worst"]),
        ],
    ]
    t = Table(cells, colWidths=[3.4 * cm] * 5)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 16),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 1), (-1, 1), 10),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
                ("BACKGROUND", (0, 1), (-1, 1), LIGHT),
            ]
        )
    )
    return t


def _grid_table(header: list[str], rows: list[list[str]], widths: list[float]) -> Table:
    data_rows = [header] + rows
    t = Table(data_rows, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), DARK),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#d1d5db")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    t.setStyle(TableStyle(style))
    return t


def build_report(report_id: str, title: str) -> Path:
    REPORTS_DIR.mkdir(exist_ok=True)
    out_path = REPORTS_DIR / f"{report_id}.pdf"

    summary = data.overall_summary()
    by_cat = data.summary_by_category()
    worst = data.worst_pages(limit=10)

    styles = _styles()
    story = []

    story.append(Paragraph(title, styles["H1"]))
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(f"Generated {generated} · report {report_id}", styles["Muted"]))
    story.append(Spacer(1, 0.6 * cm))

    story.append(Paragraph("At a glance", styles["H2"]))
    story.append(_kpi_table(summary))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("By category (SQL GROUP BY)", styles["H2"]))
    cat_rows = [
        [c["category"], str(c["pages"]), str(c["avg_score"]), str(c["issues"])]
        for c in by_cat
    ]
    story.append(
        _grid_table(
            ["Category", "Pages", "Avg score", "Issues"],
            cat_rows,
            [5 * cm, 3 * cm, 4 * cm, 4 * cm],
        )
    )
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph("Pages needing attention (lowest scores)", styles["H2"]))
    worst_rows = [
        [w["url"], w["category"], str(w["seo_score"]), str(w["issues"])] for w in worst
    ]
    story.append(
        _grid_table(
            ["URL", "Category", "Score", "Issues"],
            worst_rows,
            [8.5 * cm, 3 * cm, 2.2 * cm, 2.3 * cm],
        )
    )
    story.append(Spacer(1, 0.8 * cm))
    story.append(
        Paragraph(
            "This report was produced as a background job: the API accepted the "
            "request instantly, a worker ran the SQL aggregation and rendered this "
            "PDF, and the artifact is served via a download link.",
            styles["Muted"],
        )
    )

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        title=title,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
    )
    doc.build(story)
    return out_path
