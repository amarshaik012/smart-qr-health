from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import os, re

from .core.config import settings
from .core.db import Base, engine, SessionLocal, db_healthcheck
from .models.patient import Patient

# Routers
from .routers import admin, reception, doctor, patients, pharmadesk, verify


# ----------------------------------------
# ⚙️ Initialize FastAPI
# ----------------------------------------
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.3.22",
    description="Smart QR Health – Unified Patient & Prescription Portal",
)

# Ensure static + templates directories exist
static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")
os.makedirs(static_dir, exist_ok=True)

# Static & templates setup
app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)
templates.env.globals.update({"datetime": datetime})


# ----------------------------------------
# 🌐 CORS Middleware
# ----------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: Restrict this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------------------
# 🏁 Startup Event
# ----------------------------------------
@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database ready and initialized.")
    except Exception as e:
        print(f"⚠️ Database init skipped: {e}")


# ----------------------------------------
# ❤️ Health Check Endpoints
# ----------------------------------------
@app.get("/health", tags=["Health"])
def health():
    """Basic service health endpoint"""
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": "0.3.22"}


@app.get("/health/db", tags=["Health"])
def health_db():
    """Database connection test"""
    ok, error = db_healthcheck()
    return {"database": "ok" if ok else "error", "error": error}


# ----------------------------------------
# 🧭 Root Routes
# ----------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/portal", status_code=307)


@app.get("/portal", response_class=HTMLResponse, include_in_schema=False)
def choose_portal(request: Request):
    return templates.TemplateResponse(
        "base.html",
        {
            "request": request,
            "title": "Smart QR Health Portal",
            "show_portal_selection": True,
        },
    )


# ----------------------------------------
# 🧾 Public Patient Page (Updated)
# ----------------------------------------
@app.get("/p/{patient_uid}", response_class=HTMLResponse)
def resolve_patient(request: Request, patient_uid: str):
    """Public route for viewing patient details via QR UID"""
    with SessionLocal() as db:
        patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Normalize height
        if patient.height:
            patient.height = re.sub(
                r"(ft|feet)+", "ft", patient.height.strip(), flags=re.IGNORECASE
            )

        qr_url = f"/static/qr/{patient.qr_filename}"

        return templates.TemplateResponse(
            "patient_details.html",
            {
                "request": request,
                "patient": patient,
                "qr_url": qr_url,
                "height": patient.height,
            },
        )


# ----------------------------------------
# 🔗 Include Routers
# ----------------------------------------
app.include_router(admin.router)
app.include_router(reception.router)
app.include_router(doctor.router)
app.include_router(patients.router)
app.include_router(pharmadesk.router)
app.include_router(verify.router)