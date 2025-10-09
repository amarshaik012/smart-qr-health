from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
import os, csv

from ..core.db import get_db
from ..models.patient import Patient

router = APIRouter(prefix="/doctor", tags=["Doctor"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals["datetime"] = datetime  # for templates

PRESCRIPTIONS_CSV = "app/static/data/prescriptions.csv"
os.makedirs(os.path.dirname(PRESCRIPTIONS_CSV), exist_ok=True)

DOCTOR_USERNAME = "doctor"
DOCTOR_PASSWORD = "1234"


# -------------------------
# 🔐 Auth Helpers
# -------------------------
def _auth_guard(request: Request) -> bool:
    """Check if doctor is authenticated."""
    return request.cookies.get("doctor_auth") == "true"


# -------------------------
# 🩺 Doctor Login
# -------------------------
@router.get("/login", response_class=HTMLResponse)
def doctor_login_page(request: Request):
    return templates.TemplateResponse("doctor/login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse)
def doctor_login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == DOCTOR_USERNAME and password == DOCTOR_PASSWORD:
        response = RedirectResponse(url="/doctor/dashboard", status_code=303)
        response.set_cookie(key="doctor_auth", value="true", httponly=True)
        return response
    return templates.TemplateResponse(
        "doctor/login.html", {"request": request, "error": "Invalid credentials"}
    )


# -------------------------
# 🚪 Logout
# -------------------------
@router.get("/logout")
def doctor_logout():
    response = RedirectResponse(url="/doctor/login", status_code=302)
    response.delete_cookie("doctor_auth")
    return response


# -------------------------
# 🏠 Dashboard (Enhanced + Analytics)
# -------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def doctor_dashboard(request: Request, db: Session = Depends(get_db)):
    if not _auth_guard(request):
        return RedirectResponse(url="/doctor/login", status_code=302)

    patients = db.query(Patient).order_by(Patient.id.desc()).all()
    today = datetime.utcnow().date()
    week_ago = today - timedelta(days=6)

    # Load prescriptions
    prescription_records = []
    if os.path.exists(PRESCRIPTIONS_CSV):
        with open(PRESCRIPTIONS_CSV, newline="") as f:
            reader = csv.DictReader(f)
            prescription_records = list(reader)

    # Group prescriptions by patient and count visits by day
    presc_by_patient = {}
    visits_by_day = {(today - timedelta(days=i)): 0 for i in range(7)}

    for row in prescription_records:
        uid = row["PatientUID"]
        ts = datetime.fromisoformat(row["Timestamp"])
        presc_by_patient.setdefault(uid, []).append(ts)

        visit_day = ts.date()
        if visit_day in visits_by_day:
            visits_by_day[visit_day] += 1

    # Enrich patients
    for p in patients:
        # Age
        if p.dob:
            try:
                dob_date = datetime.strptime(p.dob, "%Y-%m-%d").date()
                p.age = (date.today().year - dob_date.year) - (
                    (date.today().month, date.today().day) < (dob_date.month, dob_date.day)
                )
            except Exception:
                p.age = "-"
        else:
            p.age = "-"

        # Visits
        if p.patient_uid in presc_by_patient:
            visits = presc_by_patient[p.patient_uid]
            p.visit_count = len(visits)
            last_visit = max(visits)
            p.last_visit = last_visit.strftime("%d %b %Y")
        else:
            p.visit_count = 0
            p.last_visit = "-"

    # Dashboard stats
    patients_today = sum(
        1 for p in patients
        if p.last_visit != "-" and datetime.strptime(p.last_visit, "%d %b %Y").date() == today
    )
    visits_this_week = sum(
        1 for p in patients
        if p.last_visit != "-" and datetime.strptime(p.last_visit, "%d %b %Y").date() >= week_ago
    )

    chart_labels = [d.strftime("%a") for d in sorted(visits_by_day.keys())]
    chart_data = [visits_by_day[d] for d in sorted(visits_by_day.keys())]

    return templates.TemplateResponse(
        "doctor/dashboard.html",
        {
            "request": request,
            "patients": patients,
            "total_patients": len(patients),
            "patients_today": patients_today,
            "total_prescriptions": len(prescription_records),
            "visits_this_week": visits_this_week,
            "chart_labels": chart_labels,
            "chart_data": chart_data,
        },
    )


# -------------------------
# 💊 Prescription Form
# -------------------------
@router.get("/prescribe/{patient_uid}", response_class=HTMLResponse)
def prescribe_page(request: Request, patient_uid: str, db: Session = Depends(get_db)):
    if not _auth_guard(request):
        return RedirectResponse(url="/doctor/login", status_code=302)

    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    return templates.TemplateResponse(
        "doctor/prescribe.html", {"request": request, "patient": patient, "error": None}
    )


@router.post("/prescribe/{patient_uid}", response_class=HTMLResponse)
def prescribe_submit(
    request: Request,
    patient_uid: str,
    diagnosis: str = Form(...),
    prescription: str = Form(...),
    notes: str = Form(None),
    db: Session = Depends(get_db),
):
    if not _auth_guard(request):
        return RedirectResponse(url="/doctor/login", status_code=302)

    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    try:
        file_exists = os.path.isfile(PRESCRIPTIONS_CSV)
        with open(PRESCRIPTIONS_CSV, mode="a", newline="") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["PatientUID", "Name", "Diagnosis", "Prescription", "Notes", "Timestamp"])
            writer.writerow([
                patient.patient_uid,
                patient.name,
                diagnosis.strip(),
                prescription.strip(),
                notes.strip() if notes else "",
                datetime.utcnow().isoformat(),
            ])
    except Exception as e:
        return templates.TemplateResponse(
            "doctor/prescribe.html",
            {"request": request, "patient": patient, "error": f"Error saving prescription: {e}"},
        )

    return RedirectResponse(url="/doctor/dashboard", status_code=303)


# -------------------------
# 📋 Patient History
# -------------------------
@router.get("/history/{patient_uid}", response_class=HTMLResponse)
def patient_history(request: Request, patient_uid: str, db: Session = Depends(get_db)):
    if not _auth_guard(request):
        return RedirectResponse(url="/doctor/login", status_code=302)

    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    prescriptions = []
    if os.path.exists(PRESCRIPTIONS_CSV):
        with open(PRESCRIPTIONS_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["PatientUID"] == patient_uid:
                    prescriptions.append(row)

    prescriptions.sort(key=lambda x: x["Timestamp"], reverse=True)

    return templates.TemplateResponse(
        "doctor/history.html",
        {"request": request, "patient": patient, "prescriptions": prescriptions},
    )