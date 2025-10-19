# =========================
# 🐍 Stage 1: Build Image
# =========================
FROM python:3.11-slim

# Prevent Python from writing .pyc files & enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Working directory inside the container
WORKDIR /app

# Install dependencies for bcrypt and psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# ✅ Copy requirements file directly (no backend/ prefix)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ✅ Copy app source (no backend/ prefix)
COPY app ./app

# Prepare static directories (for QR and prescription data)
RUN mkdir -p /app/app/static/qr /app/app/static/data && \
    chmod -R 777 /app/app/static

# Environment variables
ENV STATIC_DIR=/app/app/static
ENV PYTHONPATH=/app

# Expose FastAPI port
EXPOSE 8000

# Default command to run FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]