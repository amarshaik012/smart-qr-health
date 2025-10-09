# =========================
# 🐍 Stage 1: Build Image
# =========================
FROM python:3.11-slim

# Prevent Python from writing pyc files and buffering output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Working directory inside container
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy application code
COPY ./app ./app

# Expose FastAPI default port
EXPOSE 8000

# Set environment variables
ENV STATIC_DIR=/app/app/static
ENV PYTHONPATH=/app

# Create necessary directories inside container
RUN mkdir -p /app/app/static/qr /app/app/static/data

# Grant permissions for static and data folders
RUN chmod -R 777 /app/app/static

# =========================
# 🧠 Command to run FastAPI
# =========================
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]