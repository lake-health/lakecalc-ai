# Lakecalc AI

A FastAPI-based backend for parsing PDFs, running OCR on images, and extracting intraocular lens (IOL) data.  
Built with Python, deployed on [Railway](https://railway.app), and powered by OpenAI + Google OCR.

---

## Features
- 📄 Upload and parse PDF or image files
- 🔎 OCR fallback for scanned documents
- 📊 Extract structured IOL data from documents
- ⚡ FastAPI with auto-generated API docs at `/docs`
- 🚀 Production-ready deployment on Railway using Gunicorn + Uvicorn workers

---

## Getting Started

### 1. Clone and install
```bash
git clone https://github.com/lake-health/lakecalc-ai.git
cd lakecalc-ai
pip install -r requirements.txt
