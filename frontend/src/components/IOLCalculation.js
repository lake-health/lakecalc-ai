import React, { useState, useEffect } from 'react';

const IOLCalculation = ({ reviewedData, selectedFamilies }) => {
  const [calculations, setCalculations] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [targetRefraction, setTargetRefraction] = useState(0.0);

  useEffect(() => {
    if (reviewedData) {
      calculateIOLPower();
    }
  }, [reviewedData, targetRefraction]); // eslint-disable-line react-hooks/exhaustive-deps

  const parseEuropeanFloat = (value) => {
    if (!value) return null;
    // Convert comma to dot and remove units
    const cleanValue = String(value).replace(',', '.').replace(/[^\d.-]/g, '');
    const parsed = parseFloat(cleanValue);
    return isNaN(parsed) ? null : parsed;
  };

  // Helper function to create extracted data for an eye
  const createExtractedData = (eyeData, eye) => ({
    device: reviewedData.device || "Unknown",
    eye: eye,
    al_mm: parseEuropeanFloat(eyeData.axial_length),
    acd_mm: parseEuropeanFloat(eyeData.acd),
    lt_mm: parseEuropeanFloat(eyeData.lt),
    cct_um: parseEuropeanFloat(eyeData.cct) ? Math.round(parseEuropeanFloat(eyeData.cct) * 1000) : null, // Convert mm to um
    wtw_mm: parseEuropeanFloat(eyeData.wtw),
    gender: reviewedData.gender || "M", // Use patient gender (auto-extracted or manually set)
    notes: reviewedData.notes || null,
    confidence: {},
    // New SIA fields (magnitude and axis)
    assumed_sia_od_magnitude: reviewedData.assumed_sia_od_magnitude || null,
    assumed_sia_od_axis: reviewedData.assumed_sia_od_axis || null,
    assumed_sia_os_magnitude: reviewedData.assumed_sia_os_magnitude || null,
    assumed_sia_os_axis: reviewedData.assumed_sia_os_axis || null,
    // Legacy SIA fields for backward compatibility
    assumed_sia_od: reviewedData.od.assumed_sia || null,
    assumed_sia_os: reviewedData.os.assumed_sia || null,
    ks: {
      k1_power: parseEuropeanFloat(eyeData.k1),
      k2_power: parseEuropeanFloat(eyeData.k2),
      k1_axis: parseEuropeanFloat(eyeData.k1_axis),
      k2_axis: parseEuropeanFloat(eyeData.k2_axis)
    }
  });

  const calculateIOLPower = async () => {
    if (!reviewedData) return;

    setIsLoading(true);
    setError(null);

    try {
      // Debug logging
      console.log('Frontend Debug - reviewedData.od:', reviewedData.od);
      console.log('Frontend Debug - reviewedData.os:', reviewedData.os);
      
      const extractedData = createExtractedData(reviewedData.od, "OD");
      console.log('Frontend Debug - extractedData:', extractedData);

      const [odResponse, osResponse] = await Promise.all([
        // Right Eye (OD) calculation
        fetch('http://localhost:8000/calculate/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            extracted_data: createExtractedData(reviewedData.od, "OD"),
            target_refraction: targetRefraction,
            surgeon_factor: 1.0,
            iol_manufacturer: selectedFamilies.OD?.brand || null,
            iol_model: selectedFamilies.OD?.family || null
          }),
        }),
        // Left Eye (OS) calculation  
        fetch('http://localhost:8000/calculate/', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            extracted_data: createExtractedData(reviewedData.os, "OS"),
            target_refraction: targetRefraction,
            surgeon_factor: 1.0,
            iol_manufacturer: selectedFamilies.OS?.brand || selectedFamilies.OD?.brand || null,
            iol_model: selectedFamilies.OS?.family || selectedFamilies.OD?.family || null
          }),
        })
      ]);

      if (!odResponse.ok || !osResponse.ok) {
        throw new Error('Calculation request failed');
      }

      const odResult = await odResponse.json();
      const osResult = await osResponse.json();
      
      // Combine results for both eyes
      setCalculations({
        od: odResult,
        os: osResult
      });
    } catch (error) {
      setError('Failed to calculate IOL power. Please try again.');
      console.error('Calculation error:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const renderFormulaRow = (calculation, index) => {
    const isRecommended = calculation.formula === calculations.od?.recommended_formula;

    return (
      <div key={calculation.formula} className={`table-row ${isRecommended ? 'recommended' : ''}`}>
        <div className="col-formula">
          <span className="formula-name">{calculation.formula}</span>
        </div>
        <div className="col-power">
          <span className="power-value">{calculation.iol_power}</span>
        </div>
        <div className="col-status">
          {calculation.notes && (
            <span className="status-info" title={calculation.notes}>
              ⓘ
            </span>
          )}
        </div>
      </div>
    );
  };

  const renderEyeResults = (eyeData, eyeName) => {
    if (!eyeData) return null;

    return (
      <div className="eye-section">
        <h3>{eyeName}</h3>
        <div className="iol-diagram-section">
          <div className="iol-diagram">
            <div className="iol-outer-ring">
              <div className="iol-inner-ring">
                <div className="iol-center">
                  <div className="axis-line" style={{ transform: `rotate(${eyeData.toric_calculation?.toric_axis || 0}deg)` }}></div>
                  <div className="axis-label">{eyeData.toric_calculation?.toric_axis || 0}°</div>
                </div>
              </div>
            </div>
          </div>
          <div className="iol-info">
            <p><strong>Recommended IOL:</strong> {eyeData.recommended_formula}</p>
            <p><strong>Power:</strong> {eyeData.calculations?.find(c => c.formula === eyeData.recommended_formula)?.iol_power || eyeData.calculations?.[0]?.iol_power || 'N/A'} D</p>
            <p><strong>Axis:</strong> {eyeData.toric_calculation?.toric_axis || 0}°</p>
          </div>
        </div>
        
        <div className="formulas-comparison">
          <h4>Formula Comparison</h4>
          <div className="formulas-table">
            <div className="table-header">
              <div className="col-formula">Formula</div>
              <div className="col-power">IOL Power (D)</div>
              <div className="col-status">Status</div>
            </div>
            <div className="table-body">
              {eyeData.calculations?.map(renderFormulaRow) || []}
            </div>
          </div>
        </div>
      </div>
    );
  };

  if (isLoading) {
    return (
      <div className="calculation-container">
        <div className="calculation-header">
          <h2>IOL Power Calculations</h2>
          <p>Calculating optimal IOL power using multiple formulas...</p>
        </div>
        <div className="loading-spinner">
          <div className="spinner"></div>
          <p>Processing biometry data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="calculation-container">
        <div className="error-message">
          <div className="error-icon">❌</div>
          <div className="error-text">{error}</div>
          <button className="retry-button" onClick={calculateIOLPower}>
            Try Again
          </button>
        </div>
      </div>
    );
  }

  if (!calculations) {
    return (
      <div className="calculation-container">
        <div className="calculation-header">
          <h2>IOL Power Calculations</h2>
          <p>Ready to calculate IOL power</p>
        </div>
        <button className="calculate-button" onClick={calculateIOLPower}>
          Calculate IOL Power
        </button>
      </div>
    );
  }

  return (
    <div className="calculation-container">
      <div className="calculation-header">
        <h2>IOL Power Calculations</h2>
        <p>Advanced calculations using multiple formulas for optimal accuracy</p>
      </div>

      <div className="calculation-controls">
        <div className="control-group">
          <label htmlFor="target-refraction">Target Refraction (D):</label>
          <div className="target-refraction-controls">
            <button 
              className="increment-btn"
              onClick={() => setTargetRefraction(prev => (prev + 0.25).toFixed(2) * 1)}
              title="Increase by 0.25 D"
            >
              +
            </button>
            <input
              id="target-refraction"
              type="number"
              step="0.25"
              value={targetRefraction}
              onChange={(e) => setTargetRefraction(parseFloat(e.target.value) || 0)}
              className="control-input"
            />
            <button 
              className="decrement-btn"
              onClick={() => setTargetRefraction(prev => (prev - 0.25).toFixed(2) * 1)}
              title="Decrease by 0.25 D"
            >
              −
            </button>
          </div>
        </div>
      </div>

      <div className="calculation-results">
        <div className="eye-results">
          {renderEyeResults(calculations.od, "Right Eye (OD)")}
          {renderEyeResults(calculations.os, "Left Eye (OS)")}
        </div>
      </div>

      {calculations.od?.notes && calculations.od.notes.length > 0 && (
        <div className="clinical-notes">
          <h4>Clinical Notes</h4>
          <ul>
            {calculations.od.notes.map((note, index) => (
              <li key={index}>{note}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export default IOLCalculation;