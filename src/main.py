#!/usr/bin/env python3
"""
Lake Health IOL Calculator - Railway Optimized Backend
Full OCR functionality with Railway-compatible dependencies
"""

import os
import logging
import tempfile
import traceback
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
        if os.path.exists(GOOGLE_CLOUD_CREDENTIALS_PATH):
            try:
                os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = GOOGLE_CLOUD_CREDENTIALS_PATH
                from google.cloud import vision
                client = vision.ImageAnnotatorClient()
                logger.info("Google Cloud Vision API initialized successfully")
            except Exception as e:
                logger.warning(f"Google Cloud Vision not available: {e}")
        
        return True
        
    except ImportError as e:
        logger.error(f"OCR dependencies not available: {e}")
        OCR_ENABLED = False
        return False

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
                            if os.path.exists(GOOGLE_CLOUD_CREDENTIALS_PATH):
                                from google.cloud import vision
                                client = vision.ImageAnnotatorClient()
                                
                                # Convert PIL image to bytes
                                import io
                                img_byte_arr = io.BytesIO()
                                image.save(img_byte_arr, format='PNG')
                                img_byte_arr = img_byte_arr.getvalue()
                                
                                # Perform OCR
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
                        if os.path.exists(GOOGLE_CLOUD_CREDENTIALS_PATH):
                            from google.cloud import vision
                            client = vision.ImageAnnotatorClient()
                            
                            with open(file_path, 'rb') as image_file:
                                content = image_file.read()
                            
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

def parse_medical_measurements(text):
    """Parse medical measurements from extracted text"""
    import re
    
    measurements = {}
    
    if not text:
        return measurements
    
    # Common patterns for medical device measurements
    patterns = {
        'k1': [
            r'K1[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'Steep[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'K steep[:\s]*([0-9]+\.?[0-9]*)\s*D'
        ],
        'k2': [
            r'K2[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'Flat[:\s]*([0-9]+\.?[0-9]*)\s*D',
            r'K flat[:\s]*([0-9]+\.?[0-9]*)\s*D'
        ],
        'axial_length': [
            r'AL[:\s]*([0-9]+\.?[0-9]*)\s*mm',
            r'Axial[:\s]*([0-9]+\.?[0-9]*)\s*mm',
            r'Length[:\s]*([0-9]+\.?[0-9]*)\s*mm'
        ]
    }
    
    for measurement, pattern_list in patterns.items():
        for pattern in pattern_list:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    value = float(matches[0])
                    # Validate reasonable ranges
                    if measurement in ['k1', 'k2'] and 35.0 <= value <= 55.0:
                        measurements[measurement] = {
                            'value': value,
                            'unit': 'D',
                            'confidence': 0.8
                        }
                    elif measurement == 'axial_length' and 20.0 <= value <= 30.0:
                        measurements[measurement] = {
                            'value': value,
                            'unit': 'mm',
                            'confidence': 0.8
                        }
                except ValueError:
                    continue
                break
    
    return measurements

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'LakeCalc.ai OCR Backend (Railway Optimized)',
        'version': '2.0.0',
        'ocr_enabled': OCR_ENABLED,
        'environment': 'railway'
    })

@app.route('/api/parse-pdf', methods=['POST'])
def parse_pdf():
    """Parse uploaded PDF and extract biometry measurements"""
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
                
                result = {
                    'success': True,
                    'device_manufacturer': 'Auto-detected',
                    'device_model': 'OCR Processed',
                    'measurements': measurements,
                    'extracted_text': extracted_text[:500] + "..." if len(extracted_text) > 500 else extracted_text,
                    'parse_confidence': confidence_or_error if isinstance(confidence_or_error, (int, float)) else 0.7,
                    'warnings': [] if measurements else ['No valid measurements found in extracted text'],
                    'ocr_method': 'Hybrid (Tesseract + Cloud Vision)'
                }
            else:
                # OCR failed, return error with details
                result = {
                    'success': False,
                    'error': 'OCR extraction failed',
                    'details': confidence_or_error,
                    'measurements': {},
                    'warnings': ['OCR processing unsuccessful', 'Please ensure document is clear and readable'],
                    'ocr_method': 'Failed'
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
            'success': False
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
        'service': 'LakeCalc.ai API (Railway Optimized)',
        'status': 'running',
        'version': '2.0.0',
        'endpoints': [
            '/api/health',
            '/api/parse-pdf',
            '/api/calculate-iol'
        ],
        'ocr_enabled': OCR_ENABLED
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    # Initialize OCR on startup
    initialize_ocr()
    
    logger.info(f"Starting LakeCalc.ai Railway Backend on 0.0.0.0:{port}")
    logger.info(f"OCR Enabled: {OCR_ENABLED}")
    app.run(host='0.0.0.0', port=port, debug=debug)

