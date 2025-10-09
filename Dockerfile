# -------- Base image --------
    FROM python:3.11-slim AS base

    # Prevent Python cache & buffering
    ENV PYTHONDONTWRITEBYTECODE=1
    ENV PYTHONUNBUFFERED=1
    
    WORKDIR /app
    
    # Install system deps for tesseract + build essentials
    RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        libtesseract-dev \
        libleptonica-dev \
        build-essential \
        libpq-dev \
     && rm -rf /var/lib/apt/lists/*
    
    # -------- Install Python deps --------
    COPY backend/requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt
    
    # -------- Copy app code --------
    COPY backend/app ./app
    
    # Create dirs for static/data and set perms
    RUN mkdir -p /app/app/static/qr /app/app/static/data && chmod -R 777 /app/app/static
    
    EXPOSE 8000
    
    # -------- Run FastAPI --------
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]