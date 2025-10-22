"""
RunPod LLM API Client for LakeCalc-AI
Client for calling the dedicated RunPod LLM API service
"""

import asyncio
import logging
import time
from typing import Dict, Any, Optional
import requests
from dataclasses import dataclass
import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', '..'))

try:
    from app.config.runpod_config import get_config
except ImportError:
    # Fallback if config not available
    def get_config():
        return None

logger = logging.getLogger(__name__)

@dataclass
class RunPodLLMConfig:
    """Configuration for RunPod LLM API client"""
    base_url: str = "http://localhost:8001"  # Default to local for development
    timeout: int = 120  # 2 minutes timeout
    max_retries: int = 3
    retry_delay: float = 2.0
    confidence_threshold: float = 0.3

class RunPodLLMClient:
    """Client for calling RunPod LLM API service"""
    
    def __init__(self, config: RunPodLLMConfig = None):
        self.config = config or RunPodLLMConfig()
        self.session = requests.Session()
        self.session.timeout = self.config.timeout
        
    async def health_check(self) -> Dict[str, Any]:
        """Check if the RunPod LLM API is healthy"""
        try:
            response = self.session.get(f"{self.config.base_url}/health")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Health check failed: {response.status_code}")
                return {"status": "unhealthy", "error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {"status": "unhealthy", "error": str(e)}
    
    async def parse_biometry(self, text: str, device_type: str = None) -> Dict[str, Any]:
        """
        Parse biometry text using RunPod LLM API
        
        Args:
            text: Raw text to parse
            device_type: Optional device type hint
            
        Returns:
            Dict with parsed data, confidence, and metadata
        """
        start_time = time.time()
        
        try:
            # Prepare request payload
            payload = {
                "text": text,
                "device_type": device_type,
                "confidence_threshold": self.config.confidence_threshold
            }
            
            logger.info(f"Calling RunPod LLM API at {self.config.base_url}/parse")
            
            # Make request with retries
            for attempt in range(self.config.max_retries):
                try:
                    response = self.session.post(
                        f"{self.config.base_url}/parse",
                        json=payload,
                        timeout=self.config.timeout
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        processing_time = time.time() - start_time
                        
                        logger.info(f"✅ RunPod LLM API success: confidence={result.get('confidence', 0):.2f}, time={processing_time:.2f}s")
                        
                        return {
                            "success": True,
                            "extracted_data": result.get("extracted_data", {}),
                            "confidence": result.get("confidence", 0.0),
                            "processing_time": processing_time,
                            "method": "runpod_llm",
                            "error": None
                        }
                    else:
                        logger.warning(f"RunPod LLM API error: {response.status_code} - {response.text}")
                        if attempt < self.config.max_retries - 1:
                            await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                            continue
                        else:
                            return {
                                "success": False,
                                "extracted_data": {},
                                "confidence": 0.0,
                                "processing_time": time.time() - start_time,
                                "method": "runpod_llm",
                                "error": f"HTTP {response.status_code}: {response.text}"
                            }
                            
                except requests.exceptions.Timeout:
                    logger.warning(f"RunPod LLM API timeout (attempt {attempt + 1}/{self.config.max_retries})")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                        continue
                    else:
                        return {
                            "success": False,
                            "extracted_data": {},
                            "confidence": 0.0,
                            "processing_time": time.time() - start_time,
                            "method": "runpod_llm",
                            "error": "Request timeout"
                        }
                        
                except requests.exceptions.ConnectionError:
                    logger.warning(f"RunPod LLM API connection error (attempt {attempt + 1}/{self.config.max_retries})")
                    if attempt < self.config.max_retries - 1:
                        await asyncio.sleep(self.config.retry_delay * (attempt + 1))
                        continue
                    else:
                        return {
                            "success": False,
                            "extracted_data": {},
                            "confidence": 0.0,
                            "processing_time": time.time() - start_time,
                            "method": "runpod_llm",
                            "error": "Connection failed"
                        }
                        
        except Exception as e:
            logger.error(f"RunPod LLM API unexpected error: {e}")
            processing_time = time.time() - start_time
            return {
                "success": False,
                "extracted_data": {},
                "confidence": 0.0,
                "processing_time": processing_time,
                "method": "runpod_llm",
                "error": str(e)
            }
    
    async def list_models(self) -> Dict[str, Any]:
        """List available models on RunPod"""
        try:
            response = self.session.get(f"{self.config.base_url}/models")
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to list models: {response.status_code}")
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"Error listing models: {e}")
            return {"error": str(e)}
    
    async def pull_model(self, model_name: str) -> Dict[str, Any]:
        """Pull a model to RunPod"""
        try:
            response = self.session.post(
                f"{self.config.base_url}/models/{model_name}/pull"
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Failed to pull model {model_name}: {response.status_code}")
                return {"error": f"HTTP {response.status_code}"}
        except Exception as e:
            logger.error(f"Error pulling model {model_name}: {e}")
            return {"error": str(e)}

class HybridLLMProcessor:
    """
    Hybrid LLM processor that tries RunPod LLM API first,
    then falls back to local processing
    """
    
    def __init__(self, runpod_config: RunPodLLMConfig = None):
        self.runpod_client = RunPodLLMClient(runpod_config)
        
    async def process_with_hybrid(self, text: str, device_type: str = None) -> Dict[str, Any]:
        """
        Process text with hybrid approach:
        1. Try RunPod LLM API first
        2. Fall back to local processing if needed
        """
        logger.info("🔄 Starting hybrid LLM processing...")
        
        # First, check if RunPod LLM API is available
        health = await self.runpod_client.health_check()
        if health.get("status") == "healthy" and health.get("ollama_available"):
            logger.info("✅ RunPod LLM API is healthy, using cloud processing")
            
            # Try RunPod LLM API
            result = await self.runpod_client.parse_biometry(text, device_type)
            
            if result["success"] and result["confidence"] >= self.runpod_client.config.confidence_threshold:
                logger.info(f"✅ RunPod LLM API success: confidence={result['confidence']:.2f}")
                return result
            else:
                logger.warning(f"⚠️ RunPod LLM API result insufficient: confidence={result['confidence']:.2f}")
                # Continue to fallback
        else:
            logger.warning(f"⚠️ RunPod LLM API unavailable: {health.get('error', 'Unknown error')}")
        
        # No local fallback - RunPod only approach
        logger.error("❌ RunPod LLM API failed and no local fallback available")
        return {
            "success": False,
            "extracted_data": {},
            "confidence": 0.0,
            "processing_time": 0.0,
            "method": "runpod_failed",
            "error": "RunPod LLM API is unavailable. Please check your RunPod instance."
        }

# Global instance for easy access
_hybrid_processor = None

def get_hybrid_processor() -> HybridLLMProcessor:
    """Get or create global hybrid processor instance"""
    global _hybrid_processor
    if _hybrid_processor is None:
        # Use configuration if available
        config_obj = get_config()
        if config_obj:
            config = RunPodLLMConfig(
                base_url=config_obj.BASE_URL,
                timeout=config_obj.TIMEOUT,
                max_retries=config_obj.MAX_RETRIES,
                retry_delay=config_obj.RETRY_DELAY,
                confidence_threshold=config_obj.CONFIDENCE_THRESHOLD
            )
            _hybrid_processor = HybridLLMProcessor(config)
        else:
            _hybrid_processor = HybridLLMProcessor()
    return _hybrid_processor

async def process_with_hybrid_llm(text: str, device_type: str = None) -> Dict[str, Any]:
    """Convenience function for hybrid LLM processing"""
    processor = get_hybrid_processor()
    return await processor.process_with_hybrid(text, device_type)
