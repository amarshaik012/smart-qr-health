from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import os, re, shortuuid

from .core.config import settings
from .core.db import Base, engine, SessionLocal, db_healthcheck
from .models.patient import Patient
from .core.qr_utils import generate_qr_image, append_to_csv

# ✅ Routers
from .routers import admin, reception, doctor, patients, pharmadesk


# -------------------------------
# ⚙️ Initialize App
# -------------------------------
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.3.20",
    description="Smart QR Health – Unified Patient & Prescription Portal",
)

# -------------------------------
# 📂 Static & Templates
# -------------------------------
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update({"datetime": datetime})

# -------------------------------
# 🌐 CORS Middleware
# -------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # in production, restrict to your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------
# 🏁 Startup – Initialize DB
# -------------------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    print("✅ Database ready and initialized.")


# -------------------------------
# 🧭 Root – Landing Page
# -------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/portal", status_code=307)


@app.get("/portal", response_class=HTMLResponse, include_in_schema=False)
def choose_portal(request: Request):
    """Unified landing page for all roles."""
    return templates.TemplateResponse(
        "base.html",
        {
            "request": request,
            "title": "Smart QR Health Portal",
            "show_portal_selection": True,
        },
    )


# -------------------------------
# ❤️ Health Checks
# -------------------------------
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": "0.3.20"}


@app.get("/health/db", tags=["Health"])
def health_db():
    ok, error = db_healthcheck()
    return {"database": "ok" if ok else "error", "error": error}


# -------------------------------
# 🧾 Public Patient QR Page
# -------------------------------
@app.get("/p/{patient_uid}", response_class=HTMLResponse)
def resolve_patient(request: Request, patient_uid: str):
    """Public QR access: view patient details by QR UID"""
    with SessionLocal() as db:
        patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()

        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        # Clean height formatting
        if patient.height:
            patient.height = (
                re.sub(r"(ft|feet)+", "ft", patient.height.strip(), flags=re.IGNORECASE)
                .replace("  ", " ")
                .strip()
            )

        qr_url = f"/static/qr/{patient.qr_filename}"

        return templates.TemplateResponse(
            "patient.html",
            {"request": request, "patient": patient, "qr_url": qr_url},
        )


# -------------------------------
# 🔗 Include All Routers
# -------------------------------
app.include_router(admin.router)
app.include_router(reception.router)
app.include_router(doctor.router)
app.include_router(patients.router)
app.include_router(pharmadesk.router)