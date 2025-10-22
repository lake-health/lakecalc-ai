
@app.post("/parse", response_model=BiometryParseResponse)
async def parse_biometry(request: BiometryParseRequest):
    """Parse biometry text using LLM"""
    start_time = datetime.now()
    
    try:
        logger.info(f"Starting biometry parsing with model: {DEFAULT_MODEL}")
        
        # Build the prompt for biometry extraction
        prompt = build_biometry_prompt(request.text)
        
        # Try primary model first
        result = await call_ollama(DEFAULT_MODEL, prompt)
        
        if not result or result.get("confidence", 0) < request.confidence_threshold:
            logger.info(f"Primary model confidence too low, trying fallback: {FALLBACK_MODEL}")
            result = await call_ollama(FALLBACK_MODEL, prompt)
        
        if not result:
            raise HTTPException(status_code=500, detail="LLM processing failed")
        
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return BiometryParseResponse(
            success=True,
            extracted_data=result.get("data", {}),
            confidence=result.get("confidence", 0.0),
            processing_time=processing_time,
            method="llm"
        )
        
    except Exception as e:
        logger.error(f"Biometry parsing failed: {e}")
        processing_time = (datetime.now() - start_time).total_seconds()
        
        return BiometryParseResponse(
            success=False,
            extracted_data={},
            confidence=0.0,
            processing_time=processing_time,
            method="llm",
            error=str(e)
        )

def build_biometry_prompt(text: str) -> str:
    """Build optimized prompt for biometry extraction"""
    return f"""You are a medical AI assistant specialized in extracting biometry data from ophthalmology reports.

Extract the following biometry measurements from the text below. Return ONLY valid JSON with the exact field names shown:

{{
  "patient_name": "Patient Name",
  "birth_date": "MM/DD/YYYY",
  "age": 75,
  "od": {{
    "axial_length": 25.25,
    "k1": 42.60,
    "k2": 43.52,
    "k_axis_1": 14,
    "k_axis_2": 104,
    "acd": 3.25,
    "lt": 4.50,
    "wtw": 12.25,
    "cct": 540
  }},
  "os": {{
    "axial_length": 24.85,
    "k1": 43.10,
    "k2": 44.25,
    "k_axis_1": 165,
    "k_axis_2": 75,
    "acd": 3.15,
    "lt": 4.65,
    "wtw": 12.30,
    "cct": 535
  }}
}}

Rules:
- Return ONLY the JSON object, no explanations
- Use null for missing values
- Ensure all numbers are properly formatted
- Extract both OD (right eye) and OS (left eye) data when available
- Patient name should be extracted if visible
- Calculate age from birth date if available

Text to analyze:
{text[:2000]}

JSON:"""

async def call_ollama(model: str, prompt: str) -> Optional[Dict[str, Any]]:
    """Call Ollama API with the given model and prompt"""
    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": 0.1,
                "top_p": 0.9,
                "max_tokens": 1000
            }
        }
        
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json=payload,
            timeout=60
        )
        
        if response.status_code != 200:
            logger.error(f"Ollama API error: {response.status_code} - {response.text}")
            return None
        
        result = response.json()
        response_text = result.get("response", "").strip()
        
        # Try to extract JSON from response
        try:
            # Find JSON in the response
            start_idx = response_text.find('{')
            end_idx = response_text.rfind('}') + 1
            
            if start_idx != -1 and end_idx > start_idx:
                json_text = response_text[start_idx:end_idx]
                data = json.loads(json_text)
                
                # Calculate confidence based on data completeness
                confidence = calculate_confidence(data)
                
                return {
                    "data": data,
                    "confidence": confidence,
                    "raw_response": response_text
                }
            else:
                logger.error("No valid JSON found in response")
                return None
                
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            logger.error(f"Raw response: {response_text}")
            return None
            
    except Exception as e:
        logger.error(f"Ollama call failed: {e}")
        return None

def calculate_confidence(data: Dict[str, Any]) -> float:
    """Calculate confidence score based on data completeness"""
    if not isinstance(data, dict):
        return 0.0
    
    # Key fields to check
    key_fields = ["od", "os"]
    od_fields = ["axial_length", "k1", "k2"]
    os_fields = ["axial_length", "k1", "k2"]
    
    total_fields = 0
    filled_fields = 0
    
    # Check OD data
    if "od" in data and isinstance(data["od"], dict):
        for field in od_fields:
            total_fields += 1
            if data["od"].get(field) is not None:
                filled_fields += 1
    
    # Check OS data
    if "os" in data and isinstance(data["os"], dict):
        for field in os_fields:
            total_fields += 1
            if data["os"].get(field) is not None:
                filled_fields += 1
    
    # Check patient data
    patient_fields = ["patient_name", "age"]
    for field in patient_fields:
        total_fields += 1
        if data.get(field) is not None:
            filled_fields += 1
    
    if total_fields == 0:
        return 0.0
    
    return filled_fields / total_fields
