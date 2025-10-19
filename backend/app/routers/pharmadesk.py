# app/routers/pharmadesk.py
from __future__ import annotations

from fastapi import (
    APIRouter,
    Request,
    Form,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Query,
    Response,
)
from fastapi.responses import (
    RedirectResponse,
    HTMLResponse,
    StreamingResponse,
    JSONResponse,
)
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, text
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Tuple, Set
import os
import csv
import io
import uuid
import json
from pathlib import Path

from ..core.db import get_db
from ..models.patient import Patient
from ..models.medicine import Medicine
from ..models.dispense import Dispense
from ..utils.pdf_utils import generate_bill_pdf

# ---------------------------------------------------------------------------
# Optional signing support (for share links). Falls back to plain links if
# the library or SECRET is not present — no crashes.
# ---------------------------------------------------------------------------
try:
    from itsdangerous import URLSafeSerializer, BadSignature
except Exception:
    URLSafeSerializer = None  # type: ignore
    BadSignature = Exception  # type: ignore

# bcrypt via passlib (no extra local module needed)
try:
    from passlib.hash import bcrypt as _bcrypt_hash
except Exception:  # hard fallback if passlib/bcrypt isn’t available
    _bcrypt_hash = None  # type: ignore

router = APIRouter(prefix="/pharmadesk", tags=["PharmaDesk"])
templates = Jinja2Templates(directory="app/templates")
templates.env.globals.update({"datetime": datetime})

# ---------------------------------------------------------------------------
# Shared CSV location for prescriptions (doctor + pharmadesk)
# ---------------------------------------------------------------------------
DATA_DIR = Path("app/static/data")
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    # If parent is read-only in container, bind mount will still provide it
    print(f"[PharmaDesk] WARN: mkdir {DATA_DIR} failed → {e}")
PRESCRIPTIONS_CSV = DATA_DIR / "prescriptions.csv"
print(f"[PharmaDesk] Using prescriptions CSV → {PRESCRIPTIONS_CSV}")

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _cookie_ok(request: Request) -> bool:
    return request.cookies.get("pharma_auth") == "ok"

def _verify_password(plain: str, hashed: str) -> bool:
    if not plain or not hashed:
        return False
    if _bcrypt_hash is None:
        return False
    try:
        return _bcrypt_hash.verify(plain, hashed)
    except Exception:
        return False

def _fetch_user(db: Session, username: str) -> Optional[Dict[str, Any]]:
    """
    Look up a user in a 'users' table if you created it.
    Returns a dict with keys: id, username, email, password, role
    """
    try:
        row = (
            db.execute(
                text(
                    "SELECT id, username, email, password, role "
                    "FROM users WHERE lower(username)=lower(:u) LIMIT 1"
                ),
                {"u": username.strip()},
            )
            .mappings()
            .first()
        )
        return dict(row) if row else None
    except Exception:
        return None

# ---------------------------------------------------------------------------
# Signed link helper (optional)
# ---------------------------------------------------------------------------
def _get_signer() -> Optional[URLSafeSerializer]:
    secret = os.getenv("PHARMADESK_SECRET") or os.getenv("SECRET_KEY") or os.getenv("JWT_SECRET")
    if not secret or URLSafeSerializer is None:
        return None
    return URLSafeSerializer(secret, salt="pharmadesk-share-links")

# ---------------------------------------------------------------------------
# Import-preview in-memory cache
# ---------------------------------------------------------------------------
IMPORT_PREVIEW_CACHE: Dict[str, Dict[str, Any]] = {}
IMPORT_PREVIEW_TTL_MINUTES = 45

def _now() -> datetime:
    return datetime.utcnow()

def _purge_import_cache() -> None:
    cutoff = _now() - timedelta(minutes=IMPORT_PREVIEW_TTL_MINUTES)
    for token in list(IMPORT_PREVIEW_CACHE.keys()):
        if IMPORT_PREVIEW_CACHE[token]["created_at"] < cutoff:
            IMPORT_PREVIEW_CACHE.pop(token, None)

# ---------------------------------------------------------------------------
# CSV mapping → Medicine model
# (Your Medicine model: name, strength, form, mrp, tax_pct, stock_qty, reorder_level)
# ---------------------------------------------------------------------------
_MEDICINE_FIELD_MAP = {
    "name": "name",
    "medicine": "name",
    "drugname": "name",
    "strength": "strength",
    "form": "form",
    "mrp": "mrp",
    "price": "mrp",
    "cost": "mrp",
    "tax": "tax_pct",
    "tax_pct": "tax_pct",

    # stock
    "qty": "stock_qty",
    "quantity": "stock_qty",
    "stock": "stock_qty",
    "stock_qty": "stock_qty",

    # reorder
    "reorder": "reorder_level",
    "reorder_level": "reorder_level",
    "reorder_lev": "reorder_level",  # your Excel header

    # optional batch/expiry (safe even if model ignores these)
    "batch": "batch_no",
    "batch_no": "batch_no",
    "expiry": "expiry_date",
    "expiry_date": "expiry_date",
}

