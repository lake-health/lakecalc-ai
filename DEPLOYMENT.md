# LakeCalc.ai Deployment Guide

## GitHub → Railway Deployment

### Step 1: Create GitHub Repository

1. Go to [GitHub.com](https://github.com) and create a new repository
2. Name it `lakecalc-ai` or similar
3. Make it public or private (your choice)
4. Don't initialize with README (we have one)

### Step 2: Upload Files

1. Download all files from this package
2. Upload them to your GitHub repository
3. Commit the changes

### Step 3: Connect to Railway

1. Go to [Railway.app](https://railway.app)
2. Click "New Project"
3. Select "Deploy from GitHub repo"
4. Choose your `lakecalc-ai` repository
5. Railway will automatically detect the configuration

### Step 4: Set Environment Variables

In Railway dashboard:
1. Go to your project → Variables
2. Add: `GOOGLE_APPLICATION_CREDENTIALS_JSON`
3. Value: Your Google Cloud service account JSON (as text)

### Step 5: Deploy

Railway will automatically:
- Install Python dependencies
- Install system packages (tesseract, poppler-utils)
- Build and deploy your application
- Provide a public URL

## Configuration Files

- `nixpacks.toml`: Build configuration
- `requirements.txt`: Python dependencies
- `Aptfile`: System packages
- `Procfile`: Start command
- `runtime.txt`: Python version

## Troubleshooting

If deployment fails:
1. Check build logs in Railway dashboard
2. Verify environment variables are set
3. Ensure all files are uploaded correctly

## Domain Setup

Once deployed, you can:
1. Use the Railway-provided URL
2. Connect your custom domain (lakecalc.ai)
3. Set up SSL (automatic with Railway)

