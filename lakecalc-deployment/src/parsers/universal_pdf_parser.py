#!/usr/bin/env python3
"""
Universal PDF Parser for Biometry Devices
Supports: Pentacam, IOL Master, Galilei, OPD-Scan, Lenstar, Eyestar, and more
Enhanced with OCR support for image-based PDFs
"""

import re
import logging
import re
import pdfplumber
import PyPDF2
from dataclasses import dataclass
from datetime import datetime

# Initialize logger first
logger = logging.getLogger(__name__)

# Temporarily disable OCR import to resolve deployment issues
OCR_AVAILABLE = False
logger.info("OCR temporarily disabled for stable deployment")

@dataclass
class BiometryMeasurement:
    """Single biometry measurement"""
    value: float
    unit: str
    confidence: float = 1.0
    source: str = ""

@dataclass
class ParsedBiometry:
    """Parsed biometry data from PDF"""
    # Required measurements
    axial_length: Optional[BiometryMeasurement] = None
    k1: Optional[BiometryMeasurement] = None
    k2: Optional[BiometryMeasurement] = None
    acd: Optional[BiometryMeasurement] = None
    
    # Optional measurements
    lens_thickness: Optional[BiometryMeasurement] = None
    cct: Optional[BiometryMeasurement] = None
    wtw: Optional[BiometryMeasurement] = None
    pupil_diameter: Optional[BiometryMeasurement] = None
    
    # Device information
    device_manufacturer: str = ""
    device_model: str = ""
    software_version: str = ""
    measurement_date: Optional[datetime] = None
    
    # Patient information (if available)
    patient_id: str = ""
    patient_name: str = ""
    patient_age: Optional[int] = None
    eye: str = ""  # OD, OS, or both
    
    # Quality indicators
    parse_confidence: float = 0.0
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []

