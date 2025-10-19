import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # 🧠 App Info
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Smart QR Health Platform")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # 🌍 Base URLs
    BASE_URL: str = os.getenv("BASE_URL", "http://localhost:8000")
    PUBLIC_BASE_URL: str = os.getenv("PUBLIC_BASE_URL", "http://localhost:8000")

    # 🗄️ Database (PostgreSQL or fallback SQLite)
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "strongpass")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "app")

    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"postgresql+psycopg2://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    )

    # 📦 File storage
    QR_SAVE_DIR: str = os.getenv("QR_SAVE_DIR", "/tmp/qr")
    DATA_SAVE_DIR: str = os.getenv("DATA_SAVE_DIR", "/tmp/data")
    REPORTS_DIR: str = os.getenv("REPORTS_DIR", "/tmp/reports")

    # 🔒 Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "changeme")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 60))

    # 🐳 Docker flag
    RUNNING_IN_DOCKER: bool = os.getenv("RUNNING_IN_DOCKER", "false").lower() == "true"

    # 🕓 Timezone / Logs
    TIMEZONE: str = os.getenv("TIMEZONE", "Asia/Kolkata")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

settings = Settings()
print(f"[CONFIG] Loaded DB: {settings.DATABASE_URL}")