from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import os, re, csv

from .core.config import settings
from .core.db import Base, engine, SessionLocal, db_healthcheck
from .models.patient import Patient
from .core.qr_utils import generate_qr_image  # dynamic QR

# Routers
from .routers import admin, reception, doctor, patients, pharmadesk, verify

# -------------------------------------------------------
# ⚙️ App init
# -------------------------------------------------------
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.3.31",
    description="Smart QR Health – Unified Patient & Prescription Portal",
)

# -------------------------------------------------------
# 🗂️ Static + Templates
# -------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
static_dir = os.path.join(BASE_DIR, "static")
templates_dir = os.path.join(BASE_DIR, "templates")
os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)
templates.env.globals.update({"datetime": datetime})

# -------------------------------------------------------
# 🌐 CORS
# -------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # relax for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------
# 🏁 Startup
# -------------------------------------------------------
@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"⚠️ Database init skipped: {e}")

# -------------------------------------------------------
# ❤️ Health
# -------------------------------------------------------
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": "0.3.31"}

@app.get("/health/db", tags=["Health"])
def health_db():
    ok, error = db_healthcheck()
    return {"database": "ok" if ok else "error", "error": error}

# -------------------------------------------------------
# 🧾 Dynamic QR (streams PNG)
# -------------------------------------------------------
@app.get("/qr/{uid}")
def serve_qr(uid: str):
    return generate_qr_image(uid)

# -------------------------------------------------------
# 🧭 Root & Portal
# -------------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/portal", status_code=307)

@app.get("/portal", response_class=HTMLResponse, include_in_schema=False)
def choose_portal(request: Request):
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "title": "Smart QR Health Portal", "show_portal_selection": True},
    )

# -------------------------------------------------------
# 🔎 Helper: load prescriptions from CSV
# -------------------------------------------------------
PRESCRIPTIONS_CSV = os.path.join(static_dir, "data", "prescriptions.csv")
os.makedirs(os.path.dirname(PRESCRIPTIONS_CSV), exist_ok=True)

def load_prescriptions_for(uid: str):
    """
    Return list of dicts: {Date, Diagnosis, Prescription} for given UID, newest first.
    Works with the CSV written by the doctor flow.
    """
    rows = []
    if os.path.exists(PRESCRIPTIONS_CSV):
        with open(PRESCRIPTIONS_CSV, newline="") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("PatientUID") == uid:
                    ts = r.get("Timestamp", "")
                    # format a nice date
                    try:
                        dt = datetime.fromisoformat(ts.replace("Z", ""))
                        date_str = dt.strftime("%d %b %Y")
                        sort_key = dt.isoformat()
                    except Exception:
                        date_str = ts
                        sort_key = ts
                    rows.append({
                        "Date": date_str,
                        "Diagnosis": r.get("Diagnosis", "") or "-",
                        "Prescription": r.get("Prescription", "") or "-",
                        "_sort": sort_key,
                    })
    # newest first
    rows.sort(key=lambda x: x["_sort"], reverse=True)
    for r in rows:
        r.pop("_sort", None)
    return rows

# -------------------------------------------------------
# 🧬 Public Patient Details Page
# -------------------------------------------------------
@app.get("/p/{patient_uid}", response_class=HTMLResponse)
def resolve_patient(request: Request, patient_uid: str):
    with SessionLocal() as db:
        patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Clean height like "5.6 ft"
        if patient.height:
            patient.height = re.sub(r"(ft|feet)+", "ft", patient.height.strip(), flags=re.I)
            patient.height = re.sub(r"\s+", " ", patient.height).strip()

        # Load prescriptions from CSV
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
# 🔗 Routers
# -------------------------------------------------------
app.include_router(admin.router)
app.include_router(reception.router)
app.include_router(doctor.router)
app.include_router(patients.router)
app.include_router(pharmadesk.router)
app.include_router(verify.router)