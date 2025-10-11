from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import os
import re

from .core.config import settings
from .core.db import Base, engine, SessionLocal, db_healthcheck
from .models.patient import Patient
from .core.qr_utils import generate_qr_image  # ✅ QR generator import

# Routers
from .routers import admin, reception, doctor, patients, pharmadesk, verify


# -------------------------------------------------------
# ⚙️ Initialize FastAPI
# -------------------------------------------------------
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.3.24",
    description="Smart QR Health – Unified Patient & Prescription Portal",
)

# -------------------------------------------------------
# 🗂️ Static + Templates setup
# -------------------------------------------------------
BASE_DIR = os.path.dirname(__file__)
static_dir = os.path.join(BASE_DIR, "static")
templates_dir = os.path.join(BASE_DIR, "templates")

os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)
templates.env.globals.update({"datetime": datetime})


# -------------------------------------------------------
# 🌐 CORS (for cross-domain portals)
# -------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ✅ relax for dev, tighten later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -------------------------------------------------------
# 🏁 Startup Event
# -------------------------------------------------------
@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"⚠️ Database init skipped: {e}")


# -------------------------------------------------------
# ❤️ Health Endpoints
# -------------------------------------------------------
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": "0.3.24"}


@app.get("/health/db", tags=["Health"])
def health_db():
    ok, error = db_healthcheck()
    return {"database": "ok" if ok else "error", "error": error}


# -------------------------------------------------------
# 🧾 Dynamic QR Generator (for Render)
# -------------------------------------------------------
@app.get("/qr/{uid}")
def serve_qr(uid: str):
    """
    Dynamically generate and stream QR image as PNG.
    Works both locally and on Render (no static writes).
    """
    try:
        return generate_qr_image(uid)
    except Exception as e:
        print(f"[QR ERROR] {e}")
        raise HTTPException(status_code=404, detail="QR not found")


# -------------------------------------------------------
# 🧭 Root and Portal Routes
# -------------------------------------------------------
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


# -------------------------------------------------------
# 🧬 Public Patient Details Page
# -------------------------------------------------------
@app.get("/p/{patient_uid}", response_class=HTMLResponse)
def resolve_patient(request: Request, patient_uid: str):
    with SessionLocal() as db:
        patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        if patient.height:
            patient.height = re.sub(
                r"(ft|feet)+", "ft", patient.height.strip(), flags=re.IGNORECASE
            )

        qr_url = f"/qr/{patient.patient_uid}"
        return templates.TemplateResponse(
            "patient_details.html",
            {"request": request, "patient": patient, "qr_url": qr_url},
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