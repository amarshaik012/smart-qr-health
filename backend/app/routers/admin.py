from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from datetime import datetime, date, timedelta
from collections import defaultdict
from passlib.context import CryptContext

from ..core.db import get_db
from ..models.patient import Patient
from ..models.doctor import Doctor
from ..models.payment import Payment
from ..models.dispense import Dispense
from ..models.medicine import Medicine

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update({"datetime": datetime})

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ------------------------------------------------
# 🏠 Admin Home → Redirect
# ------------------------------------------------
@router.get("/", response_class=HTMLResponse)
def admin_home_redirect():
    return RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)

# ------------------------------------------------
# 🔐 Admin Login Page
# ------------------------------------------------
@router.get("/login", response_class=HTMLResponse)
def admin_login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request})

@router.post("/login", response_class=HTMLResponse)
def admin_login_post(request: Request, username: str = Form(...), password: str = Form(...)):
    ADMIN_USERNAME = "admin"
    ADMIN_PASSWORD = "admin123"
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        response = RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)
        response.set_cookie(key="admin_auth", value="true")
        return response
    return templates.TemplateResponse(
        "admin/login.html", {"request": request, "error": "Invalid credentials"}, status_code=401
    )

# ------------------------------------------------
# 📊 API: Pharmacy Sales Summary
# ------------------------------------------------
@router.get("/api/sales-summary")
def sales_summary(db: Session = Depends(get_db)):
    today = date.today()
    week_start = today - timedelta(days=6)
    month_start = today.replace(day=1)

    today_sales = db.query(func.coalesce(func.sum(Dispense.total_amount), 0.0))\
        .filter(func.date(Dispense.created_at) == today).scalar() or 0.0
    week_sales = db.query(func.coalesce(func.sum(Dispense.total_amount), 0.0))\
        .filter(Dispense.created_at >= week_start).scalar() or 0.0
    month_sales = db.query(func.coalesce(func.sum(Dispense.total_amount), 0.0))\
        .filter(Dispense.created_at >= month_start).scalar() or 0.0
    total_sales = db.query(func.coalesce(func.sum(Dispense.total_amount), 0.0)).scalar() or 0.0

    # last 7 days chart
    last7 = [today - timedelta(days=i) for i in range(6, -1, -1)]
    chart_data = []
    for d in last7:
        amt = db.query(func.coalesce(func.sum(Dispense.total_amount), 0.0))\
            .filter(func.date(Dispense.created_at) == d).scalar() or 0.0
        chart_data.append({"date": d.strftime("%b %d"), "total": round(amt, 2)})

    return {
        "today_sales": round(today_sales, 2),
        "week_sales": round(week_sales, 2),
        "month_sales": round(month_sales, 2),
        "total_sales": round(total_sales, 2),
        "chart": chart_data
    }

# ------------------------------------------------
# 🧾 API: Top Medicines (Last 30 Days)
# ------------------------------------------------
@router.get("/api/top-medicines")
def top_medicines(db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(days=30)
    rows = (
        db.query(Medicine.name, func.sum(Dispense.qty).label("qty"))
        .join(Medicine, Medicine.id == Dispense.medicine_id)
        .filter(Dispense.created_at >= since)
        .group_by(Medicine.name)
        .order_by(desc("qty"))
        .limit(5)
        .all()
    )
    return [{"name": r[0], "qty": int(r[1] or 0)} for r in rows]

# ------------------------------------------------
# 📋 Dashboard – Patients + Doctors + Payments + Sales
# ------------------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    patients = db.query(Patient).order_by(Patient.id.desc()).all()
    doctors  = db.query(Doctor).order_by(Doctor.id.desc()).all()

    total_patients = len(patients)
    today = date.today()
    recent_patients = 0
    grouped_patients = defaultdict(list)

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

    # 🩺 Doctor Stats
    total_doctors     = len(doctors)
    approved_doctors  = sum(1 for d in doctors if d.status == "approved")
    pending_doctors   = sum(1 for d in doctors if d.status == "pending")
    rejected_doctors  = sum(1 for d in doctors if d.status == "rejected")

    # 💳 Payments Aggregates
    total_revenue   = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(Payment.status == "paid").scalar() or 0.0
    todays_revenue  = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
        func.date(Payment.created_at) == today, Payment.status == "paid"
    ).scalar() or 0.0
    pending_amount  = db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(Payment.status == "pending").scalar() or 0.0
    avg_payment     = db.query(func.coalesce(func.avg(Payment.amount), 0.0)).filter(Payment.status == "paid").scalar() or 0.0

    # 📈 Chart: Patients last 7 days
    last7 = [today - timedelta(days=i) for i in range(6, -1, -1)]
    chart_labels = [d.strftime("%b %d") for d in last7]
    chart_values = [
        db.query(Patient).filter(func.date(Patient.created_at) == d).count() for d in last7
    ]

    # 💹 Chart: Revenue last 7 days
    revenue_values = [
        db.query(func.coalesce(func.sum(Payment.amount), 0.0)).filter(
            func.date(Payment.created_at) == d, Payment.status == "paid"
        ).scalar() or 0.0
        for d in last7
    ]
    revenue_chart = {"labels": chart_labels, "values": [round(v or 0.0, 2) for v in revenue_values]}

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "grouped_patients": grouped_patients,
            "total_patients": total_patients,
            "recent_patients": recent_patients,
            "total_doctors": total_doctors,
            "approved_doctors": approved_doctors,
            "pending_doctors": pending_doctors,
            "rejected_doctors": rejected_doctors,
            # payments
            "total_revenue": round(total_revenue or 0.0, 2),
            "todays_revenue": round(todays_revenue or 0.0, 2),
            "pending_payments": round(pending_amount or 0.0, 2),
            "avg_payment": round(avg_payment or 0.0, 2),
            # charts
            "chart_labels": chart_labels,
            "chart_values": chart_values,
            "revenue_chart": revenue_chart,
        },
    )

# ------------------------------------------------
# 🩺 Manage Doctors
# ------------------------------------------------
@router.get("/manage-doctors", response_class=HTMLResponse)
def manage_doctors(request: Request, db: Session = Depends(get_db)):
    doctors = db.query(Doctor).order_by(Doctor.id.desc()).all()
    return templates.TemplateResponse("admin/manage_doctors.html", {"request": request, "doctors": doctors})

@router.get("/approve-doctor/{doctor_id}")
def approve_doctor(doctor_id: int, db: Session = Depends(get_db)):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if doctor:
        doctor.status = "approved"
        db.commit()
    return RedirectResponse(url="/admin/manage-doctors", status_code=HTTP_302_FOUND)

@router.get("/reject-doctor/{doctor_id}")
def reject_doctor(doctor_id: int, db: Session = Depends(get_db)):
    doctor = db.query(Doctor).filter(Doctor.id == doctor_id).first()
    if doctor:
        doctor.status = "rejected"
        db.commit()
    return RedirectResponse(url="/admin/manage-doctors", status_code=HTTP_302_FOUND)

# ------------------------------------------------
# 🗑️ Delete Patient
# ------------------------------------------------
@router.get("/delete/{id}")
def delete_patient(id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == id).first()
    if patient:
        db.delete(patient)
        db.commit()
    return RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)

# ------------------------------------------------
# 🚪 Logout
# ------------------------------------------------
@router.get("/logout")
def logout():
    response = RedirectResponse(url="/admin/login", status_code=HTTP_302_FOUND)
    response.delete_cookie("admin_auth")
    return response