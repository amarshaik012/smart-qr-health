from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings
import os

SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

# ✅ Detect database type
if SQLALCHEMY_DATABASE_URL.startswith("sqlite"):
    # Local dev fallback (auto-create folder)
    db_path = SQLALCHEMY_DATABASE_URL.replace("sqlite:///", "")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    print(f"[DB CONFIG] Using SQLite → {db_path}")
else:
    print(f"[DB CONFIG] Using Postgres → {SQLALCHEMY_DATABASE_URL}")

# ✅ Engine setup
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False}
    if "sqlite" in SQLALCHEMY_DATABASE_URL else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def db_healthcheck():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as e:
        return False, str(e)