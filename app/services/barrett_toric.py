"""
Barrett Toric Calculator Implementation
Advanced vector-based astigmatism analysis for toric IOL recommendations.

This implementation follows the Barrett Toric Calculator methodology:
- Vector-based astigmatism calculations using polar coordinates
- Proper SIA vector subtraction (not simple arithmetic)
- Residual astigmatism prediction
- Toric power and axis optimization
"""

import math
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from app.models.schema import ExtractedBiometry


@dataclass
class AstigmatismVector:
    """Represents astigmatism as a vector in polar coordinates."""
    magnitude: float  # diopters
    axis: float      # degrees (0-180)
    
    def to_cartesian(self) -> Tuple[float, float]:
        """Convert polar coordinates to Cartesian (J0, J45)."""
        # Convert to radians and double angle for astigmatism
        theta_rad = math.radians(self.axis * 2)
        j0 = self.magnitude * math.cos(theta_rad)
        j45 = self.magnitude * math.sin(theta_rad)
        return j0, j45
    
    @classmethod
    def from_cartesian(cls, j0: float, j45: float) -> 'AstigmatismVector':
        """Create vector from Cartesian coordinates (J0, J45)."""
        magnitude = math.sqrt(j0**2 + j45**2)
        if magnitude == 0:
            return cls(magnitude=0, axis=0)
        
        # Calculate axis (divide by 2 for astigmatism)
        axis_rad = math.atan2(j45, j0) / 2
        axis = math.degrees(axis_rad)
        
        # Normalize axis to 0-180 range
        if axis < 0:
            axis += 180
        
        return cls(magnitude=magnitude, axis=axis)


@dataclass
class BarrettToricResult:
    """Result of Barrett Toric calculation."""
    recommend_toric: bool
    corneal_astigmatism: AstigmatismVector
    effective_astigmatism: AstigmatismVector
    residual_astigmatism: AstigmatismVector
    recommended_toric_power: float
    recommended_toric_axis: float
    confidence_level: str
    rationale: List[str]
    toric_threshold: float = 0.75  # Barrett recommended threshold


