"""
Unified extraction service that integrates new parser with existing system.
"""

import logging
import os
from pathlib import Path
from typing import Dict, Any, Optional
import hashlib

from .universal_parser import UniversalParser
from .cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class UnifiedExtractService:
    """
    Unified extraction service that provides fallback between new and legacy parsers.
    """
    
    def __init__(self):
        self.cost_tracker = CostTracker()
        self.universal_parser = UniversalParser(self.cost_tracker)
        
        # Feature flag controls
        self.use_new_parser = os.getenv("USE_NEW_PARSER", "false").lower() == "true"
        self.rollout_percent = int(os.getenv("NEW_PARSER_ROLLOUT_PERCENT", "0"))
        
        logger.info(f"UnifiedExtractService initialized: new_parser={self.use_new_parser}, rollout={self.rollout_percent}%")
    
    def should_use_new_parser(self, user_id: str) -> bool:
        """Determine if user should use new parser based on feature flags."""
        if not self.use_new_parser:
            return False
        
        if self.rollout_percent <= 0:
            return False
        
        if self.rollout_percent >= 100:
            return True
        
        # Gradual rollout based on user ID hash
        user_hash = int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 100
        return user_hash < self.rollout_percent
    
    def extract_with_universal_parser(self, file_path: str, user_id: str = None) -> Dict[str, Any]:
        """Extract using the new universal parser."""
        try:
            logger.info(f"Using universal parser for {file_path}")
            
            result = self.universal_parser.parse(file_path, user_id)
            
            if result.success:
                # Convert to legacy format for compatibility
                return self._convert_to_legacy_format(result)
            else:
                logger.warning(f"Universal parser failed: {result.error_message}")
                return {"error": result.error_message, "parser": "universal"}
                
        except Exception as e:
            logger.error(f"Universal parser error: {e}")
            return {"error": str(e), "parser": "universal"}
    
    def extract_with_legacy_parser(self, file_path: str) -> Dict[str, Any]:
        """Extract using the existing legacy parser."""
        try:
            logger.info(f"Using legacy parser for {file_path}")
            
            # Import existing parser functions
            from app.ocr import ocr_file
            from app.parser import parse_text
            
            # Run existing OCR pipeline
            text, err = ocr_file(Path(file_path))
            if not text:
                text = f"OCR failed: {err}"
                logger.warning(f"OCR failed for {file_path}: {err}")
            
            # Parse with existing parser
            file_id = Path(file_path).stem
            parsed = parse_text(file_id, text)
            
            # Convert to dict and add parser info
            result = parsed.model_dump()
            result["parser"] = "legacy"
            result["raw_text"] = text
            
            return result
            
        except Exception as e:
            logger.error(f"Legacy parser error: {e}")
            return {"error": str(e), "parser": "legacy"}
    
    def extract(self, file_path: str, user_id: str = None) -> Dict[str, Any]:
        """
        Unified extract method that chooses between new and legacy parsers.
        
        Args:
            file_path: Path to document to extract
            user_id: User ID for feature flag and budget tracking
            
        Returns:
            Dict with extracted data and parser information
        """
        if not user_id:
            user_id = "anonymous"
        
        # Check if we should use new parser
        if self.should_use_new_parser(user_id):
            # Try new parser first
            result = self.extract_with_universal_parser(file_path, user_id)
            
            # If new parser failed, fallback to legacy
            if "error" in result:
                logger.info(f"New parser failed, falling back to legacy: {result['error']}")
                result = self.extract_with_legacy_parser(file_path)
                result["fallback_reason"] = "new_parser_failed"
            else:
                result["fallback_reason"] = None
        else:
            # Use legacy parser
            result = self.extract_with_legacy_parser(file_path)
            result["fallback_reason"] = "feature_flag_disabled"
        
        # Add metadata
        from datetime import datetime
        result["extraction_timestamp"] = datetime.now().isoformat()
        result["user_id"] = user_id
        
        return result
    
    def _convert_to_legacy_format(self, result) -> Dict[str, Any]:
        """Convert universal parser result to legacy format."""
        data = result.extracted_data
        
        # Map to legacy field names
        legacy_data = {
            # Core measurements
            "al_mm": data.get("axial_length"),
            "acd_mm": data.get("acd"),
            "lt_mm": data.get("lt"),
            "wtw_mm": data.get("wtw"),
            "cct_um": data.get("cct"),
            
            # Keratometry
            "ks": {
                "k1_power": data.get("k1"),
                "k2_power": data.get("k2"),
                "k1_axis": data.get("k_axis_1"),
                "k2_axis": data.get("k_axis_2"),
            },
            
            # Demographics
            "age": data.get("age"),
            "gender": data.get("gender"),
            
            # Target
            "target_refraction": data.get("target_refraction"),
            
            # SIA
            "sia_magnitude": data.get("sia_magnitude"),
            "sia_axis": data.get("sia_axis"),
            
            # Metadata
            "parser": "universal",
            "confidence": result.confidence,
            "method": result.method.value,
            "cost": result.cost,
            "processing_time": result.processing_time,
            "warnings": result.warnings or [],
            "raw_text": result.raw_text,
        }
        
        # Add eye information if available
        if data.get("eye"):
            legacy_data["eye"] = data["eye"]
        
        return legacy_data
    
    def get_parser_status(self) -> Dict[str, Any]:
        """Get current parser configuration status."""
        return {
            "use_new_parser": self.use_new_parser,
            "rollout_percent": self.rollout_percent,
            "universal_parser_available": True,
            "legacy_parser_available": True,
            "cost_tracker_enabled": True,
        }
    
    def update_rollout_percentage(self, percentage: int) -> bool:
        """Update rollout percentage (admin function)."""
        try:
            if 0 <= percentage <= 100:
                self.rollout_percent = percentage
                os.environ["NEW_PARSER_ROLLOUT_PERCENT"] = str(percentage)
                logger.info(f"Updated rollout percentage to {percentage}%")
                return True
            else:
                logger.error(f"Invalid rollout percentage: {percentage}")
                return False
        except Exception as e:
            logger.error(f"Failed to update rollout percentage: {e}")
            return False
    
    def emergency_fallback(self) -> bool:
        """Emergency function to disable new parser."""
        try:
            self.use_new_parser = False
            os.environ["USE_NEW_PARSER"] = "false"
            logger.warning("Emergency fallback activated - new parser disabled")
            return True
        except Exception as e:
            logger.error(f"Failed to activate emergency fallback: {e}")
            return False


# Global instance
unified_extract_service = UnifiedExtractService()


def get_unified_extract_service() -> UnifiedExtractService:
    """Get the global unified extract service instance."""
    return unified_extract_service
