#!/bin/bash
# Update RunPod with latest GitHub changes

echo "🚀 Updating RunPod API with improved axis extraction..."

# Go to project directory
cd /lakecalc-ai

# Pull latest changes from GitHub
git pull

# Kill existing API process
pkill -f runpod_llm_api_fixed.py

# Start updated API in background
nohup python3 runpod_llm_api_fixed.py > runpod_api.log 2>&1 &

# Wait for startup
sleep 3

# Test the improved API
echo "🧪 Testing improved axis extraction..."
curl -X POST "http://localhost:8003/parse" \
  -F "file=@test_dual_eye.txt"

echo ""
echo "✅ RunPod API updated with improved axis extraction!"







