"""
Local LLM processor for biometry parsing.
This will replace external LLM calls with a fine-tuned local model.
"""

import logging
import json
import requests
import time
from typing import Dict, Any, Optional
from .base_parser import BaseParser, ProcessingMethod, ParsingResult, BiometryData

logger = logging.getLogger(__name__)


class LocalLLMProcessor(BaseParser):
    """Local LLM processor using Ollama for biometry parsing."""
    
    def __init__(self, model_name: str = "tinyllama:1.1b", cost_tracker=None):
        super().__init__(cost_tracker)
        self.method = ProcessingMethod.LLM
        self.model_name = model_name
        self.base_url = "http://localhost:11434"
        self._check_ollama_connection()
    
    def _check_ollama_connection(self):
        """Check if Ollama service is running."""
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=5)
            if response.status_code == 200:
                logger.info(f"✅ Ollama service is running. Available models: {response.json()}")
            else:
                logger.warning("⚠️ Ollama service responded but with error")
        except requests.exceptions.ConnectionError:
            logger.warning("⚠️ Ollama service not running. Please start with: ollama serve")
        except Exception as e:
            logger.error(f"❌ Error checking Ollama connection: {e}")
    
    def can_parse(self, document_path: str) -> bool:
        """Local LLM can theoretically parse any text content."""
        return True
    
    def parse(self, document_path: str, user_id: str = None, raw_text: str = None) -> ParsingResult:
        """Process document with local LLM."""
        start_time = time.time()
        
        try:
            if not raw_text:
                # Extract text first if not provided
                from .text_extractor import TextExtractor
                text_extractor = TextExtractor(self.cost_tracker)
                text_result = text_extractor.parse(document_path, user_id)
                raw_text = text_result.raw_text
                if not raw_text:
                    return ParsingResult(
                        success=False,
                        confidence=0.0,
                        method=self.method,
                        extracted_data={},
                        error_message="No raw text available for local LLM processing"
                    )
            
            logger.info(f"Processing document with local LLM ({self.model_name}) for user {user_id}")
            
            # Build prompt for biometry extraction
            prompt = self._build_biometry_prompt(raw_text)
            
            # Query local model
            llm_output = self._query_local_model(prompt)
            
            # Parse LLM output
            extracted_data = self._parse_llm_output(llm_output)
            
            # Assess confidence
            confidence = self._assess_confidence(extracted_data)
            processing_time = time.time() - start_time
            
            result = ParsingResult(
                success=len(extracted_data) > 0,
                confidence=confidence,
                method=self.method,
                extracted_data=extracted_data,
                processing_time=processing_time,
                cost=0.0,  # Local inference is free!
                raw_text=raw_text
            )
            
            logger.info(f"Local LLM processing completed: confidence={confidence:.2f}, cost=$0.00")
            return result
            
        except Exception as e:
            logger.error(f"Local LLM processing failed: {e}")
            return ParsingResult(
                success=False,
                confidence=0.0,
                method=self.method,
                extracted_data={},
                error_message=str(e)
            )
    
    def _build_biometry_prompt(self, text: str) -> str:
        """Build a specialized prompt for universal biometry extraction."""
        return f"""Text: {text}

Extract numbers and return JSON only:
{{"axial_length": 25.25, "k1": 42.60, "k2": 43.52, "k_axis_1": 14, "k_axis_2": 104, "eye": "OD"}}"""
    
    def _query_local_model(self, prompt: str) -> str:
        """Query the local Ollama model."""
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    'model': self.model_name,
                    'prompt': prompt,
                    'stream': False,
                    'options': {
                        'temperature': 0.1,  # Low temperature for consistent output
                        'top_p': 0.9,
                        'top_k': 40
                    }
                },
                timeout=120  # Increased timeout for complex prompts
            )
            
            if response.status_code == 200:
                return response.json()['response']
            else:
                raise Exception(f"Ollama API error: {response.status_code} - {response.text}")
                
        except requests.exceptions.ConnectionError:
            raise Exception("Cannot connect to Ollama service. Please ensure 'ollama serve' is running.")
        except Exception as e:
            raise Exception(f"Local LLM query failed: {e}")
    
    def _parse_llm_output(self, llm_output: str) -> Dict[str, Any]:
        """Parse the JSON output from the local LLM."""
        try:
            # Clean the output - remove any markdown formatting
            cleaned_output = llm_output.strip()
            if cleaned_output.startswith('```json'):
                cleaned_output = cleaned_output[7:]
            if cleaned_output.endswith('```'):
                cleaned_output = cleaned_output[:-3]
            
            # Parse JSON
            data = json.loads(cleaned_output)
            
            # Handle case where LLM returns a list instead of dict
            if isinstance(data, list):
                logger.warning(f"LLM returned list instead of dict: {data}")
                if len(data) > 0 and isinstance(data[0], dict):
                    data = data[0]  # Take first item if it's a list of dicts
                else:
                    logger.error("LLM returned unexpected list format")
                    return {}
            
            # Convert all numeric values to appropriate types
            for key, value in data.items():
                if isinstance(value, str) and value.replace('.', '').replace('-', '').isdigit():
                    try:
                        data[key] = float(value)
                    except ValueError:
                        pass
                elif value is None:
                    data[key] = None
            
            logger.debug(f"Local LLM extracted data: {data}")
            return data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse local LLM JSON output: {e}")
            logger.error(f"Raw output: {llm_output}")
            return {}
        except Exception as e:
            logger.error(f"Error parsing local LLM output: {e}")
            return {}
    
    def _assess_confidence(self, extracted_data: Dict[str, Any]) -> float:
        """Assess confidence in local LLM results."""
        if not extracted_data:
            return 0.0
        
        # Critical fields for biometry
        critical_fields = ['axial_length', 'k1', 'k2', 'eye']
        found_critical = sum(1 for field in critical_fields if extracted_data.get(field) is not None)
        
        # Base confidence on critical fields found
        base_confidence = found_critical / len(critical_fields)
        
        # Bonus for additional fields
        additional_fields = ['acd', 'lt', 'wtw', 'cct', 'age', 'k_axis_1', 'k_axis_2']
        found_additional = sum(1 for field in additional_fields if extracted_data.get(field) is not None)
        bonus_confidence = found_additional / len(additional_fields) * 0.2
        
        total_confidence = min(base_confidence + bonus_confidence, 1.0)
        
        logger.debug(f"Local LLM confidence assessment: {total_confidence:.2f} "
                    f"(critical: {found_critical}/{len(critical_fields)}, "
                    f"additional: {found_additional}/{len(additional_fields)})")
        
        return total_confidence


# Factory function for easy integration
def create_local_llm_processor(model_name: str = "codellama:7b", cost_tracker=None) -> LocalLLMProcessor:
    """Create a local LLM processor instance."""
    return LocalLLMProcessor(model_name=model_name, cost_tracker=cost_tracker)
