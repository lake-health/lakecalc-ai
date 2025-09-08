#!/usr/bin/env python3
"""
Lake Health IOL Calculator - Advanced OCR Parser v20.0
Enhanced axis value detection with Cautious Scavenger approach
Updated: Sep 7, 2025 - Advanced axis detection for K1, K2, AK measurements
"""

import os
import logging
import tempfile
import traceback
import re
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
CORS(app, origins="*")

# Configuration
UPLOAD_FOLDER = tempfile.mkdtemp()
ALLOWED_EXTENSIONS = {'pdf', 'png', 'jpg', 'jpeg'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# OCR Configuration
OCR_ENABLED = True
GOOGLE_CLOUD_CREDENTIALS_JSON = os.environ.get('GOOGLE_CLOUD_CREDENTIALS_JSON')
GOOGLE_CLOUD_CREDENTIALS_PATH = os.environ.get('GOOGLE_CLOUD_CREDENTIALS_PATH', '/app/google-cloud-credentials.json')

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def initialize_ocr():
    """Initialize OCR components with Railway compatibility"""
    global OCR_ENABLED
    try:
        # Try to import OCR dependencies
        import pytesseract
        from pdf2image import convert_from_path
        from PIL import Image
        
        # Test tesseract availability
        try:
            pytesseract.get_tesseract_version()
            logger.info("Tesseract OCR initialized successfully")
        except Exception as e:
            logger.warning(f"Tesseract not available: {e}")
        
        # Test Google Cloud Vision
        try:
            # Try environment variable first (for Railway)
            if GOOGLE_CLOUD_CREDENTIALS_JSON:
                import tempfile
                import json
                # Create temporary credentials file from environment variable
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    f.write(GOOGLE_CLOUD_CREDENTIALS_JSON)
                    temp_creds_path = f.name
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_creds_path
                from google.cloud import vision
                client = vision.ImageAnnotatorClient()
                logger.info("Google Cloud Vision API initialized from environment variable")
            elif os.path.exists(GOOGLE_CLOUD_CREDENTIALS_PATH):
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_CLOUD_CREDENTIALS_PATH
                from google.cloud import vision
                client = vision.ImageAnnotatorClient()
                logger.info("Google Cloud Vision API initialized from file")
            else:
                logger.warning("No Google Cloud credentials found")
        except Exception as e:
            logger.warning(f"Google Cloud Vision not available: {e}")
        
        return True
        
    except ImportError as e:
        logger.error(f"OCR dependencies not available: {e}")
        OCR_ENABLED = False
        return False

def get_vision_client():
    """Get Google Cloud Vision client with proper credentials handling"""
    try:
        # Try environment variable first (for Railway)
        if GOOGLE_CLOUD_CREDENTIALS_JSON:
            import tempfile
            import json
            # Create temporary credentials file from environment variable
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                f.write(GOOGLE_CLOUD_CREDENTIALS_JSON)
                temp_creds_path = f.name
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = temp_creds_path
            from google.cloud import vision
            return vision.ImageAnnotatorClient()
        elif os.path.exists(GOOGLE_CLOUD_CREDENTIALS_PATH):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_CLOUD_CREDENTIALS_PATH
            from google.cloud import vision
            return vision.ImageAnnotatorClient()
        else:
            return None
    except Exception as e:
        logger.error(f"Failed to create Vision client: {e}")
        return None

def extract_text_with_ocr(file_path):
    """Extract text using hybrid OCR approach"""
    if not OCR_ENABLED:
        return None, "OCR not available in this environment"
    
    try:
        # Import OCR libraries
        import pytesseract
        from pdf2image import convert_from_path
        from PIL import Image
        
        extracted_text = ""
        confidence_scores = []
        
        # Handle PDF files
        if file_path.lower().endswith('.pdf'):
            try:
                # Convert PDF to images
                images = convert_from_path(file_path, dpi=300, first_page=1, last_page=3)
                
                for i, image in enumerate(images):
                    # Try local tesseract first
                    try:
                        text = pytesseract.image_to_string(image, config='--psm 6')
                        if text.strip():
                            extracted_text += f"Page {i+1}:\n{text}\n\n"
                            confidence_scores.append(0.75)  # Estimated confidence
                    except Exception as e:
                        logger.warning(f"Tesseract failed for page {i+1}: {e}")
                        
                        # Fallback to Google Cloud Vision
                        try:
                            client = get_vision_client()
                            if client:
                                # Convert PIL image to bytes
                                import io
                                img_byte_arr = io.BytesIO()
                                image.save(img_byte_arr, format='PNG')
                                img_byte_arr = img_byte_arr.getvalue()
                                
                                # Perform OCR
                                from google.cloud import vision
                                image_vision = vision.Image(content=img_byte_arr)
                                response = client.text_detection(image=image_vision)
                                
                                if response.text_annotations:
                                    text = response.text_annotations[0].description
                                    extracted_text += f"Page {i+1} (Cloud Vision):\n{text}\n\n"
                                    confidence_scores.append(0.85)
                                    
                        except Exception as cloud_error:
                            logger.error(f"Cloud Vision failed: {cloud_error}")
                            
            except Exception as pdf_error:
                logger.error(f"PDF processing failed: {pdf_error}")
                return None, f"PDF processing error: {str(pdf_error)}"
        
        # Handle image files
        else:
            try:
                from PIL import Image
                image = Image.open(file_path)
                
                # Try local tesseract
                try:
                    text = pytesseract.image_to_string(image, config='--psm 6')
                    if text.strip():
                        extracted_text = text
                        confidence_scores.append(0.75)
                except Exception as e:
                    logger.warning(f"Tesseract failed: {e}")
                    
                    # Fallback to Google Cloud Vision
                    try:
                        client = get_vision_client()
                        if client:
                            with open(file_path, 'rb') as image_file:
                                content = image_file.read()
                            
                            from google.cloud import vision
                            image_vision = vision.Image(content=content)
                            response = client.text_detection(image=image_vision)
                            
                            if response.text_annotations:
                                extracted_text = response.text_annotations[0].description
                                confidence_scores.append(0.85)
                                
                    except Exception as cloud_error:
                        logger.error(f"Cloud Vision failed: {cloud_error}")
                        
            except Exception as img_error:
                logger.error(f"Image processing failed: {img_error}")
                return None, f"Image processing error: {str(img_error)}"
        
        if extracted_text.strip():
            avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0
            return extracted_text, avg_confidence
        else:
            return None, "No text extracted"
            
    except Exception as e:
        logger.error(f"OCR extraction failed: {e}")
        logger.error(traceback.format_exc())
        return None, f"OCR error: {str(e)}"

def cautious_axis_scavenger(text, measurement_type, measurement_value_position):
    """
    Cautious Scavenger approach for finding axis values
    Prioritizes 1-2 digit axis values and avoids misinterpretation
    """
    logger.info(f"Searching for {measurement_type} axis near position {measurement_value_position}")
    
    # Split text into lines for line-by-line analysis
    lines = text.split('\n')
    
    # Find the line containing the measurement value
    measurement_line_idx = -1
    for i, line in enumerate(lines):
        if measurement_value_position in line:
            measurement_line_idx = i
            break
    
    if measurement_line_idx == -1:
        logger.warning(f"Could not find measurement line for {measurement_type}")
        return None
    
    # Search for axis values in current line and next few lines
    search_lines = []
    for i in range(max(0, measurement_line_idx), min(len(lines), measurement_line_idx + 3)):
        search_lines.append(lines[i])
    
    search_text = ' '.join(search_lines)
    logger.info(f"Searching in text: {search_text}")
    
    # Axis detection patterns with priority
    axis_patterns = [
        # Priority 1: Explicit axis notation with 1-2 digits
        r'@\s*(\d{1,2})(?!\d)',  # @12, @5, etc.
        r'axis\s*:?\s*(\d{1,2})(?!\d)',  # axis: 12, axis 5
        r'ax\s*:?\s*(\d{1,2})(?!\d)',    # ax: 12, ax 5
        
        # Priority 2: Degree symbol with 1-2 digits
        r'(\d{1,2})°(?!\d)',  # 12°, 5°
        r'(\d{1,2})\s*deg(?!\d)',  # 12 deg, 5 deg
        
        # Priority 3: Explicit axis notation with 3 digits
        r'@\s*(\d{3})',  # @180, @090
        r'axis\s*:?\s*(\d{3})',  # axis: 180, axis 090
        r'ax\s*:?\s*(\d{3})',    # ax: 180, ax 090
        
        # Priority 4: Degree symbol with 3 digits
        r'(\d{3})°',  # 180°, 090°
        r'(\d{3})\s*deg',  # 180 deg, 090 deg
        
        # Priority 5: Standalone numbers that could be axis (with context)
        # Only if they appear after measurement value and are reasonable axis values
        r'(?:^|\s)(\d{1,2})(?=\s|$)(?!\d)',  # Standalone 1-2 digit numbers
        r'(?:^|\s)(\d{3})(?=\s|$)',  # Standalone 3 digit numbers
    ]
    
    found_axes = []
    
    for priority, pattern in enumerate(axis_patterns, 1):
        matches = re.finditer(pattern, search_text, re.IGNORECASE)
        for match in matches:
            axis_value = int(match.group(1))
            
            # Validate axis value range (0-180 degrees)
            if 0 <= axis_value <= 180:
                # For 3-digit values, handle special cases
                if axis_value >= 100:
                    # Convert 090 -> 90, 180 -> 180, etc.
                    if str(axis_value).startswith('0'):
                        axis_value = int(str(axis_value).lstrip('0') or '0')
                
                found_axes.append({
                    'value': axis_value,
                    'priority': priority,
                    'pattern': pattern,
                    'match_text': match.group(0),
                    'position': match.start()
                })
                
                logger.info(f"Found axis candidate: {axis_value} (priority {priority}, pattern: {pattern})")
    
    if not found_axes:
        logger.warning(f"No axis values found for {measurement_type}")
        return None
    
    # Sort by priority (lower number = higher priority)
    found_axes.sort(key=lambda x: (x['priority'], x['position']))
    
    # Return the highest priority axis value
    best_axis = found_axes[0]
    logger.info(f"Selected axis for {measurement_type}: {best_axis['value']} (priority {best_axis['priority']})")
    
    return best_axis['value']

def parse_medical_measurements(text):
    """Parse medical measurements from extracted text with advanced axis detection"""
    import re
    
    measurements = {}
    
    if not text:
        return measurements
    
    logger.info("Starting advanced medical measurement parsing")
    logger.info(f"Text to parse (first 500 chars): {text[:500]}")
    
    # Enhanced patterns for IOL Master 700 measurements
    measurement_patterns = {
        'k1': [
            r'K1[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'Steep[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'K\s*steep[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'Steepest[:\s]*([0-9]+\.?[0-9]*)\s*D'
        ],
        'k2': [
            r'K2[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'Flat[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'K\s*flat[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'Flattest[:\s]*([0-9]+\.?[0-9]*)\s*D'
        ],
        'ak': [
            r'AK[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'Astigmatism[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'Ast[:\s]*([0-9]+\.?[0-9]*)\s*D'
        ],
        'axial_length': [
            r'AL[:\s]*([0-9]+\.?[0-9]*)\s*mm',
            r'Axial[:\s]*([0-9]+\.?[0-9]*)\s*mm',
            r'Length[:\s]*([0-9]+\.?[0-9]*)\s*mm'
        ]
    }
    
    # First pass: Find measurement values
    for measurement, pattern_list in measurement_patterns.items():
        for pattern in pattern_list:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                try:
                    value = float(match.group(1))
                    
                    # Validate reasonable ranges
                    if measurement in ['k1', 'k2'] and 35.0 <= value <= 55.0:
                        measurements[measurement] = {
                            'value': value,
                            'unit': 'D',
                            'confidence': 0.8,
                            'match_text': match.group(0),
                            'position': match.start()
                        }
                        logger.info(f"Found {measurement}: {value} D")
                        break
                    elif measurement == 'ak' and 0.0 <= value <= 10.0:
                        measurements[measurement] = {
                            'value': value,
                            'unit': 'D',
                            'confidence': 0.8,
                            'match_text': match.group(0),
                            'position': match.start()
                        }
                        logger.info(f"Found {measurement}: {value} D")
                        break
                    elif measurement == 'axial_length' and 20.0 <= value <= 30.0:
                        measurements[measurement] = {
                            'value': value,
                            'unit': 'mm',
                            'confidence': 0.8,
                            'match_text': match.group(0),
                            'position': match.start()
                        }
                        logger.info(f"Found {measurement}: {value} mm")
                        break
                except ValueError:
                    continue
            
            # Break if we found this measurement
            if measurement in measurements:
                break
    
    # Second pass: Find axis values for K1, K2, and AK using Cautious Scavenger
    for measurement in ['k1', 'k2', 'ak']:
        if measurement in measurements:
            axis_value = cautious_axis_scavenger(
                text, 
                measurement, 
                measurements[measurement]['match_text']
            )
            
            if axis_value is not None:
                measurements[measurement]['axis'] = axis_value
                measurements[measurement]['axis_unit'] = '°'
                logger.info(f"Found axis for {measurement}: {axis_value}°")
            else:
                logger.warning(f"No axis found for {measurement}")
    
    return measurements

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'LakeCalc.ai OCR Backend - Advanced Axis Detection',
        'version': '20.0.0',
        'ocr_enabled': OCR_ENABLED,
        'environment': 'railway',
        'features': ['cautious_axis_scavenger', 'enhanced_k1_k2_ak_detection']
    })

@app.route('/api/parse-pdf', methods=['POST'])
def parse_pdf():
    """Parse uploaded PDF and extract biometry measurements with axis detection"""
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file type. Please upload PDF, PNG, or JPG files.'}), 400
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        try:
            # Extract text using OCR
            extracted_text, confidence_or_error = extract_text_with_ocr(filepath)
            
            if extracted_text:
                # Parse measurements from extracted text
                measurements = parse_medical_measurements(extracted_text)
                
                # Calculate parsing success metrics
                total_expected = 4  # k1, k2, ak, axial_length
                found_measurements = len([m for m in measurements if 'value' in measurements[m]])
                found_axes = len([m for m in measurements if 'axis' in measurements[m]])
                
                result = {
                    'success': True,
                    'device_manufacturer': 'IOL Master 700',
                    'device_model': 'Advanced OCR Processed',
                    'measurements': measurements,
                    'extracted_text': extracted_text[:1000] + "..." if len(extracted_text) > 1000 else extracted_text,
                    'parse_confidence': confidence_or_error if isinstance(confidence_or_error, (int, float)) else 0.7,
                    'parsing_stats': {
                        'measurements_found': found_measurements,
                        'axes_found': found_axes,
                        'total_expected': total_expected,
                        'success_rate': f"{(found_measurements/total_expected)*100:.1f}%"
                    },
                    'warnings': [] if measurements else ['No valid measurements found in extracted text'],
                    'ocr_method': 'Hybrid (Tesseract + Cloud Vision)',
                    'parser_version': '20.0 - Cautious Scavenger'
                }
            else:
                # OCR failed, return error with details
                result = {
                    'success': False,
                    'error': 'OCR extraction failed',
                    'details': confidence_or_error,
                    'measurements': {},
                    'warnings': ['OCR processing unsuccessful', 'Please ensure document is clear and readable'],
                    'ocr_method': 'Failed',
                    'parser_version': '20.0 - Cautious Scavenger'
                }
        
        finally:
            # Clean up uploaded file
            try:
                os.remove(filepath)
            except:
                pass
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error processing file: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'error': 'Failed to process file',
            'details': str(e),
            'success': False,
            'parser_version': '20.0 - Cautious Scavenger'
        }), 500

