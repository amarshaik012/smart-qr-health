import os
from sqlalchemy import create_engine, text

# ✅ Absolute path to your SQLite file
BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "app.db")
DB_URL = f"sqlite:///{DB_PATH}"

# ✅ Create a direct engine (bypasses FastAPI's relative one)
engine = create_engine(DB_URL, connect_args={"check_same_thread": False})

print(f"📍 Using database at: {DB_PATH}")

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE patients ADD COLUMN status VARCHAR(20) DEFAULT 'waiting';"))
        conn.commit()
        print("✅ Column 'status' added successfully!")
    except Exception as e:
        print("⚠️ Column may already exist or error occurred:", e)