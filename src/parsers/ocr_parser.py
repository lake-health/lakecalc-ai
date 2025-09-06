"""
OCR-based parser for medical device PDFs and images
Handles Pentacam, IOL Master, Lenstar, Nidek, and other devices
"""

import pytesseract
from pdf2image import convert_from_path
from PIL import Image
import re
import logging
from typing import Dict, List, Optional, Tuple, Union
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class OCRMeasurement:
    """Represents a measurement extracted via OCR"""
    value: float
    unit: str
    confidence: float
    source: str
    raw_text: str

class OCRParser:
    """OCR-based parser for medical device documents"""
    
    def __init__(self):
        self.device_patterns = {
            'pentacam': {
                'manufacturer': 'Oculus',
                'model': 'Pentacam',
                'type': 'topography',
                'identifiers': [r'pentacam', r'oculus', r'scheimpflug'],
                'patterns': {
                    'k1': [
                        # Standard patterns
                        r'K1\s*[:\-\[\]]*\s*(\d+\.?\d*)\s*D?',
                        r'KI\s*[:\-\[\]]*\s*(\d+\.?\d*)\s*D?',
                        # Handle OCR artifacts like "KI [45.30"
                        r'KI\s*[:\-\[\]]*\s*(\d{2})\.(\d{1,2})',
                        r'K1\s*[:\-\[\]]*\s*(\d{2})\.(\d{1,2})',
                        # Handle separated digits like "45 30" -> "45.30"
                        r'KI?\s*[:\-\[\]]*\s*(\d{2})\s*(\d{1,2})\s*D?',
                        # Pentacam specific with mm prefix
                        r'mm\s*K1\s*[:\-\[\]]*\s*(\d+\.?\d*)',
                        r'mm\s*KI\s*[:\-\[\]]*\s*(\d+\.?\d*)'
                    ],
                    'k2': [
                        # Standard patterns
                        r'K2\s*[:\-\[\]]*\s*(\d+\.?\d*)\s*D?',
                        r'k2\s*[:\-\[\]]*\s*(\d+\.?\d*)\s*D?',
                        # Handle OCR artifacts like "k2ae7D" -> "46.7D"
                        r'k2[a-z]*(\d{2})\.?(\d{1,2})\s*D?',
                        r'K2[a-z]*(\d{2})\.?(\d{1,2})\s*D?',
                        # Handle patterns like "k2[7.00" where we need context
                        r'k2\s*[:\-\[\]]*\s*(\d{1,2})\.(\d{1,2})\s*D?',
                        # Pentacam specific with mm prefix
                        r'mm\s*K2\s*[:\-\[\]]*\s*(\d+\.?\d*)',
                        r'mm\s*k2\s*[:\-\[\]]*\s*(\d+\.?\d*)'
                    ],
                    'astigmatism': [
                        r'Astig[:\-\[\]]*\s*(\d+\.?\d*)\s*D?',
                        r'dstig[:\-\[\]]*\s*(\d+\.?\d*)\s*D?',
                        # Handle OCR artifacts like "dstig:[1.4D"
                        r'[Aa]stig[:\-\[\]]*\s*(\d)\.?(\d)\s*D?'
                    ],
                    'axis': [
                        r'(\d{1,3})°',
                        r'@\s*(\d{1,3})°'
                    ]
                }
            },
            'iol_master': {
                'manufacturer': 'Zeiss',
                'model': 'IOL Master',
                'type': 'biometry',
                'identifiers': [r'iol\s*master', r'zeiss', r'optical\s*biometry'],
                'patterns': {
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
            },
            'nidek': {
                'manufacturer': 'Nidek',
                'model': 'AL-Scan',
                'type': 'biometry',
                'identifiers': [r'nidek', r'al[\-\s]*scan'],
                'patterns': {
                    'axial_length': [
                        r'AL\s*[:\-]?\s*(\d+\.?\d*)\s*mm',
                        r'(\d+\.?\d*)\s*mm.*AL'
                    ],
                    'k1': [
                        r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D'
                    ],
                    'k2': [
                        r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D'
                    ]
                }
            },
            'lenstar': {
                'manufacturer': 'Haag-Streit',
                'model': 'Lenstar',
                'type': 'biometry',
                'identifiers': [r'lenstar', r'haag[\-\s]*streit'],
                'patterns': {
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
            }
        }
    
    def parse_file(self, file_path: str) -> Dict:
        """Parse a PDF or image file using OCR"""
        try:
            # Determine file type and extract images
            images = self._extract_images(file_path)
            
            if not images:
                return self._create_error_result("Failed to extract images from file")
            
            # Perform OCR on all images
            ocr_text = ""
            for image in images:
                page_text = self._perform_ocr(image)
                ocr_text += page_text + "\n"
            
            # Detect device type
            device_info = self._detect_device(ocr_text)
            
            # Parse measurements based on device type
            measurements = self._parse_measurements(ocr_text, device_info)
            
            return {
                'success': True,
                'device_info': device_info,
                'measurements': measurements,
                'raw_ocr_text': ocr_text,
                'confidence': self._calculate_overall_confidence(measurements)
            }
            
        except Exception as e:
            logger.error(f"OCR parsing failed: {e}")
            return self._create_error_result(f"OCR parsing failed: {str(e)}")
    
    def _extract_images(self, file_path: str) -> List[Image.Image]:
        """Extract images from PDF or load image file directly"""
        images = []
        
        try:
            file_lower = file_path.lower()
            
            if file_lower.endswith('.pdf'):
                # Convert PDF to images
                images = convert_from_path(file_path, dpi=300)
                logger.info(f"Converted PDF to {len(images)} images")
            
            elif file_lower.endswith(('.png', '.jpg', '.jpeg', '.tiff', '.bmp')):
                # Load image directly
                image = Image.open(file_path)
                images = [image]
                logger.info(f"Loaded image file: {file_path}")
            
            else:
                logger.error(f"Unsupported file type: {file_path}")
                
        except Exception as e:
            logger.error(f"Failed to extract images from {file_path}: {e}")
            
        return images
    
    def _perform_ocr(self, image: Image.Image) -> str:
        """Perform OCR on a single image"""
        try:
            # Configure tesseract for better medical text recognition
            config = '--oem 3 --psm 6 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz.:-°@()[]{}/ '
            
            text = pytesseract.image_to_string(image, config=config)
            return text
            
        except Exception as e:
            logger.error(f"OCR failed on image: {e}")
            return ""
    
    def _detect_device(self, text: str) -> Dict[str, str]:
        """Detect device type from OCR text"""
        text_lower = text.lower()
        
        for device_name, device_config in self.device_patterns.items():
            for identifier in device_config['identifiers']:
                if re.search(identifier, text_lower):
                    return {
                        'manufacturer': device_config['manufacturer'],
                        'model': device_config['model'],
                        'type': device_config['type'],
                        'detected_device': device_name
                    }
        
        return {
            'manufacturer': 'Unknown',
            'model': 'Unknown',
            'type': 'biometry',
            'detected_device': 'unknown'
        }
    
    def _parse_measurements(self, text: str, device_info: Dict) -> Dict:
        """Parse measurements based on device type"""
        device_name = device_info.get('detected_device', 'unknown')
        
        if device_name not in self.device_patterns:
            return self._parse_generic_measurements(text)
        
        device_config = self.device_patterns[device_name]
        measurements = {}
        
        for measurement_type, patterns in device_config['patterns'].items():
            value = self._extract_measurement_with_cleanup(text, patterns, measurement_type)
            if value:
                measurements[measurement_type] = value
        
        # Special handling for bilateral measurements (OD/OS)
        if device_name == 'pentacam':
            measurements.update(self._parse_bilateral_pentacam(text))
        
        return measurements
    
    def _extract_measurement_with_cleanup(self, text: str, patterns: List[str], measurement_type: str) -> Optional[OCRMeasurement]:
        """Extract measurement with OCR cleanup"""
        for pattern in patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            
            for match in matches:
                try:
                    if len(match.groups()) == 1:
                        # Single capture group
                        raw_value = match.group(1)
                        cleaned_value = self._clean_ocr_value(raw_value, measurement_type)
                        
                    elif len(match.groups()) == 2:
                        # Two capture groups (e.g., "45" and "3" -> "45.3")
                        part1, part2 = match.groups()
                        cleaned_value = float(f"{part1}.{part2}")
                        raw_value = f"{part1}{part2}"
                    
                    else:
                        continue
                    
                    if cleaned_value is not None:
                        unit = self._get_unit_for_measurement(measurement_type)
                        confidence = self._calculate_measurement_confidence(raw_value, cleaned_value, measurement_type)
                        
                        return OCRMeasurement(
                            value=cleaned_value,
                            unit=unit,
                            confidence=confidence,
                            source="OCR",
                            raw_text=match.group(0)
                        )
                        
                except (ValueError, AttributeError) as e:
                    logger.debug(f"Failed to parse measurement {match.group(0)}: {e}")
                    continue
        
        return None
    
    def _clean_ocr_value(self, raw_value: str, measurement_type: str) -> Optional[float]:
        """Clean OCR artifacts from measurement values"""
        try:
            # Remove common OCR artifacts
            cleaned = raw_value.replace('O', '0').replace('l', '1').replace('I', '1')
            cleaned = re.sub(r'[^\d.]', '', cleaned)
            
            if not cleaned:
                return None
            
            # Handle missing decimal points based on measurement type
            if measurement_type in ['k1', 'k2']:
                # K-values are typically 40-50 D
                if '.' not in cleaned and len(cleaned) >= 3:
                    # Handle cases like "453" -> "45.3" or "467" -> "46.7"
                    if len(cleaned) == 3:
                        cleaned = f"{cleaned[:2]}.{cleaned[2:]}"
                    elif len(cleaned) == 4:
                        cleaned = f"{cleaned[:2]}.{cleaned[2:]}"
                
                value = float(cleaned)
                
                # Validate K-value range (typically 35-55 D)
                if 35.0 <= value <= 55.0:
                    return value
                
                # Handle OCR errors where values are way off
                # For example, if OCR reads "7.00" but context suggests it should be "46.5"
                if value < 10.0:
                    # Likely missing the first digit, try common K-value prefixes
                    for prefix in ['4', '45', '46', '47']:
                        test_value = float(f"{prefix}.{cleaned.replace('.', '')}")
                        if 35.0 <= test_value <= 55.0:
                            return test_value
                
                return value if 20.0 <= value <= 70.0 else None  # Broader range as fallback
                
            elif measurement_type == 'astigmatism':
                # Astigmatism is typically 0-5 D
                if '.' not in cleaned and len(cleaned) == 2:
                    # Handle cases like "14" -> "1.4"
                    cleaned = f"{cleaned[0]}.{cleaned[1]}"
                
                value = float(cleaned)
                return value if 0.0 <= value <= 10.0 else None
                
            elif measurement_type == 'axial_length':
                # Axial length is typically 20-30 mm
                value = float(cleaned)
                return value if 15.0 <= value <= 35.0 else None
                
            else:
                # Generic cleaning
                return float(cleaned)
                
        except (ValueError, AttributeError):
            return None
    
    def _get_unit_for_measurement(self, measurement_type: str) -> str:
        """Get appropriate unit for measurement type"""
        unit_map = {
            'k1': 'D',
            'k2': 'D', 
            'astigmatism': 'D',
            'axial_length': 'mm',
            'acd': 'mm',
            'cct': 'μm',
            'axis': '°'
        }
        return unit_map.get(measurement_type, '')
    
    def _calculate_measurement_confidence(self, raw_value: str, cleaned_value: float, measurement_type: str) -> float:
        """Calculate confidence score for OCR measurement"""
        confidence = 0.7  # Base confidence for OCR
        
        # Boost confidence for clean extractions
        if '.' in raw_value:
            confidence += 0.1
        
        # Boost confidence for values in expected ranges
        if measurement_type in ['k1', 'k2'] and 40.0 <= cleaned_value <= 50.0:
            confidence += 0.1
        elif measurement_type == 'astigmatism' and 0.5 <= cleaned_value <= 3.0:
            confidence += 0.1
        
        return min(confidence, 1.0)
    
    def _parse_bilateral_pentacam(self, text: str) -> Dict:
        """Parse bilateral Pentacam measurements (OD/OS)"""
        measurements = {}
        
        # Split text into OD and OS sections
        od_section = ""
        os_section = ""
        
        # Look for OD and OS indicators
        lines = text.split('\n')
        current_eye = None
        
        for line in lines:
            line_lower = line.lower()
            if 'od' in line_lower or 'direito' in line_lower or 'right' in line_lower:
                current_eye = 'od'
            elif 'os' in line_lower or 'esquerdo' in line_lower or 'left' in line_lower:
                current_eye = 'os'
            
            if current_eye == 'od':
                od_section += line + "\n"
            elif current_eye == 'os':
                os_section += line + "\n"
        
        # Parse each eye separately
        if od_section:
            od_measurements = self._parse_single_eye_pentacam(od_section, 'OD')
            measurements.update(od_measurements)
        
        if os_section:
            os_measurements = self._parse_single_eye_pentacam(os_section, 'OS')
            measurements.update(os_measurements)
        
        return measurements
    
    def _parse_single_eye_pentacam(self, text: str, eye: str) -> Dict:
        """Parse Pentacam measurements for a single eye"""
        measurements = {}
        
        # Pentacam-specific patterns with OCR cleanup
        patterns = {
            'k1': [
                r'K1\s*[:\-]?\s*(\d+\.?\d*)',
                r'KI\s*[:\-]?\s*(\d{2})(\d)',  # OCR artifact: "KI 453"
                r'Rp.*?K1\s*[:\-]?\s*(\d+\.?\d*)',
                r'Rp.*?KI\s*[:\-]?\s*(\d{2})(\d)'
            ],
            'k2': [
                r'K2\s*[:\-]?\s*(\d+\.?\d*)',
                r'k2\s*[:\-]?\s*(\d{2})(\d)',  # OCR artifact: "k2 467"
                r'Re.*?K2\s*[:\-]?\s*(\d+\.?\d*)',
                r'Re.*?k2\s*[:\-]?\s*(\d{2})(\d)'
            ]
        }
        
        for measurement_type, pattern_list in patterns.items():
            measurement = self._extract_measurement_with_cleanup(text, pattern_list, measurement_type)
            if measurement:
                key = f"{eye.lower()}_{measurement_type}"
                measurements[key] = measurement
        
        return measurements
    
    def _get_unit_for_measurement(self, measurement_type: str) -> str:
        """Get the appropriate unit for a measurement type"""
        unit_map = {
            'k1': 'D',
            'k2': 'D',
            'astigmatism': 'D',
            'axial_length': 'mm',
            'acd': 'mm',
            'cct': 'μm',
            'axis': '°'
        }
        return unit_map.get(measurement_type, '')
    
    def _calculate_measurement_confidence(self, raw_value: str, cleaned_value: float, measurement_type: str) -> float:
        """Calculate confidence score for a measurement"""
        confidence = 0.8  # Base confidence for OCR
        
        # Increase confidence if value is in expected range
        if measurement_type in ['k1', 'k2']:
            if 40.0 <= cleaned_value <= 50.0:
                confidence += 0.1
        elif measurement_type == 'axial_length':
            if 20.0 <= cleaned_value <= 30.0:
                confidence += 0.1
        elif measurement_type == 'astigmatism':
            if 0.0 <= cleaned_value <= 10.0:
                confidence += 0.1
        
        # Decrease confidence if heavy cleanup was needed
        if len(raw_value) != len(str(cleaned_value).replace('.', '')):
            confidence -= 0.1
        
        return max(0.0, min(1.0, confidence))
    
    def _calculate_overall_confidence(self, measurements: Dict) -> float:
        """Calculate overall confidence score"""
        if not measurements:
            return 0.0
        
        confidences = []
        for measurement in measurements.values():
            if isinstance(measurement, OCRMeasurement):
                confidences.append(measurement.confidence)
        
        return sum(confidences) / len(confidences) if confidences else 0.0
    
    def _parse_generic_measurements(self, text: str) -> Dict:
        """Parse measurements from unknown device types"""
        measurements = {}
        
        # Generic patterns for common measurements
        generic_patterns = {
            'k1': [r'K1\s*[:\-]?\s*(\d+\.?\d*)\s*D'],
            'k2': [r'K2\s*[:\-]?\s*(\d+\.?\d*)\s*D'],
            'axial_length': [r'AL\s*[:\-]?\s*(\d+\.?\d*)\s*mm'],
            'acd': [r'ACD\s*[:\-]?\s*(\d+\.?\d*)\s*mm']
        }
        
        for measurement_type, patterns in generic_patterns.items():
            measurement = self._extract_measurement_with_cleanup(text, patterns, measurement_type)
            if measurement:
                measurements[measurement_type] = measurement
        
        return measurements
    
    def _create_error_result(self, error_message: str) -> Dict:
        """Create error result structure"""
        return {
            'success': False,
            'error': error_message,
            'device_info': {
                'manufacturer': 'Unknown',
                'model': 'Unknown',
                'type': 'biometry'
            },
            'measurements': {},
            'confidence': 0.0
        }

