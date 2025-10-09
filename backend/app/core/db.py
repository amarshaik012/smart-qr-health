# backend/app/core/db.py
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings

# ------------------------------------
# ⚙️ Database Configuration
# ------------------------------------
SQLALCHEMY_DATABASE_URL = settings.DATABASE_URL

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in SQLALCHEMY_DATABASE_URL else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ------------------------------------
# 🧠 Database Health Check
# ------------------------------------
def db_healthcheck():
    """Simple DB healthcheck for /health/db route."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as e:
        return False, str(e)