"""
Toric IOL Policy System

This module defines policies for toric IOL recommendations based on different
clinical philosophies regarding astigmatism management and ATR progression.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ToricPolicy:
    """Policy for toric IOL recommendations based on astigmatism orientation and magnitude."""
    
    # Orientation-specific thresholds (POST-bias totals)
    thr_recommend_ATR: float
    thr_recommend_WTR: float
    thr_recommend_OBL: float

    thr_border_low_ATR: float
    thr_border_low_WTR: float
    thr_border_low_OBL: float

    thr_border_high_ATR: float
    thr_border_high_WTR: float
    thr_border_high_OBL: float

    # Postop residual ceiling and gain rule
    thr_postop_max: float = 0.50
    base_min_gain: float = 0.50
    gain_scale: float = 0.30  # min_gain = max(base_min_gain, gain_scale * postbias_cyl)

    # Pre-bias floors to avoid "manufactured" ATR-only cases
    prebias_floor_ATR: float = 0.20
    prebias_floor_WTR: float = 0.50
    prebias_floor_OBL: float = 0.40

    # Quality gating (optional)
    axis_repeatability_max_deg: float = 20.0
    k_repeatability_max_D: float = 0.40
    quality_penalty: float = 0.25  # added to recommend & min_gain if noisy


# === Policy Presets ===

TORIC_POLICIES: Dict[str, ToricPolicy] = {
    "balanced": ToricPolicy(
        thr_recommend_ATR=0.50, thr_recommend_WTR=0.90, thr_recommend_OBL=0.75,
        thr_border_low_ATR=0.25, thr_border_low_WTR=0.75, thr_border_low_OBL=0.50,
        thr_border_high_ATR=0.50, thr_border_high_WTR=0.90, thr_border_high_OBL=0.75,
    ),
    # ATR-forward lifetime philosophy
    "lifetime_atr": ToricPolicy(
        thr_recommend_ATR=0.25, thr_recommend_WTR=1.00, thr_recommend_OBL=0.75,
        thr_border_low_ATR=0.25, thr_border_low_WTR=0.75, thr_border_low_OBL=0.50,
        thr_border_high_ATR=0.50, thr_border_high_WTR=1.00, thr_border_high_OBL=0.75,
        thr_postop_max=0.50, base_min_gain=0.50, gain_scale=0.30,
        prebias_floor_ATR=0.20, prebias_floor_WTR=0.50, prebias_floor_OBL=0.40,
    ),
    "conservative": ToricPolicy(
        thr_recommend_ATR=0.50, thr_recommend_WTR=1.25, thr_recommend_OBL=1.00,
        thr_border_low_ATR=0.50, thr_border_low_WTR=1.00, thr_border_low_OBL=0.75,
        thr_border_high_ATR=0.75, thr_border_high_WTR=1.25, thr_border_high_OBL=1.00,
        thr_postop_max=0.50, base_min_gain=0.60, gain_scale=0.35,
        prebias_floor_ATR=0.30, prebias_floor_WTR=0.60, prebias_floor_OBL=0.50,
    ),
}


def get_policy(policy_key: str) -> ToricPolicy:
    """Get a toric policy by key, defaulting to lifetime_atr if not found."""
    return TORIC_POLICIES.get(policy_key, TORIC_POLICIES["lifetime_atr"])


def get_available_policies() -> Dict[str, str]:
    """Get available policy keys and descriptions."""
    return {
        "balanced": "Balanced approach - moderate thresholds for all orientations",
        "lifetime_atr": "Lifetime ATR philosophy - lower thresholds for ATR, higher for WTR",
        "conservative": "Conservative approach - higher thresholds, stricter criteria"
    }


def create_custom_policy(**kwargs) -> ToricPolicy:
    """Create a custom toric policy from parameters."""
    # Start with balanced defaults
    defaults = {
        "thr_recommend_ATR": 0.50,
        "thr_recommend_WTR": 0.90,
        "thr_recommend_OBL": 0.75,
        "thr_border_low_ATR": 0.25,
        "thr_border_low_WTR": 0.75,
        "thr_border_low_OBL": 0.50,
        "thr_border_high_ATR": 0.50,
        "thr_border_high_WTR": 0.90,
        "thr_border_high_OBL": 0.75,
        "thr_postop_max": 0.50,
        "base_min_gain": 0.50,
        "gain_scale": 0.30,
        "prebias_floor_ATR": 0.20,
        "prebias_floor_WTR": 0.50,
        "prebias_floor_OBL": 0.40,
        "axis_repeatability_max_deg": 20.0,
        "k_repeatability_max_D": 0.40,
        "quality_penalty": 0.25,
    }
    
    # Override with provided values
    defaults.update(kwargs)
    return ToricPolicy(**defaults)
