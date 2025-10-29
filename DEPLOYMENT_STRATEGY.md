# 🚀 LakeCalc AI Deployment Strategy

**Date:** October 29, 2025  
**Status:** Ready for Railway + RunPod Integration

---

## 🎯 **ARCHITECTURE OVERVIEW**

```
┌─────────────────────────────────────────────────────────┐
│                    PRODUCTION FLOW                       │
└─────────────────────────────────────────────────────────┘

Local Dev (Mac)
    ↓
GitHub (lake-health/lakecalc-ai)
    ↓
Railway Staging (testing) ──→ RunPod GPU (shared)
    ↓                          (Ollama + biometry-llama)
Railway Production (live)  ──→ Same RunPod GPU
    ↓
lakecalc.ai (custom domain)
```

### **Key Principles**
- **Single Source of Truth:** GitHub main branch
- **Shared GPU:** RunPod instance serves both staging and production
- **Environment Variables:** Control behavior per environment
- **Immutable Deployments:** Railway auto-deploys from GitHub
- **Health Checks:** Continuous monitoring of all services

---

## 📊 **CURRENT STATE**

### ✅ **What's Working**
1. **Backend API (FastAPI)**
   - IOL calculations (SRK/T, Haigis, Cooke K6) ✓
   - Biometry parser (`/parse/parse`) ✓
   - Toric calculator ✓
   - IOL database ✓
   - Health checks (`/health`, `/parse/health`) ✓

2. **RunPod GPU**
   - URL: `https://88cj1hbr8cc66z-11434.proxy.runpod.net`
   - Models: `biometry-llama:latest`, `llama3.1:8b`, `llava:latest`
   - Status: Running ✓
   - Persistent storage: `/workspace/.ollama` ✓

3. **GitHub Repository**
   - URL: `https://github.com/lake-health/lakecalc-ai`
   - Branch: `main` (up to date) ✓
   - Dockerfile + Railway config ready ✓

### ⚠️ **What's Missing**
- Railway staging environment not deployed
- Railway production environment not set up
- Environment variables not configured
- Custom domain (`lakecalc.ai`) not pointed to Railway

---

## 🔧 **ENVIRONMENT CONFIGURATION**

### **Environment Variables (Railway)**

#### **Staging Environment**
```bash
RUNPOD_OLLAMA_URL=https://88cj1hbr8cc66z-11434.proxy.runpod.net
OLLAMA_TIMEOUT=60
PYTHONUNBUFFERED=1
PORT=8000  # Railway sets this automatically
ENVIRONMENT=staging
```

#### **Production Environment**
```bash
RUNPOD_OLLAMA_URL=https://88cj1hbr8cc66z-11434.proxy.runpod.net
OLLAMA_TIMEOUT=60
PYTHONUNBUFFERED=1
PORT=8000  # Railway sets this automatically
ENVIRONMENT=production
```

### **Local Development**
```bash
# No RUNPOD_OLLAMA_URL - defaults to http://localhost:11434
# Requires local Ollama installation for testing
```

---

## 📝 **DEPLOYMENT STEPS**

### **Step 1: Commit Environment-Aware Changes**
```bash
cd "/Users/jonathanlake/Documents/*Projects/lakecalc-ai"
git add app/services/biometry_parser.py DEPLOYMENT_STRATEGY.md
git commit -m "feat: make BiometryParser environment-aware for Railway deployment"
git push origin main
```

### **Step 2: Create Railway Staging Environment**
1. **Railway Dashboard** → New Project
2. **Deploy from GitHub** → Select `lake-health/lakecalc-ai`
3. **Project Name:** `lakecalc-ai-staging`
4. **Build Settings:**
   - Builder: Dockerfile (auto-detected)
   - Root Directory: `/` (default)
5. **Deploy Settings:**
   - Health Check Path: `/health`
   - Health Check Timeout: `100`
   - Restart Policy: `ON_FAILURE`
   - Auto Deploy: `main` branch
6. **Environment Variables:** (add from table above)
7. **Deploy** and wait for green status

### **Step 3: Verify Staging Deployment**
```bash
# Get staging domain from Railway UI
STAGING_URL="<staging-domain>.up.railway.app"

# Health check
curl -s https://$STAGING_URL/health

# Parser health check
curl -s https://$STAGING_URL/parse/health

# Test biometry parsing
curl -s -X POST \
  -F "file=@test_files/2935194_franciosi_carina_2024.10.01 18_00_37_IOL.pdf" \
  https://$STAGING_URL/parse/parse
```

### **Step 4: Create Railway Production Environment**
1. **Railway Dashboard** → Add New Service to existing project
   - OR create separate `lakecalc-ai-production` project
2. **Deploy from GitHub** → Same repo `lake-health/lakecalc-ai`
3. **Same settings as staging** (except environment variable: `ENVIRONMENT=production`)
4. **Add Custom Domain:** `api.lakecalc.ai` (or `lakecalc.ai`)
5. **DNS Configuration:**
   - Add CNAME record: `lakecalc.ai` → `<production-domain>.up.railway.app`
   - Wait for DNS propagation (5-60 minutes)

### **Step 5: Test Production Deployment**
```bash
# Health check
curl -s https://lakecalc.ai/health

# Parser test
curl -s -X POST \
  -F "file=@test_files/2935194_franciosi_carina_2024.10.01 18_00_37_IOL.pdf" \
  https://lakecalc.ai/parse/parse
```

