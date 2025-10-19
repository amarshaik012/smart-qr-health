from fastapi.templating import Jinja2Templates
from datetime import datetime
import os

# -----------------------------------------------------
# 📁 Template Directory Setup
# -----------------------------------------------------
# Allow override via env var; defaults to app/templates
TEMPLATES_DIR = os.getenv("TEMPLATES_DIR", "app/templates")

# Initialize Jinja2 template engine
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Expose globals to Jinja templates
templates.env.globals.update({
    "datetime": datetime,
    "APP_NAME": "SmartQR Health",
    "PHARMADESK_BRAND": "PharmaDesk",
})