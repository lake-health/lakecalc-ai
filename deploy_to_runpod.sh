#!/bin/bash
# Deploy LakeCalc-AI LLM API to RunPod

set -e

echo "🚀 Deploying LakeCalc-AI LLM API to RunPod..."

# Update system
echo "📦 Updating system packages..."
apt-get update
apt-get install -y python3 python3-pip python3-venv git curl wget

# Create working directory
echo "📁 Setting up workspace..."
mkdir -p /workspace/lakecalc-ai
cd /workspace/lakecalc-ai

# Create virtual environment
echo "🐍 Setting up Python environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install fastapi uvicorn pydantic requests python-multipart

echo "✅ Setup complete! Ready to create LLM API service..."


