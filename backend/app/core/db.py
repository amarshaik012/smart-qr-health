from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings


# ✅ Use psycopg2 driver for PostgreSQL
DATABASE_URL = settings.DATABASE_URL.replace("psycopg", "psycopg2")

# ✅ SQLAlchemy engine with safe defaults
engine = create_engine(
    DATABASE_URL,
    echo=False,          # set True only for debugging SQL
    pool_pre_ping=True,  # auto-checks connections automatically
)

# ✅ Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ✅ Declarative base class
Base = declarative_base()


# ✅ Dependency for FastAPI routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ✅ Healthcheck function for database connectivity
def db_healthcheck():
    """Quick DB connection check."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, None
    except Exception as e:
        return False, str(e)