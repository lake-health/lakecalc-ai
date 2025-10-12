# 🛡️ FORMULA PROTECTION POLICY

## ⚠️ CRITICAL: DO NOT MODIFY THESE FORMULAS

This document establishes **MANDATORY PROTECTION** for the three validated IOL power calculation formulas.

### 🚫 PROTECTED FORMULAS

#### 1. SRK/T (Retzlaff-Sanders-Kraff Theoretical)
- **Status**: ✅ VALIDATED & LOCKED
- **File**: `app/services/calculations.py` - `_calculate_srkt()`
- **Expected Range**: 21.4-21.6 D for emmetropia
- **Protection Level**: MAXIMUM

#### 2. Haigis (Three-Constant Formula)
- **Status**: ✅ VALIDATED & LOCKED  
- **File**: `app/services/calculations.py` - `_calculate_haigis()`
- **Expected Range**: 21.65 D (within ±0.02 D of theoretical 21.68 D)
- **Protection Level**: MAXIMUM

#### 3. Cooke K6 (API-Based)
- **Status**: ✅ VALIDATED & LOCKED
- **File**: `app/services/calculations.py` - `_calculate_cooke_k6_api()`
- **Expected Range**: 21.5-22.5 D for emmetropia
- **Protection Level**: MAXIMUM

### 🚫 PROTECTED CONSTANTS

#### IOL-Specific Constants Database
- **File**: `iol_constants_parsed.json`
- **Source**: `IOLexport.xml` (IOLcon database)
- **Protection Level**: MAXIMUM
- **Rule**: Constants are AUTHORITATIVE and MUST NOT be modified

### 🔒 PROTECTION MECHANISMS

#### 1. Code Safeguards
- **SRK/T Validation**: Runtime check prevents regression to simplified formula
- **Formula Signatures**: Each formula has unique debug markers
- **Unit Tests**: Comprehensive tests prevent accidental changes

#### 2. Documentation Safeguards
- **This File**: Mandatory protection policy
- **Code Comments**: Extensive warnings in formula implementations
- **API Documentation**: Clear usage guidelines

#### 3. Development Safeguards
- **Code Reviews**: Any formula changes require explicit approval
- **Testing Requirements**: All changes must pass validation tests
- **Version Control**: Formula changes tracked with detailed commit messages

### 📋 MODIFICATION PROTOCOL

#### Before ANY Formula Changes:
1. **Document the reason** for modification
2. **Run comprehensive tests** to validate current behavior
3. **Create backup** of current implementation
4. **Get explicit approval** from project lead
5. **Update this protection document**

#### After ANY Formula Changes:
1. **Validate against known test cases**
2. **Update unit tests** if needed
3. **Update documentation**
4. **Commit with detailed message**
5. **Notify team of changes**

### 🧪 VALIDATION TEST CASES

#### SRK/T Test Case
```
AL = 23.77 mm, K = 42.62 D, A-constant = 118.90, Target = 0.00 D
Expected Result: 21.82 D (±0.5 D tolerance)
```

#### Haigis Test Case
```
AL = 23.77 mm, K = 42.62 D, ACD = 2.83 mm, a0 = -0.769, a1 = 0.234, a2 = 0.217
Expected Result: 21.65 D (±0.02 D tolerance)
```

#### Cooke K6 Test Case
```
AL = 23.77 mm, K1 = 41.45 D, K2 = 43.8 D, ACD = 2.83 mm, LT = 4.95 mm
Expected Result: 21.5 D (±0.5 D tolerance)
```

### ⚠️ WARNING SIGNS

#### If you see these errors, STOP and investigate:
- `🚨 CRITICAL ERROR: SRK/T result matches simplified SRK regression`
- `Error in SRK/T calculation`
- `Error in Haigis calculation`
- `Error in Cooke K6 calculation`

#### If formulas produce unexpected results:
1. **Check IOL constants** haven't been modified
2. **Verify formula implementations** match this document
3. **Run validation test cases**
4. **Check for accidental regressions**

### 📞 ESCALATION

#### For Formula Issues:
- **Primary**: Review this document and code comments
- **Secondary**: Run unit tests to identify discrepancies
- **Tertiary**: Contact project lead for formula modifications

#### For Constants Issues:
- **Primary**: Verify `IOLexport.xml` source hasn't changed
- **Secondary**: Re-run `parse_iol_constants.py` script
- **Tertiary**: Contact project lead for constants updates

---

## 🎯 MVP STATUS

**Current Status**: ✅ ALL THREE FORMULAS VALIDATED & LOCKED
**Next Phase**: Toric IOL enhancements
**Protection Level**: MAXIMUM

**Last Updated**: 2025-10-09
**Validated By**: Project Lead
**Next Review**: Before any formula modifications
