"""
LLM-based document parsing for complex formatting and low-quality documents.
"""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
import time
import json

from .base_parser import BaseParser, ProcessingMethod, ParsingResult
from .text_extractor import TextExtractor

logger = logging.getLogger(__name__)


class LLMProcessor(BaseParser):
    """LLM-based processor for complex document parsing."""
    
    def __init__(self, cost_tracker=None):
        super().__init__(cost_tracker)
        self.method = ProcessingMethod.LLM
        self.text_extractor = TextExtractor(cost_tracker)
    
    def can_parse(self, document_path: str) -> bool:
        """LLM can handle any document type."""
        return True
    
    def parse(self, document_path: str, user_id: str = None) -> ParsingResult:
        """Process document using LLM for complex formatting."""
        import time
        start_time = time.time()
        
        try:
            # First try text extraction to get raw text
            text_result = self.text_extractor.parse(document_path, user_id)
            
            if not text_result.raw_text:
                return ParsingResult(
                    success=False,
                    confidence=0.0,
                    method=self.method,
                    extracted_data={},
                    error_message="No text extracted for LLM processing"
                )
            
            # Use LLM to parse the text with structured prompts
            extracted_data = self._parse_with_llm(text_result.raw_text, document_path)
            
            # Assess confidence based on extracted data
            confidence = self._assess_llm_confidence(extracted_data)
            
            processing_time = time.time() - start_time
            
            # Track cost (LLM is paid service)
            cost = self.cost_tracker.get_cost_estimate("llm_gpt4") if self.cost_tracker else 0.30
            
            result = self.format_result(
                extracted_data=extracted_data,
                method=self.method,
                confidence=confidence,
                cost=cost
            )
            
            result.raw_text = text_result.raw_text
            result.processing_time = processing_time
            
            # Track usage if cost tracker available
            if self.cost_tracker and user_id:
                self.cost_tracker.track_usage(user_id, "llm_gpt4", cost)
            
            logger.info(f"LLM processing completed: confidence={confidence:.2f}, cost=${cost:.2f}")
            
            return result
            
        except Exception as e:
            logger.error(f"LLM processing failed: {e}")
            return ParsingResult(
                success=False,
                confidence=0.0,
                method=self.method,
                extracted_data={},
                error_message=str(e)
            )
    
    def _parse_with_llm(self, text: str, document_path: str) -> Dict[str, Any]:
        """Use LLM to extract biometry data from text."""
        try:
            # Create structured prompt for LLM
            prompt = self._create_biometry_prompt(text)
            
            # Call OpenAI API
            response = self._call_openai_api(prompt)
            
            # Parse LLM response
            extracted_data = self._parse_llm_response(response)
            
            return extracted_data
            
        except Exception as e:
            logger.error(f"LLM parsing failed: {e}")
            # Fallback to regex parsing
            return self.text_extractor._parse_biometry_text(text)
    
    def _create_biometry_prompt(self, text: str) -> str:
        """Create structured prompt for biometry extraction."""
        return f"""
You are a medical AI assistant specializing in extracting biometry data from ophthalmology documents.

Extract the following measurements from this medical document text. Return ONLY a JSON object with the extracted values. Use null for missing values.

Required fields:
- axial_length (mm)
- k1 (diopters)
- k2 (diopters) 
- k_axis_1 (degrees)
- k_axis_2 (degrees)
- acd (mm)
- lt (mm)
- wtw (mm)
- cct (μm)
- age (years)
- eye (OD/OS)
- target_refraction (diopters)
- sia_magnitude (diopters)
- sia_axis (degrees)

Document text:
{text[:2000]}  # Limit text length for API

Return only valid JSON:
"""
    
    def _call_openai_api(self, prompt: str) -> str:
        """Call OpenAI API for text processing."""
        try:
            from openai import OpenAI
            
            # Initialize OpenAI client
            client = OpenAI()
            
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {"role": "system", "content": "You are a medical AI assistant that extracts biometry data from ophthalmology documents. Always return valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1,
                max_tokens=1000
            )
            
            return response.choices[0].message.content.strip()
            
        except Exception as e:
            logger.error(f"OpenAI API call failed: {e}")
            raise
    
    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response and extract biometry data."""
        try:
            # Clean response (remove markdown if present)
            clean_response = response.strip()
            if clean_response.startswith('```json'):
                clean_response = clean_response[7:]
            if clean_response.endswith('```'):
                clean_response = clean_response[:-3]
            clean_response = clean_response.strip()
            
            # Parse JSON
            data = json.loads(clean_response)
            
            # Validate and convert types
            extracted_data = {}
            for key, value in data.items():
                if value is not None:
                    try:
                        if key in ['axial_length', 'k1', 'k2', 'k_axis_1', 'k_axis_2', 'acd', 'lt', 'wtw', 'cct', 'age', 'target_refraction', 'sia_magnitude', 'sia_axis']:
                            extracted_data[key] = float(value)
                        else:
                            extracted_data[key] = str(value)
                    except (ValueError, TypeError):
                        continue
            
            # Calculate derived values
            if 'k1' in extracted_data and 'k2' in extracted_data:
                extracted_data['k_mean'] = (extracted_data['k1'] + extracted_data['k2']) / 2.0
                extracted_data['cyl_power'] = abs(extracted_data['k1'] - extracted_data['k2'])
            
            return extracted_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            return {}
        except Exception as e:
            logger.error(f"Failed to parse LLM response: {e}")
            return {}
    
    def _assess_llm_confidence(self, data: Dict[str, Any]) -> float:
        """Assess confidence in LLM-extracted data."""
        confidence = 0.0
        
        # Critical fields
        if data.get('axial_length'):
            confidence += 0.3
        if data.get('k1') and data.get('k2'):
            confidence += 0.4
        
        # Important fields
        if data.get('acd'):
            confidence += 0.1
        if data.get('lt'):
            confidence += 0.05
        if data.get('wtw'):
            confidence += 0.05
        
        # Optional fields
        if data.get('age'):
            confidence += 0.05
        if data.get('target_refraction'):
            confidence += 0.05
        
        return min(confidence, 0.95)  # Cap at 95% for LLM