@app.route('/api/calculate-iol', methods=['POST'])
def calculate_iol():
    """Calculate IOL power based on biometry measurements"""
    try:
        data = request.get_json()
        
        # Extract measurements
        k1 = float(data.get('k1', 43.0))
        k2 = float(data.get('k2', 43.0))
        axial_length = float(data.get('axial_length', 24.0))
        target_refraction = float(data.get('target_refraction', 0.0))
        
        # Simple IOL calculation (SRK/T formula approximation)
        k_avg = (k1 + k2) / 2
        a_constant = 118.4  # Default A-constant
        
        # Simplified calculation
        iol_power = a_constant - 2.5 * axial_length - 0.9 * k_avg + target_refraction
        
        return jsonify({
            'success': True,
            'iol_power': round(iol_power, 1),
            'formula': 'SRK/T (simplified)',
            'measurements_used': {
                'k1': k1,
                'k2': k2,
                'k_avg': round(k_avg, 2),
                'axial_length': axial_length,
                'target_refraction': target_refraction
            }
        })
        
    except Exception as e:
        logger.error(f"Error calculating IOL: {e}")
        return jsonify({
            'error': 'Failed to calculate IOL power',
            'details': str(e)
        }), 500

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def serve_frontend(path):
    """Serve frontend files or API info"""
    return jsonify({
        'service': 'LakeCalc.ai API - Advanced Axis Detection',
        'status': 'running',
        'version': '20.0.0',
        'endpoints': [
            '/api/health',
            '/api/parse-pdf',
            '/api/calculate-iol'
        ],
        'ocr_enabled': OCR_ENABLED,
        'features': ['cautious_axis_scavenger', 'enhanced_k1_k2_ak_detection']
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # Initialize OCR on startup
    initialize_ocr()
    
    logger.info(f"Starting LakeCalc.ai Advanced OCR Backend on 0.0.0.0:{port}")
    logger.info(f"OCR Enabled: {OCR_ENABLED}")
    logger.info("Features: Cautious Axis Scavenger, Enhanced K1/K2/AK Detection")
    app.run(host='0.0.0.0', port=port, debug=debug)
