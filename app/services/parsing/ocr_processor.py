"""
OCR processing with Google Cloud Vision integration.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import time

from .base_parser import BaseParser, ProcessingMethod, ParsingResult
from .text_extractor import TextExtractor

logger = logging.getLogger(__name__)


class GoogleCloudVisionOCR(BaseParser):
    """OCR processor using Google Cloud Vision API."""
    
    def __init__(self, cost_tracker=None):
        super().__init__(cost_tracker)
        self.method = ProcessingMethod.OCR
        self.text_extractor = TextExtractor(cost_tracker)
    
    def can_parse(self, document_path: str) -> bool:
        """Check if we can process this document with OCR."""
        path = Path(document_path)
        
        # Support PDF and image files
        return path.suffix.lower() in ['.pdf', '.jpg', '.jpeg', '.png', '.tiff', '.bmp']
    
    def parse(self, document_path: str, user_id: str = None) -> ParsingResult:
        """Process document with Google Cloud Vision OCR."""
        import time
        start_time = time.time()
        
        try:
            # Use existing Google Cloud Vision integration
            from app.ocr import ocr_file
            
            path = Path(document_path)
            logger.info(f"Processing {path} with Google Cloud Vision OCR")
            
            # Run OCR using existing system
            text, error = ocr_file(path)
            
            if error:
                return ParsingResult(
                    success=False,
                    confidence=0.0,
                    method=self.method,
                    extracted_data={},
                    error_message=f"OCR failed: {error}"
                )
            
            if not text or len(text.strip()) < 50:
                return ParsingResult(
                    success=False,
                    confidence=0.0,
                    method=self.method,
                    extracted_data={},
                    error_message="OCR produced insufficient text"
                )
            
            # Parse biometry data from OCR text
            extracted_data = self.text_extractor._parse_biometry_text(text)
            
            # Assess confidence based on OCR quality and extracted data
            confidence = self._assess_ocr_confidence(text, extracted_data)
            
            processing_time = time.time() - start_time
            
            # Track cost (Google Cloud Vision is paid service)
            cost = self.cost_tracker.get_cost_estimate("ocr_easyocr") if self.cost_tracker else 0.02
            
            result = self.format_result(
                extracted_data=extracted_data,
                method=self.method,
                confidence=confidence,
                cost=cost
            )
            
            result.raw_text = text
            result.processing_time = processing_time
            
            # Track usage if cost tracker available
            if self.cost_tracker and user_id:
                self.cost_tracker.track_usage(user_id, "ocr_easyocr", cost)
            
            logger.info(f"OCR completed: confidence={confidence:.2f}, cost=${cost:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"Google Cloud Vision OCR failed: {e}")
            return ParsingResult(
                success=False,
                confidence=0.0,
                method=self.method,
                extracted_data={},
                error_message=str(e)
            )
    
    def _assess_ocr_confidence(self, text: str, extracted_data: Dict[str, Any]) -> float:
        """Assess confidence in OCR results."""
        confidence = 0.0
        
        # Base confidence from text quality
        if len(text) > 200:
            confidence += 0.3
        if len(text) > 500:
            confidence += 0.1
        
        # Check for common OCR artifacts (lower confidence)
        ocr_artifacts = ['|', '||', '|||', '...', '??', '!!']
        artifact_count = sum(text.count(artifact) for artifact in ocr_artifacts)
        if artifact_count > 10:
            confidence -= 0.1
        
        # Confidence from extracted data quality
        if extracted_data.get('axial_length'):
            confidence += 0.2
        if extracted_data.get('k1') and extracted_data.get('k2'):
            confidence += 0.3
        if extracted_data.get('acd'):
            confidence += 0.1
        if extracted_data.get('lt'):
            confidence += 0.05
        
        # Bonus for having multiple measurements
        measurement_count = len([k for k, v in extracted_data.items() 
                               if isinstance(v, (int, float)) and not k.startswith('_')])
        if measurement_count >= 5:
            confidence += 0.05
        
        return min(confidence, 0.95)  # Cap at 95% for OCR


class TesseractOCR(BaseParser):
    """OCR processor using Tesseract (free alternative)."""
    
    def __init__(self, cost_tracker=None):
        super().__init__(cost_tracker)
        self.method = ProcessingMethod.OCR
        self.text_extractor = TextExtractor(cost_tracker)
    
    def can_parse(self, document_path: str) -> bool:
        """Check if we can process this document with Tesseract."""
        path = Path(document_path)
        
        # Tesseract supports most image formats
        return path.suffix.lower() in ['.jpg', '.jpeg', '.png', '.tiff', '.bmp']
    
    def parse(self, document_path: str, user_id: str = None) -> ParsingResult:
        """Process document with Tesseract OCR."""
        import time
        start_time = time.time()
        
        try:
            import pytesseract
            from PIL import Image
            
            path = Path(document_path)
            logger.info(f"Processing {path} with Tesseract OCR")
            
            # Load and process image
            image = Image.open(path)
            
            # Configure Tesseract for better medical text recognition
            config = '--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.,°Dmmμm'
            
            # Extract text
            text = pytesseract.image_to_string(image, config=config)
            
            if not text or len(text.strip()) < 20:
                return ParsingResult(
                    success=False,
                    confidence=0.0,
                    method=self.method,
                    extracted_data={},
                    error_message="Tesseract produced insufficient text"
                )
            
            # Parse biometry data from OCR text
            extracted_data = self.text_extractor._parse_biometry_text(text)
            
            # Assess confidence (Tesseract typically lower than Google Cloud Vision)
            confidence = self._assess_ocr_confidence(text, extracted_data) * 0.8  # Scale down
            
            processing_time = time.time() - start_time
            
            # Tesseract is free
            cost = 0.0
            
            result = self.format_result(
                extracted_data=extracted_data,
                method=self.method,
                confidence=confidence,
                cost=cost
            )
            
            result.raw_text = text
            result.processing_time = processing_time
            
            # Track usage (free service)
            if self.cost_tracker and user_id:
                self.cost_tracker.track_usage(user_id, "ocr_tesseract", cost)
            
            logger.info(f"Tesseract OCR completed: confidence={confidence:.2f}, cost=${cost:.2f}")
            
            return result
            
        except ImportError:
            logger.error("Tesseract not available. Install with: pip install pytesseract")
            return ParsingResult(
                success=False,
                confidence=0.0,
                method=self.method,
                extracted_data={},
                error_message="Tesseract not installed"
            )
        except Exception as e:
            logger.error(f"Tesseract OCR failed: {e}")
            return ParsingResult(
                success=False,
                confidence=0.0,
                method=self.method,
                extracted_data={},
                error_message=str(e)
            )
    
    def _assess_ocr_confidence(self, text: str, extracted_data: Dict[str, Any]) -> float:
        """Assess confidence in Tesseract OCR results."""
        # Similar to Google Cloud Vision but with lower baseline
        confidence = 0.0
        
        # Base confidence from text quality
        if len(text) > 100:
            confidence += 0.2
        if len(text) > 300:
            confidence += 0.1
        
        # Confidence from extracted data quality
        if extracted_data.get('axial_length'):
            confidence += 0.2
        if extracted_data.get('k1') and extracted_data.get('k2'):
            confidence += 0.3
        if extracted_data.get('acd'):
            confidence += 0.1
        
        return min(confidence, 0.85)  # Lower cap for Tesseract


class OCRProcessor(BaseParser):
    """Unified OCR processor that chooses between available OCR engines."""
    
    def __init__(self, cost_tracker=None):
        super().__init__(cost_tracker)
        self.method = ProcessingMethod.OCR
        
        # Initialize available OCR engines
        self.google_vision = GoogleCloudVisionOCR(cost_tracker)
        self.tesseract = TesseractOCR(cost_tracker)
    
    def can_parse(self, document_path: str) -> bool:
        """Check if we can process this document with any OCR engine."""
        return (self.google_vision.can_parse(document_path) or 
                self.tesseract.can_parse(document_path))
    
    def parse(self, document_path: str, user_id: str = None) -> ParsingResult:
        """Process document with best available OCR engine."""
        
        # Check user budget to determine which OCR to use
        if self.cost_tracker and user_id:
            can_use_google, _ = self.cost_tracker.can_use_service(user_id, "ocr_easyocr")
            can_use_tesseract, _ = self.cost_tracker.can_use_service(user_id, "ocr_tesseract")
        else:
            can_use_google = True
            can_use_tesseract = True
        
        # Try Google Cloud Vision first (better quality)
        if can_use_google and self.google_vision.can_parse(document_path):
            logger.info("Using Google Cloud Vision OCR")
            result = self.google_vision.parse(document_path, user_id)
            
            # If successful with good confidence, return it
            if result.success and result.confidence > 0.35:  # Lower threshold to match universal parser
                return result
            
            # If failed but we can try Tesseract, continue to fallback
            if not result.success and can_use_tesseract:
                logger.info("Google Cloud Vision failed, trying Tesseract")
            elif result.confidence <= 0.6:
                logger.info("Google Cloud Vision low confidence, trying Tesseract")
        
        # Try Tesseract as fallback (free)
        if can_use_tesseract and self.tesseract.can_parse(document_path):
            logger.info("Using Tesseract OCR")
            result = self.tesseract.parse(document_path, user_id)
            
            if result.success:
                return result
        
        # Both OCR engines failed
        return ParsingResult(
            success=False,
            confidence=0.0,
            method=self.method,
            extracted_data={},
            error_message="All OCR engines failed"
        )
