"""
RunPod LLM API Configuration
Configuration for the hybrid LLM processing setup
"""

import os
from typing import Optional

class RunPodConfig:
    """Configuration for RunPod LLM API integration"""
    
    # RunPod LLM API URL
    # For local development, this might be localhost:8001
    # For production, this would be your RunPod instance URL
    BASE_URL: str = os.getenv(
        "RUNPOD_LLM_API_URL", 
        "https://nko8ymjws3px2s-8001.proxy.runpod.net"  # Your RunPod URL
    )
    
    # API timeout settings
    TIMEOUT: int = int(os.getenv("RUNPOD_LLM_TIMEOUT", "120"))  # 2 minutes
    MAX_RETRIES: int = int(os.getenv("RUNPOD_LLM_MAX_RETRIES", "3"))
    RETRY_DELAY: float = float(os.getenv("RUNPOD_LLM_RETRY_DELAY", "2.0"))
    
    # Confidence threshold for RunPod LLM results
    CONFIDENCE_THRESHOLD: float = float(os.getenv("RUNPOD_LLM_CONFIDENCE_THRESHOLD", "0.8"))
    
    # Enable/disable RunPod LLM API
    ENABLED: bool = os.getenv("RUNPOD_LLM_ENABLED", "true").lower() == "true"
    
    # Fallback to local LLM if RunPod is unavailable
    FALLBACK_TO_LOCAL: bool = os.getenv("RUNPOD_LLM_FALLBACK", "true").lower() == "true"
    
    @classmethod
    def get_config_dict(cls) -> dict:
        """Get configuration as dictionary"""
        return {
            "base_url": cls.BASE_URL,
            "timeout": cls.TIMEOUT,
            "max_retries": cls.MAX_RETRIES,
            "retry_delay": cls.RETRY_DELAY,
            "confidence_threshold": cls.CONFIDENCE_THRESHOLD,
            "enabled": cls.ENABLED,
            "fallback_to_local": cls.FALLBACK_TO_LOCAL
        }
    
    @classmethod
    def is_configured(cls) -> bool:
        """Check if RunPod is properly configured"""
        return (
            cls.BASE_URL and 
            cls.BASE_URL != "http://localhost:8001" and
            cls.ENABLED
        )

# Environment-specific configurations
class DevelopmentConfig(RunPodConfig):
    """Development configuration"""
    BASE_URL = "https://nko8ymjws3px2s-8001.proxy.runpod.net"  # Use RunPod for development
    ENABLED = True  # Enable RunPod for development
    FALLBACK_TO_LOCAL = True

class ProductionConfig(RunPodConfig):
    """Production configuration"""
    # This would be set via environment variables in production
    BASE_URL = os.getenv("RUNPOD_LLM_API_URL", "")
    ENABLED = True
    FALLBACK_TO_LOCAL = True

class RunPodConfig(RunPodConfig):
    """RunPod-specific configuration"""
    BASE_URL = os.getenv("RUNPOD_LLM_API_URL", "")
    ENABLED = True
    FALLBACK_TO_LOCAL = False  # No fallback needed on RunPod itself

def get_config() -> RunPodConfig:
    """Get the appropriate configuration based on environment"""
    environment = os.getenv("ENVIRONMENT", "development").lower()
    
    if environment == "production":
        return ProductionConfig()
    elif environment == "runpod":
        return RunPodConfig()
    else:
        return DevelopmentConfig()
