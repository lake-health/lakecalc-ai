"""
IOL Power Calculation API Routes
"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

from app.services.calculations import IOLCalculator, IOLCalculationInput, extract_calculation_input
from app.services.toric_calculator import ToricCalculator
from app.models.schema import ExtractedBiometry


class CalculationRequest(BaseModel):
    """Request model for IOL power calculations."""
    extracted_data: ExtractedBiometry
    target_refraction: float = Field(default=0.0, description="Target postoperative refraction in diopters")
    surgeon_factor: float = Field(default=1.0, description="Surgeon-specific A-constant adjustment factor")
    iol_manufacturer: Optional[str] = Field(default=None, description="IOL manufacturer (e.g., 'Alcon')")
    iol_model: Optional[str] = Field(default=None, description="IOL model (e.g., 'AcrySof IQ')")


class CalculationResponse(BaseModel):
    """Response model for IOL power calculations."""
    eye: str = Field(description="Eye being calculated (OD/OS)")
    calculations: List[Dict] = Field(description="Results from different calculation formulas")
    toric_calculation: Optional[Dict] = Field(default=None, description="Toric IOL calculation if applicable")
    recommended_formula: str = Field(description="Recommended formula based on data quality")
    overall_confidence: str = Field(description="Overall confidence level")
    notes: List[str] = Field(description="Clinical notes and warnings")


router = APIRouter()
calculator = IOLCalculator()


@router.post("/", response_model=CalculationResponse)
async def calculate_iol_power(request: CalculationRequest) -> CalculationResponse:
    """
    Calculate IOL power using multiple formulas.
    
    This endpoint takes extracted biometry data and calculates IOL power
    using SRK/T, Holladay, and Haigis formulas.
    """
    try:
        # Convert extracted data to calculation input
        calc_input = extract_calculation_input(
            request.extracted_data,
            request.target_refraction
        )
        
        # Add IOL-specific information
        calc_input.iol_manufacturer = request.iol_manufacturer
        calc_input.iol_model = request.iol_model
        
        # Apply surgeon factor
        calc_input.surgeon_factor = request.surgeon_factor
        
        # Calculate using all available formulas
        results = calculator.calculate_all_formulas(calc_input)
        
        # Convert results to response format
        calculation_results = []
        for result in results:
            calculation_results.append({
                "formula": result.formula_name,
                "iol_power": result.iol_power,
                "prediction_accuracy": result.prediction_accuracy,
                "confidence_level": result.confidence_level,
                "notes": result.notes,
                "formula_data": result.formula_specific_data
            })
        
        # Determine recommended formula (prioritize SRK/T, then highest accuracy)
        recommended_formula = "SRK/T"  # Primary recommendation
        if calculation_results:
            # First try to find SRK/T
            srkt_result = next((r for r in calculation_results if r["formula"] == "SRK/T"), None)
            if srkt_result:
                recommended_formula = "SRK/T"
            else:
                # Fall back to highest accuracy formula
                recommended_formula = max(
                    calculation_results,
                    key=lambda x: x["prediction_accuracy"]
                )["formula"]
        
        # Calculate overall confidence
        if calculation_results:
            avg_accuracy = sum(r["prediction_accuracy"] for r in calculation_results) / len(calculation_results)
            if avg_accuracy >= 90:
                overall_confidence = "High"
            elif avg_accuracy >= 80:
                overall_confidence = "Medium"
            else:
                overall_confidence = "Low"
        else:
            overall_confidence = "Low"
        
        # Calculate toric IOL if we have K data
        toric_calculation = None
        if (request.extracted_data.ks.k1_power and 
            request.extracted_data.ks.k2_power and
            request.extracted_data.ks.k1_axis and
            request.extracted_data.ks.k2_axis):
            
            from app.services.calculations import calculate_toric_iol
            
            # Calculate corneal astigmatism
            k1 = request.extracted_data.ks.k1_power
            k2 = request.extracted_data.ks.k2_power
            corneal_astigmatism = abs(k2 - k1) if k1 and k2 else 0.0
            
            # Get base IOL power from recommended formula
            base_iol_power = calculation_results[0]["iol_power"] if calculation_results else 0.0
            
            toric_calculation = calculate_toric_iol(
                base_iol_power,
                corneal_astigmatism,
                request.extracted_data.ks.k1_axis or 90
            )
        
        # Generate clinical notes
        notes = []
        
        # Data quality notes
        if not calc_input.axial_length:
            notes.append("⚠️ Warning: Axial length not available - calculations may be inaccurate")
        if not calc_input.k_avg:
            notes.append("⚠️ Warning: Keratometry data not available - calculations may be inaccurate")
        
        # Clinical warnings
        if calc_input.axial_length and (calc_input.axial_length < 22.0 or calc_input.axial_length > 26.0):
            notes.append("⚠️ Warning: Extreme axial length - consider multiple formulas and manual verification")
        
        if calc_input.k_avg and (calc_input.k_avg < 40.0 or calc_input.k_avg > 46.0):
            notes.append("⚠️ Warning: Extreme keratometry values - consider corneal topography")
        
        if toric_calculation and toric_calculation["recommended_toric"]:
            notes.append(f"💡 Recommendation: Consider toric IOL for {toric_calculation['corneal_astigmatism']:.1f}D astigmatism")
        
        return CalculationResponse(
            eye=request.extracted_data.eye or "Unknown",
            calculations=calculation_results,
            toric_calculation=toric_calculation,
            recommended_formula=recommended_formula,
            overall_confidence=overall_confidence,
            notes=notes
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Calculation error: {str(e)}")


@router.get("/formulas")
async def get_available_formulas() -> Dict[str, Dict]:
    """
    Get information about available calculation formulas.
    """
    return {
        "SRK/T": {
            "description": "SRK/T: True theoretical formula with vergence model and retinal thickness correction",
            "required_data": ["axial_length", "keratometry"],
            "accuracy": "Exceptional for all eye lengths with proper A-constants",
            "best_for": "Primary recommendation - most comprehensive theoretical implementation"
        },
        "Haigis": {
            "description": "Haigis: Published three-constant formula with optimized constants",
            "required_data": ["axial_length", "keratometry", "acd", "lt"],
            "accuracy": "Highest for eyes with complete biometry",
            "best_for": "Secondary recommendation for complex cases with full biometry"
        },
        "Cooke K6": {
            "description": "Cooke K6: API-based formula with advanced biometry integration",
            "required_data": ["axial_length", "keratometry", "acd", "lt", "wtw", "cct"],
            "accuracy": "Exceptional for eyes with complete biometry data",
            "best_for": "Premium recommendation for cases with full biometry (API-based)"
        }
    }


@router.post("/toric")
async def calculate_toric_iol(request: CalculationRequest) -> Dict:
    """
    Calculate toric IOL power and axis.
    """
    try:
        calc_input = extract_calculation_input(
            request.extracted_data,
            request.target_refraction
        )
        calc_input.surgeon_factor = request.surgeon_factor
        
        # Validate we have K data
        if not (request.extracted_data.ks.k1_power and 
                request.extracted_data.ks.k2_power and
                request.extracted_data.ks.k1_axis and
                request.extracted_data.ks.k2_axis):
            raise HTTPException(
                status_code=400, 
                detail="Keratometry data (K1, K2, axes) required for toric calculation"
            )
        
        # Calculate toric IOL using the enhanced function
        from app.services.calculations import calculate_toric_iol
        
        # Get base IOL power from SRK/T
        iol_results = calculator.calculate_all_formulas(calc_input)
        base_iol_power = iol_results[0].iol_power if iol_results else 0.0
        
        # Get corneal astigmatism
        k1 = request.extracted_data.ks.k1_power
        k2 = request.extracted_data.ks.k2_power
        corneal_astigmatism = abs(k2 - k1) if k1 and k2 else 0.0
        axis = request.extracted_data.ks.k1_axis or 90
        
        toric_result = calculate_toric_iol(
            base_iol_power,
            corneal_astigmatism,
            axis,
            assumed_sia=0.3
        )
        
        return toric_result
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Toric calculation error: {str(e)}")


class AdvancedToricRequest(BaseModel):
    """Request model for advanced toric IOL calculations."""
    extracted_data: ExtractedBiometry
    target_refraction: float = 0.0
    # SIA parameters (new separated format)
    sia_od_magnitude: Optional[float] = Field(None, description="SIA magnitude for OD eye (diopters)")
    sia_od_axis: Optional[float] = Field(None, description="SIA axis for OD eye (degrees)")
    sia_os_magnitude: Optional[float] = Field(None, description="SIA magnitude for OS eye (diopters)")
    sia_os_axis: Optional[float] = Field(None, description="SIA axis for OS eye (degrees)")
    # Toric policy selection
    toric_policy: Optional[str] = Field("lifetime_atr", description="Toric policy: balanced, lifetime_atr, conservative, or custom")
    # Tunable parameters (optional)
    gamma_params: Optional[Dict[str, float]] = Field(None, description="Posterior cornea model parameters")
    directional_weights: Optional[Dict[str, float]] = Field(None, description="WTR/ATR weighting factors")
    toricity_params: Optional[Dict[str, float]] = Field(None, description="Toricity ratio parameters")
    atr_boost: Optional[float] = Field(None, description="ATR correction boost factor")


@router.post("/advanced-toric")
async def calculate_advanced_toric(request: AdvancedToricRequest):
    """
    Advanced toric IOL calculation using power vector notation and iterative refinement.
    
    This endpoint implements the blended (theory + empirical) design with:
    - Power vector notation for stable calculations
    - Tunable posterior cornea estimator
    - ELP-dependent toricity ratio
    - ATR/WTR directional weighting
    - Iterative refinement loop
    """
    try:
        calculator = ToricCalculator()
        
        # Update parameters if provided
        if any([request.gamma_params, request.directional_weights, 
                request.toricity_params, request.atr_boost is not None]):
            update_params = {}
            if request.gamma_params:
                update_params['gamma_params'] = request.gamma_params
            if request.directional_weights:
                update_params['directional_weights'] = request.directional_weights
            if request.toricity_params:
                update_params['toricity_params'] = request.toricity_params
            if request.atr_boost is not None:
                update_params['atr_boost'] = request.atr_boost
            calculator.update_parameters(**update_params)
        
        results = {}
        
        # Process the single eye from ExtractedBiometry
        eye_data = request.extracted_data
        eye = eye_data.eye or 'od'
        
        # Skip if no data
        if not eye_data or not eye_data.al_mm:
            results['error'] = "No axial length data available"
        else:
            
            # Get keratometry data
            k1 = eye_data.ks.k1_power
            k2 = eye_data.ks.k2_power
            k1_axis = eye_data.ks.k1_axis
            k2_axis = eye_data.ks.k2_axis
            
            if not all([k1, k2, k1_axis is not None, k2_axis is not None]):
                results[eye] = {
                    "error": "Incomplete keratometry data",
                    "required": ["k1", "k2", "k1_axis", "k2_axis"]
                }
            else:
                # Get SIA parameters
                if eye.lower() == 'od':
                    sia_magnitude = request.sia_od_magnitude or 0.1
                    sia_axis = request.sia_od_axis or 120.0
                else:
                    sia_magnitude = request.sia_os_magnitude or 0.2
                    sia_axis = request.sia_os_axis or 120.0
            
                # Calculate base IOL power using SRK/T to get ELP
                calc_input = IOLCalculationInput(
                    axial_length=eye_data.al_mm,
                    k_avg=(k1 + k2) / 2.0,
                    acd=eye_data.acd_mm,
                    lt=eye_data.lt_mm,
                    target_refraction=request.target_refraction,
                    wtw=eye_data.wtw_mm,
                    cct=eye_data.cct_um / 1000.0 if eye_data.cct_um else None,
                    k1=k1, k2=k2,
                    k1_axis=k1_axis, k2_axis=k2_axis
                )
                
                iol_calculator = IOLCalculator()
                iol_results = iol_calculator.calculate_all_formulas(calc_input)
                
                # Get ELP from SRK/T result
                srkt_result = next((r for r in iol_results if r.formula_name == "SRK/T"), None)
                if not srkt_result:
                    results[eye] = {"error": "SRK/T calculation required for ELP"}
                else:
                    elp_mm = srkt_result.formula_specific_data.get("ELP_mm", 5.0)
                    
                    # Calculate advanced toric IOL
                    toric_result = calculator.calculate_toric_iol(
                        k1=k1, k2=k2, k1_axis=k1_axis, k2_axis=k2_axis,
                        sia_magnitude=sia_magnitude, sia_axis=sia_axis,
                        elp_mm=elp_mm, target_refraction=request.target_refraction,
                        policy_key=request.toric_policy or "lifetime_atr"
                    )
                    
                    # Combine IOL and toric results
                    results[eye] = {
                        "base_iol_power": srkt_result.iol_power,
                        "recommend_toric": toric_result.recommend_toric,
                        "chosen_toric_power": toric_result.chosen_cyl_power,
                        "total_astigmatism": {
                            "magnitude": toric_result.total_astigmatism,
                            "axis": toric_result.total_axis
                        },
                        "residual_astigmatism": {
                            "magnitude": toric_result.residual_astigmatism,
                            "axis": toric_result.residual_axis
                        },
                        "elp_mm": toric_result.elp_mm,
                        "toricity_ratio": toric_result.toricity_ratio,
                        "iterations": toric_result.iterations,
                        "rationale": toric_result.rationale,
                        "sia_used": {
                            "magnitude": sia_magnitude,
                            "axis": sia_axis
                        },
                        "parameters": {
                            "gamma_params": calculator.gamma_params,
                            "directional_weights": calculator.directional_weights,
                            "toricity_params": calculator.toricity_params,
                            "atr_boost": calculator.atr_boost
                        }
                    }
        
        return {
            "status": "success",
            "results": results,
            "method": "Advanced power vector analysis with iterative refinement",
            "timestamp": "2025-10-09T21:00:00Z"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Advanced toric calculation error: {str(e)}")