---

## 🧪 **TESTING STRATEGY**

### **Staging Tests (Required Before Production)**
1. **API Health:** `/health` returns 200
2. **Parser Health:** `/parse/health` returns 200
3. **Biometry Parsing:** Test with Carina and Geraldo PDFs
4. **IOL Calculations:** Test with sample biometry data
5. **Toric Recommendations:** Test with high astigmatism case
6. **Error Handling:** Test with invalid inputs

### **Production Smoke Tests (After Deploy)**
1. **DNS Resolution:** Verify `lakecalc.ai` resolves correctly
2. **HTTPS Certificate:** Verify SSL/TLS is valid
3. **API Endpoints:** Run all staging tests again on production URL
4. **Performance:** Measure response times (target: < 30s for parsing)

---

## 🔍 **MONITORING & DEBUGGING**

### **Railway Logs**
```bash
# Via CLI
railway logs -f

# Via UI
Railway Dashboard → Service → Logs tab
```

### **RunPod Health Check**
```bash
# Verify Ollama is responding
curl -s https://88cj1hbr8cc66z-11434.proxy.runpod.net/api/tags

# Should return list of models including biometry-llama
```

### **Common Issues & Fixes**

#### **Issue: Parser returns 500 error**
**Cause:** RunPod Ollama not reachable
**Fix:**
```bash
# 1. Check RunPod is running (RunPod dashboard)
# 2. Test direct Ollama access:
curl -s https://88cj1hbr8cc66z-11434.proxy.runpod.net/api/tags

# 3. Check Railway env vars are set correctly
railway variables

# 4. Check Railway logs for connection errors
railway logs -f
```

#### **Issue: Railway build fails**
**Cause:** Dockerfile or dependencies issue
**Fix:**
```bash
# Check Railway build logs
# Verify Dockerfile is valid:
docker build -t lakecalc-ai .
docker run -p 8000:8000 -e RUNPOD_OLLAMA_URL=https://88cj1hbr8cc66z-11434.proxy.runpod.net lakecalc-ai
```

#### **Issue: Health check fails**
**Cause:** App not starting or port mismatch
**Fix:**
```bash
# Check Railway logs for startup errors
railway logs -f

# Verify PORT env var is set automatically by Railway
# Verify app.main:app starts correctly
```

---

## 🚀 **ROLLBACK STRATEGY**

### **Rollback to Previous Version**
1. **Railway UI** → Service → Deployments
2. Find last known good deployment
3. Click "Redeploy" on that commit

### **Emergency Rollback**
```bash
# Revert to previous commit
git revert HEAD
git push origin main

# Railway will auto-deploy the revert
```

---

## 📈 **PERFORMANCE TARGETS**

### **Response Times**
- Health check: < 100ms
- Biometry parsing: < 30 seconds
- IOL calculation: < 500ms
- Toric recommendation: < 1 second

### **Uptime**
- Target: 99.9% uptime
- Railway: Auto-restart on failure
- RunPod: Keep GPU instance running 24/7

### **Cost Estimation**
- **Railway Staging:** ~$5/month (minimal traffic)
- **Railway Production:** ~$20-50/month (depends on traffic)
- **RunPod GPU:** ~$0.34/hour × 24 × 30 = ~$245/month
- **Total:** ~$270-300/month

---

## 🔐 **SECURITY BEST PRACTICES**

### **Environment Variables**
- ✅ Store sensitive data (API keys, URLs) in Railway variables
- ✅ Never commit `.env` files to GitHub
- ✅ Use different credentials for staging vs production

### **HTTPS**
- ✅ Railway provides automatic SSL certificates
- ✅ Enforce HTTPS for all traffic
- ✅ Verify certificate validity regularly

### **API Security**
- ⚠️ Consider adding API key authentication for production
- ⚠️ Implement rate limiting to prevent abuse
- ⚠️ Add CORS whitelist for allowed domains

---

## 📚 **NEXT STEPS**

### **Immediate (Today)**
1. ✅ Commit environment-aware changes
2. ⏳ Deploy to Railway staging
3. ⏳ Test staging deployment
4. ⏳ Document staging URL and credentials

### **Short-term (This Week)**
1. Deploy to Railway production
2. Configure custom domain `lakecalc.ai`
3. Run comprehensive tests on production
4. Monitor logs and performance

### **Medium-term (This Month)**
1. Add API authentication
2. Implement rate limiting
3. Set up monitoring/alerting
4. Train model on additional PDF formats
5. Optimize parsing performance

### **Long-term (Next Quarter)**
1. Add batch processing for multiple PDFs
2. Implement PDF report generation
3. Expand IOL database with more families
4. Add additional formulas (Hoffer Q, Barrett Universal II)
5. Create web UI for calculator

---

## 📞 **SUPPORT & CONTACTS**

### **Services**
- **Railway:** https://railway.app/dashboard
- **RunPod:** https://runpod.io/console/pods
- **GitHub:** https://github.com/lake-health/lakecalc-ai

### **Documentation**
- [API Documentation](API_DOCUMENTATION.md)
- [Handoff Document](HANDOFF_DOCUMENT.md)
- [Biometry Parser Reality](BIOMETRY_PARSER_REALITY.md)

---

**Last Updated:** October 29, 2025  
**Version:** 1.0  
**Status:** Ready for Deployment

