import React, { useState, useEffect } from 'react';

const IOLSuggestion = ({ reviewedData }) => {
  const [suggestions, setSuggestions] = useState(null);
  const [families, setFamilies] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadFamilies();
    calculateSuggestions();
  }, [reviewedData]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadFamilies = async () => {
    try {
      const response = await fetch('http://localhost:8000/suggest/families');
      if (response.ok) {
        const data = await response.json();
        setFamilies(data);
      }
    } catch (error) {
      console.error('Failed to load IOL families:', error);
    }
  };

  const calculateSuggestions = async () => {
    if (!reviewedData) return;

    setIsLoading(true);
    setError(null);

    try {
      // Calculate deltaK for both eyes
      const odDeltaK = calculateDeltaK(reviewedData.od);
      const osDeltaK = calculateDeltaK(reviewedData.os);

      // Get suggestions for both eyes
      const [odSuggestion, osSuggestion] = await Promise.all([
        getSuggestion(odDeltaK),
        getSuggestion(osDeltaK)
      ]);

      setSuggestions({
        od: { deltaK: odDeltaK, ...odSuggestion },
        os: { deltaK: osDeltaK, ...osSuggestion }
      });
    } catch (error) {
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

  const getSuggestion = async (deltaK) => {
    try {
      const response = await fetch('http://localhost:8000/suggest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          deltaK: deltaK,
          sia: null // Using default SIA value
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
            <label>Effective Astigmatism</label>
            <span className="value">{suggestion.effective_astig.toFixed(2)} D</span>
          </div>
          <div className="measurement-item">
            <label>Threshold</label>
            <span className="value">{suggestion.threshold.toFixed(2)} D</span>
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

        {suggestion.recommend_toric && families.length > 0 && (
          <div className="iol-families">
            <h5>Available Toric IOL Families</h5>
            <div className="families-grid">
              {families.map((family, index) => (
                <div key={index} className="family-card">
                  <h6>{family.name || `Family ${index + 1}`}</h6>
                  {family.description && <p>{family.description}</p>}
                  {family.powers && (
                    <div className="powers">
                      <span>Available powers: {family.powers.join(', ')}</span>
                    </div>
                  )}
                </div>
              ))}
            </div>
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
          <button className="new-analysis-button" onClick={() => window.location.reload()}>
            Start New Analysis
          </button>
        </div>
      </div>
    </div>
  );
};

export default IOLSuggestion;
