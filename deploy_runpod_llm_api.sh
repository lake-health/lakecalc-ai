#!/bin/bash
# Deploy LLM API service to RunPod

set -e

echo "🚀 Deploying LakeCalc-AI LLM API to RunPod..."

# Configuration
RUNPOD_API_URL="https://api.runpod.io/graphql"
RUNPOD_API_KEY="${RUNPOD_API_KEY:-}"
POD_ID="${POD_ID:-}"

if [ -z "$RUNPOD_API_KEY" ]; then
    echo "❌ Error: RUNPOD_API_KEY environment variable not set"
    echo "Please set your RunPod API key:"
    echo "export RUNPOD_API_KEY='your-api-key-here'"
    exit 1
fi

if [ -z "$POD_ID" ]; then
    echo "❌ Error: POD_ID environment variable not set"
    echo "Please set your RunPod Pod ID:"
    echo "export POD_ID='your-pod-id-here'"
    exit 1
fi

# Create deployment package
echo "📦 Creating deployment package..."
mkdir -p runpod_deployment
cp runpod_llm_api.py runpod_deployment/
cp requirements.txt runpod_deployment/

# Create startup script for RunPod
cat > runpod_deployment/start_llm_api.sh << 'EOF'
#!/bin/bash
set -e

echo "🚀 Starting LakeCalc-AI LLM API Service..."

# Update system
apt-get update
apt-get install -y python3 python3-pip python3-venv git curl

# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install Ollama if not present
if ! command -v ollama &> /dev/null; then
    echo "📥 Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Start Ollama service
echo "🔄 Starting Ollama service..."
ollama serve &
sleep 10

# Pull required models
echo "📥 Pulling LLM models..."
ollama pull llama3.1:8b || echo "Warning: Failed to pull llama3.1:8b"
ollama pull tinyllama:1.1b || echo "Warning: Failed to pull tinyllama:1.1b"

# Start LLM API service
echo "🚀 Starting LLM API service..."
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python3 runpod_llm_api.py &

# Keep container running
echo "✅ LLM API service started successfully!"
echo "🌐 API available at: http://0.0.0.0:8001"
echo "📖 Health check: http://0.0.0.0:8001/health"
echo "📚 API docs: http://0.0.0.0:8001/docs"

# Wait for services
wait
EOF

chmod +x runpod_deployment/start_llm_api.sh

# Create Dockerfile for RunPod
cat > runpod_deployment/Dockerfile << 'EOF'
FROM nvidia/cuda:11.8-devel-ubuntu20.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy application files
COPY . .

# Make startup script executable
RUN chmod +x start_llm_api.sh

# Expose port
EXPOSE 8001

# Start the service
CMD ["./start_llm_api.sh"]
EOF

# Create requirements.txt for RunPod
cat > runpod_deployment/requirements.txt << 'EOF'
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.9.2
requests>=2.31.0
python-multipart==0.0.9
EOF

echo "📦 Deployment package created in runpod_deployment/"

# Upload to RunPod (if we have the API)
if [ ! -z "$RUNPOD_API_KEY" ]; then
    echo "🚀 Uploading to RunPod..."
    
    # Create a simple deployment script
    cat > runpod_deployment/deploy_to_runpod.sh << 'EOF'
#!/bin/bash
# This script should be run on the RunPod instance

echo "🚀 Setting up LLM API on RunPod..."

# Clone the repository or upload files
# git clone https://github.com/your-username/lakecalc-ai.git
# cd lakecalc-ai

# Or if files are already uploaded:
cd /workspace

# Make scripts executable
chmod +x start_llm_api.sh

# Start the service
./start_llm_api.sh
EOF

    chmod +x runpod_deployment/deploy_to_runpod.sh
    
    echo "✅ Deployment package ready!"
    echo ""
    echo "📋 Next steps:"
    echo "1. Upload the runpod_deployment/ folder to your RunPod instance"
    echo "2. SSH into your RunPod instance"
    echo "3. Run: ./deploy_to_runpod.sh"
    echo ""
    echo "🌐 Your LLM API will be available at: http://your-runpod-ip:8001"
    echo "📖 Health check: http://your-runpod-ip:8001/health"
    echo "📚 API docs: http://your-runpod-ip:8001/docs"
fi

echo "✅ RunPod LLM API deployment package created successfully!"


