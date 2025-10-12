# Toric IOL Policy System

## Overview

The Toric Policy System provides orientation-specific (ATR/WTR/OBL) thresholding for toric IOL recommendations, accounting for age-related astigmatism progression and different clinical philosophies.

## Implementation Status

✅ **Complete** - Backend, API, and Frontend fully integrated

## Key Features

### 1. **Orientation-Specific Thresholds**
- **ATR (Against-the-Rule)**: Axis near 0° or 180°
- **WTR (With-the-Rule)**: Axis near 90°
- **OBL (Oblique)**: All other orientations

### 2. **Pre-Bias vs Post-Bias Analysis**
- **Pre-bias**: Anterior corneal astigmatism only
- **Post-bias**: Anterior + SIA + Posterior astigmatism
- **Guard mechanism**: Prevents "manufactured" toric recommendations when pre-bias is too low

### 3. **Quality Gating**
- Axis repeatability threshold (default: 20°)
- K repeatability threshold (default: 0.40D)
- Automatic threshold adjustment for poor-quality measurements

## Available Policies

### **Lifetime ATR** (Default)
**Philosophy**: Account for natural ATR progression with age

**Thresholds**:
- ATR recommend: **0.25D** (very aggressive - anticipate progression)
- WTR recommend: **1.00D** (conservative - likely to regress)
- OBL recommend: **0.75D** (moderate)
- Postop max residual: **0.50D**
- Base min gain: **0.50D**

**Best for**: 
- Younger patients with WTR astigmatism (likely to shift to ATR)
- Patients with small ATR astigmatism (will increase with age)

### **Balanced**
**Philosophy**: Moderate approach for all orientations

**Thresholds**:
- ATR recommend: **0.50D**
- WTR recommend: **0.90D**
- OBL recommend: **0.75D**
- Postop max residual: **0.50D**
- Base min gain: **0.50D**

**Best for**:
- Average age patients
- Stable astigmatism patterns
- General cataract surgery population

### **Conservative**
**Philosophy**: Higher thresholds, stricter criteria

**Thresholds**:
- ATR recommend: **0.50D**
- WTR recommend: **1.25D**
- OBL recommend: **1.00D**
- Postop max residual: **0.50D**
- Base min gain: **0.60D**
- Gain scale: **0.35** (vs 0.30 in others)

**Best for**:
- Older patients with stable astigmatism
- Risk-averse practitioners
- Patients with borderline measurements

## API Usage

### Get Available Policies

```bash
GET http://localhost:8000/suggest/policies
```

**Response**:
```json
{
  "policies": {
    "balanced": "Balanced approach - moderate thresholds for all orientations",
    "lifetime_atr": "Lifetime ATR philosophy - lower thresholds for ATR, higher for WTR",
    "conservative": "Conservative approach - higher thresholds, stricter criteria"
  }
}
```

### Calculate with Policy

```bash
POST http://localhost:8000/suggest
```

**Request**:
```json
{
  "deltaK": 2.5,
  "sia": 0.3,
  "toric_policy": "lifetime_atr"
}
```

**Response** (excerpt):
```json
{
  "recommend_toric": true,
  "effective_astig": 3.10,
  "threshold": 1.25,
  "rationale": "Policy: Lifetime_Atr (ATR orientation) | Decision Layer: Toric IOL Recommended | Rationale: ATR: post-bias 3.10≥0.25, residual 0.13≤0.50, gain 2.97≥0.93."
}
```

## Decision Logic

### 1. **Recommend Toric**
```
post_bias_cyl >= threshold_recommend AND
residual_with_toric <= threshold_postop AND
gain >= min_gain
```

### 2. **Borderline Toric**
```
threshold_border_low <= post_bias_cyl < threshold_border_high AND
residual_with_toric <= threshold_postop AND
gain >= (min_gain - 0.25)
```

### 3. **No Toric**
All other cases

### 4. **Pre-Bias Guard**
If recommended but `pre_bias_cyl < prebias_floor`, downgrade to borderline.

## Frontend Integration

### Policy Selector UI

Located in `IOLSuggestion.js`, the policy selector provides:
- Dropdown with all available policies
- Real-time recalculation when policy changes
- Visual feedback with gradient background
- Policy descriptions for user guidance

### User Flow

1. User reviews biometry data
2. User selects toric policy from dropdown
3. System automatically recalculates recommendations
4. Results display policy name, orientation, and detailed rationale

## Testing Results

### Low Astigmatism (0.3D)
- **All policies**: No toric (below all thresholds)
- Total astigmatism: 0.41D

### Moderate Astigmatism (0.8D)
- **Lifetime ATR**: ✅ Recommend (0.92D ≥ 0.25D)
- **Balanced**: ✅ Recommend (0.92D ≥ 0.50D)
- **Conservative**: ✅ Recommend (0.92D ≥ 0.50D)

### High Astigmatism (2.5D)
- **All policies**: ✅ Recommend (well above all thresholds)
- Total astigmatism: 3.10D

## Technical Implementation

### Backend Files
- `app/services/toric_policy.py` - Policy dataclasses and presets
- `app/services/toric_calculator.py` - Policy-based decision function
- `app/models/api.py` - API request/response models with policy parameter
- `app/main.py` - `/suggest/policies` endpoint

### Frontend Files
- `frontend/src/components/IOLSuggestion.js` - Policy selector UI
- `frontend/src/App.css` - Policy selector styling

## Future Enhancements

### Custom Policy Support (Planned)
Allow users to create custom policies with:
- Adjustable thresholds for each orientation
- Custom quality gating parameters
- Personalized gain scaling

**Implementation approach**:
```javascript
// Frontend: When "Custom" selected, show threshold inputs
if (selectedPolicy === 'custom') {
  // Display custom threshold fields
  // Build ToricPolicy object on-the-fly
  // Send as `custom_policy` parameter
}
```

## Clinical Rationale

### Why Different Policies?

1. **Age-Related Changes**: Astigmatism tends to shift from WTR (young) to ATR (older)
   - Young patients with WTR → likely to progress to ATR
   - Use aggressive WTR thresholds to avoid future issues

2. **Measurement Uncertainty**: Higher astigmatism = more certainty
   - Gain scaling: `min_gain = max(base, scale * magnitude)`
   - Larger cylinders require larger absolute reduction

3. **Clinical Philosophy**: Different surgeons have different risk tolerances
   - Some prefer aggressive correction (lifetime_atr)
   - Others prefer conservative approach (conservative)
   - Most use balanced approach

## References

- Koch DD, et al. "Contribution of posterior corneal astigmatism to total corneal astigmatism." J Cataract Refract Surg. 2012
- Norrby S. "Sources of error in intraocular lens power calculation." J Cataract Refract Surg. 2008
- Holladay JT, et al. "Analysis of aggregate surgically induced refractive change, prediction error, and intraocular astigmatism." J Cataract Refract Surg. 2001

## Support

For questions or issues with the policy system, please refer to:
- `ADVANCED_TORIC_SYSTEM.md` - Technical details on toric calculations
- `FORMULA_PROTECTION.md` - Formula integrity safeguards
- `API_DOCUMENTATION.md` - Complete API reference

