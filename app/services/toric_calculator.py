"""
Advanced Toric IOL Calculator

Blended (theory + empirical) design with tunable knobs for transparent,
auditable toric IOL power calculations using power vector notation.

Key Features:
- Power vector notation for stable calculations
- Tunable posterior cornea estimator
- ELP-dependent toricity ratio
- ATR/WTR directional weighting
- Iterative refinement loop
"""

import math
from typing import List, Tuple, Dict, Any, Optional
from dataclasses import dataclass
from .toric_policy import ToricPolicy, get_policy


@dataclass
class ToricResult:
    """Result of toric IOL calculation."""
    recommend_toric: bool
    chosen_cyl_power: float  # diopters
    residual_astigmatism: float  # diopters
    residual_axis: float  # degrees
    total_astigmatism: float  # diopters
    total_axis: float  # degrees
    elp_mm: float
    toricity_ratio: float
    iterations: int
    rationale: List[str]


def to_vec(C: float, axis_deg: float) -> Tuple[float, float]:
    """
    Convert cylinder magnitude and axis to power vector (J0, J45).
    
    Args:
        C: Cylinder magnitude in diopters
        axis_deg: Axis in degrees [0, 180)
        
    Returns:
        (J0, J45) power vector components
    """
    th = math.radians(2 * axis_deg % 360)
    return (0.5 * C * math.cos(th), 0.5 * C * math.sin(th))


def from_vec(J0: float, J45: float) -> Tuple[float, float]:
    """
    Convert power vector (J0, J45) to cylinder magnitude and axis.
    
    Args:
        J0, J45: Power vector components
        
    Returns:
        (C, axis_deg) where C is magnitude and axis_deg is in [0, 180)
    """
    C = 2.0 * math.hypot(J0, J45)
    th2 = math.atan2(J45, J0)
    axis = (math.degrees(th2) / 2.0) % 180  # [0,180)
    return C, axis


def is_WTR(axis_deg: float) -> bool:
    """
    Check if axis is With-The-Rule (WTR).
    WTR: ±30° window around 90°
    
    Args:
        axis_deg: Axis in degrees
        
    Returns:
        True if WTR, False if ATR
    """
    a = axis_deg % 180
    return min(abs(a - 90), abs(a - 90 + 180), abs(a - 90 - 180)) <= 30


def posterior_vector(C_ant: float, Kmean: float, axis_ant: float,
                    gamma0: float = 0.10, gamma1: float = 0.30, gamma2: float = 0.02,
                    f_WTR: float = 1.15, f_ATR: float = 0.85) -> Tuple[float, float]:
    """
    Calculate posterior corneal astigmatism vector.
    
    Empirical model: C_post = γ₀ + γ₁·C_ant + γ₂·(K_mean - 43)
    Directional weighting: WTR gets boost, ATR gets reduction
    Posterior naturally ATR (≈180° axis)
    
    Args:
        C_ant: Anterior corneal cylinder magnitude
        Kmean: Mean keratometry
        axis_ant: Anterior corneal cylinder axis
        gamma0, gamma1, gamma2: Tunable model parameters
        f_WTR, f_ATR: Directional weighting factors
        
    Returns:
        (J0, J45) power vector for posterior astigmatism
    """
    # Base magnitude (D)
    Cpost = gamma0 + gamma1 * max(C_ant, 0.0) + gamma2 * (Kmean - 43.0)
    
    # Directional weighting
    mult = f_WTR if is_WTR(axis_ant) else f_ATR
    Cpost *= mult
    
    # ATR axis ≈ 180° → J45=0, J0=+C/2
    return (0.5 * Cpost, 0.0)


def add_sia(J0: float, J45: float, sia_mag: float, sia_axis_deg: float) -> Tuple[float, float]:
    """
    Add SIA vector to existing power vector.
    
    Args:
        J0, J45: Existing power vector components
        sia_mag: SIA magnitude in diopters
        sia_axis_deg: SIA axis in degrees
        
    Returns:
        (J0, J45) updated power vector
    """
    sj0, sj45 = to_vec(sia_mag, sia_axis_deg)
    return (J0 + sj0, J45 + sj45)


def toricity_ratio(elp_mm: float, base: float = 1.46, slope: float = 0.00) -> float:
    """
    Calculate ELP-dependent toricity ratio.
    
    TR(ELP) converts IOL cylinder to corneal-equivalent:
    C_corneal_equiv = C_IOL / TR(ELP)
    
    Args:
        elp_mm: Effective lens position in mm
        base: Base toricity ratio
        slope: ELP slope factor (future enhancement)
        
    Returns:
        Toricity ratio
    """
    return base + slope * (elp_mm - 5.0)


