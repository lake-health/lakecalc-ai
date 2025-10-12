"""
Base parser class for universal biometry document parsing.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from enum import Enum


class ProcessingMethod(Enum):
    """Processing methods for document parsing."""
    TEXT_EXTRACTION = "text_extraction"
    OCR = "ocr"
    LLM = "llm"
    MANUAL_REVIEW = "manual_review"


@dataclass
class ParsingResult:
    """Result from document parsing."""
    success: bool
    confidence: float  # 0.0 to 1.0
    method: ProcessingMethod
    extracted_data: Dict[str, Any]
    raw_text: Optional[str] = None
    cost: float = 0.0
    processing_time: float = 0.0
    error_message: Optional[str] = None
    warnings: List[str] = None

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


@dataclass
class BiometryData:
    """Structured biometry data extracted from documents."""
    # Eye identification
    eye: str  # "OD" or "OS"
    
    # Core measurements
    axial_length: Optional[float] = None  # mm
    k1: Optional[float] = None  # D
    k2: Optional[float] = None  # D
    k_axis_1: Optional[float] = None  # degrees
    k_axis_2: Optional[float] = None  # degrees
    acd: Optional[float] = None  # mm (anterior chamber depth)
    lt: Optional[float] = None  # mm (lens thickness)
    wtw: Optional[float] = None  # mm (white-to-white)
    cct: Optional[float] = None  # μm (central corneal thickness)
    
    # Demographics (optional)
    age: Optional[int] = None
    gender: Optional[str] = None
    
    # Target refraction
    target_refraction: Optional[float] = None  # D
    
    # SIA (Surgically Induced Astigmatism)
    sia_magnitude: Optional[float] = None  # D
    sia_axis: Optional[float] = None  # degrees
    
    # Quality indicators
    confidence: float = 0.0
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class BaseParser(ABC):
    """Abstract base class for document parsers."""
    
    def __init__(self, cost_tracker=None):
        self.cost_tracker = cost_tracker
        self.method = ProcessingMethod.TEXT_EXTRACTION
    
    @abstractmethod
    def can_parse(self, document_path: str) -> bool:
        """Check if this parser can handle the document type."""
        pass
    
    @abstractmethod
    def parse(self, document_path: str, user_id: str = None) -> ParsingResult:
        """Parse the document and extract biometry data."""
        pass
    
    def validate_extracted_data(self, data: Dict[str, Any]) -> List[str]:
        """Validate extracted data and return warnings."""
        warnings = []
        
        # Check for missing critical data
        if not data.get('axial_length'):
            warnings.append("Missing axial length - critical for IOL calculation")
        if not data.get('k1') or not data.get('k2'):
            warnings.append("Missing keratometry data - critical for IOL calculation")
        
        # Check for reasonable ranges
        al = data.get('axial_length')
        if al and (al < 15.0 or al > 35.0):
            warnings.append(f"Axial length {al:.2f}mm outside normal range (15-35mm)")
        
        k1 = data.get('k1')
        k2 = data.get('k2')
        if k1 and (k1 < 35.0 or k1 > 50.0):
            warnings.append(f"K1 {k1:.2f}D outside normal range (35-50D)")
        if k2 and (k2 < 35.0 or k2 > 50.0):
            warnings.append(f"K2 {k2:.2f}D outside normal range (35-50D)")
        
        # Check for missing optional but important data
        if not data.get('acd'):
            warnings.append("Missing ACD - may affect formula accuracy")
        
        return warnings
    
    def merge_biometry_data(self, od_data: BiometryData, os_data: BiometryData) -> Dict[str, BiometryData]:
        """Merge OD and OS data into a single structure."""
        return {
            "od": od_data,
            "os": os_data
        }
    
    def calculate_k_mean(self, k1: float, k2: float) -> float:
        """Calculate mean keratometry."""
        return (k1 + k2) / 2.0
    
    def calculate_cyl_power(self, k1: float, k2: float) -> float:
        """Calculate cylinder power from K1 and K2."""
        return abs(k1 - k2)
    
    def format_result(self, extracted_data: Dict[str, Any], method: ProcessingMethod, 
                     confidence: float, cost: float = 0.0) -> ParsingResult:
        """Format parsing result with validation."""
        warnings = self.validate_extracted_data(extracted_data)
        
        return ParsingResult(
            success=True,
            confidence=confidence,
            method=method,
            extracted_data=extracted_data,
            cost=cost,
            warnings=warnings
        )