def _norm(h: str) -> str:
    return (h or "").strip().lower()

def _row_to_payload(row: Dict[str, str]) -> Dict[str, Any]:
    p: Dict[str, Any] = {}
    for raw_k, v in row.items():
        k = _norm(raw_k)
        if k not in _MEDICINE_FIELD_MAP:
            continue
        field = _MEDICINE_FIELD_MAP[k]
        val = (v or "").strip()
        try:
            if field in ("mrp", "tax_pct"):
                p[field] = float(val) if val else 0.0
            elif field in ("stock_qty", "reorder_level"):
                p[field] = int(float(val)) if val else 0
            else:
                p[field] = val or ""
        except Exception:
            if field in ("mrp", "tax_pct"):
                p[field] = 0.0
            elif field in ("stock_qty", "reorder_level"):
                p[field] = 0
            else:
                p[field] = ""
    if not p.get("name"):
        p["name"] = row.get("name") or row.get("medicine") or row.get("drugname") or ""
    return p

# Small helper
def _lc(s: Optional[str]) -> str:
    return (s or "").strip().lower()

# =============================================================================
#                                 AUTH ROUTES
# =============================================================================
@router.get("/login", response_class=HTMLResponse)
def pharmadesk_login_page(request: Request):
    if _cookie_ok(request):
        return RedirectResponse("/pharmadesk/", status_code=302)
    return templates.TemplateResponse("pharmadesk/login.html", {"request": request})

