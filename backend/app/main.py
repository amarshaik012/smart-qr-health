from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import os, csv, json

# -------------------------------------------------------
# ⚙️ Core Imports
# -------------------------------------------------------
from .core.config import settings
from .core.db import Base, engine, SessionLocal, db_healthcheck
from .models.patient import Patient
from .core.qr_utils import generate_qr_image
from .core.template_engine import templates

# -------------------------------------------------------
# 🧩 Routers
# -------------------------------------------------------
from .routers import admin, reception, doctor, patients, verify, pharmadesk  # ✅ single pharmadesk file only

# -------------------------------------------------------
# 🚀 FastAPI Initialization
# -------------------------------------------------------
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.6.0",
    description="Smart QR Health – Unified Patient, Doctor, and Pharma Portal",
)

# -------------------------------------------------------
# 🗂️ Static & Report Directories
# -------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

REPORTS_DIR = os.getenv("REPORTS_DIR", "/tmp/reports")
os.makedirs(REPORTS_DIR, exist_ok=True)
app.mount("/reports", StaticFiles(directory=REPORTS_DIR), name="reports")

# -------------------------------------------------------
# 🌐 CORS Middleware
# -------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------
# 🏁 Startup Events
# -------------------------------------------------------
@app.on_event("startup")
def on_startup():
    """Initialize database and environment paths."""
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database models created.")
    except Exception as e:
        print(f"⚠️ Database init skipped: {e}")

    print(f"📦 Static dir: {STATIC_DIR}")
    print(f"📄 Data dir: {os.getenv('DATA_SAVE_DIR', '/tmp/data')}")
    print(f"🧾 Reports dir: {REPORTS_DIR}")
    print(f"🗃️ Database: {settings.DATABASE_URL}")

# -------------------------------------------------------
# ❤️ Health Checks
# -------------------------------------------------------
@app.get("/health", tags=["Health"])
def health():
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": "0.6.0",
    }

@app.get("/health/db", tags=["Health"])
def health_db():
    ok, error = db_healthcheck()
    return {"database": "ok" if ok else "error", "error": error}

# -------------------------------------------------------
# 🧾 Debug Info
# -------------------------------------------------------
@app.get("/debug/info")
def debug_info():
    return {
        "environment": settings.ENVIRONMENT,
        "base_url": settings.PUBLIC_BASE_URL,
        "database": str(settings.DATABASE_URL),
        "directories": {
            "static": STATIC_DIR,
            "reports": REPORTS_DIR,
            "data": os.getenv("DATA_SAVE_DIR", "/tmp/data"),
        },
    }

# -------------------------------------------------------
# 🧾 Dynamic QR Generator
# -------------------------------------------------------
@app.get("/qr/{uid}")
def serve_qr(uid: str):
    """Serve dynamically generated patient QR."""
    return generate_qr_image(uid)

# -------------------------------------------------------
# 🧭 Root & Portal Selector
# -------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    """Redirect root URL to the portal."""
    return RedirectResponse(url="/portal", status_code=307)

@app.get("/portal", response_class=HTMLResponse, include_in_schema=False)
def choose_portal(request: Request):
    """Render the main portal selection page."""
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "title": "Smart QR Health Portal", "show_portal_selection": True},
    )

# -------------------------------------------------------
# 🧬 Public Patient Page (QR)
# -------------------------------------------------------
PRESCRIPTIONS_CSV = os.path.join("/tmp/data", "prescriptions.csv")
os.makedirs(os.path.dirname(PRESCRIPTIONS_CSV), exist_ok=True)

def load_prescriptions_for(uid: str):
    """Load prescription data for a patient UID."""
    rows = []
    if os.path.exists(PRESCRIPTIONS_CSV):
        with open(PRESCRIPTIONS_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("PatientUID") != uid:
                    continue
                ts = r.get("Timestamp", "")
                try:
                    dt = datetime.fromisoformat(ts.replace("Z", ""))
                    date_str = dt.strftime("%d %b %Y")
                    sort_key = dt.isoformat()
                except Exception:
                    date_str, sort_key = ts, ts
                try:
                    pres = json.loads(r.get("Medicines", "[]"))
                except Exception:
                    pres = r.get("Medicines", "")
                rows.append({
                    "Date": date_str,
                    "Doctor": r.get("Doctor", "-"),
                    "Diagnosis": r.get("Diagnosis", "-"),
                    "Prescription": pres,
                    "_sort": sort_key,
                })
    rows.sort(key=lambda x: x["_sort"], reverse=True)
    for r in rows:
        r.pop("_sort", None)
    return rows

@app.get("/p/{patient_uid}", response_class=HTMLResponse)
def resolve_patient(request: Request, patient_uid: str):
    """Render patient info via QR scan."""
    with SessionLocal() as db:
        patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        prescriptions = load_prescriptions_for(patient_uid)
        return templates.TemplateResponse(
            "patient_details.html",
            {
                "request": request,
                "patient": patient,
                "qr_url": f"/qr/{patient.patient_uid}",
                "prescriptions": prescriptions,
            },
        )

# -------------------------------------------------------
# 🔗 Router Registration
# -------------------------------------------------------
app.include_router(admin.router)
app.include_router(reception.router)
app.include_router(doctor.router)
app.include_router(patients.router)
app.include_router(verify.router)
app.include_router(pharmadesk.router)  # ✅ unified PharmaDesk router