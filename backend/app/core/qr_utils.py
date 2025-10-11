import qrcode
import re
import os
import socket
from io import BytesIO
from pathlib import Path
import csv
from fastapi.responses import StreamingResponse

def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"

QR_DIR = Path("/app/app/static/qr")
QR_DIR.mkdir(parents=True, exist_ok=True)

CSV_PATH = Path("/app/app/static/data/patients.csv")
CSV_PATH.parent.mkdir(parents=True, exist_ok=True)

BASE_URL = os.getenv("BASE_URL") or f"http://{get_local_ip()}:8000"
print(f"[QR CONFIG] Final BASE_URL → {BASE_URL}")

def normalize_height(height: str | None) -> str:
    if not height:
        return ""
    height = height.strip().lower()
    height = re.sub(r"(ft|feet)+", "ft", height, flags=re.I)
    height = re.sub(r"\s+", " ", height).strip()
    if not re.search(r"(ft|feet)$", height):
        height += " ft"
    return height

def generate_qr_image(uid: str, qr_path: str = None):
    qr_content = f"{BASE_URL}/p/{uid}"
    img = qrcode.make(qr_content)

    if os.getenv("RENDER") or not qr_path:
        buf = BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        print(f"[QR GENERATED STREAM] {qr_content}")
        return StreamingResponse(buf, media_type="image/png")

    img.save(qr_path)
    print(f"[QR GENERATED] {qr_content} → saved at {qr_path}")
    return qr_path

def append_to_csv(data: dict):
    file_exists = CSV_PATH.exists()
    fieldnames = [
        "patient_uid", "name", "phone", "email", "gender",
        "dob", "weight", "height", "qr_url", "timestamp"
    ]

    if "height" in data:
        data["height"] = normalize_height(data["height"])

    if "qr_filename" in data and "qr_url" not in data:
        data["qr_url"] = f"/qr/{data['qr_filename'].replace('.png', '')}"

    valid_rows = []
    if file_exists:
        try:
            with open(CSV_PATH, newline="") as f:
                reader = csv.DictReader(f)
                if reader.fieldnames is None or any(h not in fieldnames for h in reader.fieldnames):
                    raise ValueError("Invalid header detected")
                valid_rows = list(reader)
        except Exception as e:
            print(f"[WARN] Corrupted CSV detected ({e}), recreating patients.csv")
            valid_rows = []

    with open(CSV_PATH, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in valid_rows:
            clean_row = {k: row.get(k, "") for k in fieldnames}
            writer.writerow(clean_row)
        writer.writerow({k: data.get(k, "") for k in fieldnames})
    print(f"[CSV UPDATED] Added patient → {data.get('name', '')}")