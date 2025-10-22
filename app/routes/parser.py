"""
API endpoints for document parsing and biometry extraction.
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import tempfile
import os

from app.services.parsing.universal_llm_parser import UniversalLLMParser
from app.services.parsing.cost_tracker import CostTracker
from app.services.parsing.base_parser import ParsingResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/parser", tags=["parser"])

# Initialize parser and cost tracker
cost_tracker = CostTracker()
universal_parser = UniversalLLMParser(cost_tracker)


class ParseRequest(BaseModel):
    """Request model for document parsing."""
    user_id: Optional[str] = Field(None, description="User ID for budget tracking")
    processing_options: Optional[Dict[str, bool]] = Field(
        default_factory=dict,
        description="Processing options (text_extraction, ocr, llm)"
    )


class ParseResponse(BaseModel):
    """Response model for document parsing."""
    success: bool
    confidence: float
    method: str
    extracted_data: Dict[str, Any]
    cost: float
    processing_time: float
    warnings: List[str] = []
    error_message: Optional[str] = None
    # Debug fields
    file_hash: Optional[str] = None
    original_filename: Optional[str] = None
    processing_steps: Optional[str] = None
    error_details: Optional[str] = None
    raw_text: Optional[str] = None


class BudgetSummary(BaseModel):
    """User budget summary."""
    user_id: str
    tier: str
    current_month: Dict[str, Any]
    remaining: Dict[str, Any]


@router.post("/parse", response_model=ParseResponse)
async def parse_document(
    file: UploadFile = File(...),
    user_id: Optional[str] = Form(None),
    processing_options: Optional[str] = Form("{}")
):
    """
    Parse a single document for biometry data.
    
    Args:
        file: Uploaded document (PDF, image, text)
        user_id: User ID for budget tracking
        processing_options: JSON string of processing options
        
    Returns:
        ParseResponse with extracted biometry data
    """
    try:
        # Create temporary file for uploaded document
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
            content = await file.read()
            temp_file.write(content)
            temp_file_path = temp_file.name
        
        try:
            # Parse options
            import json
            options = json.loads(processing_options) if processing_options else {}
            
            # Parse document
            result = await universal_parser.parse(temp_file_path, user_id)
            
            # Generate file hash for debug
            import hashlib
            file_hash = hashlib.sha256(file.filename.encode()).hexdigest()[:8]
            
            # Convert to response model
            response = ParseResponse(
                success=result.success,
                confidence=result.confidence,
                method=result.method.value,
                extracted_data=result.extracted_data,
                cost=result.cost,
                processing_time=result.processing_time,
                warnings=result.warnings or [],
                error_message=result.error_message,
                # Debug information
                file_hash=file_hash,
                original_filename=file.filename,
                processing_steps=str(getattr(result, 'processing_steps', None)),
                error_details=getattr(result, 'error_details', None),
                raw_text=result.raw_text[:1000] if result.raw_text else None
            )
            
            return response
            
        finally:
            # Clean up temporary file
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
    
    except Exception as e:
        logger.error(f"Document parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.post("/parse-multiple", response_model=ParseResponse)
async def parse_multiple_documents(
    files: List[UploadFile] = File(...),
    user_id: Optional[str] = Form(None),
    merge_results: bool = Form(True)
):
    """
    Parse multiple documents and optionally merge results.
    
    Useful for cases like:
    - Pentacam + IOLMaster data
    - Multiple pages of same document
    - OD and OS in separate files
    """
    try:
        temp_files = []
        
        try:
            # Save all uploaded files temporarily
            for file in files:
                with tempfile.NamedTemporaryFile(delete=False, suffix=Path(file.filename).suffix) as temp_file:
                    content = await file.read()
                    temp_file.write(content)
                    temp_files.append(temp_file.name)
            
            # Parse each document
            results = {}
            for i, temp_file_path in enumerate(temp_files):
                file_result = await universal_parser.parse(temp_file_path, user_id)
                results[files[i].filename] = file_result
            
            if merge_results and len(results) > 1:
                # Merge results
                final_result = universal_parser.merge_parsing_results(results)
            else:
                # Return first successful result or first result
                successful_results = [r for r in results.values() if r.success]
                if successful_results:
                    final_result = successful_results[0]
                else:
                    final_result = list(results.values())[0]
            
            # Convert to response model
            response = ParseResponse(
                success=final_result.success,
                confidence=final_result.confidence,
                method=final_result.method.value,
                extracted_data=final_result.extracted_data,
                cost=final_result.cost,
                processing_time=final_result.processing_time,
                warnings=final_result.warnings or [],
                error_message=final_result.error_message
            )
            
            return response
            
        finally:
            # Clean up temporary files
            for temp_file_path in temp_files:
                if os.path.exists(temp_file_path):
                    os.unlink(temp_file_path)
    
    except Exception as e:
        logger.error(f"Multiple document parsing failed: {e}")
        raise HTTPException(status_code=500, detail=f"Parsing failed: {str(e)}")


@router.get("/budget/{user_id}", response_model=BudgetSummary)
async def get_user_budget(user_id: str):
    """Get user's current budget status and usage."""
    try:
        budget_summary = universal_parser.get_user_budget_summary(user_id)
        return BudgetSummary(**budget_summary)
    
    except Exception as e:
        logger.error(f"Failed to get budget for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get budget: {str(e)}")


