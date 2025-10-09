from fastapi import APIRouter, Request, Form, Depends, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND
from sqlalchemy.orm import Session
from datetime import datetime, date
from collections import defaultdict
import os, random, time, shortuuid, re

from ..core.db import get_db
from ..models.patient import Patient
from ..core.qr_utils import generate_qr_image, append_to_csv

router = APIRouter(prefix="/reception", tags=["Reception"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update({"datetime": datetime})

RECEPTION_USERNAME = "reception"
RECEPTION_PASSWORD = "reception123"

otp_store = {}

# -------------------------------
# 🔐 Login
# -------------------------------
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("reception/login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == RECEPTION_USERNAME and password == RECEPTION_PASSWORD:
        response = RedirectResponse(url="/reception/dashboard", status_code=HTTP_302_FOUND)
        response.set_cookie(key="reception_auth", value="true", httponly=True)
        return response
    return templates.TemplateResponse(
        "reception/login.html", {"request": request, "error": "Invalid username or password"}
    )


# -------------------------------
# 🏠 Dashboard — Grouped by Date
# -------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    if not request.cookies.get("reception_auth"):
        return RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)

    patients = db.query(Patient).order_by(Patient.id.desc()).all()
    today = date.today()
    grouped_patients = defaultdict(list)
    recent_patients = 0

    for p in patients:
        created_time = getattr(p, "created_at", None) or getattr(p, "timestamp", None)
        if created_time:
            try:
                if isinstance(created_time, str):
                    created_time = datetime.fromisoformat(created_time)
                reg_date = created_time.date()
            except Exception:
                reg_date = today
        else:
            reg_date = today

        grouped_patients[reg_date].append(p)
        if reg_date == today:
            recent_patients += 1

    grouped_patients = dict(sorted(grouped_patients.items(), reverse=True))
    total_patients = len(patients)

    return templates.TemplateResponse(
        "reception/dashboard.html",
        {
            "request": request,
            "grouped_patients": grouped_patients,
            "total_patients": total_patients,
            "recent_patients": recent_patients,
        },
    )


# -------------------------------
# 📲 OTP Send + Verify
# -------------------------------
@router.post("/send-otp")
def send_otp(phone: str = Form(...)):
    otp = random.randint(100000, 999999)
    expiry = time.time() + 300
    otp_store[phone] = (otp, expiry)
    print(f"[DEBUG] OTP for {phone}: {otp}")
    return JSONResponse({"message": f"OTP sent successfully to {phone}"})


@router.post("/verify-otp")
def verify_otp(phone: str = Form(...), otp: str = Form(...)):
    if phone not in otp_store:
        return JSONResponse({"message": "No OTP found. Please request again."}, status_code=400)
    saved_otp, expiry = otp_store[phone]
    if time.time() > expiry:
        del otp_store[phone]
        return JSONResponse({"message": "OTP expired. Please resend."}, status_code=400)
    if str(saved_otp) != str(otp.strip()):
        return JSONResponse({"message": "Invalid OTP. Please try again."}, status_code=400)
    del otp_store[phone]
    return JSONResponse({"message": "OTP verified successfully"})


# -------------------------------
# 🧾 Register New Patient
# -------------------------------
@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    if not request.cookies.get("reception_auth"):
        return RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)
    return templates.TemplateResponse("reception/register.html", {"request": request})


@router.post("/register", response_class=HTMLResponse)
def register_patient(
    request: Request,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    gender: str = Form(...),
    dob: str = Form(None),
    weight: str = Form(None),
    height: str = Form(None),
    db: Session = Depends(get_db),
):
    if not request.cookies.get("reception_auth"):
        return RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)

    if not re.fullmatch(r"\d{10}", phone.strip()):
        return templates.TemplateResponse(
            "reception/register.html", {"request": request, "error": "Phone number must be 10 digits"}
        )

    if db.query(Patient).filter(Patient.phone == phone).first():
        return templates.TemplateResponse(
            "reception/register.html", {"request": request, "error": "Phone already registered"}
        )

    uid = shortuuid.uuid()[:12]
    qr_filename = f"{uid}.png"
    qr_dir = "app/static/qr"
    os.makedirs(qr_dir, exist_ok=True)
    qr_path = os.path.join(qr_dir, qr_filename)
    generate_qr_image(uid, qr_path)

    patient = Patient(
        patient_uid=uid,
        name=name,
        phone=phone,
        email=email,
        gender=gender,
        dob=datetime.strptime(dob, "%Y-%m-%d").date() if dob else None,
        weight=weight,
        height=height,
        qr_filename=qr_filename,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    append_to_csv({
        "patient_uid": uid,
        "name": name,
        "phone": phone,
        "email": email,
        "gender": gender,
        "dob": dob or "",
        "weight": weight or "",
        "height": height or "",
        "qr_url": f"/static/qr/{qr_filename}",
        "timestamp": datetime.utcnow().isoformat(),
    })

    # Redirect to QR Preview after registration
    return RedirectResponse(url=f"/reception/qr-preview/{uid}", status_code=HTTP_302_FOUND)


# -------------------------------
# 🪪 QR Preview / Print Page
# -------------------------------
@router.get("/qr-preview/{patient_uid}", response_class=HTMLResponse)
def qr_preview(request: Request, patient_uid: str, db: Session = Depends(get_db)):
    """Show the printable QR card preview for a newly-registered patient."""
    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        return HTMLResponse("Patient not found", status_code=404)

    return templates.TemplateResponse(
        "reception/qr_preview.html",
        {
            "request": request,
            "name": patient.name,
            "phone": patient.phone,
            "qr_filename": patient.qr_filename,
            "hospital_name": "Smart QR Health Hospital",
        },
    )


# -------------------------------
# ✏️ Edit Patient
# -------------------------------
@router.get("/edit/{id}", response_class=HTMLResponse)
def edit_patient_page(request: Request, id: int, db: Session = Depends(get_db)):
    if not request.cookies.get("reception_auth"):
        return RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)
    patient = db.query(Patient).filter(Patient.id == id).first()
    if not patient:
        return HTMLResponse("Patient not found", status_code=404)
    return templates.TemplateResponse("reception/edit.html", {"request": request, "patient": patient})


@router.post("/edit/{id}", response_class=HTMLResponse)
def edit_patient_submit(
    request: Request,
    id: int,
    name: str = Form(...),
    phone: str = Form(...),
    email: str = Form(...),
    gender: str = Form(...),
    db: Session = Depends(get_db)
):
    if not request.cookies.get("reception_auth"):
        return RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)

    patient = db.query(Patient).filter(Patient.id == id).first()
    if not patient:
        return HTMLResponse("Patient not found", status_code=404)

    if not re.fullmatch(r"\d{10}", phone.strip()):
        return templates.TemplateResponse("reception/edit.html", {"request": request, "patient": patient, "error": "Invalid phone number"})

    patient.name = name
    patient.phone = phone
    patient.email = email
    patient.gender = gender
    db.commit()
    db.refresh(patient)

    return RedirectResponse(url="/reception/dashboard", status_code=HTTP_302_FOUND)


# -------------------------------
# 🚪 Logout
# -------------------------------
@router.get("/logout")
def logout():
    response = RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)
    response.delete_cookie("reception_auth")
    return response