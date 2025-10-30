from fastapi import APIRouter, HTTPException
from app.services.storage import resolve_path
from app.services.biometry_parser_universal import BiometryParser
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize parser
parser = BiometryParser()

@router.get("/{file_id}")
async def extract_fields(file_id: str):
    """
    Extract biometry data from uploaded PDF using universal RunPod parser
    Returns data for BOTH eyes (OD and OS) in one call
    """
    path = resolve_path(file_id)
    if not path:
        raise HTTPException(status_code=404, detail="File not found")
    
    try:
        # Use new universal parser
        logger.info(f"Extracting biometry from {path}")
        complete_data = parser.extract_complete_biometry(str(path))
        
        # Map to frontend expected format
        response = {
            "patient_name": complete_data.get("patient_name", ""),
            "age": complete_data.get("age", None),
            "device": complete_data.get("device", ""),
            "od": {
                "axial_length": complete_data.get("od", {}).get("axial_length"),
                "acd": complete_data.get("od", {}).get("acd"),
                "lt": complete_data.get("od", {}).get("lt"),
                "wtw": complete_data.get("od", {}).get("wtw"),
                "cct": complete_data.get("od", {}).get("cct"),
                "k1": complete_data.get("od", {}).get("k1"),
                "k2": complete_data.get("od", {}).get("k2"),
                "k1_axis": complete_data.get("od", {}).get("k_axis_1"),
                "k2_axis": complete_data.get("od", {}).get("k_axis_2"),
            },
            "os": {
                "axial_length": complete_data.get("os", {}).get("axial_length"),
                "acd": complete_data.get("os", {}).get("acd"),
                "lt": complete_data.get("os", {}).get("lt"),
                "wtw": complete_data.get("os", {}).get("wtw"),
                "cct": complete_data.get("os", {}).get("cct"),
                "k1": complete_data.get("os", {}).get("k1"),
                "k2": complete_data.get("os", {}).get("k2"),
                "k1_axis": complete_data.get("os", {}).get("k_axis_1"),
                "k2_axis": complete_data.get("os", {}).get("k_axis_2"),
            },
            "confidence": {
                # Set all confidence to 0.95 (high) for now
                # We can refine this later based on extraction quality
                "od.axial_length": 0.95,
                "od.acd": 0.95,
                "od.lt": 0.95,
                "od.wtw": 0.95,
                "od.cct": 0.95,
                "od.k1": 0.95,
                "od.k2": 0.95,
                "od.k1_axis": 0.95,
                "od.k2_axis": 0.95,
                "os.axial_length": 0.95,
                "os.acd": 0.95,
                "os.lt": 0.95,
                "os.wtw": 0.95,
                "os.cct": 0.95,
                "os.k1": 0.95,
                "os.k2": 0.95,
                "os.k1_axis": 0.95,
                "os.k2_axis": 0.95,
            },
            "notes": None
        }
        
        # Check if any critical values are missing
        od_has_data = any([
            response["od"].get("axial_length"),
            response["od"].get("k1"),
            response["od"].get("k2")
        ])
        os_has_data = any([
            response["os"].get("axial_length"),
            response["os"].get("k1"),
            response["os"].get("k2")
        ])
        
        if not od_has_data and not os_has_data:
            response["notes"] = "Low-confidence extraction. Please review and correct values."
            logger.warning(f"Low confidence extraction for {file_id}")
        
        logger.info(f"Successfully extracted biometry for {file_id}")
        return response
        
    except Exception as e:
        logger.error(f"Error extracting biometry for {file_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Extraction failed: {str(e)}")
