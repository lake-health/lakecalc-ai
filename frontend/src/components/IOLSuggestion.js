import React, { useState, useEffect } from 'react';
import IOLFamilyPopup from './IOLFamilyPopup';

const IOLSuggestion = ({ reviewedData, onSuggestionComplete, onSuggestionSuccess }) => {
  const [suggestions, setSuggestions] = useState(null);
  const [families, setFamilies] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);
  const [showFamilyPopup, setShowFamilyPopup] = useState(false);
  const [selectedEye, setSelectedEye] = useState(null);
  const [selectedFamilies, setSelectedFamilies] = useState({});
  
  // Policy selection state
  const [policies, setPolicies] = useState({});
  const [selectedPolicy, setSelectedPolicy] = useState('lifetime_atr');
  const [showCustomPolicy, setShowCustomPolicy] = useState(false);

  useEffect(() => {
    loadFamilies();
    loadPolicies();
    if (reviewedData) {
      calculateSuggestions();
    }
  }, [reviewedData]); // eslint-disable-line react-hooks/exhaustive-deps

  // Recalculate suggestions when policy changes
  useEffect(() => {
    if (reviewedData && Object.keys(policies).length > 0) {
      calculateSuggestions();
    }
  }, [selectedPolicy]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadFamilies = async () => {
    try {
      const response = await fetch('http://localhost:8000/suggest/families');
      if (response.ok) {
        const data = await response.json();
        setFamilies(data.families || []);
      }
    } catch (error) {
      console.error('Failed to load IOL families:', error);
      setFamilies([]);
    }
  };

  const loadPolicies = async () => {
    try {
      const response = await fetch('http://localhost:8000/suggest/policies');
      if (response.ok) {
        const data = await response.json();
        setPolicies(data.policies || {});
      }
    } catch (error) {
      console.error('Failed to load toric policies:', error);
      setPolicies({});
    }
  };

  const calculateSuggestions = async () => {
    if (!reviewedData) return;

    console.log('🔄 Recalculating suggestions with policy:', selectedPolicy);
    setIsLoading(true);
    setError(null);

    try {
      // Calculate deltaK for both eyes
      const odDeltaK = calculateDeltaK(reviewedData.od);
      const osDeltaK = calculateDeltaK(reviewedData.os);

      // Get suggestions for both eyes with correct SIA values
      const [odSuggestion, osSuggestion] = await Promise.all([
        getSuggestion({
          ...reviewedData.od, 
          eye: "OD",
          assumed_sia_magnitude: reviewedData.od.assumed_sia_od_magnitude,
          assumed_sia_axis: reviewedData.od.assumed_sia_od_axis
        }),
        getSuggestion({
          ...reviewedData.os, 
          eye: "OS",
          assumed_sia_magnitude: reviewedData.os.assumed_sia_os_magnitude,
          assumed_sia_axis: reviewedData.os.assumed_sia_os_axis
        })
      ]);

      console.log('✅ Suggestions updated for policy:', selectedPolicy);
      setSuggestions({
        od: { deltaK: odDeltaK, ...odSuggestion },
        os: { deltaK: osDeltaK, ...osSuggestion }
      });
    } catch (error) {
      console.error('❌ Error calculating suggestions:', error);
      setError('Failed to calculate IOL suggestions. Please try again.');
    } finally {
      setIsLoading(false);
    }
  };

  const calculateDeltaK = (eyeData) => {
    const k1 = parseFloat(eyeData.k1) || 0;
    const k2 = parseFloat(eyeData.k2) || 0;
    return Math.abs(k1 - k2);
  };

  const getSuggestion = async (eyeData) => {
    try {
      // Calculate deltaK from the eye data
      const k1 = parseFloat(eyeData.k1) || 0;
      const k2 = parseFloat(eyeData.k2) || 0;
      const deltaK = Math.abs(k2 - k1);
      
      const response = await fetch('http://localhost:8000/suggest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          deltaK: deltaK,
          sia: parseFloat(eyeData.assumed_sia_magnitude || (eyeData.eye === "OD" ? 0.1 : 0.2)), // Use eye-specific defaults
          sia_magnitude: parseFloat(eyeData.assumed_sia_magnitude || (eyeData.eye === "OD" ? 0.1 : 0.2)),
          sia_axis: parseFloat(eyeData.assumed_sia_axis || 120),
          toric_policy: selectedPolicy
        }),
      });

      if (!response.ok) {
        throw new Error('Suggestion request failed');
      }

      return await response.json();
    } catch (error) {
      throw new Error('Failed to get suggestion');
    }
  };

  const renderEyeSuggestion = (eye, eyeLabel, suggestion) => (
    <div className="eye-suggestion">
      <h3>{eyeLabel}</h3>
      <div className="suggestion-content">
        <div className="measurement-summary">
          <div className="measurement-item">
            <label>Delta K</label>
            <span className="value">{suggestion.deltaK.toFixed(2)} D</span>
          </div>
          <div className="measurement-item">
            <label>Total Preop Astigmatism</label>
            <span className="value">{suggestion.effective_astig ? suggestion.effective_astig.toFixed(2) : 'N/A'} D</span>
          </div>
          <div className="measurement-item">
            <label>Policy Applied</label>
            <span className="value">{selectedPolicy.split('_').map(word => {
              // Special handling for medical acronyms
              if (word.toLowerCase() === 'atr') return 'ATR';
              if (word.toLowerCase() === 'wtr') return 'WTR';
              if (word.toLowerCase() === 'obl') return 'OBL';
              return word.charAt(0).toUpperCase() + word.slice(1);
            }).join(' ')}</span>
          </div>
        </div>

        <div className={`recommendation ${suggestion.recommend_toric ? 'toric' : 'non-toric'}`}>
          <div className="recommendation-header">
            <div className="recommendation-icon">
              {suggestion.recommend_toric ? (
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M9 12l2 2 4-4"></path>
                  <circle cx="12" cy="12" r="10"></circle>
                </svg>
              ) : (
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <circle cx="12" cy="12" r="10"></circle>
                  <line x1="15" y1="9" x2="9" y2="15"></line>
                  <line x1="9" y1="9" x2="15" y2="15"></line>
                </svg>
              )}
            </div>
            <h4>
              {suggestion.recommend_toric ? 'Toric IOL Recommended' : 'Non-Toric IOL Acceptable'}
            </h4>
          </div>
          <p className="rationale">{suggestion.rationale}</p>
        </div>

        {/* Debug info */}
        <div style={{fontSize: '12px', color: '#666', marginTop: '10px'}}>
          Debug: recommend_toric={suggestion.recommend_toric ? 'true' : 'false'}, families.length={families ? families.length : 'undefined'}
        </div>
        
          {(suggestion.recommend_toric || (families && families.length > 0)) && (
            <div className="iol-families">
              <h5>{suggestion.recommend_toric ? 'Available Toric IOL Families' : 'Available IOL Families'}</h5>
              <button 
                className="select-family-button"
                onClick={() => {
                  setSelectedEye(eye);
                  setShowFamilyPopup(true);
                }}
                disabled={!families || !Array.isArray(families)}
              >
                {families && Array.isArray(families) ? 'Select IOL Family' : 'Loading Families...'}
              </button>
              
              {/* Selected Family Display */}
              {selectedFamilies[eye] && (
                <div className="selected-family">
                  <h6>Selected IOL Family:</h6>
                  <div className="selected-family-card">
                    <div className="family-brand">{selectedFamilies[eye].brand}</div>
                    <div className="family-name">{selectedFamilies[eye].family}</div>
                    <div className="family-details">
                      <span>A-constant: {selectedFamilies[eye].a_constant}</span>
                      <span>{selectedFamilies[eye].model_count} models</span>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
      </div>
    </div>
  );

  if (isLoading) {
    return (
      <div className="suggestion-container">
        <div className="suggestion-header">
          <h2>Calculating IOL Suggestions</h2>
          <p>Analyzing your measurements to provide IOL recommendations...</p>
        </div>
        <div className="loading-status">
          <div className="spinner"></div>
          <p>This may take a few moments</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="suggestion-container">
        <div className="error-message">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y1="9" x2="9" y2="15"></line>
            <line x1="9" y1="9" x2="15" y2="15"></line>
          </svg>
          {error}
        </div>
        <button className="retry-button" onClick={calculateSuggestions}>
          Try Again
        </button>
      </div>
    );
  }

  if (!suggestions) {
    return null;
  }

  return (
    <div className="suggestion-container">
      <div className="suggestion-header">
        <h2>IOL Recommendations</h2>
        <p>Based on your measurements, here are our IOL suggestions</p>
        <div className="database-note">
          <small>📊 Database updated October 7, 2025 - 617 IOL models across 268 families</small>
        </div>
      </div>

      {/* Policy Selection Section */}
      <div className="policy-selector-section">
        <h3>Toric Decision Policy</h3>
        <p className="policy-description">
          Select your clinical approach to astigmatism management. Different policies account for age-related ATR progression.
        </p>
        <div className="policy-selector">
          <label htmlFor="policy-select">Policy:</label>
          <select 
            id="policy-select"
            value={selectedPolicy} 
            onChange={(e) => {
              console.log('🎯 Policy changed to:', e.target.value);
              setSelectedPolicy(e.target.value);
            }}
            className="policy-dropdown"
          >
            {Object.entries(policies).map(([key, description]) => (
              <option key={key} value={key}>
                {key.split('_').map(word => {
                  // Special handling for medical acronyms
                  if (word.toLowerCase() === 'atr') return 'ATR';
                  if (word.toLowerCase() === 'wtr') return 'WTR';
                  if (word.toLowerCase() === 'obl') return 'OBL';
                  return word.charAt(0).toUpperCase() + word.slice(1);
                }).join(' ')} - {description}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="suggestions-content">
        <div className="eye-suggestions">
          {renderEyeSuggestion('od', 'Right Eye (OD)', suggestions.od)}
          {renderEyeSuggestion('os', 'Left Eye (OS)', suggestions.os)}
        </div>

        <div className="summary-section">
          <h3>Summary</h3>
          <div className="summary-content">
            <div className="summary-item">
              <span className="label">Right Eye:</span>
              <span className={`recommendation ${suggestions.od.recommend_toric ? 'toric' : 'non-toric'}`}>
                {suggestions.od.recommend_toric ? 'Toric Recommended' : 'Non-Toric OK'}
              </span>
            </div>
            <div className="summary-item">
              <span className="label">Left Eye:</span>
              <span className={`recommendation ${suggestions.os.recommend_toric ? 'toric' : 'non-toric'}`}>
                {suggestions.os.recommend_toric ? 'Toric Recommended' : 'Non-Toric OK'}
              </span>
            </div>
          </div>
        </div>

        <div className="suggestion-actions">
          {onSuggestionComplete && (
            <button 
              className="proceed-button" 
              onClick={() => {
                if (onSuggestionSuccess) {
                  onSuggestionSuccess(selectedFamilies);
                } else {
                  onSuggestionComplete();
                }
              }}
              disabled={Object.keys(selectedFamilies).length === 0}
            >
              {Object.keys(selectedFamilies).length === 0 
                ? 'Select IOL Families First' 
                : 'Proceed to IOL Power Calculation'}
            </button>
          )}
          <button className="new-analysis-button" onClick={() => window.location.reload()}>
            Start New Analysis
          </button>
        </div>
      </div>

      {showFamilyPopup && families && Array.isArray(families) && (
        <IOLFamilyPopup
          families={families}
          selectedEye={selectedEye}
          onClose={() => setShowFamilyPopup(false)}
          onSelect={(family) => {
            console.log('Selected family:', family);
            setSelectedFamilies(prev => ({
              ...prev,
              [selectedEye]: family
            }));
            setShowFamilyPopup(false);
          }}
        />
      )}
    </div>
  );
};

export default IOLSuggestion;
