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
from .runpod_llm_client import get_hybrid_processor
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
        
        # Initialize processors - hybrid only approach
        self.hybrid_processor = get_hybrid_processor()
        self.text_extractor = TextExtractor(cost_tracker)
        self.ocr_processor = OCRProcessor(cost_tracker)
        
        # Pure LLM-first processing order - LLM only
        self.processing_order = [
            ProcessingMethod.LLM,  # LLM as primary and only method
            ProcessingMethod.MANUAL_REVIEW  # Last resort only
        ]
        
        # Confidence thresholds - Pure LLM approach
        self.confidence_thresholds = {
            ProcessingMethod.LLM: 0.3,  # Low bar for LLM - use it for everything
            ProcessingMethod.MANUAL_REVIEW: 1.0  # Manual review only when LLM fails
        }
    
    def can_parse(self, document_path: str) -> bool:
        """Universal parser can handle any document type."""
        return True
    
    async def parse(self, document_path: str, user_id: str = None) -> ParsingResult:
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
        
        try:
            # Step 1: Extract raw text from document
            logger.info("Step 1: Extracting raw text...")
            raw_text = self._extract_raw_text(document_path)
            
            if not raw_text:
                logger.error("❌ Could not extract text from document")
                return self._create_manual_review_request(document_path, user_id)
            
            logger.info(f"✅ Extracted {len(raw_text)} characters of text")
            
            # Step 2: Send to RunPod LLM API
            logger.info("Step 2: Sending to RunPod LLM API...")
            llm_result = await self.hybrid_processor.process_with_hybrid(raw_text)
            
            if llm_result.get("success"):
                processing_time = time.time() - start_time
                logger.info(f"✅ RunPod LLM succeeded: confidence={llm_result.get('confidence', 0):.2f}")
                
                return ParsingResult(
                    success=True,
                    method=ProcessingMethod.LLM,
                    confidence=llm_result.get("confidence", 0),
                    extracted_data=llm_result.get("extracted_data", {}),
                    cost=0.0,
                    processing_time=processing_time,
                    warnings=[],
                    error_message=None,
                    raw_text=raw_text[:1000]
                )
            else:
                logger.error(f"❌ RunPod LLM failed: {llm_result.get('error', 'Unknown error')}")
                
        except Exception as e:
            logger.error(f"❌ Universal parser failed: {e}")
        
        # All methods failed - return manual review request
        logger.error("All parsing methods failed, requesting manual review")
        return self._create_manual_review_request(document_path, user_id)
    
    async def _try_method(self, document_path: str, method: ProcessingMethod, user_id: str = None) -> ParsingResult:
        """Try a specific parsing method."""
        try:
            if method == ProcessingMethod.LLM:
                # Use hybrid processor (RunPod LLM API + local fallback)
                return await self._process_with_hybrid_llm(document_path, user_id)
            # TEXT_EXTRACTION removed - LLM only approach
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
                raw_text=None
            )
    
    async def _process_with_hybrid_llm(self, document_path: str, user_id: str = None) -> ParsingResult:
        """Process document with hybrid LLM approach (RunPod + local fallback)"""
        try:
            # Get raw text from document
            raw_text = self._extract_raw_text(document_path)
            if not raw_text:
                raise ValueError("Could not extract text from document")
            
            # Use hybrid processor
            result = await self.hybrid_processor.process_with_hybrid(raw_text)
            
            if result["success"]:
                # Convert to ParsingResult format
                return ParsingResult(
                    success=True,
                    method=ProcessingMethod.LLM,
                    confidence=result["confidence"],
                    extracted_data=result["extracted_data"],
                    cost=0.0,  # RunPod LLM API is free for now
                    processing_time=result["processing_time"],
                    warnings=[],
                    error_message=None,
                    raw_text=raw_text[:1000]  # Store first 1000 chars
                )
            else:
                raise ValueError(result.get("error", "Hybrid LLM processing failed"))
                
        except Exception as e:
            logger.error(f"Hybrid LLM processing failed: {e}")
            return ParsingResult(
                success=False,
                method=ProcessingMethod.LLM,
                confidence=0.0,
                extracted_data={},
                cost=0.0,
                processing_time=0.0,
                warnings=[],
                error_message=str(e),
                raw_text=None
            )
    
    def _extract_raw_text(self, document_path: str) -> str:
        """Extract raw text from document for LLM processing"""
        try:
            # Try text extraction first
            text_result = self.text_extractor.parse(document_path)
            if text_result.success and text_result.raw_text:
                return text_result.raw_text
            
            # Fallback to OCR
            ocr_result = self.ocr_processor.parse(document_path)
            if ocr_result.success and ocr_result.raw_text:
                return ocr_result.raw_text
                
            return ""
        except Exception as e:
            logger.error(f"Failed to extract raw text: {e}")
            return ""
    
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
            raw_text=None
        )