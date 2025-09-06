# LakeCalc.ai Railway Deployment Instructions

## 🚂 Step-by-Step Railway Deployment

### 1. Create New Railway Service
- Go to your Railway dashboard
- Click "New Project" or "+" button
- Select "Empty Service" (NOT GitHub repo)
- Name it: `lakecalc-production`

### 2. Upload Code
- In the new service, look for "Deploy from local files" or file upload option
- Upload the `lakecalc-railway-deployment.zip` file
- Railway will automatically extract and deploy

### 3. Add Environment Variables
Go to your service → Variables → Add these:

```
GOOGLE_CLOUD_CREDENTIALS_JSON=[paste your Google Cloud JSON here]
OCR_FALLBACK_ONLY=false
FLASK_ENV=production
PORT=5000
```

### 4. Configure Domain
- Go to service Settings → Domains
- Add custom domain: `lakecalc.ai`
- Railway will provide DNS instructions

### 5. Test Deployment
- Visit your Railway service URL
- Test `/api/health` endpoint
- Should show: `{"status": "healthy", "ocr_enabled": true}`

## 📁 Package Contents
- `app.py` - Main Flask application
- `requirements.txt` - Python dependencies (Railway compatible)
- `Procfile` - Railway startup command
- `runtime.txt` - Python version specification
- `nixpacks.toml` - Railway build configuration
- `Aptfile` - System dependencies (tesseract, etc.)
- `src/` - OCR parsers and IOL calculators
- `static/` - Frontend files (React build)

## 🔧 Key Features
- ✅ Hybrid OCR (local tesseract + Google Cloud Vision)
- ✅ Medical device PDF processing (Pentacam, IOL Master, etc.)
- ✅ Professional IOL calculations
- ✅ Railway-optimized dependencies
- ✅ Production-ready configuration

## 🆘 Troubleshooting
If deployment fails:
1. Check build logs for errors
2. Verify environment variables are set
3. Ensure Google Cloud credentials are valid JSON
4. Contact support with specific error messages

## 🎯 Expected Result
- Working LakeCalc.ai at your Railway URL
- OCR functionality for medical device PDFs
- Ready to point lakecalc.ai domain

