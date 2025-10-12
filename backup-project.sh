#!/bin/bash

# LakeCalc AI Project Backup Script
# Creates a compressed backup of the entire project

echo "🚀 Starting LakeCalc AI Project Backup..."

# Get current date for backup filename
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="lakecalc-ai-backup-${DATE}.tar.gz"

# Navigate to parent directory
cd /Users/jonathanlake/Documents/*Projects

echo "📦 Creating backup: ${BACKUP_NAME}"

# Create compressed backup
tar -czf "${BACKUP_NAME}" lakecalc-ai/

# Check if backup was created successfully
if [ $? -eq 0 ]; then
    echo "✅ Backup created successfully: ${BACKUP_NAME}"
    echo "📁 Location: $(pwd)/${BACKUP_NAME}"
    echo "📊 Size: $(du -h "${BACKUP_NAME}" | cut -f1)"
    
    # Optional: Move to Dropbox folder (uncomment if needed)
    # mv "${BACKUP_NAME}" ~/Dropbox/
    # echo "☁️  Moved to Dropbox"
    
    echo ""
    echo "🎯 Next Steps:"
    echo "1. Upload ${BACKUP_NAME} to your cloud storage"
    echo "2. When you return, extract with: tar -xzf ${BACKUP_NAME}"
    echo "3. Follow CLOUD_GPU_SETUP.md for deployment"
    
else
    echo "❌ Backup failed!"
    exit 1
fi

echo ""
echo "🌍 Safe travels! The project will be ready when you return! ✈️"