def choose_toric(C_total: float, axis_total: float, elp_mm: float, 
                sku_iol_cyl_list: List[float], atr_boost: float = 1.05) -> Tuple[float, float, float, Tuple[float, float]]:
    """
    Choose optimal toric IOL cylinder power to minimize residual astigmatism.
    
    Args:
        C_total: Total astigmatism magnitude
        axis_total: Total astigmatism axis
        elp_mm: Effective lens position
        sku_iol_cyl_list: Available toric IOL cylinder powers
        atr_boost: ATR correction boost factor
        
    Returns:
        (residual_mag, chosen_cyl, corneal_equiv, (C_res, axis_res))
    """
    J0t, J45t = to_vec(C_total, axis_total)
    
    # Direction check for ATR boost
    _, axis_tot = from_vec(J0t, J45t)
    boost = atr_boost if not is_WTR(axis_tot) else 1.0
    
    best = None
    for cyl_iol in sku_iol_cyl_list:
        tr = toricity_ratio(elp_mm)
        c_at_cornea = (cyl_iol / tr) * boost
        J0c, J45c = to_vec(c_at_cornea, axis_total)
        rJ0, rJ45 = (J0t - J0c), (J45t - J45c)
        resid = math.hypot(rJ0, rJ45)
        
        if (best is None) or (resid < best[0]):
            best = (resid, cyl_iol, c_at_cornea, from_vec(rJ0, rJ45))
    
    return best


def toric_decision(
    # Inputs describing total corneal astigmatism at corneal plane (AFTER SIA + posterior model)
    C_total_D: float,
    axis_total_deg: float,
    # ELP and SKUs:
    elp_mm: float,
    sku_iol_cyl_list: list,
    # Strategy knobs (same as in your choose_toric)
    atr_boost: float = 1.05,
    # Decision thresholds:
    thr_recommend: float = 1.25,     # preop total cyl to strongly recommend toric
    thr_maybe_low: float = 0.75,     # lower bound for borderline zone
    thr_maybe_high: float = 1.25,    # upper bound for borderline zone
    thr_postop: float = 0.75,        # acceptable postop residual with toric
    min_gain: float = 0.75,          # minimum reduction needed to justify toric
    # Quality gates (optional):
    axis_repeatability_deg: float = 10.0,  # larger => poorer repeatability
    axis_repeatability_max: float = 20.0,  # beyond this, we likely avoid toric
    k_repeatability_D: float = 0.20,       # SD across K captures (optional)
    k_repeatability_max: float = 0.40,     # beyond this, we likely avoid toric
    # Hook to your function:
    choose_toric_fn=None,  # defaults to choose_toric defined earlier
):
    """
    Returns a dict with recommendation + rationale.
    Assumes C_total_D/axis_total_deg already include SIA + posterior adjustments.
    """
    if choose_toric_fn is None:
        choose_toric_fn = choose_toric  # use your previously defined chooser

    # Residual WITHOUT toric equals the total corneal cylinder magnitude
    non_toric_residual = float(C_total_D)

    # If axis/quality is very poor, require larger preop cylinder and larger gain
    quality_penalty = 0.0
    if axis_repeatability_deg > axis_repeatability_max or k_repeatability_D > k_repeatability_max:
        quality_penalty = 0.25  # tighten thresholds
    adj_thr_recommend = thr_recommend + quality_penalty
    adj_min_gain     = min_gain + quality_penalty

    # Find best toric SKU
    resid, sku, c_at_cornea, (cres, ares) = choose_toric_fn(
        C_total=C_total_D,
        axis_total=axis_total_deg,
        elp_mm=elp_mm,
        sku_iol_cyl_list=sku_iol_cyl_list,
        atr_boost=atr_boost,
    )
    toric_residual = float(cres)
    gain = non_toric_residual - toric_residual

    # Decision logic
    if non_toric_residual >= adj_thr_recommend and toric_residual <= thr_postop and gain >= adj_min_gain:
        rec = "recommend_toric"
        reason = (
            f"Preop cyl {non_toric_residual:.2f} D ≥ {adj_thr_recommend:.2f}; "
            f"best toric residual {toric_residual:.2f} D ≤ {thr_postop:.2f}; "
            f"gain {gain:.2f} D ≥ {adj_min_gain:.2f}."
        )
    elif thr_maybe_low <= non_toric_residual < thr_maybe_high and toric_residual <= thr_postop and gain >= (adj_min_gain - 0.25):
        rec = "borderline_toric"
        reason = (
            f"Preop cyl {non_toric_residual:.2f} D in borderline range "
            f"[{thr_maybe_low:.2f}, {thr_maybe_high:.2f}); residual {toric_residual:.2f} D, gain {gain:.2f} D."
        )
    else:
        rec = "no_toric"
        reason = (
            f"Preop cyl {non_toric_residual:.2f} D; "
            f"toric residual {toric_residual:.2f} D; gain {gain:.2f} D "
            f"does not meet thresholds."
        )

    # Quality overrides: if quality very poor, down-rate to borderline/no_toric
    quality_flag = (axis_repeatability_deg > axis_repeatability_max or k_repeatability_D > k_repeatability_max)
    if quality_flag and rec == "recommend_toric":
        rec = "borderline_toric"
        reason += " Quality concerns (axis/K repeatability) → downgraded to borderline."

    return {
        "decision": rec,
        "preop_total_cyl_d": round(non_toric_residual, 2),
        "best_toric_sku_cyl_iol_d": sku,
        "best_toric_corneal_equiv_d": round(c_at_cornea, 2),
        "predicted_residual_with_toric_d": round(toric_residual, 2),
        "predicted_residual_without_toric_d": round(non_toric_residual, 2),
        "expected_gain_d": round(gain, 2),
        "chosen_axis_deg": round(ares, 0),
        "elp_mm": round(elp_mm, 2),
        "thresholds": {
            "thr_recommend": thr_recommend,
            "thr_maybe_low": thr_maybe_low,
            "thr_maybe_high": thr_maybe_high,
            "thr_postop": thr_postop,
            "min_gain": min_gain,
        },
        "quality_inputs": {
            "axis_repeatability_deg": axis_repeatability_deg,
            "k_repeatability_D": k_repeatability_D,
        },
        "rationale": reason,
    }


