import os
from datetime import datetime
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Table, TableStyle, Paragraph, SimpleDocTemplate, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet

REPORTS_DIR = os.getenv("REPORTS_DIR", "/tmp/reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

def generate_bill_pdf(dispense, patient=None, medicine=None):
    """
    Generates a detailed pharmacy invoice PDF with totals and tax breakdown.
    """
    bill_id = dispense.id
    pdf_path = os.path.join(REPORTS_DIR, f"invoice_{bill_id}.pdf")
    styles = getSampleStyleSheet()
    story = []

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    # ---------------- Header ----------------
    story.append(Paragraph("<b>Smart QR Health Pharmacy</b>", styles["Title"]))
    story.append(Paragraph("Main Road, Ongole · Phone: +91-9876543210", styles["Normal"]))
    story.append(Paragraph("GSTIN: 36ABCDE1234FZ9", styles["Normal"]))
    story.append(Spacer(1, 8))

    # ---------------- Invoice Info ----------------
    info = [
        ["Invoice No", f"INV-{bill_id:05d}"],
        ["Date", datetime.now().strftime("%d-%b-%Y %H:%M")],
        ["Payment Mode", dispense.payment_mode or "Cash"],
        ["Pharmacist", dispense.pharmacist or "—"],
    ]
    t = Table(info, colWidths=[100, 300])
    t.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.25, colors.black),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(t)
    story.append(Spacer(1, 10))

    # ---------------- Patient Info ----------------
    if patient:
        pinfo = [
            ["Patient Name", patient.name],
            ["Patient UID", patient.patient_uid],
            ["Age / Gender", f"{getattr(patient, 'age', '—')} / {getattr(patient, 'gender', '—')}"],
        ]
        pt = Table(pinfo, colWidths=[100, 300])
        pt.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.25, colors.black),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ]))
        story.append(pt)
        story.append(Spacer(1, 10))

    # ---------------- Medicines ----------------
    data = [["#", "Item", "Batch", "EXP", "Qty", "MRP (₹)", "Tax %", "Total (₹)"]]
    try:
        import json
        items = json.loads(dispense.items_json or "[]")
    except Exception:
        items = []

    for i, it in enumerate(items, 1):
        data.append([
            i,
            it.get("label", it.get("name", "—")),
            it.get("batch_no", "—"),
            it.get("expiry", "—"),
            it.get("qty", "—"),
            f"{float(it.get('unit_price', 0)):.2f}",
            f"{float(it.get('tax_pct', 0)):.1f}",
            f"{float(it.get('unit_price', 0)) * int(it.get('qty', 0)):.2f}",
        ])

    meds_table = Table(data, repeatRows=1)
    meds_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(meds_table)
    story.append(Spacer(1, 10))

    # ---------------- Totals ----------------
    total = float(dispense.total_amount or 0)
    gst = total * 0.05  # 5% for example
    grand_total = total + gst

    totals = [
        ["Subtotal", f"₹{total:.2f}"],
        ["GST (5%)", f"₹{gst:.2f}"],
        ["Grand Total", f"₹{grand_total:.2f}"],
    ]
    totals_table = Table(totals, colWidths=[120, 100])
    totals_table.setStyle(TableStyle([
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
    ]))
    story.append(totals_table)
    story.append(Spacer(1, 15))

    story.append(Paragraph("Thank you for visiting!", styles["Normal"]))
    story.append(Paragraph("<i>Get well soon 🙏</i>", styles["Normal"]))
    story.append(Spacer(1, 10))
    story.append(Paragraph("Authorized Signatory ___________________", styles["Normal"]))

    doc.build(story)
    print(f"🧾 Invoice PDF generated: {pdf_path}")
    return pdf_path