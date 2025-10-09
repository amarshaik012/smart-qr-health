from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.status import HTTP_302_FOUND
from sqlalchemy.orm import Session
from datetime import datetime, date
from collections import defaultdict

from ..core.db import get_db
from ..models.patient import Patient

router = APIRouter(prefix="/admin", tags=["Admin"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update({"datetime": datetime})

# ------------------------------------
# 🏠 Admin Home Redirect
# ------------------------------------
@router.get("/", response_class=HTMLResponse)
def admin_home_redirect():
    """Redirects /admin → /admin/dashboard"""
    return RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)


# ------------------------------------
# 📋 Dashboard – Grouped by Registration Date
# ------------------------------------
@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    """Show patients grouped by registration date + stats"""
    patients = db.query(Patient).order_by(Patient.id.desc()).all()

    total_patients = len(patients)
    today = date.today()
    recent_patients = 0
    grouped_patients = defaultdict(list)

    for p in patients:
        created_time = None
        if hasattr(p, "created_at") and p.created_at:
            created_time = p.created_at
        elif hasattr(p, "timestamp") and p.timestamp:
            created_time = p.timestamp

        if created_time:
            try:
                if isinstance(created_time, str):
                    created_time = datetime.fromisoformat(created_time)
                reg_date = created_time.date()
            except Exception:
                reg_date = today
        else:
            reg_date = today

        # Group patients by date
        grouped_patients[reg_date].append(p)

        # Count today's registrations
        if reg_date == today:
            recent_patients += 1

    # Sort by date (descending)
    grouped_patients = dict(sorted(grouped_patients.items(), reverse=True))

    return templates.TemplateResponse(
        "admin/dashboard.html",
        {
            "request": request,
            "grouped_patients": grouped_patients,
            "total_patients": total_patients,
            "recent_patients": recent_patients,
        },
    )


# ------------------------------------
# 🗑️ Delete Patient
# ------------------------------------
@router.get("/delete/{id}")
def delete_patient(id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.id == id).first()
    if not patient:
        print(f"[WARN] Patient ID {id} not found")
        return RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)

    db.delete(patient)
    db.commit()
    print(f"[ADMIN] Deleted patient → {patient.name}")
    return RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)


# ------------------------------------
# 🚪 Logout
# ------------------------------------
@router.get("/logout")
def logout():
    response = RedirectResponse(url="/admin/dashboard", status_code=HTTP_302_FOUND)
    response.delete_cookie("admin_auth")
    return response