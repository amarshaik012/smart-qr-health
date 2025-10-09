# =========================
# 🐍 Stage 1: Build Image
# =========================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Working directory inside container
WORKDIR /app

# Install dependencies
COPY backend/requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy app code from backend/app
COPY backend/app ./app

# Expose FastAPI port
EXPOSE 8000

ENV STATIC_DIR=/app/app/static
ENV PYTHONPATH=/app

# Prepare static directories
RUN mkdir -p /app/app/static/qr /app/app/static/data
RUN chmod -R 777 /app/app/static

# Run the FastAPI app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]