#!/bin/bash

# LakeCalc AI - RunPod Deployment Script
# Run this script on your RunPod instance after git clone

echo "🚀 Starting LakeCalc AI deployment on RunPod..."

# Update system
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# Install Python dependencies
echo "🐍 Installing Python dependencies..."
pip install -r requirements.txt

# Install Ollama (if not already installed)
echo "🤖 Setting up Ollama..."
if ! command -v ollama &> /dev/null; then
    curl -fsSL https://ollama.ai/install.sh | sh
fi

# Start Ollama service
echo "🔄 Starting Ollama service..."
ollama serve &

# Wait for Ollama to start
sleep 10

# Pull recommended models
echo "📥 Downloading LLM models..."
ollama pull llama3.1:8b
ollama pull codellama:7b

# Set up environment
echo "⚙️ Configuring environment..."
export OLLAMA_HOST=0.0.0.0
export OLLAMA_PORT=11434
export FASTAPI_HOST=0.0.0.0
export FASTAPI_PORT=8000

# Create environment file
cat > .env << EOF
OLLAMA_HOST=0.0.0.0
OLLAMA_PORT=11434
FASTAPI_HOST=0.0.0.0
FASTAPI_PORT=8000
LLM_MODEL=llama3.1:8b
EOF

# Set up firewall
echo "🔥 Configuring firewall..."
ufw allow 8000
ufw allow 11434
ufw allow 22
ufw --force enable

# Test Ollama
echo "🧪 Testing Ollama connection..."
sleep 5
curl -s http://localhost:11434/api/tags

# Create startup script
echo "📝 Creating startup script..."
cat > start-lakecalc.sh << 'EOF'
#!/bin/bash
cd /workspace/lakecalc-ai
export OLLAMA_HOST=0.0.0.0
export OLLAMA_PORT=11434
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
EOF

chmod +x start-lakecalc.sh

# Test API endpoint
echo "🧪 Testing API endpoint..."
python3 -c "
import requests
import time
import subprocess

# Start server in background
print('Starting server...')
server = subprocess.Popen(['python3', '-m', 'uvicorn', 'app.main:app', '--host', '0.0.0.0', '--port', '8000'])

# Wait for server to start
time.sleep(10)

try:
    response = requests.get('http://localhost:8000/')
    if response.status_code == 200:
        print('✅ Server is running!')
        print(f'🌐 API available at: http://$(curl -s ifconfig.me):8000')
        print(f'🧪 Test endpoint: http://$(curl -s ifconfig.me):8000/parser/parse')
    else:
        print(f'❌ Server test failed: {response.status_code}')
except Exception as e:
    print(f'❌ Server test error: {e}')
finally:
    server.terminate()
"

echo ""
echo "🎉 Deployment complete!"
echo ""
echo "📋 Next Steps:"
echo "1. Start server: ./start-lakecalc.sh"
echo "2. Test API: curl http://localhost:8000/"
echo "3. Upload biometry file via browser interface"
echo "4. Monitor logs for any issues"
echo ""
echo "🌐 Your server will be available at:"
echo "   http://$(curl -s ifconfig.me):8000"
echo "   http://$(curl -s ifconfig.me):8000/static/test_local_llm.html"
echo ""
echo "🚀 Ready for universal biometry parsing!"
