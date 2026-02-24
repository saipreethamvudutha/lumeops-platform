"""
HIPAA Compliance Report — PDF Generator.

Generates a professional, downloadable PDF compliance report
using ReportLab. Includes:
  - Executive summary with compliance status
  - PII/ePHI safeguarding details
  - Encryption status
  - Access control summary
  - Audit logging statistics
  - HIPAA requirement checklist with PASS/FAIL indicators

No PII is included in the report itself.
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def generate_compliance_pdf(report_data: dict[str, Any]) -> bytes:
    """
    Generate a HIPAA compliance report as a PDF.

    Args:
        report_data: The compliance report dict (same shape as ComplianceReportResponse).

    Returns:
        PDF file contents as bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#1e293b"),
        spaceBefore=16,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "BodyText",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#334155"),
        leading=14,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#64748b"),
    )

    elements: list = []

    # ── Title Block ──────────────────────────────────────────────────────
    elements.append(Paragraph("LumeOps", title_style))
    elements.append(
        Paragraph("HIPAA Compliance Evidence Report", subtitle_style)
    )

    # Report metadata
    period = report_data.get("period", {})
    generated_at = report_data.get("generated_at", "")
    if isinstance(generated_at, datetime):
        generated_at = generated_at.strftime("%B %d, %Y at %H:%M UTC")

    meta_data = [
        ["Report ID", report_data.get("report_id", "N/A")],
        ["Generated", str(generated_at)],
        ["Period", f"{period.get('days', 30)} days"],
    ]
    meta_table = Table(meta_data, colWidths=[1.5 * inch, 5 * inch])
    meta_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#334155")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(meta_table)
    elements.append(Spacer(1, 16))

    # ── Executive Summary ────────────────────────────────────────────────
    elements.append(Paragraph("Executive Summary", heading_style))

    summary = report_data.get("executive_summary", {})
    compliance_status = summary.get("compliance_status", "UNKNOWN")
    status_color = colors.HexColor("#16a34a") if compliance_status == "COMPLIANT" else colors.HexColor("#dc2626")

    summary_data = [
        ["Compliance Status", compliance_status],
        ["Total Inferences", f"{summary.get('total_inferences', 0):,}"],
        ["PII Instances Redacted", f"{summary.get('pii_instances_redacted', 0):,}"],
    ]
    summary_table = Table(summary_data, colWidths=[2.5 * inch, 4 * inch])
    summary_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("TEXTCOLOR", (1, 0), (1, 0), status_color),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#334155")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    elements.append(summary_table)
    elements.append(Spacer(1, 12))

    # ── Personal Information Safeguarding ────────────────────────────────
    elements.append(
        Paragraph("Personal Information Safeguarding", heading_style)
    )

    pis = report_data.get("personal_information_safeguarding", {})

    enc_rest = pis.get("encryption_at_rest", {})
    enc_transit = pis.get("encryption_in_transit", {})
    pii_redact = pis.get("pii_redaction", {})

    safeguard_data = [
        ["Control", "Status", "Details"],
        [
            "Encryption at Rest",
            enc_rest.get("status", "N/A"),
            enc_rest.get("method", "N/A"),
        ],
        [
            "Encryption in Transit",
            enc_transit.get("status", "N/A"),
            enc_transit.get("protocol", "N/A"),
        ],
        [
            "PII/ePHI Redaction",
            pii_redact.get("status", "N/A"),
            f"{pii_redact.get('instances_redacted', 0):,} instances redacted",
        ],
    ]
    safeguard_table = Table(
        safeguard_data, colWidths=[2 * inch, 1.5 * inch, 3 * inch]
    )
    safeguard_table.setStyle(
        TableStyle(
            [
                # Header row
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")),
                # Status column color
                ("TEXTCOLOR", (1, 1), (1, -1), colors.HexColor("#16a34a")),
                # Grid
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    elements.append(safeguard_table)
    elements.append(Spacer(1, 12))

    # ── Access Controls ──────────────────────────────────────────────────
    elements.append(Paragraph("Access Controls", heading_style))

    ac = report_data.get("access_controls", {})
    ac_data = [
        ["Authentication", ac.get("authentication", "N/A")],
        ["Unique Keys Used", str(ac.get("unique_keys_used", 0))],
        ["Rate Limiting", ac.get("rate_limiting", "N/A")],
    ]
    ac_table = Table(ac_data, colWidths=[2.5 * inch, 4 * inch])
    ac_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    elements.append(ac_table)
    elements.append(Spacer(1, 12))

    # ── Audit Logging ────────────────────────────────────────────────────
    elements.append(Paragraph("Audit Logging", heading_style))

    al = report_data.get("audit_logging", {})
    al_data = [
        ["Total Events", f"{al.get('total_events', 0):,}"],
        ["Retention Period", al.get("retention", "7 years")],
        ["Tamper Protection", al.get("tamper_protection", "N/A")],
        ["Storage", "PostgreSQL (primary) + Elasticsearch (searchable)"],
    ]
    al_table = Table(al_data, colWidths=[2.5 * inch, 4 * inch])
    al_table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.HexColor("#334155")),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, colors.HexColor("#e2e8f0")),
            ]
        )
    )
    elements.append(al_table)
    elements.append(Spacer(1, 12))

    # ── Compliance Checklist ─────────────────────────────────────────────
    elements.append(Paragraph("HIPAA Compliance Checklist", heading_style))

    checklist = report_data.get("compliance_checklist", [])
    checklist_header = ["Requirement", "Status", "Evidence"]
    checklist_rows = [checklist_header]

    for item in checklist:
        if isinstance(item, dict):
            req = item.get("requirement", "")
            stat = item.get("status", "")
            evidence = item.get("evidence", "")
        else:
            req = getattr(item, "requirement", "")
            stat = getattr(item, "status", "")
            evidence = getattr(item, "evidence", "")
        checklist_rows.append([req, stat, evidence])

    checklist_table = Table(
        checklist_rows, colWidths=[2.2 * inch, 0.8 * inch, 3.5 * inch]
    )

    # Build dynamic style with conditional status colors
    checklist_style = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 1), (0, -1), colors.HexColor("#334155")),
        ("TEXTCOLOR", (2, 1), (2, -1), colors.HexColor("#475569")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]

    # Color status cells
    for i, row in enumerate(checklist_rows[1:], start=1):
        status_val = row[1]
        if status_val == "PASS":
            checklist_style.append(
                ("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#16a34a"))
            )
        elif status_val == "FAIL":
            checklist_style.append(
                ("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#dc2626"))
            )
        else:
            checklist_style.append(
                ("TEXTCOLOR", (1, i), (1, i), colors.HexColor("#d97706"))
            )
        # Alternate row backgrounds
        if i % 2 == 0:
            checklist_style.append(
                ("BACKGROUND", (0, i), (-1, i), colors.HexColor("#f8fafc"))
            )

    checklist_table.setStyle(TableStyle(checklist_style))
    elements.append(checklist_table)
    elements.append(Spacer(1, 20))

    # ── Footer ───────────────────────────────────────────────────────────
    footer_text = (
        "This report was auto-generated by LumeOps Healthcare AI Observability Platform. "
        "It provides evidence of HIPAA compliance controls in effect during the reporting period. "
        "This document does not constitute legal advice."
    )
    elements.append(Paragraph(footer_text, label_style))

    # Build PDF
    doc.build(elements)
    return buffer.getvalue()
