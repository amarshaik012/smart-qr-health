# backend/app/routers/reception.py
from fastapi import APIRouter, Request, Form, Depends
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND
from sqlalchemy.orm import Session
from datetime import datetime, date
from collections import defaultdict
import os, random, time, shortuuid, re, csv

# Core
from ..core.db import get_db
from ..models.patient import Patient
from ..models.doctor import Doctor
from ..models.payment import Payment           # <— existing
from ..core.qr_utils import generate_qr_image, append_to_csv

router = APIRouter(prefix="/reception", tags=["Reception"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update({"datetime": datetime})

RECEPTION_USERNAME = "reception"
RECEPTION_PASSWORD = "reception123"

# ✅ Use environment-based writable dirs (Docker safe)
QR_SAVE_DIR = os.getenv("QR_SAVE_DIR", "/tmp/qr")
DATA_SAVE_DIR = os.getenv("DATA_SAVE_DIR", "/tmp/data")

os.makedirs(QR_SAVE_DIR, exist_ok=True)
os.makedirs(DATA_SAVE_DIR, exist_ok=True)

PAYMENTS_CSV = os.path.join(DATA_SAVE_DIR, "payments.csv")

# Validation regex
PHONE_RE = re.compile(r"^\d{10}$")
GMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@gmail\.com$")

# OTP store (simulated)
otp_store: dict[str, tuple[int, float]] = {}

# -----------------------------
# Auth
# -----------------------------
@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("reception/login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == RECEPTION_USERNAME and password == RECEPTION_PASSWORD:
        resp = RedirectResponse(url="/reception/dashboard", status_code=HTTP_302_FOUND)
        resp.set_cookie(key="reception_auth", value="true", httponly=True, samesite="Lax")
        return resp
    return templates.TemplateResponse(
        "reception/login.html", {"request": request, "error": "Invalid username or password"}
    )


# -----------------------------
# Dashboard
# -----------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    if not request.cookies.get("reception_auth"):
        return RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)

    patients = db.query(Patient).order_by(Patient.id.desc()).all()
    today = date.today()
    grouped_patients: dict[date, list[Patient]] = defaultdict(list)
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


# -----------------------------
# OTP (simulated)
# -----------------------------
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


# -----------------------------
# Register (GET)
# -----------------------------
@router.get("/register", response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    if not request.cookies.get("reception_auth"):
        return RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)

    doctors = db.query(Doctor).filter(Doctor.status == "approved").all()
    today_str = date.today().isoformat()
    return templates.TemplateResponse(
        "reception/register.html",
        {"request": request, "doctors": doctors, "error": None, "today": today_str, "form_data": {}},
    )


# -----------------------------
# Register (POST)
# -----------------------------
@router.post("/register", response_class=HTMLResponse)
def register_patient(
    request: Request,
    name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    gender: str = Form(""),
    dob: str = Form(""),
    weight: str = Form(""),
    height: str = Form(""),
    assigned_doctor: str = Form(""),
    payment_mode: str = Form(""),
    payment_amount: str = Form(""),
    payment_ref: str = Form(""),
    db: Session = Depends(get_db),
):
    if not request.cookies.get("reception_auth"):
        return RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)

    # Helper to preserve form data
    def fail(msg: str):
        doctors = db.query(Doctor).filter(Doctor.status == "approved").all()
        today_str = date.today().isoformat()
        form_data = {
            "name": name,
            "phone": phone,
            "email": email,
            "gender": gender,
            "dob": dob,
            "weight": weight,
            "height": height,
            "assigned_doctor": assigned_doctor,
            "payment_mode": payment_mode,
            "payment_amount": payment_amount,
            "payment_ref": payment_ref,
        }
        return templates.TemplateResponse(
            "reception/register.html",
            {"request": request, "error": msg, "doctors": doctors, "today": today_str, "form_data": form_data},
            status_code=400,
        )

    # ---------- Strict validation ----------
    if not name.strip():
        return fail("Full name is required.")
    if not PHONE_RE.fullmatch(phone.strip()):
        return fail("Phone number must be exactly 10 digits.")
    if not GMAIL_RE.fullmatch(email.strip()):
        return fail("Email must be a valid Gmail address (e.g., name@gmail.com).")
    if gender not in {"Male", "Female", "Other"}:
        return fail("Please select a valid gender.")
    try:
        dob_date = datetime.strptime(dob, "%Y-%m-%d").date()
    except Exception:
        return fail("Invalid Date of Birth.")
    if dob_date > date.today():
        return fail("Date of Birth cannot be in the future.")
    if not weight:
        return fail("Weight is required.")
    if not height:
        return fail("Height is required.")
    if not assigned_doctor:
        return fail("Please assign a doctor.")
    doctor_obj = db.query(Doctor).filter(Doctor.name == assigned_doctor, Doctor.status == "approved").first()
    if not doctor_obj:
        return fail("Assigned doctor is not valid or not approved.")
    if payment_mode not in {"Cash", "UPI", "Card"}:
        return fail("Select a valid payment mode (Cash / UPI / Card).")
    try:
        amount_val = float(payment_amount)
        if amount_val < 0:
            raise ValueError
    except Exception:
        return fail("Payment amount must be a number (0 or above).")
    if db.query(Patient).filter(Patient.phone == phone.strip()).first():
        return fail("Phone number is already registered.")

    # ---------- Generate QR ----------
    uid = shortuuid.uuid()[:12]
    qr_filename = f"{uid}.png"
    qr_path = os.path.join(QR_SAVE_DIR, qr_filename)
    generate_qr_image(uid, qr_path)

    # ---------- Create patient ----------
    patient = Patient(
        patient_uid=uid,
        name=name.strip(),
        phone=phone.strip(),
        email=email.strip(),
        gender=gender.strip(),
        dob=dob,
        weight=weight.strip(),
        height=height.strip(),
        assigned_doctor=assigned_doctor.strip(),
        doctor_id=doctor_obj.id,
        qr_filename=qr_filename,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)

    # ---------- CSV Logs ----------
    append_to_csv({
        "patient_uid": uid,
        "name": patient.name,
        "phone": patient.phone,
        "email": patient.email,
        "gender": patient.gender,
        "dob": dob,
        "weight": weight,
        "height": height,
        "assigned_doctor": assigned_doctor,
        "qr_url": f"/static/qr/{qr_filename}",
        "timestamp": datetime.utcnow().isoformat(),
    })

    file_exists = os.path.isfile(PAYMENTS_CSV)
    with open(PAYMENTS_CSV, "a", newline="") as f:
        w = csv.writer(f)
        if not file_exists:
            w.writerow(["Timestamp", "PatientUID", "Name", "Mode", "Amount", "Reference"])
        w.writerow([datetime.utcnow().isoformat(), uid, patient.name, payment_mode, f"{amount_val:.2f}", payment_ref])

    # ---------- Also persist to DB ----------
    try:
        status = "paid" if amount_val > 0 else "pending"
        method = payment_mode.lower()
        db.add(
            Payment(
                patient_id=patient.id,
                doctor_id=doctor_obj.id,
                amount=amount_val,
                status=status,
                method=method,
                ref=(payment_ref or "").strip(),
            )
        )
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"[WARN] Payment DB insert failed: {e}")

    return RedirectResponse(url=f"/reception/qr-preview/{uid}", status_code=HTTP_302_FOUND)


