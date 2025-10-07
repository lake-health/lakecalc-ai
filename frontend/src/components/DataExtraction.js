import React, { useState, useEffect } from 'react';

const DataExtraction = ({ fileId, onExtractionSuccess }) => {
  const [isExtracting, setIsExtracting] = useState(false);
  const [extractedData, setExtractedData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (fileId) {
      extractData();
    }
  }, [fileId]); // eslint-disable-line react-hooks/exhaustive-deps

  const extractData = async () => {
    setIsExtracting(true);
    setError(null);

    try {
      const response = await fetch(`http://localhost:8000/extract/${fileId}`);
      
      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Extraction failed');
      }

      const result = await response.json();
      console.log('DataExtraction received result:', result);
      setExtractedData(result);
      onExtractionSuccess(result);
    } catch (error) {
      setError(error.message || 'Failed to extract data. Please try again.');
    } finally {
      setIsExtracting(false);
    }
  };

  const formatValue = (value) => {
    if (!value || value === '') return 'Not detected';
    return value;
  };

  const getConfidenceColor = (confidence) => {
    if (confidence >= 0.8) return 'high';
    if (confidence >= 0.5) return 'medium';
    return 'low';
  };

  const getConfidenceLabel = (confidence) => {
    if (confidence >= 0.8) return 'High';
    if (confidence >= 0.5) return 'Medium';
    return 'Low';
  };

  if (isExtracting) {
    return (
      <div className="extraction-container">
        <div className="extraction-header">
          <h2>Extracting IOL Data</h2>
          <p>Processing your document and extracting measurements...</p>
        </div>
        <div className="extraction-status">
          <div className="spinner"></div>
          <p>This may take a few moments</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="extraction-container">
        <div className="error-message">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y1="9" x2="9" y2="15"></line>
            <line x1="9" y1="9" x2="15" y2="15"></line>
          </svg>
          {error}
        </div>
        <button className="retry-button" onClick={extractData}>
          Try Again
        </button>
      </div>
    );
  }

  if (!extractedData) {
    return null;
  }

  return (
    <div className="extraction-container">
      <div className="extraction-header">
        <h2>Extracted IOL Data</h2>
        <p>Review the extracted measurements below</p>
        {extractedData.llm_fallback && (
          <div className="llm-fallback-notice">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M9 12l2 2 4-4"></path>
              <circle cx="12" cy="12" r="10"></circle>
            </svg>
            Some values were enhanced using AI analysis
          </div>
        )}
      </div>

      <div className="extraction-results">
        <div className="eye-data">
          <div className="eye-section">
            <h3>Right Eye (OD)</h3>
            <div className="measurements-grid">
              <div className="measurement">
                <label>Axial Length</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['od.axial_length'] || 0)}`}>
                  {formatValue(extractedData.od.axial_length)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['od.axial_length'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>ACD</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['od.acd'] || 0)}`}>
                  {formatValue(extractedData.od.acd)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['od.acd'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>Lens Thickness</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['od.lt'] || 0)}`}>
                  {formatValue(extractedData.od.lt)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['od.lt'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>CCT</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['od.cct'] || 0)}`}>
                  {formatValue(extractedData.od.cct)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['od.cct'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>WTW</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['od.wtw'] || 0)}`}>
                  {formatValue(extractedData.od.wtw)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['od.wtw'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>K1</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['od.k1'] || 0)}`}>
                  {formatValue(extractedData.od.k1)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['od.k1'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>K2</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['od.k2'] || 0)}`}>
                  {formatValue(extractedData.od.k2)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['od.k2'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>K1 Axis</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['od.k1_axis'] || 0)}`}>
                  {formatValue(extractedData.od.k1_axis)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['od.k1_axis'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>K2 Axis</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['od.k2_axis'] || 0)}`}>
                  {formatValue(extractedData.od.k2_axis)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['od.k2_axis'] || 0)}
                </span>
              </div>
            </div>
          </div>

          <div className="eye-section">
            <h3>Left Eye (OS)</h3>
            <div className="measurements-grid">
              <div className="measurement">
                <label>Axial Length</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['os.axial_length'] || 0)}`}>
                  {formatValue(extractedData.os.axial_length)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['os.axial_length'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>ACD</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['os.acd'] || 0)}`}>
                  {formatValue(extractedData.os.acd)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['os.acd'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>Lens Thickness</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['os.lt'] || 0)}`}>
                  {formatValue(extractedData.os.lt)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['os.lt'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>CCT</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['os.cct'] || 0)}`}>
                  {formatValue(extractedData.os.cct)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['os.cct'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>WTW</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['os.wtw'] || 0)}`}>
                  {formatValue(extractedData.os.wtw)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['os.wtw'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>K1</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['os.k1'] || 0)}`}>
                  {formatValue(extractedData.os.k1)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['os.k1'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>K2</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['os.k2'] || 0)}`}>
                  {formatValue(extractedData.os.k2)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['os.k2'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>K1 Axis</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['os.k1_axis'] || 0)}`}>
                  {formatValue(extractedData.os.k1_axis)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['os.k1_axis'] || 0)}
                </span>
              </div>
              <div className="measurement">
                <label>K2 Axis</label>
                <span className={`value confidence-${getConfidenceColor(extractedData.confidence['os.k2_axis'] || 0)}`}>
                  {formatValue(extractedData.os.k2_axis)}
                </span>
                <span className="confidence">
                  {getConfidenceLabel(extractedData.confidence['os.k2_axis'] || 0)}
                </span>
              </div>
            </div>
          </div>
        </div>

        {extractedData.notes && (
          <div className="extraction-notes">
            <h4>Notes</h4>
            <p>{extractedData.notes}</p>
          </div>
        )}

        <div className="extraction-actions">
          <button className="continue-button" onClick={() => onExtractionSuccess(extractedData)}>
            Continue to Review
          </button>
        </div>
      </div>
    </div>
  );
};

export default DataExtraction;
