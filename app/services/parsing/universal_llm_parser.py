"""
Universal LLM-First Biometry Parser

This parser uses the local LLM as the primary extraction method,
with minimal fallbacks for edge cases.
"""

import logging
import time
from pathlib import Path
from typing import Dict, Any, Optional

from .base_parser import BaseParser, ProcessingMethod, ParsingResult, BiometryData
from .local_llm_processor import LocalLLMProcessor
from .text_extractor import TextExtractor
from .ocr_processor import OCRProcessor
from .cost_tracker import CostTracker

logger = logging.getLogger(__name__)


class UniversalLLMParser(BaseParser):
    """
    Universal biometry parser using LLM-first approach.
    
    Strategy:
    1. Local LLM (primary) - handles any format
    2. Text extraction (fallback) - for simple text files
    3. OCR (fallback) - for images/scanned documents
    4. Manual review (last resort)
    """
    
    def __init__(self, cost_tracker: CostTracker = None):
        super().__init__(cost_tracker)
        
        # Initialize processors
        self.local_llm = LocalLLMProcessor(cost_tracker=cost_tracker)
        self.text_extractor = TextExtractor(cost_tracker)
        self.ocr_processor = OCRProcessor(cost_tracker)
        
        # LLM-first processing order - always try LLM first
        self.processing_order = [
            ProcessingMethod.LLM,  # Local LLM as primary method
            ProcessingMethod.TEXT_EXTRACTION,  # Fallback for simple text files
            ProcessingMethod.OCR,  # Fallback for images
            ProcessingMethod.MANUAL_REVIEW  # Last resort
        ]
        
        # Confidence thresholds - LLM-first approach
        self.confidence_thresholds = {
            ProcessingMethod.LLM: 0.5,  # LLM should be primary
            ProcessingMethod.TEXT_EXTRACTION: 0.5,  # Lower bar for fallbacks
            ProcessingMethod.OCR: 0.4  # Lower bar for fallbacks
        }
    
    def can_parse(self, document_path: str) -> bool:
        """Universal parser can handle any document type."""
        return True
    
    def parse(self, document_path: str, user_id: str = None) -> ParsingResult:
        """
        Parse biometry document using LLM-first approach.
        
        Args:
            document_path: Path to the document
            user_id: User identifier for cost tracking
            
        Returns:
            ParsingResult with extracted biometry data
        """
        start_time = time.time()
        document_path = Path(document_path)
        
        logger.info(f"Starting universal LLM parsing of {document_path.name}")
        
        # Try LLM first with any available text
        try:
            logger.info("Trying local LLM first...")
            
            # Get raw text from any available source
            raw_text = None
            
            # Try text extraction first to get raw text
            try:
                text_result = self._try_method(document_path, ProcessingMethod.TEXT_EXTRACTION, user_id)
                if text_result and text_result.raw_text:
                    raw_text = text_result.raw_text
                    logger.info("✅ Got text from text extraction")
            except Exception as e:
                logger.info(f"Text extraction failed: {e}")
            
            # If no text from text extraction, try OCR
            if not raw_text:
                try:
                    ocr_result = self._try_method(document_path, ProcessingMethod.OCR, user_id)
                    if ocr_result and ocr_result.raw_text:
                        raw_text = ocr_result.raw_text
                        logger.info("✅ Got text from OCR")
                except Exception as e:
                    logger.info(f"OCR failed: {e}")
            
            # Now try LLM with the raw text
            llm_result = self.local_llm.parse(document_path, user_id, raw_text=raw_text)
            
            if llm_result.success and llm_result.confidence >= 0.5:
                processing_time = time.time() - start_time
                llm_result.processing_time = processing_time
                logger.info(f"✅ LLM succeeded: confidence={llm_result.confidence:.2f}")
                return llm_result
            else:
                logger.info(f"⚠️ LLM confidence too low: {llm_result.confidence:.2f}")
        except Exception as e:
            logger.error(f"LLM failed: {e}")
        
        # Fallback to other methods if LLM fails
        logger.info("LLM failed, trying fallback methods...")
        
        # Try text extraction as fallback
        try:
            logger.info("Trying text extraction fallback...")
            text_result = self._try_method(document_path, ProcessingMethod.TEXT_EXTRACTION, user_id)
            
            if text_result.success and text_result.confidence >= 0.5:
                processing_time = time.time() - start_time
                text_result.processing_time = processing_time
                logger.info(f"✅ Text extraction fallback succeeded: confidence={text_result.confidence:.2f}")
                return text_result
        except Exception as e:
            logger.error(f"Text extraction fallback failed: {e}")
        
        # Try OCR as final fallback
        try:
            logger.info("Trying OCR fallback...")
            ocr_result = self._try_method(document_path, ProcessingMethod.OCR, user_id)
            
            if ocr_result.success and ocr_result.confidence >= 0.4:
                processing_time = time.time() - start_time
                ocr_result.processing_time = processing_time
                logger.info(f"✅ OCR fallback succeeded: confidence={ocr_result.confidence:.2f}")
                return ocr_result
        except Exception as e:
            logger.error(f"OCR fallback failed: {e}")
        
        # All methods failed - return manual review request
        logger.error("All parsing methods failed, requesting manual review")
        return self._create_manual_review_request(document_path, user_id)
    
    def _try_method(self, document_path: str, method: ProcessingMethod, user_id: str = None) -> ParsingResult:
        """Try a specific parsing method."""
        try:
            if method == ProcessingMethod.LLM:
                return self.local_llm.parse(document_path, user_id)
            elif method == ProcessingMethod.TEXT_EXTRACTION:
                return self.text_extractor.parse(document_path, user_id)
            elif method == ProcessingMethod.OCR:
                return self.ocr_processor.parse(document_path, user_id)
            else:
                raise ValueError(f"Unknown processing method: {method}")
        except Exception as e:
            logger.error(f"Method {method} failed: {e}")
            return ParsingResult(
                success=False,
                method=method,
                confidence=0.0,
                extracted_data={},
                cost=0.0,
                processing_time=0.0,
                warnings=[],
                error_message=str(e),
                file_hash="",
                original_filename=Path(document_path).name,
                processing_steps=None,
                error_details=None,
                raw_text=None
            )
    
    def _create_manual_review_request(self, document_path: str, user_id: str = None) -> ParsingResult:
        """Create a manual review request when all automated methods fail."""
        return ParsingResult(
            success=False,
            method=ProcessingMethod.MANUAL_REVIEW,
            confidence=0.0,
            extracted_data={},
            cost=0.0,
            processing_time=0.0,
            warnings=[],
            error_message=f"All automated parsing methods failed for {Path(document_path).name}. Manual review required.",
            file_hash="",
            original_filename=Path(document_path).name,
            processing_steps=None,
            error_details=None,
            raw_text=None
        )