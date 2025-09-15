# LakeCalc.ai - IOL Calculator with OCR

A comprehensive Intraocular Lens (IOL) calculator with advanced OCR capabilities for processing medical documents.

## Features

- **Hybrid OCR System**: Combines Tesseract OCR with Google Cloud Vision API
- **IOL Calculations**: Comprehensive formulas for lens power calculations
- **PDF Processing**: Extract data from medical documents and reports
- **React Frontend**: Modern, responsive user interface
- **Flask Backend**: Robust API with OCR processing

## Deployment

This application is configured for deployment on Railway.app with automatic builds.

### Environment Variables Required

- `GOOGLE_APPLICATION_CREDENTIALS_JSON`: Google Cloud Vision API credentials (JSON format)

### Tech Stack

- **Backend**: Python 3.11, Flask, Tesseract OCR, Google Cloud Vision
- **Frontend**: React, TypeScript, Vite
- **Deployment**: Railway.app with Nixpacks

## Local Development

1. Install dependencies: `pip install -r requirements.txt`
2. Set up Google Cloud credentials
3. Run: `python app.py`

## Medical Disclaimer

This tool is for educational and research purposes only. Always consult with qualified medical professionals for clinical decisions.