# -----------------------------
# QR Preview
# -----------------------------
@router.get("/qr-preview/{patient_uid}", response_class=HTMLResponse)
def qr_preview(request: Request, patient_uid: str, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        return HTMLResponse("Patient not found", status_code=404)
    return templates.TemplateResponse(
        "reception/qr_preview.html",
        {
            "request": request,
            "name": patient.name,
            "phone": patient.phone,
            "assigned_doctor": patient.assigned_doctor or "Unassigned",
            "qr_filename": patient.qr_filename,
            "hospital_name": "Smart QR Health Hospital",
            "patient_uid": patient.patient_uid,
        },
    )


# -----------------------------
# Edit + Logout
# -----------------------------
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
    db: Session = Depends(get_db),
):
    if not request.cookies.get("reception_auth"):
        return RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)

    patient = db.query(Patient).filter(Patient.id == id).first()
    if not patient:
        return HTMLResponse("Patient not found", status_code=404)
    if not PHONE_RE.fullmatch(phone.strip()):
        return templates.TemplateResponse(
            "reception/edit.html",
            {"request": request, "patient": patient, "error": "Invalid phone number"},
        )

    patient.name = name.strip()
    patient.phone = phone.strip()
    patient.email = email.strip()
    patient.gender = gender.strip()
    db.commit()
    db.refresh(patient)
    return RedirectResponse(url="/reception/dashboard", status_code=HTTP_302_FOUND)


@router.get("/logout")
def logout():
    resp = RedirectResponse(url="/reception/login", status_code=HTTP_302_FOUND)
    resp.delete_cookie("reception_auth")
    return resp