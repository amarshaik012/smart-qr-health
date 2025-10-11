from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from datetime import datetime
import os, re

from .core.config import settings
from .core.db import Base, engine, SessionLocal, db_healthcheck
from .models.patient import Patient
from .core.qr_utils import generate_qr_image  # ✅ dynamic QR generator

# Routers
from .routers import admin, reception, doctor, patients, pharmadesk, verify

# -----------------------------------------------------
# ⚙️ Initialize FastAPI
# -----------------------------------------------------
app = FastAPI(
    title=settings.PROJECT_NAME,
    version="0.3.23",
    description="Smart QR Health – Unified Patient & Prescription Portal",
)

# -----------------------------------------------------
# 📁 Static / Templates setup
# -----------------------------------------------------
static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

os.makedirs(static_dir, exist_ok=True)

app.mount("/static", StaticFiles(directory=static_dir), name="static")
templates = Jinja2Templates(directory=templates_dir)
templates.env.globals.update({"datetime": datetime})

# -----------------------------------------------------
# 🌐 CORS
# -----------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # ⚠️ restrict later for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------------------------------
# 🏁 Startup
# -----------------------------------------------------
@app.on_event("startup")
def on_startup():
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ Database initialized successfully.")
    except Exception as e:
        print(f"⚠️ Database init skipped: {e}")

# -----------------------------------------------------
# ❤️ Health routes
# -----------------------------------------------------
@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "service": settings.PROJECT_NAME, "version": "0.3.23"}


@app.get("/health/db", tags=["Health"])
def health_db():
    ok, error = db_healthcheck()
    return {"database": "ok" if ok else "error", "error": error}

# -----------------------------------------------------
# 🧾 Dynamic QR Route (for Render)
# -----------------------------------------------------
@app.get("/qr/{uid}", response_class=StreamingResponse)
def serve_qr(uid: str):
    """
    Generates and streams the QR live from BASE_URL.
    This avoids 404s from missing static files on Render.
    """
    try:
        return generate_qr_image(uid)
    except Exception as e:
        print(f"[QR ERROR] {e}")
        raise HTTPException(status_code=404, detail="QR not found")

# -----------------------------------------------------
# 🧭 Root + Portal
# -----------------------------------------------------
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/portal", status_code=307)


@app.get("/portal", response_class=HTMLResponse, include_in_schema=False)
def choose_portal(request: Request):
    return templates.TemplateResponse(
        "base.html",
        {"request": request, "title": "Smart QR Health Portal", "show_portal_selection": True},
    )

# -----------------------------------------------------
# 🧬 Public Patient Details Page
# -----------------------------------------------------
@app.get("/p/{patient_uid}", response_class=HTMLResponse)
def resolve_patient(request: Request, patient_uid: str):
    with SessionLocal() as db:
        patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        if patient.height:
            patient.height = re.sub(r"(ft|feet)+", "ft", patient.height.strip(), flags=re.IGNORECASE)

        qr_url = f"/qr/{patient.patient_uid}"  # ✅ dynamic QR endpoint
        return templates.TemplateResponse(
            "patient_details.html",
            {"request": request, "patient": patient, "qr_url": qr_url},
        )

# -----------------------------------------------------
# 🔗 Routers
# -----------------------------------------------------
app.include_router(admin.router)
app.include_router(reception.router)
app.include_router(doctor.router)
app.include_router(patients.router)
app.include_router(pharmadesk.router)
app.include_router(verify.router)