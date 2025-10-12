from fastapi import APIRouter, HTTPException
from app.models.schema import SuggestionRequest, SuggestionResponse
from app.services.barrett_toric import BarrettToricCalculator
from app.services.toric_calculator import ToricCalculator
from app.services.iol_database import get_iol_database

router = APIRouter()

@router.post("/", response_model=SuggestionResponse)
async def suggest_iol(req: SuggestionRequest):
    """
    Advanced toric IOL recommendation using the new Advanced Toric Calculator.
    
    This endpoint now uses our blended (theory + empirical) design with power vector notation.
    """
    try:
        # Initialize Advanced Toric Calculator
        calculator = ToricCalculator()
        
        # Extract keratometry data
        k = req.data.ks
        if not (k.k1_power and k.k2_power and k.k1_axis and k.k2_axis):
            return SuggestionResponse(
                recommend_toric=False,
                rationale="Insufficient keratometry data for advanced toric calculation",
                suggested_families=["Alcon AcrySof IQ Non-Toric", "J&J Tecnis Non-Toric"],
                image_hint_url=None,
            )
        
        # Use new SIA fields if available, otherwise fall back to legacy
        if hasattr(req, 'sia_magnitude') and hasattr(req, 'sia_axis') and req.sia_magnitude is not None:
            sia_magnitude = req.sia_magnitude
            sia_axis = req.sia_axis or 120.0  # Default axis if not provided
        else:
            # Legacy fallback
            legacy_sia = req.sia_d or 0.0
            sia_magnitude = legacy_sia
            sia_axis = 120.0
        
        # Estimate ELP (we need this for the toric calculation)
        # For suggestion purposes, use a reasonable estimate
        elp_mm = 5.0  # Default ELP estimate
        
        # Calculate advanced toric IOL recommendation
        toric_result = calculator.calculate_toric_iol(
            k1=k.k1_power, k2=k.k2_power, 
            k1_axis=k.k1_axis, k2_axis=k.k2_axis,
            sia_magnitude=sia_magnitude, sia_axis=sia_axis,
            elp_mm=elp_mm, target_refraction=0.0
        )
        
        # Prepare rationale
        rationale_lines = [
            f"Advanced Toric Calculator Analysis:",
            f"Anterior corneal astigmatism: {abs(k.k2_power - k.k1_power):.2f}D @ {k.k1_axis:.0f}°",
            f"SIA: {sia_magnitude:.2f}D @ {sia_axis:.0f}°",
            f"Total astigmatism: {toric_result.total_astigmatism:.2f}D @ {toric_result.total_axis:.0f}°",
            f"Residual astigmatism: {toric_result.residual_astigmatism:.2f}D @ {toric_result.residual_axis:.0f}°"
        ]
        
        if toric_result.recommend_toric:
            rationale_lines.append(f"Toric recommended: {toric_result.chosen_cyl_power:.1f}D")
            rationale_lines.append(f"Recommendation: Toric IOL (residual {toric_result.residual_astigmatism:.2f}D)")
        else:
            rationale_lines.append(f"Recommendation: Spherical IOL (residual {toric_result.residual_astigmatism:.2f}D)")
        
        # Get IOL database
        db = get_iol_database()
        
        if toric_result.recommend_toric:
            # Get families with toric models
            families_data = db.get_families_for_recommendation(recommend_toric=True)
            families = [f"{f['brand']} {f['family']}" for f in families_data]
        else:
            # Get all families (they all have non-toric options)
            families_data = db.get_families_for_recommendation(recommend_toric=False)
            families = [f"{f['brand']} {f['family']}" for f in families_data]
        
        return SuggestionResponse(
            recommend_toric=toric_result.recommend_toric,
            rationale=" | ".join(rationale_lines),
            suggested_families=families,
            image_hint_url=None,
        )
        
    except Exception as e:
        # Fallback to simple calculation if advanced calculation fails
        k = req.data.ks
        sia = req.sia_d or 0.0
        
        recommend_toric = False
        rationale_lines = [f"Advanced calculation failed: {str(e)[:100]}, using fallback method"]
        
        if k.delta_k is not None:
            effective_astig = max(0.0, (k.delta_k or 0.0) - abs(sia))
            recommend_toric = effective_astig >= 1.0  # Fallback threshold
            rationale_lines.append(f"deltaK={k.delta_k:.2f}D; SIA={sia:.2f}D → effective ~{effective_astig:.2f}D")
        else:
            rationale_lines.append("Insufficient K data; defaulting to non-toric")
        
        families = [
            "Alcon AcrySof IQ Toric / Non-Toric",
            "J&J Tecnis Toric / Non-Toric",
            "Rayner Toric / Non-Toric",
            "Hoya Toric / Non-Toric",
        ]
        
        return SuggestionResponse(
            recommend_toric=recommend_toric,
            rationale=" | ".join(rationale_lines),
            suggested_families=families,
            image_hint_url=None,
        )