class BarrettToricCalculator:
    """Barrett Toric Calculator for advanced toric IOL recommendations."""
    
    def __init__(self):
        # Barrett Toric Calculator constants
        self.toric_threshold = 0.75  # diopters (Barrett recommended)
        self.posterior_corneal_factor = 0.3  # Factor for posterior corneal astigmatism
        
    def parse_sia_string(self, sia_string: str) -> Optional[AstigmatismVector]:
        """Parse SIA string format like '0.1 deg 120' or '0.2D @ 120°'."""
        if not sia_string:
            return None
            
        try:
            # Remove common suffixes and normalize
            clean_string = sia_string.lower().strip()
            clean_string = re.sub(r'[^\d.\-\s]', ' ', clean_string)
            
            # Extract numbers
            numbers = re.findall(r'-?\d+\.?\d*', clean_string)
            if len(numbers) >= 2:
                magnitude = float(numbers[0])
                axis = float(numbers[1])
                return AstigmatismVector(magnitude=magnitude, axis=axis)
        except (ValueError, IndexError):
            pass
        
        return None
    
    def calculate_corneal_astigmatism(self, k1: float, k2: float, 
                                    k1_axis: float, k2_axis: float) -> AstigmatismVector:
        """Calculate corneal astigmatism vector from keratometry."""
        if not all([k1, k2, k1_axis, k2_axis]):
            return AstigmatismVector(magnitude=0, axis=0)
        
        # Calculate corneal astigmatism magnitude
        corneal_astig_magnitude = abs(k2 - k1)
        
        # Determine steep meridian (higher K value)
        if k2 > k1:
            steep_axis = k2_axis
        else:
            steep_axis = k1_axis
        
        return AstigmatismVector(
            magnitude=corneal_astig_magnitude,
            axis=steep_axis
        )
    
    def calculate_posterior_corneal_astigmatism(self, 
                                              corneal_astig: AstigmatismVector) -> AstigmatismVector:
        """Calculate posterior corneal astigmatism contribution."""
        # Barrett method: posterior corneal astigmatism is approximately
        # 30% of anterior corneal astigmatism, orthogonal to it
        posterior_magnitude = corneal_astig.magnitude * self.posterior_corneal_factor
        posterior_axis = corneal_astig.axis + 90
        
        # Normalize axis
        if posterior_axis >= 180:
            posterior_axis -= 180
        
        return AstigmatismVector(
            magnitude=posterior_magnitude,
            axis=posterior_axis
        )
    
    def vector_subtract_sia(self, corneal_astig: AstigmatismVector, 
                          sia: AstigmatismVector) -> AstigmatismVector:
        """Subtract SIA vector from corneal astigmatism vector."""
        if not sia or sia.magnitude == 0:
            return corneal_astig
        
        # Convert to Cartesian coordinates
        corneal_j0, corneal_j45 = corneal_astig.to_cartesian()
        sia_j0, sia_j45 = sia.to_cartesian()
        
        # Vector subtraction
        effective_j0 = corneal_j0 - sia_j0
        effective_j45 = corneal_j45 - sia_j45
        
        # Convert back to polar
        return AstigmatismVector.from_cartesian(effective_j0, effective_j45)
    
    def calculate_effective_astigmatism(self, corneal_astig: AstigmatismVector,
                                      posterior_astig: AstigmatismVector,
                                      sia: AstigmatismVector) -> AstigmatismVector:
        """Calculate total effective astigmatism."""
        # Combine anterior and posterior corneal astigmatism
        anterior_j0, anterior_j45 = corneal_astig.to_cartesian()
        posterior_j0, posterior_j45 = posterior_astig.to_cartesian()
        
        # Total corneal astigmatism (anterior + posterior)
        total_corneal_j0 = anterior_j0 + posterior_j0
        total_corneal_j45 = anterior_j45 + posterior_j45
        total_corneal = AstigmatismVector.from_cartesian(total_corneal_j0, total_corneal_j45)
        
        # Subtract SIA
        return self.vector_subtract_sia(total_corneal, sia)
    
    def calculate_toric_recommendation(self, effective_astig: AstigmatismVector,
                                     target_refraction: float = 0.0) -> Tuple[float, float]:
        """Calculate recommended toric power and axis."""
        if effective_astig.magnitude < self.toric_threshold:
            return 0.0, 0.0
        
        # Barrett method: toric power is approximately 80% of effective astigmatism
        # This accounts for the effective lens position and power vector conversion
        toric_power = effective_astig.magnitude * 0.8
        
        # Round to nearest 0.5D
        toric_power = round(toric_power * 2) / 2
        
        return toric_power, effective_astig.axis
    
    def calculate_residual_astigmatism(self, effective_astig: AstigmatismVector,
                                     toric_power: float, toric_axis: float) -> AstigmatismVector:
        """Calculate predicted residual astigmatism after toric IOL."""
        if toric_power == 0:
            return effective_astig
        
        # Create toric correction vector
        toric_correction = AstigmatismVector(magnitude=toric_power, axis=toric_axis)
        
        # Vector subtraction: effective - correction = residual
        effective_j0, effective_j45 = effective_astig.to_cartesian()
        correction_j0, correction_j45 = toric_correction.to_cartesian()
        
        residual_j0 = effective_j0 - correction_j0
        residual_j45 = effective_j45 - correction_j45
        
        return AstigmatismVector.from_cartesian(residual_j0, residual_j45)
    
    def calculate_confidence_level(self, data_quality: Dict[str, bool]) -> str:
        """Calculate confidence level based on data quality."""
        required_fields = ['k1', 'k2', 'k1_axis', 'k2_axis', 'sia']
        available_fields = sum(1 for field in required_fields if data_quality.get(field, False))
        
        if available_fields >= 5:
            return "High"
        elif available_fields >= 3:
            return "Medium"
        else:
            return "Low"
    
    def calculate_barrett_toric(self, eye_data: Dict, assumed_sia: str, 
                              target_refraction: float = 0.0) -> BarrettToricResult:
        """Main Barrett Toric calculation."""
        rationale = []
        
        # Parse SIA
        sia = self.parse_sia_string(assumed_sia)
        if sia:
            rationale.append(f"SIA: {sia.magnitude:.2f}D @ {sia.axis:.0f}°")
        else:
            rationale.append("SIA: Not provided or invalid format")
            sia = AstigmatismVector(magnitude=0, axis=0)
        
        # Extract keratometry data
        k1 = eye_data.get('k1')
        k2 = eye_data.get('k2')
        k1_axis = eye_data.get('k1_axis')
        k2_axis = eye_data.get('k2_axis')
        
        # Calculate corneal astigmatism
        corneal_astig = self.calculate_corneal_astigmatism(k1, k2, k1_axis, k2_axis)
        
        if corneal_astig.magnitude > 0:
            rationale.append(f"Corneal astigmatism: {corneal_astig.magnitude:.2f}D @ {corneal_astig.axis:.0f}°")
            
            # Calculate posterior corneal astigmatism
            posterior_astig = self.calculate_posterior_corneal_astigmatism(corneal_astig)
            rationale.append(f"Posterior corneal contribution: {posterior_astig.magnitude:.2f}D @ {posterior_astig.axis:.0f}°")
            
            # Calculate effective astigmatism
            effective_astig = self.calculate_effective_astigmatism(corneal_astig, posterior_astig, sia)
            rationale.append(f"Effective astigmatism: {effective_astig.magnitude:.2f}D @ {effective_astig.axis:.0f}°")
            
            # Determine toric recommendation
            recommend_toric = effective_astig.magnitude >= self.toric_threshold
            
            if recommend_toric:
                rationale.append(f"Toric recommended (≥{self.toric_threshold}D threshold)")
            else:
                rationale.append(f"Non-toric recommended (<{self.toric_threshold}D threshold)")
            
            # Calculate toric power and axis
            toric_power, toric_axis = self.calculate_toric_recommendation(effective_astig, target_refraction)
            
            if toric_power > 0:
                rationale.append(f"Recommended toric: {toric_power:.1f}D @ {toric_axis:.0f}°")
            
            # Calculate residual astigmatism
            residual_astig = self.calculate_residual_astigmatism(effective_astig, toric_power, toric_axis)
            if residual_astig.magnitude > 0:
                rationale.append(f"Predicted residual: {residual_astig.magnitude:.2f}D @ {residual_astig.axis:.0f}°")
        else:
            rationale.append("Insufficient keratometry data for calculation")
            effective_astig = AstigmatismVector(magnitude=0, axis=0)
            residual_astig = AstigmatismVector(magnitude=0, axis=0)
            toric_power = 0.0
            toric_axis = 0.0
            recommend_toric = False
        
        # Calculate confidence level
        data_quality = {
            'k1': bool(k1),
            'k2': bool(k2),
            'k1_axis': bool(k1_axis),
            'k2_axis': bool(k2_axis),
            'sia': sia.magnitude > 0
        }
        confidence_level = self.calculate_confidence_level(data_quality)
        
        return BarrettToricResult(
            recommend_toric=recommend_toric,
            corneal_astigmatism=corneal_astig,
            effective_astigmatism=effective_astig,
            residual_astigmatism=residual_astig,
            recommended_toric_power=toric_power,
            recommended_toric_axis=toric_axis,
            confidence_level=confidence_level,
            rationale=rationale
        )
    
    def calculate_both_eyes(self, od_data: Dict, os_data: Dict, 
                          assumed_sia_od: str, assumed_sia_os: str,
                          target_refraction: float = 0.0) -> Dict[str, BarrettToricResult]:
        """Calculate Barrett Toric for both eyes."""
        return {
            'od': self.calculate_barrett_toric(od_data, assumed_sia_od, target_refraction),
            'os': self.calculate_barrett_toric(os_data, assumed_sia_os, target_refraction)
        }


