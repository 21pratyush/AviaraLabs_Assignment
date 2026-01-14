# Stage 1: Builder
FROM python:3.11-slim AS builder

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    ca-certificates \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy only requirements to leverage Docker caching
COPY requirements.txt .

# Create a standard venv and install dependencies
RUN python3 -m venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

RUN pip install --upgrade pip setuptools wheel
# Use CPU-only torch to keep the image size smaller for the assignment
RUN pip install --no-cache-dir -r requirements.txt \
    --extra-index-url https://download.pytorch.org/whl/cpu

# PRE-DOWNLOAD MODELS: This saves time during the first API request
RUN python -c "from docling.document_converter import DocumentConverter; DocumentConverter()"

# Stage 2: Runtime
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# IMPORTANT: Install runtime-necessary system tools
# libgl1 and libglib2.0-0 are required by OpenCV (used by Docling)
RUN apt-get update && apt-get install -y --no-install-recommends \
    poppler-utils \
    libpq-dev \
    libgl1 \
    libglib2.0-0 \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the pre-built virtual environment from builder
COPY --from=builder /app/.venv /app/.venv

# Copy your application code
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]