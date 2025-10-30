# RunPod Recovery & Setup Guide

**Last Updated:** October 30, 2025  
**Purpose:** Complete procedure to recover/reset RunPod instance for LakeCalc biometry parsing

---

## 📋 **Overview**

This guide ensures you can quickly restore the RunPod environment after:
- Pod termination/restart
- Instance reset
- Accidental deletion
- Moving to a new pod

---

## 🔧 **Prerequisites**

- **RunPod Account** with GPU instance (RTX 4090 recommended)
- **SSH Access** configured
- **Test PDFs** ready (`carina.pdf`, `geraldo.pdf`)

---

## 🚀 **Step 1: Launch RunPod Pod**

1. Go to [RunPod Console](https://www.runpod.io/console/pods)
2. **Deploy New Pod:**
   - **GPU:** RTX 4090 (24GB VRAM)
   - **Template:** PyTorch 2.x (Ubuntu 22.04)
   - **Disk:** 50GB minimum
   - **Ports:** Expose TCP port `11434` (HTTP)
3. **Start the pod** and note:
   - Public IP
   - SSH port
   - HTTP service port for Ollama

---

## 🔐 **Step 2: SSH Connection**

```bash
# Test SSH connection
ssh root@<PUBLIC_IP> -p <SSH_PORT> -i ~/.ssh/id_ed25519

# If connection fails, check:
# 1. SSH key is injected in RunPod Environment Variables
# 2. Pod is fully started (check RunPod console)
# 3. Firewall allows SSH traffic
```

---

## 📦 **Step 3: Install System Dependencies**

```bash
# Update package list
apt-get update

# Install Tesseract OCR (required for text extraction)
apt-get install -y tesseract-ocr tesseract-ocr-eng

# Verify installation
tesseract --version
# Expected: tesseract 5.3.4 or newer
```

---

## 🐍 **Step 4: Create Python Virtual Environment**

```bash
# Create venv in persistent storage
cd /workspace
python3 -m venv venv

# Activate venv
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install Python dependencies
pip install requests pytesseract pillow pymupdf
```

---

## 🦙 **Step 5: Install Ollama (Persistent)**

```bash
# Set Ollama models directory to persistent storage
export OLLAMA_MODELS=/workspace/.ollama
echo 'export OLLAMA_MODELS=/workspace/.ollama' >> ~/.bashrc

# Download and install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server in background
nohup ollama serve > /workspace/ollama.log 2>&1 &

# Wait 10 seconds for server to start
sleep 10

# Verify Ollama is running
curl http://localhost:11434/api/tags
```

---

## 🤖 **Step 6: Pull Base Models**

```bash
# Pull Llama 3.1 8B (base text model)
ollama pull llama3.1:8b

# Pull LLaVA (vision model, optional for future use)
ollama pull llava:latest

# Verify models are downloaded
ollama list
# Expected output:
# NAME              ID              SIZE
# llama3.1:8b       ...             4.9 GB
# llava:latest      ...             4.7 GB
```

---

## 📂 **Step 7: Create Project Structure**

```bash
# Create directories
mkdir -p /workspace/lora_training/{data,scripts,outputs}
mkdir -p /workspace/test_files

# Set permissions
chmod -R 755 /workspace/lora_training
```

---

## 📄 **Step 8: Upload Test PDFs**

```bash
# From your LOCAL machine, upload test files:
scp -P <SSH_PORT> -i ~/.ssh/id_ed25519 \
  ~/Documents/*Projects/lakecalc-ai/test_files/*.pdf \
  root@<PUBLIC_IP>:/workspace/test_files/

# Verify upload on RunPod:
ls -lh /workspace/test_files/
# Expected:
# carina.pdf
# geraldo.pdf
```

---

## 🎓 **Step 9: Create Custom Biometry Model**

```bash
cd /workspace/lora_training

# Create Modelfile
cat > biometry-llama.modelfile << 'EOF'
FROM llama3.1:8b

SYSTEM "You are a medical biometry data extraction specialist. Extract biometry data from medical documents and return ONLY valid JSON in this exact format:

{
  "patient_name": "string",
  "age": number,
  "od": {
    "axial_length": number,
    "k1": number,
    "k2": number,
    "k_axis_1": number,
    "k_axis_2": number,
    "acd": number,
    "lt": number,
    "wtw": number,
    "cct": number
  },
  "os": {
    "axial_length": number,
    "k1": number,
    "k2": number,
    "k_axis_1": number,
    "k_axis_2": number,
    "acd": number,
    "lt": number,
    "wtw": number,
    "cct": number
  }
}

CRITICAL RULES:
- Return ONLY valid JSON, no explanations
- Extract exact values from the document
- Age should be calculated from birth date
- Axis values should be 0-180 degrees
- All measurements in correct units (mm, D, μm)
- If value not found, use null

AXIS MAPPING RULES:
- When you see K1 @ X°, set k_axis_1 = X
- When you see K2 @ Y°, set k_axis_2 = Y
- Example: K1: 42.30 D @ 100°, K2: 40.95 D @ 10° → k_axis_1: 100, k_axis_2: 10
- ALWAYS extract both axis values from K1 and K2 measurements

NAME FORMATTING:
- Convert names to proper case (e.g., 'franciosi, carina' → 'Carina Franciosi')
- Use full names when available"

PARAMETER temperature 0.1
PARAMETER num_ctx 2048
EOF

# Create custom model
ollama create biometry-llama -f biometry-llama.modelfile

# Verify model creation
ollama list | grep biometry
```

---

## 📝 **Step 10: Deploy Extraction Scripts**

```bash
cd /workspace/lora_training/scripts

# Copy the 3 UNIVERSAL extraction scripts from your repo:
# - extract_demographics_UNIVERSAL.py
# - extract_keratometry_UNIVERSAL.py
# - extract_biometry_UNIVERSAL.py

# From LOCAL machine:
scp -P <SSH_PORT> -i ~/.ssh/id_ed25519 \
  ~/Documents/*Projects/lakecalc-ai/runpod_extraction_scripts/*_UNIVERSAL.py \
  root@<PUBLIC_IP>:/workspace/lora_training/scripts/
```

---

## ✅ **Step 11: Verify Extraction**

```bash
cd /workspace/lora_training/scripts
source /workspace/venv/bin/activate

# Test demographics
python3 extract_demographics_UNIVERSAL.py /workspace/test_files/carina.pdf

# Test keratometry
python3 extract_keratometry_UNIVERSAL.py /workspace/test_files/carina.pdf OD

# Test biometry
python3 extract_biometry_UNIVERSAL.py /workspace/test_files/carina.pdf OD
```

**Expected Output:** All 3 scripts should return valid JSON with extracted data.

---

## 🌐 **Step 12: Expose Ollama API Publicly**

RunPod provides an HTTP proxy for port 11434:

```bash
# In RunPod Console, check "HTTP Services"
# You'll see a URL like:
# https://<POD_ID>-11434.proxy.runpod.net

# Test from your LOCAL machine:
curl https://<POD_ID>-11434.proxy.runpod.net/api/tags
```

**Save this URL** - it's needed for Railway integration!

---

## 📋 **Step 13: Document Environment Variables**

For Railway deployment, you'll need:

```bash
RUNPOD_OLLAMA_URL=https://<POD_ID>-11434.proxy.runpod.net
OLLAMA_TIMEOUT=300
PYTHONUNBUFFERED=1
ENVIRONMENT=production
PORT=8080
```

---

## 🔄 **Quick Recovery Checklist**

If your pod resets, run this quick recovery:

```bash
# 1. SSH in
ssh root@<PUBLIC_IP> -p <SSH_PORT> -i ~/.ssh/id_ed25519

# 2. Activate venv
source /workspace/venv/bin/activate

# 3. Restart Ollama
export OLLAMA_MODELS=/workspace/.ollama
nohup ollama serve > /workspace/ollama.log 2>&1 &

# 4. Verify models exist
ollama list

# 5. Test extraction
cd /workspace/lora_training/scripts
python3 extract_demographics_UNIVERSAL.py /workspace/test_files/carina.pdf
```

---

## ⚠️ **Common Issues & Fixes**

### **Issue 1: Ollama models not found**
```bash
# Check if OLLAMA_MODELS is set
echo $OLLAMA_MODELS

# Should output: /workspace/.ollama
# If not:
export OLLAMA_MODELS=/workspace/.ollama
echo 'export OLLAMA_MODELS=/workspace/.ollama' >> ~/.bashrc
```

### **Issue 2: Tesseract not found**
```bash
# Reinstall Tesseract
apt-get update && apt-get install -y tesseract-ocr
tesseract --version
```

### **Issue 3: Python module not found**
```bash
# Ensure venv is activated
source /workspace/venv/bin/activate

# Reinstall dependencies
pip install requests pytesseract pillow pymupdf
```

### **Issue 4: Ollama not responding**
```bash
# Check if Ollama is running
ps aux | grep ollama

# If not running, restart:
nohup ollama serve > /workspace/ollama.log 2>&1 &

# Check logs
tail -f /workspace/ollama.log
```

---

## 📊 **Verification Tests**

### **Test 1: Demographics Extraction**
```bash
result=$(python3 extract_demographics_UNIVERSAL.py /workspace/test_files/carina.pdf)
echo "$result" | grep -q "Carina" && echo "✅ Demographics test passed" || echo "❌ Test failed"
```

### **Test 2: Keratometry Extraction**
```bash
result=$(python3 extract_keratometry_UNIVERSAL.py /workspace/test_files/geraldo.pdf OS)
echo "$result" | grep -q "42.59" && echo "✅ Keratometry test passed" || echo "❌ Test failed"
```

### **Test 3: Biometry Extraction**
```bash
result=$(python3 extract_biometry_UNIVERSAL.py /workspace/test_files/carina.pdf OD)
echo "$result" | grep -q "25.25" && echo "✅ Biometry test passed" || echo "❌ Test failed"
```

---

## 🔗 **Next Steps After Recovery**

1. ✅ Verify all 3 extraction scripts work
2. 📝 Update Railway environment variables with new RunPod URL
3. 🧪 Test end-to-end pipeline
4. 🚀 Deploy to production

---

## 📞 **Support & Troubleshooting**

- **RunPod Docs:** https://docs.runpod.io/
- **Ollama Docs:** https://ollama.com/docs
- **Project Repo:** https://github.com/lake-health/lakecalc-ai

---

**Document Version:** 1.0  
**Last Tested:** October 30, 2025  
**Tested By:** Jonathan Lake