@router.post("/login", response_class=HTMLResponse)
def pharmadesk_login(
    request: Request,
    response: Response,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    # Try DB-backed login first
    user = _fetch_user(db, username)
    if user and _verify_password(password, user.get("password") or ""):
        res = RedirectResponse("/pharmadesk/", status_code=302)
        res.set_cookie("pharma_auth", "ok", max_age=86400, httponly=True)
        return res

    # Fallback dev login (if no users table or mismatch)
    if username == "admin" and password == "admin":
        res = RedirectResponse("/pharmadesk/", status_code=302)
        res.set_cookie("pharma_auth", "ok", max_age=86400, httponly=True)
        return res

    return templates.TemplateResponse(
        "pharmadesk/login.html",
        {"request": request, "error": "Invalid credentials"},
    )

@router.get("/logout")
def pharmadesk_logout():
    res = RedirectResponse("/pharmadesk/login", status_code=302)
    res.delete_cookie("pharma_auth")
    return res

@router.get("/dashboard", include_in_schema=False)
def pharmadesk_dashboard_redirect():
    # Make both /pharmadesk/dashboard and /pharmadesk/ work
    return RedirectResponse("/pharmadesk/", status_code=302)

# =============================================================================
#                               DASHBOARD (HOME)
# =============================================================================
@router.get("/", response_class=HTMLResponse)
def pharmadesk_dashboard(request: Request, db: Session = Depends(get_db)):
    if not _cookie_ok(request):
        return RedirectResponse("/pharmadesk/login", status_code=302)

    total_patients = db.query(func.count(Patient.id)).scalar() or 0
    total_medicines = db.query(func.count(Medicine.id)).scalar() or 0
    total_dispenses = db.query(func.count(Dispense.id)).scalar() or 0

    # Provide pagination keys to satisfy templates that reference them
    context = {
        "request": request,
        "kpis": {
            "patients": total_patients,
            "medicines": total_medicines,
            "dispenses": total_dispenses,
        },
        "title": "PharmaDesk Dashboard",
        # Safe defaults so dashboard.html won't crash if it references these:
        "total_pages": 1,
        "page": 1,
        "per_page": 20,
        "total": 0,
        "offset": 0,
        "meds": [],
        "q": "",
    }
    return templates.TemplateResponse("pharmadesk/dashboard.html", context)

@router.get("", include_in_schema=False)
def redirect_root_to_dashboard():
    return RedirectResponse(url="/pharmadesk/", status_code=302)

# =============================================================================
#                       CSV IMPORT (UPLOAD → PREVIEW → CONFIRM)
# =============================================================================
@router.get("/import", response_class=HTMLResponse)
def import_page(request: Request):
    if not _cookie_ok(request):
        return RedirectResponse("/pharmadesk/login", status_code=302)
    return templates.TemplateResponse(
        "pharmadesk/import.html", {"request": request, "title": "Import Medicines"}
    )

def _apply_import_sync_to_csv(
    db: Session,
    rows: List[Dict[str, Any]],
    replace_all: bool,
) -> Dict[str, int]:
    """
    Synchronize DB with CSV:

    - replace_all=True:
        * For medicines NOT present in CSV:
            - If referenced in Dispense → keep (preserving history).
            - Else → delete.
        * For medicines present in CSV:
            - Update by name if exists, else create.
    - replace_all=False:
        * Simple upsert-by-name (update if exists else create).
    """
    created = updated = skipped = deleted = kept_due_to_history = 0

    # Index new rows by lowercase name
    new_by_name: Dict[str, Dict[str, Any]] = {}
    for p in rows:
        nm = _lc(p.get("name"))
        if not nm:
            skipped += 1
            continue
        new_by_name[nm] = p

    # Load existing
    existing: List[Medicine] = db.query(Medicine).all()
    existing_by_name: Dict[str, Medicine] = {_lc(m.name): m for m in existing}

    if replace_all:
        new_names: Set[str] = set(new_by_name.keys())
        to_consider_delete: List[Medicine] = [m for n, m in existing_by_name.items() if n not in new_names]

        if to_consider_delete:
            ids = [m.id for m in to_consider_delete]
            referenced_ids = set(
                id_ for (id_,) in db.query(Dispense.medicine_id).filter(Dispense.medicine_id.in_(ids)).distinct()
            )
            for m in to_consider_delete:
                if m.id in referenced_ids:
                    kept_due_to_history += 1
                else:
                    db.delete(m)
                    deleted += 1
            db.flush()

    # Upserts
    for nm, payload in new_by_name.items():
        existing_obj = existing_by_name.get(nm)
        if existing_obj:
            for k, v in payload.items():
                if hasattr(existing_obj, k) and v is not None:
                    setattr(existing_obj, k, v)
            updated += 1
        else:
            db.add(Medicine(**payload))
            created += 1

    db.flush()
    return {
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "deleted": deleted,
        "kept_due_to_history": kept_due_to_history,
        "total": len(rows),
        "replaced_all": int(bool(replace_all)),
    }

@router.post("/import/preview", response_class=HTMLResponse)
async def import_preview(
    request: Request,
    file: UploadFile = File(...),
    quick: bool = Form(False),          # one-step import if True
    replace_all: bool = Form(False),    # sync to CSV (remove extras safely)
):
    if not _cookie_ok(request):
        return RedirectResponse("/pharmadesk/login", status_code=302)

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Please upload a CSV file.")

    content: bytes = await file.read()
    try:
        text_data = content.decode("utf-8-sig")
    except Exception:
        text_data = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text_data))
    rows: List[Dict[str, str]] = list(reader)
    parsed: List[Dict[str, Any]] = [_row_to_payload(r) for r in rows if any((v or "").strip() for v in r.values())]

    if quick:
        # Do the import immediately (no second upload)
        gen = get_db()  # generator
        db: Session = next(gen)
        try:
            summary = _apply_import_sync_to_csv(db, parsed, replace_all)
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            try:
                next(gen)  # close
            except StopIteration:
                pass

        return templates.TemplateResponse(
            "pharmadesk/import_done.html",
            {
                "request": request,
                "title": "Import Complete",
                "result": summary,
            },
        )

    token = uuid.uuid4().hex
    IMPORT_PREVIEW_CACHE[token] = {
        "created_at": _now(),
        "filename": file.filename,
        "rows_parsed": parsed,
        "count": len(parsed),
        "replace_all": bool(replace_all),
    }
    _purge_import_cache()

    return templates.TemplateResponse(
        "pharmadesk/import_preview.html",
        {
            "request": request,
            "title": "Preview Import",
            "token": token,
            "filename": file.filename,
            "rows": parsed[:50],
            "total": len(parsed),
            "replace_all": bool(replace_all),
        },
    )

@router.post("/import/confirm", response_class=HTMLResponse)
def import_confirm(
    request: Request,
    token: str = Form(...),
    create_missing: bool = Form(True),      # retained for compatibility
    update_existing: bool = Form(True),     # retained for compatibility
    replace_all: bool = Form(False),        # if True → sync DB to CSV (safe deletions)
    db: Session = Depends(get_db),
):
    if not _cookie_ok(request):
        return RedirectResponse("/pharmadesk/login", status_code=302)

    data = IMPORT_PREVIEW_CACHE.get(token)
    if not data:
        raise HTTPException(status_code=410, detail="Import session expired. Please re-upload the CSV.")

    rows: List[Dict[str, Any]] = data["rows_parsed"]

    try:
        summary = _apply_import_sync_to_csv(db, rows, replace_all)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        IMPORT_PREVIEW_CACHE.pop(token, None)  # avoid double-run on refresh

    return templates.TemplateResponse(
        "pharmadesk/import_done.html",
        {
            "request": request,
            "title": "Import Complete",
            "result": summary,
        },
    )