@router.get("/services/{user_id}")
async def get_available_services(user_id: str):
    """Get available processing services for user based on budget."""
    try:
        services = universal_parser.get_processing_options(user_id)
        return {"user_id": user_id, "services": services}
    
    except Exception as e:
        logger.error(f"Failed to get services for user {user_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get services: {str(e)}")


@router.post("/upgrade/{user_id}")
async def upgrade_user_tier(user_id: str, new_tier: str):
    """Upgrade user to new tier (free, premium, enterprise)."""
    try:
        success = cost_tracker.upgrade_user_tier(user_id, new_tier)
        
        if success:
            return {"success": True, "message": f"Upgraded user {user_id} to {new_tier} tier"}
        else:
            raise HTTPException(status_code=400, detail=f"Invalid tier: {new_tier}")
    
    except Exception as e:
        logger.error(f"Failed to upgrade user {user_id} to {new_tier}: {e}")
        raise HTTPException(status_code=500, detail=f"Upgrade failed: {str(e)}")


@router.get("/cost-estimates")
async def get_cost_estimates():
    """Get cost estimates for all processing services."""
    try:
        estimates = {}
        for service, cost in cost_tracker.SERVICE_COSTS.items():
            estimates[service] = {
                "cost_per_document": cost,
                "description": _get_service_description(service)
            }
        
        return {"cost_estimates": estimates}
    
    except Exception as e:
        logger.error(f"Failed to get cost estimates: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get cost estimates: {str(e)}")


def _get_service_description(service: str) -> str:
    """Get human-readable description for service."""
    descriptions = {
        "text_extraction": "Extract text from PDF and text files (fastest, most accurate for clean documents)",
        "ocr_tesseract": "OCR using Tesseract (free, good for simple layouts)",
        "ocr_easyocr": "OCR using EasyOCR (paid, better accuracy for complex layouts)",
        "llm_gpt4": "AI-powered parsing using GPT-4 (most accurate, handles complex formats)",
        "llm_claude": "AI-powered parsing using Claude (alternative to GPT-4)",
        "manual_review": "Manual data entry interface (always available)"
    }
    return descriptions.get(service, "Unknown service")


@router.get("/health")
async def health_check():
    """Health check for parser service."""
    return {
        "status": "healthy",
        "parser": "universal_parser",
        "cost_tracker": "enabled",
        "services": {
            "text_extraction": "available",
            "ocr": "not_implemented",
            "llm": "not_implemented"
        }
    }
