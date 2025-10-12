# Cloud GPU Setup Guide - RunPod

## 🚀 Quick Setup Steps

### 1. Apply for Startup Grants
- **URL**: https://runpod.io/startup-credits
- **Benefits**: Up to 1,000 free H100 hours (~$3,000 value)
- **Review Time**: 48 hours

### 2. Create RunPod Instance
1. Go to https://runpod.io/
2. Select **RTX 4090** template (~$0.34/hour)
3. Choose **Ubuntu 22.04** with **Ollama** pre-installed
4. Set **Persistent Storage** (recommended)
5. Configure **SSH Key** for secure access

### 3. Install Dependencies
```bash
# SSH into your RunPod instance
ssh root@[your-runpod-ip]

# Update system
apt update && apt upgrade -y

# Install Python dependencies
pip install fastapi uvicorn requests pydantic python-multipart

# Install Ollama models
ollama pull llama3.1:8b
# or
ollama pull codellama:7b
```

### 4. Upload Project
```bash
# Create project directory
mkdir -p /workspace/lakecalc-ai
cd /workspace/lakecalc-ai

# Upload your project files (via SCP or Git)
# Option 1: SCP from local machine
scp -r /path/to/lakecalc-ai/* root@[runpod-ip]:/workspace/lakecalc-ai/

# Option 2: Git clone (if you push to GitHub)
git clone [your-repo-url] .
```

### 5. Update Configuration
Edit `app/services/parsing/local_llm_processor.py`:

```python
# Change from localhost to RunPod IP
def __init__(self, model_name: str = "llama3.1:8b", cost_tracker=None):
    super().__init__(cost_tracker)
    self.method = ProcessingMethod.LLM
    self.model_name = model_name
    self.base_url = "http://localhost:11434"  # Keep localhost (Ollama runs on same instance)
    self._check_ollama_connection()
```

### 6. Test Setup
```bash
# Start the server
cd /workspace/lakecalc-ai
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# Test API
curl -X POST "http://localhost:8000/parser/parse" \
  -F "file=@uploads/2935194_franciosi_carina_2024.10.01 18_00_37_IOL.pdf" \
  -F "user_id=test_user"
```

## 🔧 Configuration Files

### Environment Variables
Create `.env` file:
```bash
# Ollama Configuration
OLLAMA_HOST=0.0.0.0
OLLAMA_PORT=11434

# FastAPI Configuration
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000

# Security (if needed)
API_KEY=your-api-key
```

### Firewall Rules
```bash
# Allow HTTP traffic
ufw allow 8000
ufw allow 11434

# Allow SSH
ufw allow 22
ufw enable
```

## 💰 Cost Optimization

### Smart Usage
- **Start/Stop**: Only run when needed
- **Spot Instances**: Use for development (cheaper)
- **Persistent Storage**: Keep models cached
- **Monitoring**: Set up cost alerts

### Estimated Costs
- **Development**: ~$5-10/day (8 hours active)
- **Testing**: ~$2-5/day (4 hours active)
- **Production**: ~$250/month (24/7)

## 🎯 Expected Results

### Before (Local)
- Method: `ocr`
- Confidence: 95% (incomplete data)
- Processing: 120+ seconds (timeouts)
- Data: Mostly "N/A" values

### After (Cloud GPU)
- Method: `llm`
- Confidence: 95%+ (complete data)
- Processing: 10-30 seconds
- Data: Complete Eyestar extraction

## 🔍 Troubleshooting

### Common Issues
1. **Connection Refused**: Check firewall rules
2. **Model Not Found**: Run `ollama pull [model-name]`
3. **Out of Memory**: Use smaller model or increase instance size
4. **Slow Performance**: Check GPU utilization

### Debug Commands
```bash
# Check Ollama status
curl http://localhost:11434/api/tags

# Check GPU usage
nvidia-smi

# Check server logs
tail -f /var/log/lakecalc.log
```

## 📞 Support
- **RunPod Docs**: https://docs.runpod.io/
- **Ollama Docs**: https://ollama.ai/docs
- **Community**: RunPod Discord

---
**Ready for cloud deployment! 🚀**