# =============================================================================
#                         INVENTORY SYNC / PAGE / IMPORT JSON
# =============================================================================
@router.post("/inventory/sync")
def inventory_sync(db: Session = Depends(get_db)):
    """
    Recompute stock using real DB columns only:
      new stock = current baseline reconstructed from (current stock + dispensed) - dispensed
    """
    dispensed = dict(
        db.query(Dispense.medicine_id, func.coalesce(func.sum(Dispense.qty), 0))
        .group_by(Dispense.medicine_id)
        .all()
    )
    meds: List[Medicine] = db.query(Medicine).all()
    synced = 0

    for m in meds:
        base = int(m.stock_qty or 0) + int(dispensed.get(m.id, 0))
        new_qty = base - int(dispensed.get(m.id, 0))
        if new_qty < 0:
            new_qty = 0
        m.stock_qty = new_qty
        synced += 1

    db.commit()
    return JSONResponse({"status": "ok", "synced": synced})

@router.get("/inventory", response_class=HTMLResponse)
def inventory_page(
    request: Request,
    db: Session = Depends(get_db),
    q: str = "",
    page: int = 1,
    per_page: int = 20,
):
    if not _cookie_ok(request):
        return RedirectResponse("/pharmadesk/login", status_code=302)

    page = max(1, int(page or 1))
    per_page = max(1, min(int(per_page or 20), 100))

    query = db.query(Medicine)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(func.lower(Medicine.name).like(func.lower(like)))

    total = query.count()
    total_pages = max((total + per_page - 1) // per_page, 1)
    page = min(page, total_pages)
    offset = (page - 1) * per_page

    meds = (
        query.order_by(func.lower(Medicine.name).asc())
        .offset(offset)
        .limit(per_page)
        .all()
    )
    return templates.TemplateResponse(
        "pharmadesk/inventory.html",
        {
            "request": request,
            "title": "Inventory",
            "meds": meds,
            "q": q,
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total": total,
            "offset": offset,  # use {{ offset + loop.index }} for clean serial numbers
        },
    )

@router.post("/inventory/import")
async def inventory_import(request: Request, db: Session = Depends(get_db)):
    if not _cookie_ok(request):
        return JSONResponse({"detail": "Unauthorized"}, status_code=401)

    form = await request.form()
    file: UploadFile = form.get("file")  # type: ignore
    confirm_flag = (form.get("confirm") or "").lower() == "yes"

    replace_raw = (form.get("replace_all") or form.get("mode") or "").strip().lower()
    replace_all = replace_raw in ("yes", "true", "1", "replace", "all")

    quick = (form.get("quick") or "").strip().lower() in ("yes", "true", "1")

    if not file or not file.filename.lower().endswith(".csv"):
        return JSONResponse({"detail": "Please upload a CSV file."}, status_code=400)

    content = await file.read()
    text_data = content.decode("utf-8-sig", errors="ignore")
    rows = list(csv.DictReader(io.StringIO(text_data)))
    parsed = [_row_to_payload(r) for r in rows if any((v or "").strip() for v in r.values())]

    if not confirm_flag and not quick:
        return {
            "status": "confirm",
            "message": f"Parsed {len(parsed)} rows from {file.filename}. "
                       f"This will {'SYNC to CSV (remove missing)' if replace_all else 'upsert by Name'}.",
            "total": len(parsed),
            "replace_all": replace_all,
        }

    # Perform the import now
    try:
        summary = _apply_import_sync_to_csv(db, parsed, replace_all)
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "status": "success",
        "message": (
            f"{'Synchronized inventory to CSV. ' if replace_all else ''}"
            f"Created: {summary['created']}, Updated: {summary['updated']}, "
            f"Deleted: {summary.get('deleted', 0)}, Kept(historical): {summary.get('kept_due_to_history', 0)}, "
            f"Skipped: {summary['skipped']}"
        ),
        **summary,
    }

# Back-to-home helper (linked by templates)
@router.get("/home", name="pharmadesk_home")
def pharmadesk_home_redirect():
    return RedirectResponse(url="/pharmadesk/", status_code=302)

# Fix accidental GET to /import/preview (avoid 405)
@router.get("/import/preview", response_class=RedirectResponse)
def import_preview_redirect():
    return RedirectResponse(url="/pharmadesk/import", status_code=302)

# =============================================================================
#                      PRESCRIPTION SHARE + VIEW  (signed optional)
# =============================================================================
@router.get("/prescription/share/{dispense_id}")
def prescription_share_link(dispense_id: int, request: Request):
    signer = _get_signer()
    base_url = str(request.url_for("prescription_view", token="T")).replace("T", "{token}")

    if signer:
        token = signer.dumps({"dispense_id": dispense_id, "ts": int(_now().timestamp())})
        share_url = base_url.format(token=token)
    else:
        share_url = str(request.url_for("prescription_view", token=f"plain:{dispense_id}"))

    return JSONResponse({"url": share_url})