class UniversalPDFParser:
    """Universal parser for all biometry device PDFs"""
    
    def __init__(self):
        """Initialize parser with device patterns"""
        self.device_patterns = self._load_device_patterns()
        self.measurement_patterns = self._load_measurement_patterns()
        
    def parse_pdf(self, pdf_path: str) -> ParsedBiometry:
        """Parse PDF and extract biometry data with OCR fallback"""
        try:
            # Try traditional text extraction first
            text = self._extract_text_pdfplumber(pdf_path)
            
            if not text or len(text.strip()) < 100:
                # Fallback to PyPDF2
                text = self._extract_text_pypdf2(pdf_path)
            
            # If text extraction fails or produces minimal text, use OCR
            if not text or len(text.strip()) < 100:
                logger.info("Text extraction failed or minimal text found, attempting OCR...")
                return self._parse_with_ocr(pdf_path)
            
            # Detect device type from extracted text
            device_info = self._detect_device(text)
            
            # Parse based on device type
            if device_info['manufacturer'].lower() == 'oculus':
                result = self._parse_pentacam(text, device_info)
            elif device_info['manufacturer'].lower() == 'zeiss':
                result = self._parse_iol_master(text, device_info)
            elif device_info['manufacturer'].lower() == 'ziemer':
                result = self._parse_galilei(text, device_info)
            elif device_info['manufacturer'].lower() == 'nidek':
                result = self._parse_opd_scan(text, device_info)
            elif device_info['manufacturer'].lower() == 'haag-streit':
                if 'lenstar' in device_info['model'].lower():
                    result = self._parse_lenstar(text, device_info)
                else:
                    result = self._parse_eyestar(text, device_info)
            elif device_info['manufacturer'].lower() == 'topcon':
                result = self._parse_aladdin(text, device_info)
            else:
                # Generic parsing for unknown devices
                result = self._parse_generic(text, device_info)
            
            # If traditional parsing failed to extract key measurements, try OCR
            if not self._has_key_measurements(result) and OCR_AVAILABLE:
                logger.info("Traditional parsing failed to extract key measurements, attempting OCR...")
                ocr_result = self._parse_with_ocr(pdf_path)
                if self._has_key_measurements(ocr_result):
                    return ocr_result
            
            return result
                
        except Exception as e:
            logger.error(f"PDF parsing failed: {e}")
            # Try OCR as last resort
            if OCR_AVAILABLE:
                try:
                    logger.info("Traditional parsing failed completely, attempting OCR as last resort...")
                    return self._parse_with_ocr(pdf_path)
                except Exception as ocr_e:
                    logger.error(f"OCR parsing also failed: {ocr_e}")
            
            result = ParsedBiometry()
            result.warnings.append(f"Parsing failed: {str(e)}")
            return result
    
    def _parse_with_ocr(self, pdf_path: str) -> ParsedBiometry:
        """Parse PDF using OCR with graceful fallback"""
        if not OCR_AVAILABLE:
            logger.warning("OCR not available, returning empty result with warning")
            result = ParsedBiometry()
            result.warnings = ["OCR parsing not available - install tesseract and pytesseract for image-based PDF support"]
            return result
        
        try:
            ocr_parser = OCRParser()
            ocr_result = ocr_parser.parse_file(pdf_path)
            
            if not ocr_result['success']:
                raise ValueError(f"OCR parsing failed: {ocr_result.get('error', 'Unknown error')}")
            
            # Convert OCR result to ParsedBiometry format
            result = ParsedBiometry()
            
            # Set device information
            device_info = ocr_result['device_info']
            result.device_manufacturer = device_info['manufacturer']
            result.device_model = device_info['model']
            
            # Convert OCR measurements to BiometryMeasurement objects
            measurements = ocr_result['measurements']
            
            for key, ocr_measurement in measurements.items():
                if isinstance(ocr_measurement, OCRMeasurement):
                    bio_measurement = BiometryMeasurement(
                        value=ocr_measurement.value,
                        unit=ocr_measurement.unit,
                        confidence=ocr_measurement.confidence,
                        source=f"OCR-{ocr_measurement.source}"
                    )
                    
                    # Map OCR measurement keys to ParsedBiometry attributes
                    if key in ['k1', 'od_k1']:
                        result.k1 = bio_measurement
                    elif key in ['k2', 'od_k2']:
                        result.k2 = bio_measurement
                    elif key == 'axial_length':
                        result.axial_length = bio_measurement
                    elif key == 'acd':
                        result.acd = bio_measurement
                    elif key == 'cct':
                        result.cct = bio_measurement
                    # Handle bilateral measurements
                    elif key == 'os_k1' and not result.k1:
                        result.k1 = bio_measurement
                    elif key == 'os_k2' and not result.k2:
                        result.k2 = bio_measurement
            
            # Set overall confidence
            result.parse_confidence = ocr_result['confidence']
            
            # Add OCR-specific information
            result.warnings = [f"Parsed using OCR (confidence: {result.parse_confidence:.2f})"]
            
            return result
            
        except Exception as e:
            logger.error(f"OCR parsing failed: {e}")
            result = ParsedBiometry()
            result.warnings = [f"OCR parsing failed: {str(e)}"]
            return result
    
    def _has_key_measurements(self, result: ParsedBiometry) -> bool:
        """Check if result has key measurements (K1, K2, or AL)"""
        return bool(result.k1 or result.k2 or result.axial_length)
    
    def _extract_text_pdfplumber(self, pdf_path: str) -> str:
        """Extract text using pdfplumber"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = ""
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return text
        except Exception as e:
            logger.warning(f"pdfplumber extraction failed: {e}")
            return ""
    
    def _extract_text_pypdf2(self, pdf_path: str) -> str:
        """Extract text using PyPDF2"""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                text = ""
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                return text
        except Exception as e:
            logger.warning(f"PyPDF2 extraction failed: {e}")
            return ""
    
    def _detect_device(self, text: str) -> Dict[str, str]:
        """Detect device manufacturer and model from text"""
        text_lower = text.lower()
        
        # Check each device pattern
        for pattern_info in self.device_patterns:
            for pattern in pattern_info['patterns']:
                if re.search(pattern, text_lower):
                    return {
                        'manufacturer': pattern_info['manufacturer'],
                        'model': pattern_info['model'],
                        'type': pattern_info['type']
                    }
        
        # Default unknown device
        return {
            'manufacturer': 'Unknown',
            'model': 'Unknown',
            'type': 'biometry'
        }
    
    def _parse_pentacam(self, text: str, device_info: Dict) -> ParsedBiometry:
        """Parse Pentacam PDF"""
        result = ParsedBiometry()
        result.device_manufacturer = device_info['manufacturer']
        result.device_model = device_info['model']
        
        # Extract patient information
        result.patient_name = self._extract_patient_name(text)
        result.patient_id = self._extract_patient_id(text)
        result.eye = self._extract_eye(text)
        
        # Pentacam-specific patterns
        patterns = {
            'k1': [
                r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Steep\s*K\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'K\s*steep\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'k2': [
                r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Flat\s*K\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'K\s*flat\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'ekr_k1': [
                r'EKR\s*K1\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'EKR\s*steep\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'ekr_k2': [
                r'EKR\s*K2\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'EKR\s*flat\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'acd': [
                r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                r'Anterior\s*Chamber\s*Depth\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'cct': [
                r'CCT\s*[:\-]?\s*(\d+\.?\d*)\s*[μu]?m',
                r'Central\s*Corneal\s*Thickness\s*[:\-]?\s*(\d+\.?\d*)\s*[μu]?m'
            ]
        }
        
        # Extract measurements with preference for EKR values
        ekr_k1 = self._extract_measurement(text, patterns['ekr_k1'])
        ekr_k2 = self._extract_measurement(text, patterns['ekr_k2'])
        
        if ekr_k1 and ekr_k2:
            # Use EKR values (preferred for IOL calculations)
            result.k1 = BiometryMeasurement(ekr_k1, "D", 1.0, "EKR")
            result.k2 = BiometryMeasurement(ekr_k2, "D", 1.0, "EKR")
        else:
            # Use standard K values
            k1 = self._extract_measurement(text, patterns['k1'])
            k2 = self._extract_measurement(text, patterns['k2'])
            if k1: result.k1 = BiometryMeasurement(k1, "D", 0.8, "Standard K")
            if k2: result.k2 = BiometryMeasurement(k2, "D", 0.8, "Standard K")
        
        # Extract other measurements
        acd = self._extract_measurement(text, patterns['acd'])
        if acd: result.acd = BiometryMeasurement(acd, "mm", 0.9, "Pentacam")
        
        cct = self._extract_measurement(text, patterns['cct'])
        if cct: result.cct = BiometryMeasurement(cct, "μm", 0.9, "Pentacam")
        
        # Calculate confidence
        result.parse_confidence = self._calculate_confidence(result)
        
        return result
    
    def _parse_iol_master(self, text: str, device_info: Dict) -> ParsedBiometry:
        """Parse IOL Master PDF"""
        result = ParsedBiometry()
        result.device_manufacturer = device_info['manufacturer']
        result.device_model = device_info['model']
        
        # Extract patient information
        result.patient_name = self._extract_patient_name(text)
        result.patient_id = self._extract_patient_id(text)
        result.eye = self._extract_eye(text)
        
        # IOL Master patterns
        patterns = {
            'axial_length': [
                r'AL\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                r'Axial\s*Length\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                r'L\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'k1': [
                r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Steep\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'k2': [
                r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Flat\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'acd': [
                r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                r'Anterior\s*Chamber\s*Depth\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'lens_thickness': [
                r'LT\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                r'Lens\s*Thickness\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'wtw': [
                r'WTW\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                r'White\s*to\s*White\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'cct': [
                r'CCT\s*[:\-]?\s*(\d+\.?\d*)\s*[μu]?m',
                r'Central\s*Corneal\s*Thickness\s*[:\-]?\s*(\d+\.?\d*)\s*[μu]?m'
            ]
        }
        
        # Extract measurements
        al = self._extract_measurement(text, patterns['axial_length'])
        if al: result.axial_length = BiometryMeasurement(al, "mm", 1.0, "IOL Master")
        
        k1 = self._extract_measurement(text, patterns['k1'])
        if k1: result.k1 = BiometryMeasurement(k1, "D", 1.0, "IOL Master")
        
        k2 = self._extract_measurement(text, patterns['k2'])
        if k2: result.k2 = BiometryMeasurement(k2, "D", 1.0, "IOL Master")
        
        acd = self._extract_measurement(text, patterns['acd'])
        if acd: result.acd = BiometryMeasurement(acd, "mm", 1.0, "IOL Master")
        
        lt = self._extract_measurement(text, patterns['lens_thickness'])
        if lt: result.lens_thickness = BiometryMeasurement(lt, "mm", 0.9, "IOL Master")
        
        wtw = self._extract_measurement(text, patterns['wtw'])
        if wtw: result.wtw = BiometryMeasurement(wtw, "mm", 0.8, "IOL Master")
        
        cct = self._extract_measurement(text, patterns['cct'])
        if cct: result.cct = BiometryMeasurement(cct, "μm", 0.8, "IOL Master")
        
        result.parse_confidence = self._calculate_confidence(result)
        return result
    
    def _parse_galilei(self, text: str, device_info: Dict) -> ParsedBiometry:
        """Parse Galilei PDF"""
        result = ParsedBiometry()
        result.device_manufacturer = device_info['manufacturer']
        result.device_model = device_info['model']
        
        # Galilei patterns (similar to Pentacam but different format)
        patterns = {
            'k1': [
                r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Steep\s*K\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'k2': [
                r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Flat\s*K\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'acd': [
                r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'cct': [
                r'CCT\s*[:\-]?\s*(\d+\.?\d*)\s*[μu]?m'
            ]
        }
        
        # Extract measurements
        k1 = self._extract_measurement(text, patterns['k1'])
        if k1: result.k1 = BiometryMeasurement(k1, "D", 0.9, "Galilei")
        
        k2 = self._extract_measurement(text, patterns['k2'])
        if k2: result.k2 = BiometryMeasurement(k2, "D", 0.9, "Galilei")
        
        acd = self._extract_measurement(text, patterns['acd'])
        if acd: result.acd = BiometryMeasurement(acd, "mm", 0.8, "Galilei")
        
        cct = self._extract_measurement(text, patterns['cct'])
        if cct: result.cct = BiometryMeasurement(cct, "μm", 0.9, "Galilei")
        
        result.parse_confidence = self._calculate_confidence(result)
        return result
    
    def _parse_opd_scan(self, text: str, device_info: Dict) -> ParsedBiometry:
        """Parse OPD-Scan PDF"""
        result = ParsedBiometry()
        result.device_manufacturer = device_info['manufacturer']
        result.device_model = device_info['model']
        
        # OPD-Scan patterns
        patterns = {
            'axial_length': [
                r'AL\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                r'Axial\s*Length\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'k1': [
                r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Steep\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'k2': [
                r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Flat\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'acd': [
                r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ]
        }
        
        # Extract measurements
        al = self._extract_measurement(text, patterns['axial_length'])
        if al: result.axial_length = BiometryMeasurement(al, "mm", 0.9, "OPD-Scan")
        
        k1 = self._extract_measurement(text, patterns['k1'])
        if k1: result.k1 = BiometryMeasurement(k1, "D", 0.9, "OPD-Scan")
        
        k2 = self._extract_measurement(text, patterns['k2'])
        if k2: result.k2 = BiometryMeasurement(k2, "D", 0.9, "OPD-Scan")
        
        acd = self._extract_measurement(text, patterns['acd'])
        if acd: result.acd = BiometryMeasurement(acd, "mm", 0.8, "OPD-Scan")
        
        result.parse_confidence = self._calculate_confidence(result)
        return result
    
    def _parse_lenstar(self, text: str, device_info: Dict) -> ParsedBiometry:
        """Parse Lenstar PDF"""
        result = ParsedBiometry()
        result.device_manufacturer = device_info['manufacturer']
        result.device_model = device_info['model']
        
        # Lenstar patterns
        patterns = {
            'axial_length': [
                r'AL\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                r'Axial\s*Length\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'k1': [
                r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Steep\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'k2': [
                r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Flat\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'acd': [
                r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'lens_thickness': [
                r'LT\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'cct': [
                r'CCT\s*[:\-]?\s*(\d+\.?\d*)\s*[μu]?m'
            ]
        }
        
        # Extract measurements
        al = self._extract_measurement(text, patterns['axial_length'])
        if al: result.axial_length = BiometryMeasurement(al, "mm", 1.0, "Lenstar")
        
        k1 = self._extract_measurement(text, patterns['k1'])
        if k1: result.k1 = BiometryMeasurement(k1, "D", 1.0, "Lenstar")
        
        k2 = self._extract_measurement(text, patterns['k2'])
        if k2: result.k2 = BiometryMeasurement(k2, "D", 1.0, "Lenstar")
        
        acd = self._extract_measurement(text, patterns['acd'])
        if acd: result.acd = BiometryMeasurement(acd, "mm", 1.0, "Lenstar")
        
        lt = self._extract_measurement(text, patterns['lens_thickness'])
        if lt: result.lens_thickness = BiometryMeasurement(lt, "mm", 0.9, "Lenstar")
        
        cct = self._extract_measurement(text, patterns['cct'])
        if cct: result.cct = BiometryMeasurement(cct, "μm", 0.9, "Lenstar")
        
        result.parse_confidence = self._calculate_confidence(result)
        return result
    
    def _parse_eyestar(self, text: str, device_info: Dict) -> ParsedBiometry:
        """Parse Eyestar PDF"""
        result = ParsedBiometry()
        result.device_manufacturer = device_info['manufacturer']
        result.device_model = device_info['model']
        
        # Similar to Lenstar patterns
        patterns = {
            'axial_length': [
                r'AL\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'k1': [
                r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'k2': [
                r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'acd': [
                r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ]
        }
        
        # Extract measurements
        al = self._extract_measurement(text, patterns['axial_length'])
        if al: result.axial_length = BiometryMeasurement(al, "mm", 0.9, "Eyestar")
        
        k1 = self._extract_measurement(text, patterns['k1'])
        if k1: result.k1 = BiometryMeasurement(k1, "D", 0.9, "Eyestar")
        
        k2 = self._extract_measurement(text, patterns['k2'])
        if k2: result.k2 = BiometryMeasurement(k2, "D", 0.9, "Eyestar")
        
        acd = self._extract_measurement(text, patterns['acd'])
        if acd: result.acd = BiometryMeasurement(acd, "mm", 0.9, "Eyestar")
        
        result.parse_confidence = self._calculate_confidence(result)
        return result
    
    def _parse_aladdin(self, text: str, device_info: Dict) -> ParsedBiometry:
        """Parse Topcon Aladdin PDF"""
        result = ParsedBiometry()
        result.device_manufacturer = device_info['manufacturer']
        result.device_model = device_info['model']
        
        # Aladdin patterns
        patterns = {
            'axial_length': [
                r'AL\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'k1': [
                r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'k2': [
                r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'acd': [
                r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ]
        }
        
        # Extract measurements
        al = self._extract_measurement(text, patterns['axial_length'])
        if al: result.axial_length = BiometryMeasurement(al, "mm", 0.9, "Aladdin")
        
        k1 = self._extract_measurement(text, patterns['k1'])
        if k1: result.k1 = BiometryMeasurement(k1, "D", 0.9, "Aladdin")
        
        k2 = self._extract_measurement(text, patterns['k2'])
        if k2: result.k2 = BiometryMeasurement(k2, "D", 0.9, "Aladdin")
        
        acd = self._extract_measurement(text, patterns['acd'])
        if acd: result.acd = BiometryMeasurement(acd, "mm", 0.8, "Aladdin")
        
        result.parse_confidence = self._calculate_confidence(result)
        return result
    
    def _parse_generic(self, text: str, device_info: Dict) -> ParsedBiometry:
        """Generic parsing for unknown devices"""
        result = ParsedBiometry()
        result.device_manufacturer = device_info['manufacturer']
        result.device_model = device_info['model']
        
        # Generic patterns that work for most devices
        patterns = {
            'axial_length': [
                r'(?:AL|Axial\s*Length)\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                r'L\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'k1': [
                r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Steep\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'k2': [
                r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D',
                r'Flat\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'acd': [
                r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ]
        }
        
        # Extract measurements with lower confidence
        al = self._extract_measurement(text, patterns['axial_length'])
        if al: result.axial_length = BiometryMeasurement(al, "mm", 0.7, "Generic")
        
        k1 = self._extract_measurement(text, patterns['k1'])
        if k1: result.k1 = BiometryMeasurement(k1, "D", 0.7, "Generic")
        
        k2 = self._extract_measurement(text, patterns['k2'])
        if k2: result.k2 = BiometryMeasurement(k2, "D", 0.7, "Generic")
        
        acd = self._extract_measurement(text, patterns['acd'])
        if acd: result.acd = BiometryMeasurement(acd, "mm", 0.6, "Generic")
        
        result.warnings.append("Unknown device type - using generic parsing")
        result.parse_confidence = self._calculate_confidence(result) * 0.8
        return result
    
    def _extract_measurement(self, text: str, patterns: List[str]) -> Optional[float]:
        """Extract measurement value using multiple patterns"""
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    value = float(match.group(1))
                    # Basic validation
                    if self._validate_measurement(value, pattern):
                        return value
                except ValueError:
                    continue
        return None
    
    def _validate_measurement(self, value: float, pattern: str) -> bool:
        """Basic validation of extracted measurements"""
        # Axial length validation
        if 'axial' in pattern.lower() or 'al' in pattern.lower():
            return 15.0 <= value <= 35.0
        
        # Keratometry validation
        if any(k in pattern.lower() for k in ['k1', 'k2', 'steep', 'flat']):
            return 35.0 <= value <= 55.0
        
        # ACD validation
        if 'acd' in pattern.lower():
            return 1.5 <= value <= 5.0
        
        # CCT validation
        if 'cct' in pattern.lower():
            return 400 <= value <= 700
        
        # Default validation
        return value > 0
    
    def _extract_patient_name(self, text: str) -> str:
        """Extract patient name from text"""
        patterns = [
            r'Patient\s*[:\-]?\s*([A-Za-z\s,]+)',
            r'Name\s*[:\-]?\s*([A-Za-z\s,]+)',
            r'Patient\s*Name\s*[:\-]?\s*([A-Za-z\s,]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if len(name) > 2 and len(name) < 50:
                    return name
        return ""
    
    def _extract_patient_id(self, text: str) -> str:
        """Extract patient ID from text"""
        patterns = [
            r'ID\s*[:\-]?\s*([A-Za-z0-9\-]+)',
            r'Patient\s*ID\s*[:\-]?\s*([A-Za-z0-9\-]+)',
            r'MRN\s*[:\-]?\s*([A-Za-z0-9\-]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return ""
    
    def _extract_eye(self, text: str) -> str:
        """Extract eye (OD/OS) from text"""
        if re.search(r'\bOD\b', text, re.IGNORECASE):
            return "OD"
        elif re.search(r'\bOS\b', text, re.IGNORECASE):
            return "OS"
        elif re.search(r'\bright\b', text, re.IGNORECASE):
            return "OD"
        elif re.search(r'\bleft\b', text, re.IGNORECASE):
            return "OS"
        return ""
    
    def _calculate_confidence(self, result: ParsedBiometry) -> float:
        """Calculate overall parsing confidence"""
        confidence = 0.0
        total_weight = 0.0
        
        # Weight measurements by importance
        measurements = [
            (result.axial_length, 0.3),  # Most important
            (result.k1, 0.25),
            (result.k2, 0.25),
            (result.acd, 0.2)
        ]
        
        for measurement, weight in measurements:
            if measurement:
                confidence += measurement.confidence * weight
                total_weight += weight
        
        if total_weight > 0:
            return confidence / total_weight
        return 0.0
    
    def _load_device_patterns(self) -> List[Dict]:
        """Load device detection patterns"""
        return [
            {
                'manufacturer': 'Oculus',
                'model': 'Pentacam',
                'type': 'topography',
                'patterns': [
                    r'pentacam',
                    r'oculus',
                    r'scheimpflug',
                    r'ekr'
                ]
            },
            {
                'manufacturer': 'Zeiss',
                'model': 'IOL Master',
                'type': 'biometry',
                'patterns': [
                    r'iol\s*master',
                    r'zeiss',
                    r'carl\s*zeiss'
                ]
            },
            {
                'manufacturer': 'Ziemer',
                'model': 'Galilei',
                'type': 'topography',
                'patterns': [
                    r'galilei',
                    r'ziemer'
                ]
            },
            {
                'manufacturer': 'Nidek',
                'model': 'OPD-Scan',
                'type': 'topography',
                'patterns': [
                    r'opd[\-\s]*scan',
                    r'nidek',
                    r'al[\-\s]*scan'
                ]
            },
            {
                'manufacturer': 'Haag-Streit',
                'model': 'Lenstar',
                'type': 'biometry',
                'patterns': [
                    r'lenstar',
                    r'haag[\-\s]*streit'
                ]
            },
            {
                'manufacturer': 'Haag-Streit',
                'model': 'Eyestar',
                'type': 'biometry',
                'patterns': [
                    r'eyestar',
                    r'eye[\-\s]*star'
                ]
            },
            {
                'manufacturer': 'Topcon',
                'model': 'Aladdin',
                'type': 'biometry',
                'patterns': [
                    r'aladdin',
                    r'topcon'
                ]
            }
        ]
    
    def _load_measurement_patterns(self) -> Dict:
        """Load measurement extraction patterns"""
        return {
            'axial_length': [
                r'(?:AL|Axial\s*Length)\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ],
            'keratometry': [
                r'K[12]?\s*[:\-]?\s*(\d+\.?\d*)\s*D'
            ],
            'acd': [
                r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm'
            ]
        }
    
    def to_dict(self, result: ParsedBiometry) -> Dict:
        """Convert ParsedBiometry to dictionary"""
        def measurement_to_dict(measurement):
            if measurement:
                return {
                    'value': measurement.value,
                    'unit': measurement.unit,
                    'confidence': measurement.confidence,
                    'source': measurement.source
                }
            return None
        
        return {
            'axial_length': measurement_to_dict(result.axial_length),
            'k1': measurement_to_dict(result.k1),
            'k2': measurement_to_dict(result.k2),
            'acd': measurement_to_dict(result.acd),
            'lens_thickness': measurement_to_dict(result.lens_thickness),
            'cct': measurement_to_dict(result.cct),
            'wtw': measurement_to_dict(result.wtw),
            'pupil_diameter': measurement_to_dict(result.pupil_diameter),
            'device_info': {
                'manufacturer': result.device_manufacturer,
                'model': result.device_model,
                'software_version': result.software_version
            },
            'patient_info': {
                'id': result.patient_id,
                'name': result.patient_name,
                'age': result.patient_age,
                'eye': result.eye
            },
            'quality': {
                'parse_confidence': result.parse_confidence,
                'warnings': result.warnings
            }
        }

