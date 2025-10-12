import React, { useState, useEffect } from 'react';

const DataReview = ({ fileId, extractedData, onReviewSuccess }) => {
  const [editedData, setEditedData] = useState({});
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [validationFlags, setValidationFlags] = useState([]);

  useEffect(() => {
    // Initialize edited data with extracted data
    console.log('DataReview received extractedData:', extractedData);
    const initialData = {};
    ['od', 'os'].forEach(eye => {
      if (extractedData[eye]) {
        Object.keys(extractedData[eye]).forEach(field => {
          if (extractedData[eye][field] && extractedData[eye][field] !== '') {
            initialData[`${eye}.${field}`] = extractedData[eye][field];
          }
        });
      }
    });
    console.log('DataReview initialData:', initialData);
    setEditedData(initialData);
  }, [extractedData]);

  const handleFieldChange = (eye, field, value) => {
    let key;
    if (eye === 'patient' && field === 'gender') {
      key = 'gender';
    } else if (eye === 'assumed_sia') {
      key = `${eye}_${field}`;
    } else {
      key = `${eye}.${field}`;
    }
    setEditedData(prev => ({
      ...prev,
      [key]: value
    }));
  };

  const handleSubmit = async () => {
    setIsSubmitting(true);
    setSubmitError(null);

    try {
      const response = await fetch('http://localhost:8000/review', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          file_id: fileId,
          edits: editedData
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Review submission failed');
      }

      const result = await response.json();
      setValidationFlags(result.flags || []);
      
      // Merge edited data with original data
      const reviewedData = { ...extractedData };
      Object.keys(editedData).forEach(key => {
        const [eye, field] = key.split('.');
        if (reviewedData[eye] && editedData[key]) {
          reviewedData[eye][field] = editedData[key];
        }
      });

      onReviewSuccess(reviewedData);
    } catch (error) {
      setSubmitError(error.message || 'Failed to submit review. Please try again.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const renderEyeSection = (eye, eyeLabel) => (
    <div className="eye-section">
      <h3>{eyeLabel}</h3>
      <div className="measurements-grid">
        <div className="measurement">
          <label>Axial Length (mm)</label>
          <input
            type="text"
            value={editedData[`${eye}.axial_length`] || ''}
            onChange={(e) => handleFieldChange(eye, 'axial_length', e.target.value)}
            placeholder="Enter axial length"
          />
        </div>
        <div className="measurement">
          <label>ACD (mm)</label>
          <input
            type="text"
            value={editedData[`${eye}.acd`] || ''}
            onChange={(e) => handleFieldChange(eye, 'acd', e.target.value)}
            placeholder="Enter ACD"
          />
        </div>
        <div className="measurement">
          <label>Lens Thickness (mm)</label>
          <input
            type="text"
            value={editedData[`${eye}.lt`] || ''}
            onChange={(e) => handleFieldChange(eye, 'lt', e.target.value)}
            placeholder="Enter lens thickness"
          />
        </div>
        <div className="measurement">
          <label>CCT (μm)</label>
          <input
            type="text"
            value={editedData[`${eye}.cct`] || ''}
            onChange={(e) => handleFieldChange(eye, 'cct', e.target.value)}
            placeholder="Enter CCT"
          />
        </div>
        <div className="measurement">
          <label>WTW (mm)</label>
          <input
            type="text"
            value={editedData[`${eye}.wtw`] || ''}
            onChange={(e) => handleFieldChange(eye, 'wtw', e.target.value)}
            placeholder="Enter WTW"
          />
        </div>
        <div className="measurement">
          <label>K1 (D)</label>
          <input
            type="text"
            value={editedData[`${eye}.k1`] || ''}
            onChange={(e) => handleFieldChange(eye, 'k1', e.target.value)}
            placeholder="Enter K1"
          />
        </div>
        <div className="measurement">
          <label>K2 (D)</label>
          <input
            type="text"
            value={editedData[`${eye}.k2`] || ''}
            onChange={(e) => handleFieldChange(eye, 'k2', e.target.value)}
            placeholder="Enter K2"
          />
        </div>
        <div className="measurement">
          <label>K1 Axis (°)</label>
          <input
            type="text"
            value={editedData[`${eye}.k1_axis`] || ''}
            onChange={(e) => handleFieldChange(eye, 'k1_axis', e.target.value)}
            placeholder="Enter K1 axis"
          />
        </div>
        <div className="measurement">
          <label>K2 Axis (°)</label>
          <input
            type="text"
            value={editedData[`${eye}.k2_axis`] || ''}
            onChange={(e) => handleFieldChange(eye, 'k2_axis', e.target.value)}
            placeholder="Enter K2 axis"
          />
        </div>
      </div>
    </div>
  );

  return (
    <div className="review-container">
      <div className="review-header">
        <h2>Review and Edit IOL Data</h2>
        <p>Please review the extracted measurements and make any necessary corrections</p>
      </div>

      <div className="review-content">
        <div className="eye-data">
          {renderEyeSection('od', 'Right Eye (OD)')}
          {renderEyeSection('os', 'Left Eye (OS)')}
        </div>

        {/* Patient Demographics Section */}
        <div className="demographics-section">
          <h3>Patient Demographics</h3>
          <p>Required for advanced IOL calculations (Hill-RBF 3.0, Kane)</p>
          <div className="demographics-inputs">
            <div className="demographics-input">
              <label>Gender {extractedData.gender && <span className="extracted-badge">Auto-extracted</span>}</label>
              <select
                value={editedData['gender'] || extractedData.gender || ''}
                onChange={(e) => handleFieldChange('patient', 'gender', e.target.value)}
                className="gender-select"
              >
                <option value="">Select Gender</option>
                <option value="M">Male</option>
                <option value="F">Female</option>
              </select>
            </div>
          </div>
        </div>

        {/* Assumed SIA Section */}
        <div className="assumed-sia-section">
          <h3>Assumed SIA (Surgeon-Induced Astigmatism)</h3>
          <p>Enter your personal SIA values for advanced toric calculations</p>
          <div className="sia-inputs">
            {/* OD (Right Eye) SIA */}
            <div className="sia-input">
              <label>OD (Right Eye)</label>
              <div className="sia-magnitude-axis">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={editedData['assumed_sia_od_magnitude'] || 0.1}
                  onChange={(e) => handleFieldChange('assumed_sia_od_magnitude', 'value', e.target.value)}
                  placeholder="0.1"
                  title="SIA Magnitude (diopters)"
                />
                <span className="sia-label">D @</span>
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="180"
                  value={editedData['assumed_sia_od_axis'] || 120}
                  onChange={(e) => handleFieldChange('assumed_sia_od_axis', 'value', e.target.value)}
                  placeholder="120"
                  title="SIA Axis (degrees)"
                />
                <span className="sia-label">°</span>
              </div>
            </div>
            
            {/* OS (Left Eye) SIA */}
            <div className="sia-input">
              <label>OS (Left Eye)</label>
              <div className="sia-magnitude-axis">
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  max="2"
                  value={editedData['assumed_sia_os_magnitude'] || 0.2}
                  onChange={(e) => handleFieldChange('assumed_sia_os_magnitude', 'value', e.target.value)}
                  placeholder="0.2"
                  title="SIA Magnitude (diopters)"
                />
                <span className="sia-label">D @</span>
                <input
                  type="number"
                  step="1"
                  min="0"
                  max="180"
                  value={editedData['assumed_sia_os_axis'] || 120}
                  onChange={(e) => handleFieldChange('assumed_sia_os_axis', 'value', e.target.value)}
                  placeholder="120"
                  title="SIA Axis (degrees)"
                />
                <span className="sia-label">°</span>
              </div>
            </div>
          </div>
        </div>

        {validationFlags.length > 0 && (
          <div className="validation-warnings">
            <h4>Validation Warnings</h4>
            <ul>
              {validationFlags.map((flag, index) => (
                <li key={index} className="warning">
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path>
                    <line x1="12" y1="9" x2="12" y2="13"></line>
                    <line x1="12" y1="17" x2="12.01" y2="17"></line>
                  </svg>
                  {flag}
                </li>
              ))}
            </ul>
          </div>
        )}

        {submitError && (
          <div className="error-message">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <circle cx="12" cy="12" r="10"></circle>
              <line x1="15" y1="9" x2="9" y2="15"></line>
              <line x1="9" y1="9" x2="15" y2="15"></line>
            </svg>
            {submitError}
          </div>
        )}

        <div className="review-actions">
          <button 
            className="submit-button" 
            onClick={handleSubmit}
            disabled={isSubmitting}
          >
            {isSubmitting ? (
              <>
                <div className="spinner small"></div>
                Submitting...
              </>
            ) : (
              'Continue to IOL Selection'
            )}
          </button>
        </div>
      </div>
    </div>
  );
};

export default DataReview;
