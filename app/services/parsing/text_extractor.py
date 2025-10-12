"""
Text extraction from PDF documents and images.
"""

import io
import logging
from pathlib import Path
from typing import Dict, Any, Optional
import re

try:
    import PyPDF2
    import pdfplumber
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    MUPDF_AVAILABLE = True
except ImportError:
    MUPDF_AVAILABLE = False

from .base_parser import BaseParser, ProcessingMethod, ParsingResult

logger = logging.getLogger(__name__)


class TextExtractor(BaseParser):
    """Extract text from PDF documents and images."""
    
    def __init__(self, cost_tracker=None):
        super().__init__(cost_tracker)
        self.method = ProcessingMethod.TEXT_EXTRACTION
    
    def can_parse(self, document_path: str) -> bool:
        """Check if we can extract text from this document."""
        path = Path(document_path)
        
        # Check file extension
        if path.suffix.lower() in ['.pdf', '.txt']:
            return True
        
        # Check if it's a readable text file
        try:
            with open(path, 'r', encoding='utf-8') as f:
                f.read(100)  # Read first 100 chars
            return True
        except:
            return False
    
    def parse(self, document_path: str, user_id: str = None) -> ParsingResult:
        """Extract text from document."""
        import time
        start_time = time.time()
        
        try:
            path = Path(document_path)
            raw_text = ""
            confidence = 0.0
            
            if path.suffix.lower() == '.pdf':
                raw_text, confidence = self._extract_from_pdf(path)
            elif path.suffix.lower() == '.txt':
                raw_text, confidence = self._extract_from_text(path)
            else:
                # Try as text file
                raw_text, confidence = self._extract_from_text(path)
            
            # For image files, always return failure to trigger OCR fallback
            if path.suffix.lower() in ['.png', '.jpg', '.jpeg']:
                return ParsingResult(
                    success=False,
                    confidence=0.0,
                    method=self.method,
                    extracted_data={},
                    raw_text=raw_text,
                    error_message="Image file - requires OCR processing"
                )
            
            if not raw_text or confidence < 0.5:
                return ParsingResult(
                    success=False,
                    confidence=confidence,
                    method=self.method,
                    extracted_data={},
                    raw_text=raw_text,
                    error_message="Low confidence text extraction"
                )
            
            # Parse biometry data from text
            extracted_data = self._parse_biometry_text(raw_text)
            
            processing_time = time.time() - start_time
            
            result = self.format_result(
                extracted_data=extracted_data,
                method=self.method,
                confidence=confidence,
                cost=0.0  # Text extraction is free
            )
            
            result.raw_text = raw_text
            result.processing_time = processing_time
            
            return result
            
        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return ParsingResult(
                success=False,
                confidence=0.0,
                method=self.method,
                extracted_data={},
                error_message=str(e)
            )
    
    def _extract_from_pdf(self, path: Path) -> tuple[str, float]:
        """Extract text from PDF using multiple methods."""
        text = ""
        confidence = 0.0
        
        # Try pdfplumber first (better for tables and structured data)
        if PDF_AVAILABLE:
            try:
                with pdfplumber.open(path) as pdf:
                    for page in pdf.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                
                if text.strip():
                    confidence = 0.9  # High confidence for successful extraction
                    logger.info(f"Extracted text from PDF using pdfplumber: {len(text)} chars")
                    return text, confidence
            except Exception as e:
                logger.warning(f"pdfplumber failed: {e}")
        
        # Try PyMuPDF as fallback
        if MUPDF_AVAILABLE:
            try:
                doc = fitz.open(path)
                for page_num in range(len(doc)):
                    page = doc.load_page(page_num)
                    page_text = page.get_text()
                    if page_text:
                        text += page_text + "\n"
                doc.close()
                
                if text.strip():
                    confidence = 0.8
                    logger.info(f"Extracted text from PDF using PyMuPDF: {len(text)} chars")
                    return text, confidence
            except Exception as e:
                logger.warning(f"PyMuPDF failed: {e}")
        
        # Try PyPDF2 as last resort
        if PDF_AVAILABLE:
            try:
                with open(path, 'rb') as file:
                    pdf_reader = PyPDF2.PdfReader(file)
                    for page in pdf_reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                
                if text.strip():
                    confidence = 0.7
                    logger.info(f"Extracted text from PDF using PyPDF2: {len(text)} chars")
                    return text, confidence
            except Exception as e:
                logger.warning(f"PyPDF2 failed: {e}")
        
        return text, confidence
    
    def _extract_from_text(self, path: Path) -> tuple[str, float]:
        """Extract text from text file."""
        try:
            # Try different encodings
            encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
            
            for encoding in encodings:
                try:
                    with open(path, 'r', encoding=encoding) as f:
                        text = f.read()
                    
                    if text.strip():
                        confidence = 0.95  # Very high confidence for text files
                        logger.info(f"Extracted text from file: {len(text)} chars")
                        return text, confidence
                except UnicodeDecodeError:
                    continue
            
            return "", 0.0
            
        except Exception as e:
            logger.error(f"Text file extraction failed: {e}")
            return "", 0.0
    
    def _parse_biometry_text(self, text: str) -> Dict[str, Any]:
        """Parse biometry data from extracted text."""
        extracted_data = {}
        
        # Normalize text for better pattern matching
        text_normalized = text.lower().replace('\n', ' ').replace('\r', ' ')
        text_normalized = re.sub(r'\s+', ' ', text_normalized)
        
        # Patterns for common biometry measurements (updated for European decimal notation)
        patterns = {
            'axial_length': [
                r'al\s*\[mm\]\s*(\d+[,.]?\d*)',  # Eyestar format: AL [mm] 25.25
                r'axial\s+length[:\s]*(\d+[,.]?\d*)\s*mm',
                r'al[:\s]*(\d+[,.]?\d*)\s*mm',
                r'length[:\s]*(\d+[,.]?\d*)\s*mm'
            ],
            'k1': [
                r'k1\s*\[d/mm/\]\s*(\d+[,.]?\d*)/[0-9]+[,.]?[0-9]*@\s*[0-9]+',  # Eyestar: K1 [D/mm/] 42.60/7.92@ 14
                r'k1\s*\[d/mm/°\]\s*(\d+[,.]?\d*)/[0-9]+[,.]?[0-9]*@\s*[0-9]+',  # Eyestar: K1 [D/mm/°] 42.60/7.92@ 14
                r'k1[:\s]*(\d+[,.]?\d*)\s*d',
                r'keratometry\s+1[:\s]*(\d+[,.]?\d*)',
                r'flat\s+keratometry[:\s]*(\d+[,.]?\d*)',
                r'k1[:\s]*(\d+[,.]?\d*)\s*diopter',
                r'flat[:\s]*(\d+[,.]?\d*)\s*d'
            ],
            'k2': [
                r'k2\s*\[d/mm/\]\s*(\d+[,.]?\d*)/[0-9]+[,.]?[0-9]*@\s*[0-9]+',  # Eyestar: K2 [D/mm/] 43.61/7.74@ 104
                r'k2\s*\[d/mm/°\]\s*(\d+[,.]?\d*)/[0-9]+[,.]?[0-9]*@\s*[0-9]+',  # Eyestar: K2 [D/mm/°] 43.61/7.74@ 104
                r'k2[:\s]*(\d+[,.]?\d*)\s*d',
                r'keratometry\s+2[:\s]*(\d+[,.]?\d*)',
                r'steep\s+keratometry[:\s]*(\d+[,.]?\d*)',
                r'k2[:\s]*(\d+[,.]?\d*)\s*diopter',
                r'steep[:\s]*(\d+[,.]?\d*)\s*d'
            ],
            'k_axis_1': [
                r'k1\s*\[d/mm/\]\s*[0-9]+[,.]?[0-9]*/[0-9]+[,.]?[0-9]*@\s*(\d+)',  # Eyestar: extract axis from K1 line
                r'k1\s*\[d/mm/°\]\s*[0-9]+[,.]?[0-9]*/[0-9]+[,.]?[0-9]*@\s*(\d+)',  # Eyestar: extract axis from K1 line
                r'k1[^@\n]*@\s*(\d+[,.]?\d*)\s*°',  # From original parser
                r'tk1[:\s]*@\s*(\d+[,.]?\d*)\s*°',
                r'k1\s+axis[:\s]*(\d+[,.]?\d*)\s*°?',
                r'flat\s+axis[:\s]*(\d+[,.]?\d*)\s*°?'
            ],
            'k_axis_2': [
                r'k2\s*\[d/mm/\]\s*[0-9]+[,.]?[0-9]*/[0-9]+[,.]?[0-9]*@\s*(\d+)',  # Eyestar: extract axis from K2 line
                r'k2\s*\[d/mm/°\]\s*[0-9]+[,.]?[0-9]*/[0-9]+[,.]?[0-9]*@\s*(\d+)',  # Eyestar: extract axis from K2 line
                r'k2[^@\n]*@\s*(\d+[,.]?\d*)\s*°',  # From original parser
                r'tk2[:\s]*@\s*(\d+[,.]?\d*)\s*°',
                r'k2\s+axis[:\s]*(\d+[,.]?\d*)\s*°?',
                r'steep\s+axis[:\s]*(\d+[,.]?\d*)\s*°?'
            ],
            # K1/K2 axes are handled by the Zeiss-specific method below
            # 'k_axis_1': [
            #     r'k1[^@\n]*@\s*(\d+[,.]?\d*)\s*°',  # From original parser - handles K1 on separate line from axis
            #     r'tk1[:\s]*@\s*(\d+[,.]?\d*)\s*°',
            #     r'k1\s+axis[:\s]*(\d+[,.]?\d*)\s*°?',
            #     r'flat\s+axis[:\s]*(\d+[,.]?\d*)\s*°?'
            # ],
            # 'k_axis_2': [
            #     r'k2[^@\n]*@\s*(\d+[,.]?\d*)\s*°',  # From original parser - handles K2 on separate line from axis
            #     r'tk2[:\s]*@\s*(\d+[,.]?\d*)\s*°',
            #     r'k2\s+axis[:\s]*(\d+[,.]?\d*)\s*°?',
            #     r'steep\s+axis[:\s]*(\d+[,.]?\d*)\s*°?'
            # ],
            'acd': [
                r'acd[:\s]*(\d+[,.]?\d*)\s*mm',
                r'anterior\s+chamber\s+depth[:\s]*(\d+[,.]?\d*)\s*mm',
                r'acd\s*\[mm\]\s*(\d+[,.]?\d*)',  # Eyestar format
                r'anterior\s+chamber\s+depth\s*\[mm\]\s*(\d+[,.]?\d*)'  # Eyestar format
            ],
            'lt': [
                r'lt[:\s]*(\d+[,.]?\d*)\s*mm',
                r'lens\s+thickness[:\s]*(\d+[,.]?\d*)\s*mm',
                r'lt\s*\[mm\]\s*(\d+[,.]?\d*)'  # Eyestar format
            ],
            'wtw': [
                r'wtw[:\s]*(\d+[,.]?\d*)\s*mm',
                r'white\s+to\s+white[:\s]*(\d+[,.]?\d*)\s*mm',
                r'wtw\s*\[mm\]\s*(\d+[,.]?\d*)'  # Eyestar format
            ],
            'cct': [
                r'cct[:\s]*(\d+[,.]?\d*)\s*μm',
                r'central\s+corneal\s+thickness[:\s]*(\d+[,.]?\d*)\s*μm',
                r'cct\s*\[µm\]\s*(\d+[,.]?\d*)'  # Eyestar format
            ],
            'age': [
                r'age[:\s]*(\d+)',
                r'patient\s+age[:\s]*(\d+)'
            ],
            'birth_date': [
                r'data de nascim[:\s]*(\d{2}/\d{2}/\d{4})',
                r'birth[:\s]*(\d{2}/\d{2}/\d{4})',
                r'birthdate[:\s]*(\d{2}/\d{2}/\d{4})',
                r'(\d{1,2}/\d{1,2}/\d{4})',  # General MM/DD/YYYY format for Eyestar
                r'(\d{1,2}-\d{1,2}-\d{4})'   # MM-DD-YYYY format
            ],
            'patient_name': [
                r'patient[:\s]*([A-Za-z\s,\.\-]+?)(?:\n|birth|id|$)',
                r'name[:\s]*([A-Za-z\s,\.\-]+?)(?:\n|birth|id|$)',
                r'paciente[:\s]*([A-Za-z\s,\.\-]+?)(?:\n|birth|id|$)',
                r'nome[:\s]*([A-Za-z\s,\.\-]+?)(?:\n|birth|id|$)'
            ],
            'target_refraction': [
                r'target[:\s]*([+-]?\d+[,.]?\d*)\s*d',
                r'desired\s+refraction[:\s]*([+-]?\d+[,.]?\d*)\s*d'
            ]
        }
        
        # Extract values using patterns
        for field, field_patterns in patterns.items():
            for pattern in field_patterns:
                match = re.search(pattern, text_normalized)
                if match:
                    try:
                        # Handle European decimal notation (comma instead of period)
                        value_str = match.group(1).replace(',', '.')
                        value = float(value_str)
                        extracted_data[field] = value
                        logger.debug(f"Extracted {field}: {value}")
                        break  # Use first match found
                    except ValueError:
                        continue
        
        # Special handling for K1/K2 axes - Zeiss IOLMaster pattern
        self._extract_zeiss_keratometry_axes(text_normalized, extracted_data)
        
        # Extract both eyes separately if available (this will also extract patient-level data)
        self._extract_dual_eye_data(text, extracted_data)
        
        # Extract patient-level data if not already extracted by dual-eye method
        if 'patient_name' not in extracted_data:
            self._extract_patient_level_data(text_normalized, extracted_data)
        
        # Try to identify eye (OD/OS) - only if not already set by dual-eye extraction
        if 'eye' not in extracted_data:
            if 'od' in text_normalized or 'right' in text_normalized:
                extracted_data['eye'] = 'OD'
            elif 'os' in text_normalized or 'left' in text_normalized:
                extracted_data['eye'] = 'OS'
        
        # Calculate derived values
        if 'k1' in extracted_data and 'k2' in extracted_data:
            extracted_data['k_mean'] = (extracted_data['k1'] + extracted_data['k2']) / 2.0
            extracted_data['cyl_power'] = abs(extracted_data['k1'] - extracted_data['k2'])
        
        # Calculate age from birth date if available
        if 'birth_date' in extracted_data and 'age' not in extracted_data:
            try:
                from datetime import datetime
                birth_str = extracted_data['birth_date']
                # Parse DD/MM/YYYY or MM/DD/YYYY format
                try:
                    birth_date = datetime.strptime(birth_str, '%d/%m/%Y')
                except ValueError:
                    birth_date = datetime.strptime(birth_str, '%m/%d/%Y')
                current_date = datetime.now()
                age = current_date.year - birth_date.year
                # Adjust if birthday hasn't occurred this year
                if current_date.month < birth_date.month or (current_date.month == birth_date.month and current_date.day < birth_date.day):
                    age -= 1
                extracted_data['age'] = age
                logger.debug(f"Calculated age: {age} from birth date: {birth_str}")
            except Exception as e:
                logger.warning(f"Failed to calculate age from birth date: {e}")
        
        # Assess confidence based on extracted fields
        confidence = self._assess_extraction_confidence(extracted_data)
        extracted_data['extraction_confidence'] = confidence
        
        logger.info(f"Extracted {len(extracted_data)} fields with confidence {confidence:.2f}")
        
        return extracted_data
    
    def _assess_extraction_confidence(self, data: Dict[str, Any]) -> float:
        """Assess confidence in extracted data based on completeness."""
        # Count how many critical fields we actually extracted (not N/A)
        critical_fields = ['axial_length', 'k1', 'k2', 'k_axis_1', 'k_axis_2', 'acd', 'cct']
        extracted_count = 0
        total_count = len(critical_fields)
        
        for field in critical_fields:
            value = data.get(field)
            if value is not None and value != 'N/A':
                extracted_count += 1
        
        # Base confidence on percentage of critical fields extracted
        if extracted_count == total_count:
            return 0.95  # All critical fields found
        elif extracted_count >= total_count * 0.8:  # 80% of fields
            return 0.80
        elif extracted_count >= total_count * 0.6:  # 60% of fields
            return 0.60
        elif extracted_count >= total_count * 0.4:  # 40% of fields
            return 0.40
        else:
            return 0.20  # Very low confidence
    
    def _extract_zeiss_keratometry_axes(self, text: str, extracted_data: dict):
        """
        Extract K1/K2 axes using proven patterns from the original parser.
        """
        try:
            # Use the exact patterns from the original parser that work
            # Pattern: K1[^@\n]*@\s*(\d+[,.]?\d*)\s*° (handles K1 on separate line from axis)
            k1_axis_pattern = r'K1[^@\n]*@\s*([0-9]+(?:[.,][0-9]+)?)\s*°'
            k1_match = re.search(k1_axis_pattern, text, re.IGNORECASE)
            if k1_match:
                k1_axis = float(k1_match.group(1).replace(',', '.'))
                extracted_data['k_axis_1'] = k1_axis
                logger.debug(f"Extracted K1 axis: {k1_axis}°")
            
            # Pattern: K2[^@\n]*@\s*(\d+[,.]?\d*)\s*° (handles K2 on separate line from axis)
            k2_axis_pattern = r'K2[^@\n]*@\s*([0-9]+(?:[.,][0-9]+)?)\s*°'
            k2_match = re.search(k2_axis_pattern, text, re.IGNORECASE)
            if k2_match:
                k2_axis = float(k2_match.group(1).replace(',', '.'))
                extracted_data['k_axis_2'] = k2_axis
                logger.debug(f"Extracted K2 axis: {k2_axis}°")
                                
        except Exception as e:
            logger.warning(f"Failed to extract Zeiss keratometry axes: {e}")
    
    def _extract_dual_eye_data(self, text: str, extracted_data: dict):
        """
        Extract data for both OD and OS eyes separately from biometry reports.
        This is common in Zeiss IOLMaster reports that contain both eyes.
        """
        try:
            # Split text into OD and OS sections
            od_section = ""
            os_section = ""
            
            if 'OD' in text and 'OS' in text:
                # Find OD and OS sections with more precise matching to avoid false matches like "OSE"
                import re
                
                # Look for OD followed by eye-related keywords (not just any OD)
                od_match = re.search(r'\bOD\b.*?(?=\bOS\b|$)', text, re.IGNORECASE | re.DOTALL)
                os_match = re.search(r'\bOS\b.*?(?=\bOD\b|$)', text, re.IGNORECASE | re.DOTALL)
                
                if od_match and os_match:
                    od_section = od_match.group(0)
                    os_section = os_match.group(0)
                    logger.debug(f"Found OD section: {od_section[:100]}...")
                    logger.debug(f"Found OS section: {os_section[:100]}...")
                else:
                    # Fallback to simple search if regex fails
                    od_start = text.find('OD')
                    os_start = text.find('OS')
                    if od_start < os_start:
                        od_section = text[od_start:os_start]
                        os_section = text[os_start:]
                    else:
                        os_section = text[os_start:od_start]
                        od_section = text[od_start:]
            elif 'OD' in text:
                od_section = text[text.find('OD'):]
            elif 'OS' in text:
                os_section = text[text.find('OS'):]
            
            # Extract both eyes if available
            dual_eye_data = {}
            
            if od_section:
                od_data = self._extract_eye_specific_data(od_section, 'OD')
                if od_data:
                    dual_eye_data['od'] = od_data
                    logger.debug(f"Extracted OD data: {od_data}")
            
            if os_section:
                os_data = self._extract_eye_specific_data(os_section, 'OS')
                if os_data:
                    dual_eye_data['os'] = os_data
                    logger.debug(f"Extracted OS data: {os_data}")
            
            # If we have dual-eye data, replace the extracted data
            if len(dual_eye_data) > 1:
                # Calculate age for both eyes if birth date is available
                self._calculate_age_for_dual_eyes(dual_eye_data, text)
                # Preserve any existing patient-level data (like patient_name, birth_date, age)
                patient_data = {k: v for k, v in extracted_data.items() if k not in ['od', 'os', 'eye']}
                extracted_data.clear()
                extracted_data.update(dual_eye_data)
                extracted_data.update(patient_data)  # Restore patient-level data
                logger.info(f"Extracted dual-eye data: {list(dual_eye_data.keys())}")
            elif len(dual_eye_data) == 1:
                # Single eye data
                eye_key = list(dual_eye_data.keys())[0]
                # Calculate age for single eye if birth date is available
                self._calculate_age_for_single_eye(dual_eye_data[eye_key], text)
                extracted_data.clear()
                extracted_data.update(dual_eye_data[eye_key])
                logger.info(f"Extracted single-eye data: {eye_key}")
                    
        except Exception as e:
            logger.warning(f"Failed to extract dual eye data: {e}")
    
    def _extract_patient_level_data(self, text: str, extracted_data: dict):
        """Extract patient-level data like name, birth date, etc."""
        try:
            # Patient name patterns
            patient_name_patterns = [
                r'patient[:\s]*([A-Za-z\s,\.\-]+?)(?:\n|birth|id|$)',
                r'name[:\s]*([A-Za-z\s,\.\-]+?)(?:\n|birth|id|$)',
                r'paciente[:\s]*([A-Za-z\s,\.\-]+?)(?:\n|birth|id|$)',
                r'nome[:\s]*([A-Za-z\s,\.\-]+?)(?:\n|birth|id|$)'
            ]
            
            for pattern in patient_name_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    patient_name = match.group(1).strip()
                    if patient_name and len(patient_name) > 2:  # Valid name
                        extracted_data['patient_name'] = patient_name
                        logger.debug(f"Extracted patient name: {patient_name}")
                        break
            
            # Birth date patterns
            birth_date_patterns = [
                r'data de nascim[:\s]*(\d{2}/\d{2}/\d{4})',
                r'birth[:\s]*(\d{2}/\d{2}/\d{4})',
                r'birthdate[:\s]*(\d{2}/\d{2}/\d{4})',
                r'(\d{1,2}/\d{1,2}/\d{4})',
                r'(\d{1,2}-\d{1,2}-\d{4})'
            ]
            
            for pattern in birth_date_patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    extracted_data['birth_date'] = match.group(1)
                    logger.debug(f"Extracted birth date: {match.group(1)}")
                    break
                    
        except Exception as e:
            logger.warning(f"Failed to extract patient-level data: {e}")
    
    def _extract_eye_specific_data(self, eye_section: str, eye: str) -> dict:
        """
        Extract biometry data from a specific eye section (OD or OS).
        """
        eye_data = {}
        try:
            # Extract K1, K2 values
            k1_match = re.search(r'k1[:\s]*(\d+[,.]?\d*)\s*d', eye_section, re.IGNORECASE)
            if k1_match:
                eye_data['k1'] = float(k1_match.group(1).replace(',', '.'))
            
            k2_match = re.search(r'k2[:\s]*(\d+[,.]?\d*)\s*d', eye_section, re.IGNORECASE)
            if k2_match:
                eye_data['k2'] = float(k2_match.group(1).replace(',', '.'))
            
            # Extract K1/K2 axes - Zeiss IOLMaster specific format
            # TSE @ degree = K1 axis, TK1 @ degree = K2 axis
            tse_match = re.search(r'tse[:\s]*@\s*(\d+[,.]?\d*)\s*°', eye_section, re.IGNORECASE)
            if tse_match:
                eye_data['k_axis_1'] = float(tse_match.group(1))
            
            tk1_match = re.search(r'tk1[:\s]*@\s*(\d+[,.]?\d*)\s*°', eye_section, re.IGNORECASE)
            if tk1_match:
                eye_data['k_axis_2'] = float(tk1_match.group(1))
            
            # Extract other measurements
            al_match = re.search(r'al[:\s]*(\d+[,.]?\d*)\s*mm', eye_section, re.IGNORECASE)
            if al_match:
                eye_data['axial_length'] = float(al_match.group(1).replace(',', '.'))
            
            acd_match = re.search(r'acd[:\s]*(\d+[,.]?\d*)\s*mm', eye_section, re.IGNORECASE)
            if acd_match:
                eye_data['acd'] = float(acd_match.group(1).replace(',', '.'))
            
            cct_match = re.search(r'cct[:\s]*(\d+[,.]?\d*)\s*μm', eye_section, re.IGNORECASE)
            if cct_match:
                eye_data['cct'] = float(cct_match.group(1).replace(',', '.'))
            
            age_match = re.search(r'age[:\s]*(\d+[,.]?\d*)\s*years', eye_section, re.IGNORECASE)
            if age_match:
                eye_data['age'] = float(age_match.group(1).replace(',', '.'))
            
            # Calculate derived values
            if 'k1' in eye_data and 'k2' in eye_data:
                eye_data['k_mean'] = (eye_data['k1'] + eye_data['k2']) / 2.0
                eye_data['cyl_power'] = abs(eye_data['k1'] - eye_data['k2'])
            
            eye_data['eye'] = eye
            
        except Exception as e:
            logger.warning(f"Failed to extract {eye} data: {e}")
        
        return eye_data
    
    def _calculate_age_for_dual_eyes(self, dual_eye_data: dict, text: str):
        """Calculate age for both eyes if birth date is available."""
        try:
            # Extract birth date from the full text
            birth_date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
            if birth_date_match:
                birth_str = birth_date_match.group(1)
                age = self._calculate_age_from_birth_date(birth_str)
                if age is not None:
                    # Set age for both eyes
                    for eye_key in dual_eye_data:
                        if isinstance(dual_eye_data[eye_key], dict):
                            dual_eye_data[eye_key]['age'] = age
                    logger.debug(f"Calculated age {age} for dual eyes from birth date {birth_str}")
        except Exception as e:
            logger.warning(f"Failed to calculate age for dual eyes: {e}")
    
    def _calculate_age_for_single_eye(self, eye_data: dict, text: str):
        """Calculate age for single eye if birth date is available."""
        try:
            # Extract birth date from the full text
            birth_date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
            if birth_date_match:
                birth_str = birth_date_match.group(1)
                age = self._calculate_age_from_birth_date(birth_str)
                if age is not None:
                    eye_data['age'] = age
                    logger.debug(f"Calculated age {age} for single eye from birth date {birth_str}")
        except Exception as e:
            logger.warning(f"Failed to calculate age for single eye: {e}")
    
    def _calculate_age_from_birth_date(self, birth_str: str) -> int:
        """Calculate age from birth date string."""
        try:
            from datetime import datetime
            # Parse DD/MM/YYYY or MM/DD/YYYY format
            try:
                birth_date = datetime.strptime(birth_str, '%d/%m/%Y')
            except ValueError:
                birth_date = datetime.strptime(birth_str, '%m/%d/%Y')
            current_date = datetime.now()
            age = current_date.year - birth_date.year
            # Adjust if birthday hasn't occurred this year
            if current_date.month < birth_date.month or (current_date.month == birth_date.month and current_date.day < birth_date.day):
                age -= 1
            return age
        except Exception as e:
            logger.warning(f"Failed to parse birth date {birth_str}: {e}")
            return None