def calculate_barrett_toric_for_extracted_data(extracted_data: Dict, 
                                             assumed_sia_od: str = "0.1 deg 120",
                                             assumed_sia_os: str = "0.2 deg 120") -> Dict:
    """Convenience function to calculate Barrett Toric for extracted biometry data."""
    calculator = BarrettToricCalculator()
    
    # Extract eye data
    od_data = extracted_data.get('od', {})
    os_data = extracted_data.get('os', {})
    
    # Calculate for both eyes
    results = calculator.calculate_both_eyes(
        od_data, os_data, 
        assumed_sia_od, assumed_sia_os
    )
    
    # Format results for API response
    return {
        'od': {
            'recommend_toric': results['od'].recommend_toric,
            'corneal_astigmatism': {
                'magnitude': results['od'].corneal_astigmatism.magnitude,
                'axis': results['od'].corneal_astigmatism.axis
            },
            'effective_astigmatism': {
                'magnitude': results['od'].effective_astigmatism.magnitude,
                'axis': results['od'].effective_astigmatism.axis
            },
            'residual_astigmatism': {
                'magnitude': results['od'].residual_astigmatism.magnitude,
                'axis': results['od'].residual_astigmatism.axis
            },
            'recommended_toric_power': results['od'].recommended_toric_power,
            'recommended_toric_axis': results['od'].recommended_toric_axis,
            'confidence_level': results['od'].confidence_level,
            'rationale': results['od'].rationale
        },
        'os': {
            'recommend_toric': results['os'].recommend_toric,
            'corneal_astigmatism': {
                'magnitude': results['os'].corneal_astigmatism.magnitude,
                'axis': results['os'].corneal_astigmatism.axis
            },
            'effective_astigmatism': {
                'magnitude': results['os'].effective_astigmatism.magnitude,
                'axis': results['os'].effective_astigmatism.axis
            },
            'residual_astigmatism': {
                'magnitude': results['os'].residual_astigmatism.magnitude,
                'axis': results['os'].residual_astigmatism.axis
            },
            'recommended_toric_power': results['os'].recommended_toric_power,
            'recommended_toric_axis': results['os'].recommended_toric_axis,
            'confidence_level': results['os'].confidence_level,
            'rationale': results['os'].rationale
        }
    }

