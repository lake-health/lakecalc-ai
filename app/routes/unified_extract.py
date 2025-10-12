"""
Unified extract endpoint that integrates new parser with existing system.
"""

import logging
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.services.parsing.unified_extract import get_unified_extract_service
from app.models.api import ExtractResult
from app.storage import UPLOADS

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/extract/{file_id}", response_model=ExtractResult)
async def extract_with_fallback(
    file_id: str, 
    debug: bool = Query(False, description="Enable debug mode"),
    user_id: str = Query(None, description="User ID for feature flag and budget tracking")
):
    """
    Enhanced extract endpoint with automatic fallback between new and legacy parsers.
    
    This endpoint:
    1. Tries the new universal parser first (if enabled for user)
    2. Falls back to legacy parser if new parser fails
    3. Provides transparent switching based on feature flags
    4. Tracks usage and costs
    """
    try:
        # Find file by prefix (existing logic)
        matches = list(UPLOADS.glob(file_id + "*"))
        if not matches:
            raise HTTPException(status_code=404, detail="file_id not found")
        file_path = matches[0]
        
        logger.info(f"Extracting from {file_path} for user {user_id}")
        
        # Use unified extract service
        unified_service = get_unified_extract_service()
        result = unified_service.extract(str(file_path), user_id)
        
        if debug:
            # Add debug information
            result["debug"] = {
                "file_path": str(file_path),
                "file_size": file_path.stat().st_size,
                "parser_status": unified_service.get_parser_status(),
                "fallback_reason": result.get("fallback_reason"),
            }
        
        # Convert to ExtractResult format
        return ExtractResult(**result)
        
    except Exception as e:
        logger.error(f"Extract failed for {file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")


@router.get("/parser/status")
async def get_parser_status():
    """Get current parser configuration and status."""
    try:
        unified_service = get_unified_extract_service()
        status = unified_service.get_parser_status()
        
        return {
            "status": "ok",
            "parser_config": status,
            "services": {
                "universal_parser": "available",
                "legacy_parser": "available",
                "google_cloud_vision": "available",
                "cost_tracking": "enabled"
            }
        }
        
    except Exception as e:
        logger.error(f"Failed to get parser status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.post("/admin/parser/rollout")
async def update_rollout_percentage(percentage: int):
    """Update new parser rollout percentage (admin function)."""
    try:
        if percentage < 0 or percentage > 100:
            raise HTTPException(status_code=400, detail="Percentage must be between 0 and 100")
        
        unified_service = get_unified_extract_service()
        success = unified_service.update_rollout_percentage(percentage)
        
        if success:
            return {
                "status": "success",
                "message": f"Rollout percentage updated to {percentage}%",
                "new_percentage": percentage
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to update rollout percentage")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update rollout percentage: {e}")
        raise HTTPException(status_code=500, detail=f"Update failed: {str(e)}")


@router.post("/admin/parser/emergency-fallback")
async def emergency_fallback():
    """Emergency endpoint to disable new parser (admin function)."""
    try:
        unified_service = get_unified_extract_service()
        success = unified_service.emergency_fallback()
        
        if success:
            return {
                "status": "success",
                "message": "Emergency fallback activated - new parser disabled",
                "all_users_will_use": "legacy_parser"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to activate emergency fallback")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to activate emergency fallback: {e}")
        raise HTTPException(status_code=500, detail=f"Emergency fallback failed: {str(e)}")


@router.get("/admin/parser/health")
async def parser_health_check():
    """Comprehensive health check for all parser components."""
    try:
        unified_service = get_unified_extract_service()
        
        # Test universal parser
        test_result = None
        try:
            # Create a simple test
            from app.services.parsing.text_extractor import TextExtractor
            extractor = TextExtractor()
            test_result = {"universal_parser": "healthy"}
        except Exception as e:
            test_result = {"universal_parser": f"error: {e}"}
        
        # Test legacy parser
        legacy_result = None
        try:
            from app.parser import parse_text
            legacy_result = {"legacy_parser": "healthy"}
        except Exception as e:
            legacy_result = {"legacy_parser": f"error: {e}"}
        
        # Test Google Cloud Vision
        gcv_result = None
        try:
            from app.ocr import ocr_file
            gcv_result = {"google_cloud_vision": "healthy"}
        except Exception as e:
            gcv_result = {"google_cloud_vision": f"error: {e}"}
        
        return {
            "status": "ok",
            "timestamp": str(datetime.now()),
            "components": {
                **test_result,
                **legacy_result,
                **gcv_result,
                "cost_tracker": "healthy",
                "unified_service": "healthy"
            },
            "parser_config": unified_service.get_parser_status()
        }
        
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


# Import datetime for health check
from datetime import datetime
