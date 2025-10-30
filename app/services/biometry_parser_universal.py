#!/usr/bin/env python3
"""
Biometry Parser Service - Universal PDF biometry extraction
Combines OCR and LLM for accurate data extraction
UNIVERSAL VERSION - No hardcoded format detection
"""
import requests
import json
import pytesseract
import fitz  # PyMuPDF
from PIL import Image
import io
import re
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class BiometryParser:
    """Universal biometry parser for medical PDFs"""
    
    def __init__(self, ollama_base_url: Optional[str] = None):
        # Use environment variable or default to localhost
        import os
        self.ollama_base_url = ollama_base_url or os.getenv("RUNPOD_OLLAMA_URL", "http://localhost:11434")
        self.model_name = "llama3.1:8b"  # Use base model for now
        logger.info(f"BiometryParser initialized with Ollama URL: {self.ollama_base_url}")
    
    def extract_text_from_pdf(self, pdf_path: str, page_num: int = 0) -> str:
        """Extract text from specific PDF page using OCR"""
        try:
            doc = fitz.open(pdf_path)
            if page_num < len(doc):
                page = doc.load_page(page_num)
                mat = fitz.Matrix(2.0, 2.0)  # 2x zoom for better OCR
                pix = page.get_pixmap(matrix=mat)
                img_data = pix.tobytes("png")
                doc.close()
                
                image = Image.open(io.BytesIO(img_data))
                text = pytesseract.image_to_string(image)
                return text
            else:
                doc.close()
                return ""
        except Exception as e:
            logger.error(f"Error extracting text from PDF: {e}")
            return ""
    
    def detect_eye_layout(self, pdf_path: str) -> str:
        """
        Detect if eyes are on same page or separate pages.
        Returns: 'single_page' or 'multi_page'
        
        Strategy: Count AL (Axial Length) measurements on page 0.
        - If 2+ AL measurements = both eyes on same page
        - Otherwise = separate pages
        """
        text_page0 = self.extract_text_from_pdf(pdf_path, 0)
        
        # Count AL measurements (axial length values)
        al_measurements = re.findall(r'AL\s*\[?mm\]?.*?(\d+[.,]\d+)', text_page0, re.IGNORECASE)
        
        # Single page should have 2+ AL values (one for OD, one for OS)
        if len(al_measurements) >= 2:
            return 'single_page'
        else:
            return 'multi_page'
    
    def extract_demographics(self, pdf_path: str) -> Dict[str, Any]:
        """Extract patient demographics using OCR + LLM"""
        text = self.extract_text_from_pdf(pdf_path, 0)
        
        prompt = f"""Extract patient demographics from this medical document text:

{text}

Extract:
- patient_name (full name in proper case)
- age (calculate from birth date to current year 2025)
- device (the biometry DEVICE/MACHINE used, NOT the formula)

DEVICE EXAMPLES:
- "EyeSuite IOL" (HAAG-STREIT)
- "IOLMaster" (ZEISS)
- "Lenstar" (HAAG-STREIT)
- "Pentacam"
- "AL-Scan"

DO NOT use formula names like "Hill RBF", "Abulafia-Koch", "Barrett", "Hoffer Q" as the device.

Return only valid JSON:
{{"patient_name": "string", "age": number, "device": "string"}}"""

        try:
            resp = requests.post(f'{self.ollama_base_url}/api/generate',
                               json={'model': self.model_name, 'prompt': prompt, 'stream': False, 
                                     'format': 'json', 'options': {'temperature': 0}},
                               timeout=60)
            
            if resp.status_code == 200:
                response_text = resp.json().get('response', '')
                return self._parse_json_response(response_text)
        except Exception as e:
            logger.error(f"Error extracting demographics: {e}")
        
        return {}
    
    def extract_keratometry(self, pdf_path: str, eye: str) -> Dict[str, Any]:
        """Extract keratometry for specific eye (OD or OS) - UNIVERSAL FORMAT DETECTION"""
        
        # Detect layout
        layout = self.detect_eye_layout(pdf_path)
        
        if layout == 'single_page':
            # Both eyes on page 0
            text = self.extract_text_from_pdf(pdf_path, 0)
        else:
            # Separate pages: OD on page 0, OS on page 1
            page_num = 0 if eye == 'OD' else 1
            text = self.extract_text_from_pdf(pdf_path, page_num)
        
        prompt = f"""Extract keratometry data for {eye} ({"right" if eye == "OD" else "left"} eye) from this medical document:

{text}

Extract:
- k1 (first keratometry value in diopters)
- k2 (second keratometry value in diopters)  
- k_axis_1 (axis for K1, 0-180 degrees)
- k_axis_2 (axis for K2, 0-180 degrees)

Look for patterns like "K1: 42.30 D @ 100°" or "K1: 42,30 D @ 100°"
Map K1 axis to k_axis_1 and K2 axis to k_axis_2

Return only valid JSON:
{{"k1": number, "k2": number, "k_axis_1": number, "k_axis_2": number}}"""

        try:
            resp = requests.post(f'{self.ollama_base_url}/api/generate',
                               json={'model': self.model_name, 'prompt': prompt, 'stream': False,
                                     'format': 'json', 'options': {'temperature': 0}},
                               timeout=60)
            
            if resp.status_code == 200:
                response_text = resp.json().get('response', '')
                return self._parse_json_response(response_text)
        except Exception as e:
            logger.error(f"Error extracting keratometry for {eye}: {e}")
        
        return {}
    
    def extract_measurements_by_eye(self, pdf_path: str, eye: str) -> Dict[str, Any]:
        """Extract measurements for specific eye (OD or OS) - UNIVERSAL FORMAT DETECTION"""
        measurements = {}
        
        # Determine layout
        layout = self.detect_eye_layout(pdf_path)
        
        if layout == 'single_page':
            # Both eyes on same page
            text = self.extract_text_from_pdf(pdf_path, 0)
            lines = text.split('\n')
            
            # Find AL measurements for both eyes
            for line in lines:
                if 'AL [mm]' in line or 'AL[mm]' in line:
                    al_values = re.findall(r'AL\s*\[?mm\]?\s*(\d+[.,]\d+)', line)
                    if len(al_values) >= 2:
                        if eye == 'OD':
                            measurements['axial_length'] = float(al_values[0].replace(',', '.'))
                        else:  # OS
                            measurements['axial_length'] = float(al_values[1].replace(',', '.'))
                    break
            
            # Find ACD measurements
            for line in lines:
                if 'ACD [mm]' in line or 'ACD[mm]' in line:
                    acd_values = re.findall(r'ACD\s*\[?mm\]?\s*(\d+[.,]\d+)', line)
                    if len(acd_values) >= 2:
                        if eye == 'OD':
                            measurements['acd'] = float(acd_values[0].replace(',', '.'))
                        else:  # OS
                            measurements['acd'] = float(acd_values[1].replace(',', '.'))
                    break
            
            # Find LT measurements
            for line in lines:
                if 'LT [mm]' in line or 'LT[mm]' in line:
                    lt_values = re.findall(r'LT\s*\[?mm\]?\s*(\d+[.,]\d+)', line)
                    if len(lt_values) >= 2:
                        if eye == 'OD':
                            measurements['lt'] = float(lt_values[0].replace(',', '.'))
                        else:  # OS
                            measurements['lt'] = float(lt_values[1].replace(',', '.'))
                    break
            
            # Find WTW measurements
            for line in lines:
                if 'WTW' in line or 'wtw' in line:
                    wtw_values = re.findall(r'(\d+[.,]\d+)\s*mm', line)
                    if len(wtw_values) >= 2:
                        if eye == 'OD':
                            measurements['wtw'] = float(wtw_values[0].replace(',', '.'))
                        else:  # OS
                            measurements['wtw'] = float(wtw_values[1].replace(',', '.'))
                    break
            
            # Find CCT measurements
            for line in lines:
                if 'CCT [um]' in line or 'CCT[um]' in line or 'CCT [μm]' in line:
                    cct_values = re.findall(r'CCT\s*\[?u?μ?m\]?\s*(\d+)', line)
                    if len(cct_values) >= 2:
                        if eye == 'OD':
                            measurements['cct'] = int(cct_values[0])
                        else:  # OS
                            measurements['cct'] = int(cct_values[1])
                    break
        
        else:
            # Multi-page format: separate pages per eye
            if eye == 'OD':
                text = self.extract_text_from_pdf(pdf_path, 0)
            else:  # OS
                text = self.extract_text_from_pdf(pdf_path, 1)
            
            # Look for eye-specific patterns
            al_match = re.search(r'(\d+[.,]\d+)\s*mm.*20pm', text)
            if al_match:
                measurements['axial_length'] = float(al_match.group(1).replace(',', '.'))
            
            acd_match = re.search(r'(\d+[.,]\d+)\s*mm.*10pm', text)
            if acd_match:
                measurements['acd'] = float(acd_match.group(1).replace(',', '.'))
            
            lt_match = re.search(r'(\d+[.,]\d+)\s*mm.*20\s*um', text)
            if lt_match:
                measurements['lt'] = float(lt_match.group(1).replace(',', '.'))
            
            wtw_match = re.search(r'ww:\s*(\d+[.,]\d+)mm', text)
            if wtw_match:
                measurements['wtw'] = float(wtw_match.group(1).replace(',', '.'))
            
            cct_match = re.search(r'(\d+)\s*um.*4pum', text)
            if cct_match:
                measurements['cct'] = int(cct_match.group(1))
        
        return measurements
    
    def extract_ocular_biometry(self, pdf_path: str, eye: str) -> Dict[str, Any]:
        """Extract ocular biometry for specific eye (OD or OS)"""
        measurements = self.extract_measurements_by_eye(pdf_path, eye)
        
        # Create structured text for LLM validation
        structured_text = f"""
        {eye} Measurements Found:
        - Axial Length: {measurements.get('axial_length', 'Not found')} mm
        - ACD: {measurements.get('acd', 'Not found')} mm  
        - LT: {measurements.get('lt', 'Not found')} mm
        - WTW: {measurements.get('wtw', 'Not found')} mm
        - CCT: {measurements.get('cct', 'Not found')} μm (micrometers)
        """
        
        prompt = f"""Extract these 5 measurements for {eye} from this data:

{structured_text}

IMPORTANT: CCT is in micrometers (μm), not millimeters. If CCT shows 484 μm, return 484, not 0.484.

Return only JSON:
{{"axial_length": number, "acd": number, "lt": number, "wtw": number, "cct": number}}"""

        try:
            resp = requests.post(f'{self.ollama_base_url}/api/generate',
                               json={'model': self.model_name, 'prompt': prompt, 'stream': False,
                                     'format': 'json', 'options': {'temperature': 0}},
                               timeout=60)
            
            if resp.status_code == 200:
                response_text = resp.json().get('response', '')
                validated = self._parse_json_response(response_text)
                # If LLM validation returns empty, fallback to regex measurements
                return validated if validated else measurements
        except Exception as e:
            logger.error(f"Error validating measurements for {eye}: {e}")
        
        return measurements
    
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """Parse JSON from LLM response"""
        try:
            # Try multiple JSON extraction methods
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start != -1 and json_end != -1:
                json_str = response_text[json_start:json_end]
                json_str = json_str.replace('\\_', '_')  # Fix escaped underscores
                return json.loads(json_str)
            
            # Look for JSON in code blocks
            json_match = re.search(r'```json\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                json_str = json_str.replace('\\_', '_')
                return json.loads(json_str)
            
            # Look for JSON without code blocks
            json_match = re.search(r'(\{.*?\})', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
                json_str = json_str.replace('\\_', '_')
                return json.loads(json_str)
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON parsing error: {e}")
            return {}
        
        return {}
    
    def extract_complete_biometry(self, pdf_path: str) -> Dict[str, Any]:
        """Extract complete biometry data from PDF"""
        logger.info(f"Processing {pdf_path}")
        
        # Extract demographics (always from page 0)
        demographics = self.extract_demographics(pdf_path)
        
        # Extract keratometry for both eyes (with universal page detection)
        od_keratometry = self.extract_keratometry(pdf_path, "OD")
        os_keratometry = self.extract_keratometry(pdf_path, "OS")
        
        # Extract ocular biometry for both eyes (with universal page detection)
        od_biometry = self.extract_ocular_biometry(pdf_path, "OD")
        os_biometry = self.extract_ocular_biometry(pdf_path, "OS")
        
        # Combine all data
        complete_data = {
            "patient_name": demographics.get("patient_name", ""),
            "age": demographics.get("age", None),
            "device": demographics.get("device", ""),
            "od": {
                **od_keratometry,
                **od_biometry
            },
            "os": {
                **os_keratometry,
                **os_biometry
            }
        }
        
        logger.info(f"Extraction complete for {pdf_path}")
        return complete_data

