#!/usr/bin/env python3
"""
Biometry Parser Service - Universal PDF biometry extraction
Combines OCR and LLM for accurate data extraction
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
    
    def __init__(self, ollama_base_url: str = "http://localhost:11434"):
        self.ollama_base_url = ollama_base_url
        self.model_name = "biometry-llama"
    
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
    
    def extract_demographics(self, text: str) -> Dict[str, Any]:
        """Extract patient demographics using LLM"""
        prompt = f"""Extract patient demographics from this medical document text:

{text}

Extract:
- patient_name (full name)
- age (calculate from birth date)
- device (measurement device/manufacturer like ZEISS, IOLMaster, etc.)

Return only valid JSON:
{{"patient_name": "string", "age": number, "device": "string"}}"""

        try:
            resp = requests.post(f'{self.ollama_base_url}/api/generate',
                               json={'model': self.model_name, 'prompt': prompt, 'stream': False},
                               timeout=60)
            
            if resp.status_code == 200:
                response_text = resp.json().get('response', '')
                return self._parse_json_response(response_text)
        except Exception as e:
            logger.error(f"Error extracting demographics: {e}")
        
        return {}
    
    def extract_keratometry(self, text: str, eye: str) -> Dict[str, Any]:
        """Extract keratometry for specific eye (OD or OS)"""
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
                               json={'model': self.model_name, 'prompt': prompt, 'stream': False},
                               timeout=60)
            
            if resp.status_code == 200:
                response_text = resp.json().get('response', '')
                return self._parse_json_response(response_text)
        except Exception as e:
            logger.error(f"Error extracting keratometry for {eye}: {e}")
        
        return {}
    
    def extract_ocular_biometry(self, pdf_path: str, eye: str) -> Dict[str, Any]:
        """Extract ocular biometry measurements for specific eye"""
        measurements = {}
        
        # Determine if this is Carina format (both eyes on same page) or Geraldo format (separate pages)
        is_carina_format = 'carina' in pdf_path.lower()
        
        if is_carina_format:
            # Carina format - both eyes on same page
            text = self.extract_text_from_pdf(pdf_path, 0)
            measurements = self._extract_carina_measurements(text, eye)
        else:
            # Geraldo format - separate pages for each eye
            page_num = 0 if eye == 'OD' else 1
            text = self.extract_text_from_pdf(pdf_path, page_num)
            measurements = self._extract_geraldo_measurements(text, eye)
        
        # Use LLM to validate and format the measurements
        return self._validate_measurements_with_llm(measurements, eye)
    
    def _extract_carina_measurements(self, text: str, eye: str) -> Dict[str, Any]:
        """Extract measurements from Carina format (both eyes on same page)"""
        measurements = {}
        lines = text.split('\n')
        
        # Find measurements in lines
        for line in lines:
            if 'AL [mm]' in line:
                al_values = re.findall(r'AL\s*\[mm\]\s*(\d+[.,]\d+)', line)
                if len(al_values) >= 2:
                    measurements['axial_length'] = float(al_values[0 if eye == 'OD' else 1].replace(',', '.'))
            
            elif 'ACD [mm]' in line:
                acd_values = re.findall(r'ACD\s*\[mm\]\s*(\d+[.,]\d+)', line)
                if len(acd_values) >= 2:
                    measurements['acd'] = float(acd_values[0 if eye == 'OD' else 1].replace(',', '.'))
            
            elif 'LT [mm]' in line:
                lt_values = re.findall(r'LT\s*\[mm\]\s*(\d+[.,]\d+)', line)
                if len(lt_values) >= 2:
                    measurements['lt'] = float(lt_values[0 if eye == 'OD' else 1].replace(',', '.'))
            
            elif 'WTWimm]' in line:
                wtw_values = re.findall(r'WTWimm\]\s*(\d+[.,]\d+)', line)
                if len(wtw_values) >= 2:
                    measurements['wtw'] = float(wtw_values[0 if eye == 'OD' else 1].replace(',', '.'))
                elif len(wtw_values) == 1:
                    alt_wtw_values = re.findall(r'WIWimm\]\s*(\d+[.,]\d+)', line)
                    if len(alt_wtw_values) >= 1:
                        measurements['wtw'] = float(alt_wtw_values[0 if eye == 'OS' else 0].replace(',', '.'))
            
            elif 'CCT [um]' in line:
                cct_values = re.findall(r'CCT\s*\[um\]\s*(\d+)', line)
                if len(cct_values) >= 2:
                    measurements['cct'] = int(cct_values[0 if eye == 'OD' else 1])
        
        return measurements
    
    def _extract_geraldo_measurements(self, text: str, eye: str) -> Dict[str, Any]:
        """Extract measurements from Geraldo format (separate pages for each eye)"""
        measurements = {}
        
        if eye == 'OD':
            # Page 1 patterns
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
        
        else:  # OS - Page 2 patterns
            al_match = re.search(r'(\d+[.,]\d+)\s*mm.*16\s*ym', text)
            if al_match:
                measurements['axial_length'] = float(al_match.group(1).replace(',', '.'))
            
            acd_match = re.search(r'(\d+[.,]\d+)\s*mm.*11pm', text)
            if acd_match:
                measurements['acd'] = float(acd_match.group(1).replace(',', '.'))
            
            lt_match = re.search(r'(\d+[.,]\d+)\s*mm.*17\s*um', text)
            if lt_match:
                measurements['lt'] = float(lt_match.group(1).replace(',', '.'))
            
            wtw_match = re.search(r'ww:\s*(\d+[.,]\d+)mm', text)
            if wtw_match:
                measurements['wtw'] = float(wtw_match.group(1).replace(',', '.'))
            
            cct_match = re.search(r'(\d+)\s*um.*4pum', text)
            if cct_match:
                measurements['cct'] = int(cct_match.group(1))
        
        return measurements
    
    def _validate_measurements_with_llm(self, measurements: Dict[str, Any], eye: str) -> Dict[str, Any]:
        """Use LLM to validate and format measurements"""
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
                               json={'model': self.model_name, 'prompt': prompt, 'stream': False},
                               timeout=60)
            
            if resp.status_code == 200:
                response_text = resp.json().get('response', '')
                return self._parse_json_response(response_text)
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
        
        # Extract OCR text
        text = self.extract_text_from_pdf(pdf_path, 0)
        
        # Extract demographics
        demographics = self.extract_demographics(text)
        
        # Extract keratometry for both eyes
        od_keratometry = self.extract_keratometry(text, "OD")
        os_keratometry = self.extract_keratometry(text, "OS")
        
        # Extract ocular biometry for both eyes
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
        
        return complete_data
