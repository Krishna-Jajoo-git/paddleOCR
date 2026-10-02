FROM python:3.11-slim

# System dependencies for OpenCV, PaddlePaddle, and PostgreSQL client
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgl1 \
    libglib2.0-0 \
    libgomp1 \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Upgrade pip and install wheel
RUN pip install --no-cache-dir --upgrade pip setuptools wheel

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY final_prescription_ocr_service_windows.py ./service.py
COPY starter_medicines.csv* ./

# Directories for persistent data and model weights cache
RUN mkdir -p /app/data /app/preprocessed /root/.paddlex

ENV PORT=8000
ENV HOST=0.0.0.0
ENV DOCKER=1
ENV DATABASE_URL="sqlite:////app/data/rx_local.db"
ENV PADDLEOCR_DEVICE="cpu"

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=45s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Production ASGI server using uvicorn
CMD ["python", "service.py"]