@router.post("/barrett-toric")
async def calculate_barrett_toric(request: dict):
    """
    Advanced Barrett Toric calculation using Assumed SIA from review form.
    
    This endpoint accepts the full extracted data with Assumed SIA values
    and returns detailed Barrett Toric analysis for both eyes.
    """
    try:
        from app.services.barrett_toric import calculate_barrett_toric_for_extracted_data
        
        # Extract data from request
        extracted_data = request.get('extracted_data', {})
        
        # Handle new SIA fields or fall back to legacy string format
        if 'assumed_sia_od_magnitude' in request and 'assumed_sia_od_axis' in request:
            assumed_sia_od = f"{request.get('assumed_sia_od_magnitude', 0.1):.1f} deg {request.get('assumed_sia_od_axis', 120.0):.0f}"
        else:
            assumed_sia_od = request.get('assumed_sia_od', '0.1 deg 120')
            
        if 'assumed_sia_os_magnitude' in request and 'assumed_sia_os_axis' in request:
            assumed_sia_os = f"{request.get('assumed_sia_os_magnitude', 0.2):.1f} deg {request.get('assumed_sia_os_axis', 120.0):.0f}"
        else:
            assumed_sia_os = request.get('assumed_sia_os', '0.2 deg 120')
        
        # Calculate Barrett Toric for both eyes
        results = calculate_barrett_toric_for_extracted_data(
            extracted_data, assumed_sia_od, assumed_sia_os
        )
        
        return {
            'success': True,
            'barrett_toric_results': results,
            'method': 'Barrett Toric Calculator',
            'threshold': 0.75  # Barrett recommended threshold
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Barrett Toric calculation error: {str(e)}")


@router.get("/families")
async def get_iol_families():
    """Get all available IOL families."""
    try:
        db = get_iol_database()
        families = db.get_all_families()
        return {
            'success': True,
            'families': families,
            'total_count': len(families)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading IOL families: {str(e)}")


@router.get("/families/{family_id}")
async def get_iol_family_details(family_id: str):
    """Get detailed information about a specific IOL family."""
    try:
        db = get_iol_database()
        family = db.get_family_by_id(family_id)
        
        if not family:
            raise HTTPException(status_code=404, detail=f"IOL family '{family_id}' not found")
        
        return {
            'success': True,
            'family': {
                'id': family.id,
                'brand': family.brand,
                'family': family.family,
                'a_constant': family.a_constant,
                'models': [
                    {
                        'id': model.id,
                        'name': model.name,
                        'type': model.type,
                        'description': model.description,
                        'toric_available': model.toric_available,
                        'toric_models': model.toric_models
                    }
                    for model in family.models
                ]
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading family details: {str(e)}")


@router.get("/families/{family_id}/models")
async def get_family_models(family_id: str, model_type: str = None):
    """Get all models for a specific family, optionally filtered by type."""
    try:
        db = get_iol_database()
        
        if model_type:
            models = db.get_models_by_type(family_id, model_type)
        else:
            models = db.get_family_models(family_id)
        
        if not models:
            raise HTTPException(status_code=404, detail=f"No models found for family '{family_id}'")
        
        return {
            'success': True,
            'family_id': family_id,
            'model_type': model_type,
            'models': models,
            'total_count': len(models)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading family models: {str(e)}")


@router.get("/families/{family_id}/toric")
async def get_toric_models(family_id: str):
    """Get all toric models for a specific family."""
    try:
        db = get_iol_database()
        toric_models = db.get_toric_models(family_id)
        
        return {
            'success': True,
            'family_id': family_id,
            'toric_models': toric_models,
            'total_count': len(toric_models)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading toric models: {str(e)}")


@router.get("/search")
async def search_iol_models(query: str):
    """Search for IOL models across all families."""
    try:
        db = get_iol_database()
        results = db.search_models(query)
        
        return {
            'success': True,
            'query': query,
            'results': results,
            'total_count': len(results)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error searching IOL models: {str(e)}")
