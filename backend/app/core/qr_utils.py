import qrcode
import re
import os
import socket
from io import BytesIO
from pathlib import Path
import csv
from fastapi.responses import StreamingResponse

# ===================================================
# 🧩 Detect Local IP or Use BASE_URL from Environment
# ===================================================
def get_local_ip() -> str:
    """Return your local LAN IP (e.g., 192.168.x.x) for QR generation."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


# ===================================================
# 📁 Directories for Storage (Local Only)
# ===================================================
# Relative paths work both locally and on Render
QR_DIR = Path("backend/app/static/qr")
QR_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH = Path("backend/app/static/data/patients.csv")
CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

# ✅ Use environment BASE_URL first, else fallback to local IP
BASE_URL = os.getenv("BASE_URL") or f"http://{get_local_ip()}:8000"
print(f"[QR CONFIG] Final BASE_URL → {BASE_URL}")


# ===================================================
# ⚙️ Height Normalization
# ===================================================
def normalize_height(height: str | None) -> str:
    """Standardize height input and fix repeated ft text."""
    if not height:
        return ""
    height = height.strip().lower()
    height = re.sub(r"(ft|feet)+", "ft", height, flags=re.I)
    height = re.sub(r"\s+", " ", height).strip()
    if not re.search(r"(ft|feet)$", height):
        height += " ft"
    return height


# ===================================================
# 🧾 QR Generator (Smart Mode)
# ===================================================
def generate_qr_image(uid: str, qr_path: str = None):
    """
    Generate a scannable QR Code with BASE_URL/p/{uid}.
    If qr_path is provided → save locally (for dev)
    Otherwise → return StreamingResponse (for Render quick demo mode)
    """
    qr_content = f"{BASE_URL}/p/{uid}"
    img = qrcode.make(qr_content)

    # Render quick-demo mode: return in-memory stream instead of file
    if os.getenv("RENDER") or not qr_path:
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        print(f"[QR GENERATED STREAM] {qr_content}")
        return StreamingResponse(buf, media_type="image/png")

    # Local dev mode: save PNG file
    img.save(qr_path)
    print(f"[QR GENERATED] {qr_content} → saved at {qr_path}")
    return qr_path


# ===================================================
# 📊 CSV Writer (Auto-Repair & Compatibility)
# ===================================================
def append_to_csv(data: dict):
    """
    Append or auto-update patients.csv.
    Auto-repairs header corruption and ensures correct schema every time.
    """
    file_exists = CSV_PATH.exists()
    fieldnames = [
        "patient_uid", "name", "phone", "email", "gender",
        "dob", "weight", "height", "qr_url", "timestamp"
    ]

    # Normalize height
    if "height" in data:
        data["height"] = normalize_height(data["height"])

    # Convert qr_filename → qr_url if needed
    if "qr_filename" in data and "qr_url" not in data:
        data["qr_url"] = f"/qr/{data['qr_filename'].replace('.png', '')}"

    # ✅ Auto-repair bad CSV header
    valid_rows = []
    if file_exists:
        try:
            with open(CSV_PATH, newline="") as f:
                reader = csv.DictReader(f)
                if (
                    reader.fieldnames is None
                    or any(h not in fieldnames for h in reader.fieldnames)
                    or len(reader.fieldnames) != len(fieldnames)
                ):
                    raise ValueError("Invalid header detected")
                valid_rows = list(reader)
        except Exception as e:
            print(f"[WARN] Corrupted CSV detected ({e}), recreating patients.csv")
            valid_rows = []

    # ✅ Rewrite clean CSV
    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        # Write valid existing rows
        for row in valid_rows:
            clean_row = {k: row.get(k, "") for k in fieldnames}
            writer.writerow(clean_row)

        # Append the new patient
        writer.writerow({k: data.get(k, "") for k in fieldnames})

    print(f"[CSV UPDATED] Added patient → {data.get('name', '')}")