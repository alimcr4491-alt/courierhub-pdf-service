import io
import os
import re
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from PyPDF2 import PdfReader, PdfWriter

app = FastAPI(title="CourierHub PDF Service")

TEMPLATE_PATH = "template.pdf"

coordinates = {
    "policy_number": (286, 10.05 * 72),
    "vehicle_reg": (286, 9.813 * 72),
    "vehicle_model": (286, 9.62 * 72),
    "policyholder_name": (286, 9.38 * 72),
    "start_date": (286, 9.15 * 72),
    "expiry_date": (286, 8.75 * 72),
    "drivers": (286, 8.46875 * 72),
}

class CertificateRequest(BaseModel):
    coverageReference: str
    vehicleRegistration: str
    vehicleModel: str
    policyholderName: str
    startDate: str
    expiryDate: str

def remove_title(full_name: str) -> str:
    titles = {"mr", "mrs", "miss", "ms", "dr", "prof", "sir", "lord", "lady"}
    parts = full_name.strip().split()
    if parts and parts[0].lower().replace(".", "") in titles:
        return " ".join(parts[1:]).upper()
    return full_name.upper()

def format_date_for_certificate(value: str, start: bool) -> str:
    """
    Accepts YYYY-MM-DD or ISO date string.
    Returns: 00:00 on 30 May 2026 / 23:59 on 29 May 2027
    """
    try:
        clean = value.split("T")[0]
        dt = datetime.strptime(clean, "%Y-%m-%d")
        prefix = "00:00 on" if start else "23:59 on"
        return f"{prefix} {dt.strftime('%d %B %Y')}"
    except Exception:
        return str(value)

@app.get("/")
def health():
    return {"status": "ok", "service": "CourierHub PDF Service"}

@app.post("/generate-pdf")
def generate_pdf(payload: CertificateRequest):
    if not os.path.exists(TEMPLATE_PATH):
        raise HTTPException(status_code=500, detail="PDF template not found")

    policy_number = payload.coverageReference
    vehicle_reg = payload.vehicleRegistration.strip().upper()
    vehicle_model = payload.vehicleModel.strip()
    full_name = payload.policyholderName.strip()

    data = {
        "policy_number": policy_number,
        "vehicle_reg": vehicle_reg,
        "vehicle_model": vehicle_model,
        "policyholder_name": full_name.upper(),
        "start_date": format_date_for_certificate(payload.startDate, True),
        "expiry_date": format_date_for_certificate(payload.expiryDate, False),
        "drivers": remove_title(full_name),
    }

    packet = io.BytesIO()
    c = canvas.Canvas(packet, pagesize=A4)
    c.setFont("Helvetica", 10.3)
    c.setFillColorRGB(0, 0, 0)

    for field, text in data.items():
        x, y = coordinates[field]
        safe_text = str(text).replace("\n", " ").strip()
        c.drawString(x, y, safe_text)

    c.save()
    packet.seek(0)

    with open(TEMPLATE_PATH, "rb") as template_file:
        template = PdfReader(template_file)
        overlay = PdfReader(packet)
        output = PdfWriter()

        page = template.pages[0]
        page.merge_page(overlay.pages[0])
        output.add_page(page)

        final_pdf = io.BytesIO()
        output.write(final_pdf)
        final_pdf.seek(0)

    filename = f"Coverage-Summary-{re.sub(r'[^A-Z0-9]', '', vehicle_reg)}.pdf"

    return Response(
        content=final_pdf.read(),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )