# Small, reliable image
FROM python:3.11-slim

WORKDIR /app

# System deps for Pillow (pdfplumber) are minimal; add locales/ghostscript if later needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App
COPY . /app

# Ensure uploads dir exists and set USE_LAYOUT_PAIRING by default
ENV USE_LAYOUT_PAIRING=true
RUN mkdir -p /data/uploads/ocr

# Railway sets $PORT; default 5000
EXPOSE 5000

# Use the same entrypoint as Procfile (Uvicorn worker via Gunicorn)
CMD sh -c 'PORT=${PORT:-5000}; gunicorn -k uvicorn.workers.UvicornWorker -w 4 -b 0.0.0.0:$PORT app.main:app'
