"""
Universal parser that orchestrates all parsing layers with cost controls.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import time

from .base_parser import BaseParser, ProcessingMethod, ParsingResult, BiometryData
from .text_extractor import TextExtractor
from .cost_tracker import CostTracker
from .ocr_processor import OCRProcessor
from .llm_processor import LLMProcessor
from .local_llm_processor import LocalLLMProcessor

logger = logging.getLogger(__name__)


class UniversalParser(BaseParser):
    """
    Universal parser that tries multiple extraction methods in order of cost.
    
    Processing order:
    1. Text extraction (FREE) - highest confidence threshold
    2. OCR (LOW COST) - medium confidence threshold  
    3. LLM (HIGH COST) - lowest confidence threshold
    4. Manual review (FREE) - always available
    """
    
    def __init__(self, cost_tracker: CostTracker = None):
        super().__init__(cost_tracker)
        
        # Initialize processing layers
        self.text_extractor = TextExtractor(cost_tracker)
        self.ocr_processor = OCRProcessor(cost_tracker)
        self.llm_processor = LLMProcessor(cost_tracker)
        self.local_llm_processor = LocalLLMProcessor(cost_tracker=cost_tracker)
        
        # Confidence thresholds for each method (LLM-first approach)
        self.confidence_thresholds = {
            ProcessingMethod.LLM: 0.5,  # Local LLM threshold - should be primary
            ProcessingMethod.TEXT_EXTRACTION: 0.8,  # Higher threshold for text extraction
            ProcessingMethod.OCR: 0.4  # OCR fallback threshold
        }
        
        # Processing order (LLM-first universal approach)
        self.processing_order = [
            ProcessingMethod.LLM,  # Start with local LLM - universal extraction
            ProcessingMethod.TEXT_EXTRACTION,  # Fallback for simple text files
            ProcessingMethod.OCR,  # Fallback for images/scanned docs
            ProcessingMethod.MANUAL_REVIEW
        ]
    
    def can_parse(self, document_path: str) -> bool:
        """Universal parser can handle any document type."""
        return True  # We can always try to parse
    
    def parse(self, document_path: str, user_id: str = None) -> ParsingResult:
        """
        Parse document using cost-aware multi-layer approach.
        
        Args:
            document_path: Path to document to parse
            user_id: User ID for budget tracking
            
        Returns:
            ParsingResult with extracted data and processing info
        """
        start_time = time.time()
        
        logger.info(f"Starting universal parsing for {document_path} (user: {user_id})")
        
        # Initialize cost tracker if not provided
        if not self.cost_tracker:
            self.cost_tracker = CostTracker()
        
        # Try each processing method in order
        for method in self.processing_order:
            logger.info(f"Trying {method.value}")
            
            # Check if user can use this service
            if method != ProcessingMethod.TEXT_EXTRACTION and method != ProcessingMethod.MANUAL_REVIEW:
                service_name = self._get_service_name(method)
                can_use, reason = self.cost_tracker.can_use_service(user_id or "anonymous", service_name)
                
                if not can_use:
                    logger.info(f"Skipping {method.value}: {reason}")
                    continue
            
            # Try processing with this method
            result = self._try_processing_method(document_path, method, user_id)
            
            if result.success:
                # Check if confidence is high enough
                threshold = self.confidence_thresholds.get(method, 0.5)
                
                if result.confidence >= threshold:
                    processing_time = time.time() - start_time
                    result.processing_time = processing_time
                    
                    logger.info(f"Success with {method.value}: confidence={result.confidence:.2f}, cost=${result.cost:.2f}")
                    return result
                else:
                    logger.info(f"{method.value} succeeded but low confidence ({result.confidence:.2f} < {threshold})")
            
            logger.info(f"{method.value} failed: {result.error_message}")
        
        # If all methods failed, return manual review request
        return self._create_manual_review_request(document_path, user_id)
    
    def _try_processing_method(self, document_path: str, method: ProcessingMethod, user_id: str) -> ParsingResult:
        """Try processing with a specific method."""
        try:
            if method == ProcessingMethod.TEXT_EXTRACTION:
                return self.text_extractor.parse(document_path, user_id)
            
            elif method == ProcessingMethod.OCR:
                return self.ocr_processor.parse(document_path, user_id)
            
            elif method == ProcessingMethod.LLM:
                # Try local LLM first, fallback to external LLM
                try:
                    logger.info("Attempting local LLM processing first...")
                    local_result = self.local_llm_processor.parse(document_path, user_id)
                    if local_result.success and local_result.confidence >= 0.5:
                        logger.info(f"Local LLM succeeded with confidence {local_result.confidence:.2f}")
                        return local_result
                    else:
                        logger.info(f"Local LLM confidence too low ({local_result.confidence:.2f}), trying external LLM...")
                except Exception as e:
                    logger.warning(f"Local LLM failed: {e}, trying external LLM...")
                
                # Fallback to external LLM
                return self.llm_processor.parse(document_path, user_id)
            
            else:
                return ParsingResult(
                    success=False,
                    confidence=0.0,
                    method=method,
                    extracted_data={},
                    error_message=f"Unknown processing method: {method}"
                )
                
        except Exception as e:
            logger.error(f"Error in {method.value}: {e}")
            return ParsingResult(
                success=False,
                confidence=0.0,
                method=method,
                extracted_data={},
                error_message=str(e)
            )
    
    def _get_service_name(self, method: ProcessingMethod) -> str:
        """Get service name for cost tracking."""
        service_map = {
            ProcessingMethod.TEXT_EXTRACTION: "text_extraction",
            ProcessingMethod.OCR: "ocr_easyocr",  # Use paid OCR service
            ProcessingMethod.LLM: "llm_gpt4",      # Use GPT-4
            ProcessingMethod.MANUAL_REVIEW: "manual_review"
        }
        return service_map.get(method, "unknown")
    
    def _create_manual_review_request(self, document_path: str, user_id: str) -> ParsingResult:
        """Create a manual review request when all automatic methods fail."""
        return ParsingResult(
            success=False,
            confidence=0.0,
            method=ProcessingMethod.MANUAL_REVIEW,
            extracted_data={},
            error_message="All automatic parsing methods failed. Manual review required.",
            warnings=["Document requires manual data entry"]
        )
    
    def parse_multiple_documents(self, document_paths: List[str], user_id: str = None) -> Dict[str, ParsingResult]:
        """
        Parse multiple documents and merge results.
        
        Useful for cases like:
        - Pentacam PDF + IOLMaster PDF
        - Multiple pages of same document
        - OD and OS data in separate files
        """
        results = {}
        
        for path in document_paths:
            logger.info(f"Parsing document: {path}")
            result = self.parse(path, user_id)
            results[path] = result
        
        return results
    
    def merge_parsing_results(self, results: Dict[str, ParsingResult]) -> ParsingResult:
        """
        Merge multiple parsing results into a single result.
        
        This handles cases where biometry data comes from multiple sources.
        """
        merged_data = {}
        total_cost = 0.0
        methods_used = []
        warnings = []
        
        # Merge data from all successful results
        for path, result in results.items():
            if result.success:
                # Merge extracted data
                for key, value in result.extracted_data.items():
                    if key in merged_data:
                        # Handle conflicts (keep first value, add warning)
                        if merged_data[key] != value:
                            warnings.append(f"Conflicting values for {key}: {merged_data[key]} vs {value} (from {path})")
                    else:
                        merged_data[key] = value
                
                # Track costs and methods
                total_cost += result.cost
                methods_used.append(result.method.value)
            else:
                warnings.append(f"Failed to parse {path}: {result.error_message}")
        
        # Calculate overall confidence
        if results:
            avg_confidence = sum(r.confidence for r in results.values() if r.success) / len([r for r in results.values() if r.success])
        else:
            avg_confidence = 0.0
        
        # Create merged result
        merged_result = ParsingResult(
            success=len(merged_data) > 0,
            confidence=avg_confidence,
            method=ProcessingMethod.TEXT_EXTRACTION,  # Primary method
            extracted_data=merged_data,
            cost=total_cost,
            warnings=warnings
        )
        
        # Add metadata about merging
        merged_result.extracted_data['_merge_info'] = {
            'sources': list(results.keys()),
            'methods_used': methods_used,
            'total_documents': len(results),
            'successful_documents': len([r for r in results.values() if r.success])
        }
        
        return merged_result
    
    def get_processing_options(self, user_id: str) -> Dict[str, Dict]:
        """Get available processing options for user based on budget."""
        if not self.cost_tracker:
            self.cost_tracker = CostTracker()
        
        return self.cost_tracker.get_available_services(user_id)
    
    def get_user_budget_summary(self, user_id: str) -> Dict[str, Any]:
        """Get user's current budget status."""
        if not self.cost_tracker:
            self.cost_tracker = CostTracker()
        
        return self.cost_tracker.get_usage_summary(user_id)