class ToricCalculator:
    """Advanced toric IOL calculator with iterative refinement."""
    
    def __init__(self):
        # Tunable parameters (can be updated from literature/bias layer)
        self.gamma_params = {
            'gamma0': 0.10,  # Base posterior magnitude
            'gamma1': 0.30,  # Anterior cylinder scaling
            'gamma2': 0.02   # K-mean dependency
        }
        
        self.directional_weights = {
            'f_WTR': 1.15,   # WTR boost factor
            'f_ATR': 0.85    # ATR reduction factor
        }
        
        self.toricity_params = {
            'base': 1.46,    # Base toricity ratio
            'slope': 0.00    # ELP slope (future)
        }
        
        self.atr_boost = 1.05  # ATR correction boost
        
        # Available toric IOL cylinder powers (example - should be loaded from database)
        self.default_toric_skus = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5, 6.0]
    
    def calculate_toric_iol(self, 
                          k1: float, k2: float, k1_axis: float, k2_axis: float,
                          sia_magnitude: float, sia_axis: float,
                          elp_mm: float, target_refraction: float = 0.0,
                          toric_skus: Optional[List[float]] = None,
                          policy_key: str = "lifetime_atr") -> ToricResult:
        """
        Calculate optimal toric IOL power with iterative refinement.
        
        Args:
            k1, k2: Keratometry readings (diopters)
            k1_axis, k2_axis: Keratometry axes (degrees)
            sia_magnitude: SIA magnitude (diopters)
            sia_axis: SIA axis (degrees)
            elp_mm: Effective lens position (mm)
            target_refraction: Target postoperative refraction
            toric_skus: Available toric IOL cylinder powers
            
        Returns:
            ToricResult with calculation details
        """
        if toric_skus is None:
            toric_skus = self.default_toric_skus
        
        rationale = []
        iterations = 0
        
        # Step 1: Calculate anterior corneal astigmatism
        delta_k = abs(k1 - k2)
        k_axis = k1_axis if k1 > k2 else k2_axis  # Steep axis
        
        # Start with deterministic algorithm label for confidence
        rationale.append("Deterministic Algorithm: Advanced toric calculator with policy-based thresholds")
        
        rationale.append(f"Anterior corneal astigmatism: {delta_k:.2f}D @ {k_axis:.0f}°")
        
        # Step 2: Convert to power vectors
        J0_ant, J45_ant = to_vec(delta_k, k_axis)
        
        # Step 3: Add SIA
        J0_postop, J45_postop = add_sia(J0_ant, J45_ant, sia_magnitude, sia_axis)
        rationale.append(f"SIA (User Input): {sia_magnitude:.2f}D @ {sia_axis:.0f}°")
        
        # Step 4: Add posterior corneal astigmatism
        k_mean = (k1 + k2) / 2.0
        J0_post, J45_post = posterior_vector(
            delta_k, k_mean, k_axis,
            **self.gamma_params, **self.directional_weights
        )
        
        J0_total, J45_total = J0_postop + J0_post, J45_postop + J45_post
        C_total, axis_total = from_vec(J0_total, J45_total)
        
        # Posterior astigmatism is calculated but not displayed to user (inferred value)
        rationale.append(f"Total astigmatism: {C_total:.2f}D @ {axis_total:.0f}°")
        
        # Step 5: Use the new policy-based deterministic decision layer
        policy = get_policy(policy_key)
        
        # Calculate pre-bias (anterior only) for guard
        pre_bias_cyl = delta_k
        pre_bias_axis = k_axis
        
        decision_result = toric_decision_with_policy(
            C_total_D=C_total,
            axis_total_deg=axis_total,
            pre_bias_cyl_d=pre_bias_cyl,
            pre_bias_axis_deg=pre_bias_axis,
            elp_mm=elp_mm,
            sku_iol_cyl_list=toric_skus,
            policy=policy,
            atr_boost=self.atr_boost
        )
        
        # Map decision to recommendation
        decision = decision_result["decision"]
        if decision == "recommend_toric":
            recommend = True
            recommendation_text = "Toric IOL Recommended"
        elif decision == "borderline_toric":
            recommend = False  # Borderline cases don't strongly recommend toric
            recommendation_text = "Toric IOL Considered (Borderline)"
        else:  # "no_toric"
            recommend = False
            recommendation_text = "Spherical IOL Sufficient"
        
        # Format policy name with proper capitalization
        policy_display = policy_key.replace('_', ' ').title()
        if 'Atr' in policy_display:
            policy_display = policy_display.replace('Atr', 'ATR')
        
        rationale.append(f"Policy: {policy_display} ({decision_result['orientation']} orientation)")
        rationale.append(f"Decision Layer: {recommendation_text}")
        rationale.append(f"Rationale: {decision_result['rationale']}")
        rationale.append(f"Preop Total: {decision_result['post_bias_total_cyl_d']}D")
        rationale.append(f"Best Toric: {decision_result['best_toric_sku_cyl_iol_d']}D IOL")
        rationale.append(f"Expected Gain: {decision_result['expected_gain_d']}D")
        
        return ToricResult(
            recommend_toric=recommend,
            chosen_cyl_power=decision_result["best_toric_sku_cyl_iol_d"],
            residual_astigmatism=decision_result["predicted_residual_with_toric_d"],
            residual_axis=decision_result["chosen_axis_deg"],
            total_astigmatism=decision_result["post_bias_total_cyl_d"],
            total_axis=axis_total,
            elp_mm=elp_mm,
            toricity_ratio=toricity_ratio(elp_mm, **self.toricity_params),
            iterations=1,  # Decision layer is deterministic, no iteration needed
            rationale=rationale
        )
    
    def update_parameters(self, **kwargs):
        """Update tunable parameters from literature or bias layer."""
        if 'gamma_params' in kwargs:
            self.gamma_params.update(kwargs['gamma_params'])
        if 'directional_weights' in kwargs:
            self.directional_weights.update(kwargs['directional_weights'])
        if 'toricity_params' in kwargs:
            self.toricity_params.update(kwargs['toricity_params'])
        if 'atr_boost' in kwargs:
            self.atr_boost = kwargs['atr_boost']