@router.get("/prescription/view/{token}", name="prescription_view", response_class=HTMLResponse)
def prescription_view(token: str, request: Request, db: Session = Depends(get_db)):
    signer = _get_signer()
    dispense_id: Optional[int] = None

    if signer:
        try:
            data = signer.loads(token)
            dispense_id = int(data.get("dispense_id"))
        except BadSignature:
            raise HTTPException(status_code=403, detail="Invalid or expired link.")
    else:
        if token.startswith("plain:"):
            try:
                dispense_id = int(token.split(":", 1)[1])
            except Exception:
                pass

    if not dispense_id:
        raise HTTPException(status_code=400, detail="Invalid link.")

    disp: Optional[Dispense] = db.query(Dispense).filter(Dispense.id == dispense_id).first()
    if not disp:
        raise HTTPException(status_code=404, detail="Prescription not found.")

    patient: Optional[Patient] = db.query(Patient).get(disp.patient_id) if disp.patient_id else None
    medicine: Optional[Medicine] = db.query(Medicine).get(disp.medicine_id) if disp.medicine_id else None

    return templates.TemplateResponse(
        "pharmadesk/prescription_view.html",
        {
            "request": request,
            "title": "Prescription",
            "dispense": disp,
            "patient": patient,
            "medicine": medicine,
            "generated_at": _now(),
        },
    )

