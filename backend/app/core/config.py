import os
from typing import ClassVar
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application configuration."""

    # project name
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "Smart QR Health API")

    # static base dir (not a model field)
    BASE_DIR: ClassVar[str] = "/app/app"
    DB_PATH: ClassVar[str] = os.path.join(BASE_DIR, "app.db")

    # sqlite database url for Render
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DB_PATH}")

    # base url for the deployed app
    PUBLIC_BASE_URL: str = os.getenv(
        "PUBLIC_BASE_URL",
        "https://smart-qr-health.onrender.com",
    )


settings = Settings()