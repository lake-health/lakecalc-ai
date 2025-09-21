## LLM Model Change (September 2025)

The default LLM model for field extraction is now `gpt-4o-mini` (see `app/utils.py`).

- The OpenAI API call uses `max_completion_tokens` instead of `max_tokens` for compatibility with newer models.
- Set your `OPENAI_API_KEY` as an environment variable locally and on Railway.
- You can override the model by passing a different model name to the utility function if needed.

**Note:** Using GPT-4o or GPT-5 models may have different cost and latency profiles compared to previous models. Monitor your usage accordingly.
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