# =============================================================================
#            QR ENTRY → PATIENT PAGE (loads latest doctor prescription)
# =============================================================================
@router.get("/prescription/{unique_id}", response_class=HTMLResponse)
def pharmadesk_prescription_from_qr(unique_id: str, request: Request, db: Session = Depends(get_db)):
    """
    Invoked when pharmacist scans the QR: /pharmadesk/prescription/{patient_uid}
    Priority:
      1) Load latest doctor prescription from shared CSV (app/static/data/prescriptions.csv)
      2) If not found, try DB Prescription model (if present)
      3) Else fall back to last Dispense for repeat
    """
    # 1) Patient
    patient = db.query(Patient).filter(Patient.patient_uid == unique_id).first()
    if not patient:
        return templates.TemplateResponse(
            "pharmadesk/prescription_view.html",
            {"request": request, "error": "❌ Invalid or unknown QR code."},
            status_code=404,
        )

    # 2) CSV – latest by Timestamp
    if PRESCRIPTIONS_CSV.exists():
        prescriptions = []
        try:
            with open(PRESCRIPTIONS_CSV, newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if (row.get("PatientUID") or "").strip() == unique_id:
                        try:
                            meds = json.loads(row.get("Medicines", "[]"))
                        except Exception:
                            meds = []
                        # Normalize to what template expects
                        row_norm = {
                            "Diagnosis": row.get("Diagnosis") or row.get("diagnosis") or "",
                            "Notes": row.get("Notes") or row.get("notes") or "",
                            "Medicines": meds,
                            "Doctor": row.get("Doctor") or row.get("doctor") or "",
                            "Timestamp": row.get("Timestamp") or "",
                        }
                        prescriptions.append(row_norm)
            prescriptions.sort(key=lambda x: x.get("Timestamp", ""), reverse=True)
            if prescriptions:
                return templates.TemplateResponse(
                    "pharmadesk/prescription_view.html",
                    {
                        "request": request,
                        "patient": patient,
                        "prescription": prescriptions[0],
                        "error": None,
                    },
                )
        except Exception as e:
            print(f"[PharmaDesk] WARN: reading CSV failed: {e}")

    # 3) DB Prescription (optional)
    try:
        from ..models.prescription import Prescription  # type: ignore
    except Exception:
        Prescription = None  # type: ignore

    prescription = None
    if Prescription is not None:
        prescription = (
            db.query(Prescription)
            .filter(Prescription.patient_id == patient.id)
            .order_by(Prescription.id.desc())
            .first()
        )
        # normalize JSON for template if present
        if prescription and getattr(prescription, "medicines_json", None) and not getattr(prescription, "Medicines", None):
            try:
                prescription.Medicines = json.loads(prescription.medicines_json)  # type: ignore[attr-defined]
            except Exception:
                prescription.Medicines = []  # type: ignore[attr-defined]

    # 4) Fall back to last dispense (so pharmacist can repeat)
    if not prescription:
        last_dispense = (
            db.query(Dispense)
            .filter(Dispense.patient_id == patient.id)
            .order_by(Dispense.id.desc())
            .first()
        )
        if last_dispense:
            class _PseudoRx:
                Diagnosis = "Previous dispense"
                Notes = getattr(last_dispense, "notes", "")
                Medicines = []
            pseudo = _PseudoRx()
            try:
                if getattr(last_dispense, "items_json", None):
                    pseudo.Medicines = json.loads(last_dispense.items_json)
            except Exception:
                pseudo.Medicines = []
            prescription = pseudo  # type: ignore[assignment]

    return templates.TemplateResponse(
        "pharmadesk/prescription_view.html",
        {
            "request": request,
            "patient": patient,
            "prescription": prescription,  # may be None → template shows yellow alert
            "error": None,
        },
    )

# =============================================================================
#                             DISPENSE + BILL FLOW
# =============================================================================
def _parse_items_json(raw: str) -> List[Dict[str, Any]]:
    try:
        data = json.loads(raw or "[]")
        if isinstance(data, list):
            # sanitize
            out: List[Dict[str, Any]] = []
            for it in data:
                if not isinstance(it, dict):
                    continue
                out.append(
                    {
                        "medicine_id": int(it.get("medicine_id") or 0),
                        "qty": int(it.get("qty") or 0),
                        "unit_price": float(it.get("unit_price") or 0.0),
                        "discount_pct": float(it.get("discount_pct") or 0.0),
                        "tax_pct": float(it.get("tax_pct") or 0.0),
                        "notes": (it.get("notes") or "").strip(),
                        # Optional passthroughs for invoice aesthetics:
                        "label": (it.get("label") or "").strip(),
                        "batch_no": (it.get("batch_no") or "").strip(),
                        "expiry": (it.get("expiry") or "").strip(),
                    }
                )
            return out
    except Exception:
        pass
    return []

def _money(n: float) -> float:
    return round(float(n or 0.0), 2)

@router.post("/dispense/{patient_uid}")
def post_dispense(
    patient_uid: str,
    items_json: str = Form("[]"),
    pharmacist: str = Form(""),
    payment_mode: str = Form("cash"),
    db: Session = Depends(get_db),
):
    """
    Receives items from the builder (pharmadesk/prescription_view.html)
    and creates a single Dispense with items_json (bill header record).
    Also decrements Medicine.stock_qty for each line.
    Redirects back to the same page with ?bill={dispense_id} for PDF download.
    """
    # Auth check optional (you already gate entry via login)
    # if not _cookie_ok(request): ...

    patient = db.query(Patient).filter(Patient.patient_uid == patient_uid).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    items = _parse_items_json(items_json)
    if not items:
        return RedirectResponse(
            url=f"/pharmadesk/prescription/{patient_uid}?err=empty",
            status_code=302,
        )

    # Validate stock and compute totals
    total_amount = 0.0
    line_errors: List[str] = []
    for ln in items:
        mid = int(ln["medicine_id"])
        qty = int(ln["qty"])
        unit = float(ln["unit_price"])
        disc = float(ln["discount_pct"])
        tax = float(ln["tax_pct"])

        med = db.query(Medicine).get(mid)
        if not med:
            line_errors.append(f"Unknown medicine id {mid}")
            continue

        stock = int(med.stock_qty or 0)
        if qty <= 0:
            line_errors.append(f"{med.name}: qty must be > 0")
            continue
        if qty > stock:
            line_errors.append(f"{med.name}: qty {qty} exceeds stock {stock}")

        subtotal = unit * qty
        after_disc = subtotal * (1 - (disc / 100.0))
        total = after_disc * (1 + (tax / 100.0))
        total_amount += total

    if line_errors:
        # Redirect with an error message (template can read request.query_params.err)
        msg = "; ".join(line_errors)[:300]
        return RedirectResponse(
            url=f"/pharmadesk/prescription/{patient_uid}?err={msg}",
            status_code=302,
        )

    # Decrement stock now
    for ln in items:
        mid = int(ln["medicine_id"])
        qty = int(ln["qty"])
        med = db.query(Medicine).get(mid)
        if med:
            current = int(med.stock_qty or 0)
            med.stock_qty = max(0, current - qty)

    # Create ONE master dispense with items_json (used for bill + history)
    disp = Dispense(
        patient_id=patient.id,
        medicine_id=None,                  # multi-line bill, not single medicine
        qty=None,
        unit_price=None,
        discount_pct=None,
        tax_pct=None,
        total_amount=_money(total_amount),
        pharmacist=(pharmacist or "pharmadesk").strip(),
        payment_mode=(payment_mode or "cash").strip().lower(),
        notes="",
        items_json=json.dumps(items),
    )
    db.add(disp)
    db.flush()  # get ID
    bill_id = int(disp.id)

    # Update patient status
    try:
        if getattr(patient, "status", None) != "dispensed":
            patient.status = "dispensed"
    except Exception:
        pass

    db.commit()

    return RedirectResponse(
        url=f"/pharmadesk/bill/preview/{bill_id}",
        status_code=302,
    )

@router.get("/bill/{dispense_id}")
def bill_download(dispense_id: int, db: Session = Depends(get_db)):
    """
    Downloadable bill (as PDF attachment).
    """
    disp: Optional[Dispense] = db.query(Dispense).filter(Dispense.id == dispense_id).first()
    if not disp:
        raise HTTPException(status_code=404, detail="Dispense not found.")

    patient: Optional[Patient] = db.query(Patient).get(disp.patient_id) if disp.patient_id else None
    medicine: Optional[Medicine] = db.query(Medicine).get(disp.medicine_id) if disp.medicine_id else None

    pdf_path: str = generate_bill_pdf(dispense=disp, patient=patient, medicine=medicine)
    with open(pdf_path, "rb") as fh:
        data = fh.read()
    filename = os.path.basename(pdf_path)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

@router.get("/dispense/{dispense_id}/bill.pdf")
def bill_pdf(dispense_id: int, db: Session = Depends(get_db)):
    """
    Inline bill (for browser preview).
    """
    disp: Optional[Dispense] = db.query(Dispense).filter(Dispense.id == dispense_id).first()
    if not disp:
        raise HTTPException(status_code=404, detail="Dispense not found.")

    patient: Optional[Patient] = db.query(Patient).get(disp.patient_id) if disp.patient_id else None
    medicine: Optional[Medicine] = db.query(Medicine).get(disp.medicine_id) if disp.medicine_id else None

    pdf_path: str = generate_bill_pdf(dispense=disp, patient=patient, medicine=medicine)
    with open(pdf_path, "rb") as fh:
        data = fh.read()
    filename = os.path.basename(pdf_path)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )

