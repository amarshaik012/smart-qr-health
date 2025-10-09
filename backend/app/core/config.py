import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Smart QR Health API")

    # ✅ Use SQLite by default (works both locally & on Render)
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    DB_PATH = os.path.join(BASE_DIR, "static", "data", "patients.db")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{DB_PATH}"
    )

    # ✅ Public URL for QR codes
    PUBLIC_BASE_URL: str = os.getenv(
        "PUBLIC_BASE_URL", "https://smart-qr-health.onrender.com"
    )


# Initialize settings
settings = Settings()