def _orient(axis_deg: float) -> str:
    """Determine astigmatism orientation: ATR, WTR, or OBL."""
    a = axis_deg % 180.0
    if min(abs(a-0), abs(a-180)) <= 30: 
        return "ATR"
    if abs(a-90) <= 30: 
        return "WTR"
    return "OBL"


def toric_decision_with_policy(
    # POST-bias (anterior + SIA + posterior/ATR)
    C_total_D: float,
    axis_total_deg: float,
    # PRE-bias (anterior-only) optional guard
    pre_bias_cyl_d: float | None,
    pre_bias_axis_deg: float | None,
    # ELP + SKUs
    elp_mm: float,
    sku_iol_cyl_list: list,
    # Policy & knobs
    policy: ToricPolicy,
    atr_boost: float = 1.05,
    # Measurement quality (optional)
    axis_repeatability_deg: float = 10.0,
    k_repeatability_D: float = 0.20,
    # Hook
    choose_toric_fn=None,
):
    """
    Policy-based toric decision with orientation-specific thresholds.
    
    This function implements the sophisticated decision layer that considers:
    - Orientation-specific thresholds (ATR vs WTR vs OBL)
    - Pre-bias vs post-bias astigmatism
    - Quality gating based on measurement repeatability
    - Gain scaling based on astigmatism magnitude
    """
    if choose_toric_fn is None:
        choose_toric_fn = choose_toric

    orient = _orient(axis_total_deg)

    # Pull thresholds from policy based on orientation
    thr_rec = {
        "ATR": policy.thr_recommend_ATR,
        "WTR": policy.thr_recommend_WTR,
        "OBL": policy.thr_recommend_OBL,
    }[orient]
    thr_low = {
        "ATR": policy.thr_border_low_ATR,
        "WTR": policy.thr_border_low_WTR,
        "OBL": policy.thr_border_low_OBL,
    }[orient]
    thr_high = {
        "ATR": policy.thr_border_high_ATR,
        "WTR": policy.thr_border_high_WTR,
        "OBL": policy.thr_border_high_OBL,
    }[orient]
    pre_floor = {
        "ATR": policy.prebias_floor_ATR,
        "WTR": policy.prebias_floor_WTR,
        "OBL": policy.prebias_floor_OBL,
    }[orient]

    # Quality penalty (optional)
    quality_pen = 0.0
    if axis_repeatability_deg > policy.axis_repeatability_max_deg or k_repeatability_D > policy.k_repeatability_max_D:
        quality_pen = policy.quality_penalty

    thr_rec += quality_pen
    min_gain = max(policy.base_min_gain + quality_pen, policy.gain_scale * float(C_total_D))

    # Non-toric residual (post-bias magnitude)
    non_toric_residual = float(C_total_D)

    # Best toric choice
    resid, sku, c_at_cornea, (cres, ares) = choose_toric_fn(
        C_total=C_total_D,
        axis_total=axis_total_deg,
        elp_mm=elp_mm,
        sku_iol_cyl_list=sku_iol_cyl_list,
        atr_boost=atr_boost,
    )
    toric_residual = float(cres)
    gain = non_toric_residual - toric_residual

    # Decision logic
    if non_toric_residual >= thr_rec and toric_residual <= policy.thr_postop_max and gain >= min_gain:
        rec = "recommend_toric"
        reason = (f"{orient}: post-bias {non_toric_residual:.2f}≥{thr_rec:.2f}, "
                  f"residual {toric_residual:.2f}≤{policy.thr_postop_max:.2f}, "
                  f"gain {gain:.2f}≥{min_gain:.2f}.")
    elif thr_low <= non_toric_residual < thr_high and toric_residual <= policy.thr_postop_max and gain >= (min_gain - 0.25):
        rec = "borderline_toric"
        reason = (f"{orient}: post-bias {non_toric_residual:.2f} in [{thr_low:.2f},{thr_high:.2f}); "
                  f"residual {toric_residual:.2f}, gain {gain:.2f}.")
    else:
        rec = "no_toric"
        reason = (f"{orient}: post-bias {non_toric_residual:.2f}; residual {toric_residual:.2f}; "
                  f"gain {gain:.2f} not sufficient.")

    # Pre-bias guard (respect philosophy while avoiding "manufactured" cases)
    if pre_bias_cyl_d is not None and rec == "recommend_toric" and pre_bias_cyl_d < pre_floor:
        rec = "borderline_toric"
        reason += f" Pre-bias anterior {pre_bias_cyl_d:.2f}<{pre_floor:.2f} → downgraded to borderline."

    return {
        "decision": rec,
        "policy": "custom",  # Will be set by caller if using preset
        "orientation": orient,
        "pre_bias_anterior_cyl_d": None if pre_bias_cyl_d is None else round(pre_bias_cyl_d, 2),
        "post_bias_total_cyl_d": round(non_toric_residual, 2),
        "best_toric_sku_cyl_iol_d": sku,
        "best_toric_corneal_equiv_d": round(c_at_cornea, 2),
        "predicted_residual_with_toric_d": round(toric_residual, 2),
        "predicted_residual_without_toric_d": round(non_toric_residual, 2),
        "expected_gain_d": round(gain, 2),
        "chosen_axis_deg": round(ares, 0),
        "elp_mm": round(elp_mm, 2),
        "rationale": reason,
    }
