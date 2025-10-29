"""
Parse route for biometry extraction
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import tempfile
import os
from pathlib import Path
import logging
from ..services.biometry_parser import BiometryParser

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize parser
parser = BiometryParser()

@router.post("/parse")
async def parse_biometry(file: UploadFile = File(...)):
    """
    Parse biometry data from uploaded PDF file
    """
    try:
        # Validate file type
        if not file.filename.lower().endswith('.pdf'):
            raise HTTPException(status_code=400, detail="Only PDF files are allowed")
        
        # Save uploaded file temporarily
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_file_path = tmp_file.name
        
        try:
            # Extract biometry data
            result = parser.extract_complete_biometry(tmp_file_path)
            
            return JSONResponse(content={
                "success": True,
                "data": result,
                "filename": file.filename
            })
            
        finally:
            # Clean up temporary file
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
                
    except Exception as e:
        logger.error(f"Error parsing biometry: {e}")
        raise HTTPException(status_code=500, detail=f"Error parsing biometry: {str(e)}")

@router.get("/health")
async def health_check():
    """
    Health check endpoint
    """
    return {"status": "healthy", "service": "biometry_parser"}
