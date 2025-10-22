# Hybrid LLM Architecture Setup Guide

## 🎯 **Overview**

This guide sets up a hybrid LLM architecture for LakeCalc-AI:

- **Local Development**: Fast iteration and testing on your machine
- **Cloud LLM Processing**: Powerful parsing using RunPod GPU instances
- **Automatic Fallback**: Seamless fallback from cloud to local processing

## 🏗️ **Architecture**

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Local App     │    │  RunPod LLM API  │    │   Local LLM     │
│  (FastAPI)      │───▶│   (GPU Server)   │    │   (Fallback)    │
│  Port 8000      │    │   Port 8001      │    │   (Ollama)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        │                        │                        ▲
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 │
                    Automatic Fallback System
```

## 🚀 **Setup Instructions**

### 1. **Local Development Environment** ✅

Your local environment is already set up and running:

```bash
# Server running on http://127.0.0.1:8000
# Test interface: http://127.0.0.1:8000/static/test_local_llm.html
```

### 2. **RunPod LLM API Service**

#### Option A: Deploy to RunPod (Recommended)

1. **Create RunPod deployment package:**
   ```bash
   ./deploy_runpod_llm_api.sh
   ```

2. **Upload to RunPod:**
   - Upload the `runpod_deployment/` folder to your RunPod instance
   - SSH into your RunPod instance
   - Run: `./deploy_to_runpod.sh`

3. **Configure your local app:**
   ```bash
   export RUNPOD_LLM_API_URL="http://your-runpod-ip:8001"
   export RUNPOD_LLM_ENABLED="true"
   ```

#### Option B: Local RunPod API (For Testing)

1. **Start RunPod LLM API locally:**
   ```bash
   python3 runpod_llm_api.py
   ```

2. **Configure for local testing:**
   ```bash
   export RUNPOD_LLM_API_URL="http://localhost:8001"
   export RUNPOD_LLM_ENABLED="true"
   ```

### 3. **Test the Hybrid Integration**

```bash
# Run the test script
python3 test_hybrid_llm.py
```

## 🔧 **Configuration**

### Environment Variables

```bash
# RunPod LLM API Configuration
export RUNPOD_LLM_API_URL="http://your-runpod-ip:8001"
export RUNPOD_LLM_ENABLED="true"
export RUNPOD_LLM_TIMEOUT="120"
export RUNPOD_LLM_MAX_RETRIES="3"
export RUNPOD_LLM_CONFIDENCE_THRESHOLD="0.8"
export RUNPOD_LLM_FALLBACK="true"

# Environment
export ENVIRONMENT="development"  # or "production"
```

### Configuration Files

- `app/config/runpod_config.py` - RunPod API configuration
- `app/services/parsing/runpod_llm_client.py` - RunPod client
- `app/services/parsing/universal_llm_parser.py` - Hybrid parser

## 🧪 **Testing**

### 1. **Test RunPod LLM API Health**

```bash
curl http://your-runpod-ip:8001/health
```

Expected response:
```json
{
  "status": "healthy",
  "ollama_available": true,
  "models_loaded": ["llama3.1:8b", "tinyllama:1.1b"],
  "timestamp": "2024-01-15T10:30:00"
}
```

### 2. **Test Biometry Parsing**

```bash
curl -X POST http://your-runpod-ip:8001/parse \
  -H "Content-Type: application/json" \
  -d '{
    "text": "Patient: John Doe\nAge: 65\nOD: AL 25.25, K1 42.60, K2 43.52",
    "confidence_threshold": 0.8
  }'
```

### 3. **Test Hybrid Integration**

```bash
python3 test_hybrid_llm.py
```

## 📊 **How It Works**

### Processing Flow

1. **Document Upload** → Local App (FastAPI)
2. **Text Extraction** → OCR/Text extraction
3. **LLM Processing** → Try RunPod LLM API first
4. **Fallback** → Local LLM if RunPod unavailable
5. **Result** → Structured biometry data

### Fallback Logic

```
RunPod LLM API Available?
├── Yes → Use RunPod LLM API
│   ├── Success & High Confidence → Return Result
│   └── Low Confidence → Try Local LLM
└── No → Use Local LLM
    ├── Success → Return Result
    └── Fail → Return Error
```

## 🎛️ **Monitoring**

### RunPod LLM API Endpoints

- `GET /health` - Service health check
- `POST /parse` - Biometry parsing
- `GET /models` - List available models
- `POST /models/{name}/pull` - Pull new model

### Local App Integration

The hybrid system automatically:
- Checks RunPod LLM API health
- Falls back to local processing
- Logs all processing steps
- Tracks confidence scores

## 🔄 **Development Workflow**

1. **Local Development**:
   - Make changes to local code
   - Test with local LLM fallback
   - Fast iteration cycle

2. **Cloud Testing**:
   - Deploy to RunPod
   - Test with cloud LLM API
   - Verify hybrid integration

3. **Production**:
   - Use RunPod LLM API as primary
   - Local LLM as fallback
   - Monitor performance and costs

## 🚨 **Troubleshooting**

### Common Issues

1. **RunPod LLM API Not Available**:
   - Check RunPod instance status
   - Verify port 8001 is open
   - Check Ollama service is running

2. **Connection Timeouts**:
   - Increase timeout settings
   - Check network connectivity
   - Verify RunPod instance IP

3. **Low Confidence Scores**:
   - Check model availability
   - Verify prompt quality
   - Review extracted text quality

### Debug Commands

```bash
# Check RunPod LLM API health
curl http://your-runpod-ip:8001/health

# List available models
curl http://your-runpod-ip:8001/models

# Test with sample text
python3 test_hybrid_llm.py

# Check local app logs
tail -f server.log
```

## 🎉 **Success Criteria**

✅ **Hybrid Architecture Working When**:
- Local app starts successfully
- RunPod LLM API responds to health checks
- Biometry parsing works with cloud LLM
- Automatic fallback to local LLM works
- Test script passes all checks

## 🚀 **Next Steps**

1. **Deploy RunPod LLM API** to cloud instance
2. **Configure environment variables** for your setup
3. **Test with real biometry files** via browser interface
4. **Monitor performance** and optimize as needed
5. **Scale up** with additional RunPod instances if needed

---

**🎯 You now have a powerful hybrid LLM architecture for universal biometry parsing!**