# =============================================================================
#                                   APIs
# =============================================================================
@router.get("/api/medicines")
def api_medicines(
    q: str = Query("", description="Query by name"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
):
    query = db.query(Medicine)
    if q:
        like = f"%{q.strip()}%"
        query = query.filter(func.lower(Medicine.name).like(func.lower(like)))

    results: List[Medicine] = (
        query.order_by(func.coalesce(Medicine.stock_qty, 0).desc(), func.lower(Medicine.name).asc())
        .limit(limit)
        .all()
    )

    items: List[Dict[str, Any]] = []
    for m in results:
        items.append(
            {
                "id": int(m.id),
                "label": m.label(),
                "stock_qty": int(m.stock_qty or 0),
                "mrp": float(m.mrp or 0),
                "tax_pct": float(m.tax_pct or 5.0),
            }
        )
    return items

@router.get("/api/assistant")
def api_assistant(
    q: str = Query("", description="e.g., 'low stock 3', 'top medicines this month', 'inventory value'"),
    db: Session = Depends(get_db),
):
    prompt = (q or "").strip().lower()

    # Low stock
    if any(w in prompt for w in ["low stock", "low", "below", "shortage", "stock alert", "reorder"]):
        threshold = 5
        for tok in prompt.replace("=", " ").replace("<", " ").replace(">", " ").split():
            try:
                num = int(tok)
                if 0 <= num <= 10000:
                    threshold = num
                    break
            except Exception:
                pass

        low_items: List[Tuple[str, int]] = (
            db.query(Medicine.name, func.coalesce(Medicine.stock_qty, 0))
            .filter(func.coalesce(Medicine.stock_qty, 0) <= threshold)
            .order_by(Medicine.stock_qty.asc(), func.lower(Medicine.name).asc())
            .limit(25)
            .all()
        )
        lines = [f"{name} — {qty} left" for name, qty in low_items]
        return {"reply": f"Low stock (≤ {threshold}) items:", "items": lines}

    # Top medicines this month
    if any(w in prompt for w in ["top", "popular", "this month", "top medicines"]):
        today = date.today()
        month_start = date(today.year, today.month, 1)
        next_month_start = date(
            today.year + (1 if today.month == 12 else 0),
            1 if today.month == 12 else today.month + 1,
            1,
        )

        top_items: List[Tuple[str, int]] = (
            db.query(Medicine.name, func.coalesce(func.sum(Dispense.qty), 0))
            .join(Medicine, Medicine.id == Dispense.medicine_id, isouter=True)
            .filter(Dispense.created_at >= month_start)
            .filter(Dispense.created_at < next_month_start)
            .group_by(Medicine.name)
            .order_by(func.coalesce(func.sum(Dispense.qty), 0).desc(), func.lower(Medicine.name).asc())
            .limit(10)
            .all()
        )
        lines = [f"{name} — {qty} dispensed" for name, qty in top_items]
        return {"reply": "Top medicines this month:", "items": lines}

    # Inventory value
    if "inventory value" in prompt or ("inventory" in prompt and "value" in prompt):
        total_value = (
            db.query(
                func.coalesce(
                    func.sum(func.coalesce(Medicine.stock_qty, 0) * func.coalesce(Medicine.mrp, 0.0)),
                    0.0,
                )
            ).scalar()
            or 0.0
        )
        return {"reply": f"Estimated inventory value: ₹{float(total_value):,.2f}", "items": []}

    return {
        "reply": "Try: ‘low stock’, ‘top medicines this month’, or ‘inventory value’. You can also say ‘low stock 3’ to set a threshold.",
        "items": [],
    }

@router.get("/api/overview")
def api_overview(db: Session = Depends(get_db)):
    total_patients = db.query(func.count(Patient.id)).scalar() or 0
    total_medicines = db.query(func.count(Medicine.id)).scalar() or 0
    total_dispenses = db.query(func.count(Dispense.id)).scalar() or 0

    top_stock = (
        db.query(Medicine.name, func.coalesce(Medicine.stock_qty, 0).label("qty"))
        .order_by(desc("qty"), func.lower(Medicine.name).asc())
        .limit(5)
        .all()
    )
    top_stock_list = [{"name": n, "qty": int(q or 0)} for n, q in top_stock]

    top_dispensed = (
        db.query(Medicine.name, func.coalesce(func.sum(Dispense.qty), 0).label("qty"))
        .join(Medicine, Medicine.id == Dispense.medicine_id, isouter=True)
        .group_by(Medicine.name)
        .order_by(desc("qty"), func.lower(Medicine.name).asc())
        .limit(5)
        .all()
    )
    top_dispensed_list = [{"name": n, "qty": int(q or 0)} for n, q in top_dispensed]

    return {
        "kpis": {
            "patients": int(total_patients),
            "medicines": int(total_medicines),
            "dispenses": int(total_dispenses),
        },
        "top_stock": top_stock_list,
        "top_dispensed": top_dispensed_list,
    }
# =====================  INVOICE PREVIEW EXTENSION  =====================
from fastapi import Request
from fastapi.responses import HTMLResponse
import json, os
from typing import Optional, List, Dict, Any
from ..models.dispense import Dispense
from ..models.medicine import Medicine
from ..models.patient import Patient
from ..utils.pdf_utils import generate_bill_pdf
from ..core.db import get_db

REPORTS_DIR = os.getenv("REPORTS_DIR", "/tmp/reports")
os.makedirs(REPORTS_DIR, exist_ok=True)


@router.get("/bill/preview/{dispense_id}", response_class=HTMLResponse)
def bill_preview(dispense_id: int, request: Request, db: Session = Depends(get_db)):
    """
    Production-grade invoice preview page.
    - Silently generates/stores PDF (record-keeping)
    - Renders a clean, printable HTML preview
    - No auto-download
    """
    disp: Optional[Dispense] = db.query(Dispense).filter(Dispense.id == dispense_id).first()
    if not disp:
        raise HTTPException(status_code=404, detail="Dispense not found.")

    patient: Optional[Patient] = db.query(Patient).get(disp.patient_id) if disp.patient_id else None
    medicine: Optional[Medicine] = db.query(Medicine).get(disp.medicine_id) if disp.medicine_id else None

    # Load items from transient attr or JSON file
    items: List[Dict[str, Any]] = []
    raw_json = getattr(disp, "items_json", None)
    json_path = os.path.join(REPORTS_DIR, f"invoice_{dispense_id}.json")
    if not raw_json and os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as jf:
            raw_json = jf.read()
    try:
        if raw_json:
            data = json.loads(raw_json)
            if isinstance(data, list):
                items = data
    except Exception as _e:
        print("[PharmaDesk] WARN: failed to load items:", _e)

    # Generate PDF silently for archive
    try:
        generate_bill_pdf(dispense=disp, patient=patient, medicine=medicine)
    except Exception as _e:
        print("[PharmaDesk] WARN: PDF generation during preview failed:", _e)

    # Compute totals
    total = round(float(disp.total_amount or 0.0), 2)
    tax_sum = 0.0
    try:
        for it in items:
            qty = int(it.get("qty") or 0)
            unit = float(it.get("unit_price") or 0.0)
            disc = float(it.get("discount_pct") or 0.0)
            tax  = float(it.get("tax_pct") or 0.0)
            subtotal = unit * qty
            after_disc = subtotal * (1 - (disc/100))
            tax_sum += after_disc * (tax/100)
    except Exception:
        tax_sum = 0.0

    return templates.TemplateResponse(
        "pharmadesk/bill_preview.html",
        {
            "request": request,
            "title": "Invoice Preview",
            "dispense": disp,
            "patient": patient,
            "items": items,
            "total": total,
            "tax_sum": round(tax_sum, 2),
        },
    )