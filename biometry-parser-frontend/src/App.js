import React, { useState } from 'react';
import './App.css';

function App() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleFileChange = (e) => {
    setFile(e.target.files[0]);
    setResult(null);
    setError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return;

    setLoading(true);
    setError(null);
    setResult(null);

    const formData = new FormData();
    formData.append('file', file);

    try {
      const response = await fetch('http://localhost:8003/parse', {
        method: 'POST',
        body: formData,
      });

      const data = await response.json();
      
      if (data.response) {
        // Handle the new universal hybrid API response format
        const parsedData = JSON.parse(data.response);
        setResult({ data: parsedData });
      } else if (data.success) {
        setResult(data);
      } else {
        setError(data.error || 'Parsing failed');
      }
    } catch (err) {
      setError(`Network error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const formatResult = (data) => {
    if (!data.data) return 'No data extracted';
    
    const { patient_name, age, od, os } = data.data;
    
    return (
      <div className="result-container">
        <h3>Extracted Biometry Data</h3>
        <div className="patient-info">
          <p><strong>Patient:</strong> {patient_name || 'N/A'}</p>
          <p><strong>Age:</strong> {age || 'N/A'}</p>
        </div>
        
        <div className="eye-data">
          <div className="eye-section">
            <h4>OD (Right Eye)</h4>
            <div className="data-grid">
              <div><strong>Axial Length:</strong> {od?.axial_length || 'N/A'}</div>
              <div><strong>K1:</strong> {od?.k1 || 'N/A'}</div>
              <div><strong>K2:</strong> {od?.k2 || 'N/A'}</div>
              <div><strong>K1 Axis:</strong> {od?.k_axis_1 || 'N/A'}°</div>
              <div><strong>K2 Axis:</strong> {od?.k_axis_2 || 'N/A'}</div>
              <div><strong>ACD:</strong> {od?.acd || 'N/A'}</div>
              <div><strong>LT:</strong> {od?.lt || 'N/A'}</div>
              <div><strong>WTW:</strong> {od?.wtw || 'N/A'}</div>
              <div><strong>CCT:</strong> {od?.cct || 'N/A'}</div>
            </div>
          </div>
          
          <div className="eye-section">
            <h4>OS (Left Eye)</h4>
            <div className="data-grid">
              <div><strong>Axial Length:</strong> {os?.axial_length || 'N/A'}</div>
              <div><strong>K1:</strong> {os?.k1 || 'N/A'}</div>
              <div><strong>K2:</strong> {os?.k2 || 'N/A'}</div>
              <div><strong>K1 Axis:</strong> {os?.k_axis_1 || 'N/A'}°</div>
              <div><strong>K2 Axis:</strong> {os?.k_axis_2 || 'N/A'}</div>
              <div><strong>ACD:</strong> {os?.acd || 'N/A'}</div>
              <div><strong>LT:</strong> {os?.lt || 'N/A'}</div>
              <div><strong>WTW:</strong> {os?.wtw || 'N/A'}</div>
              <div><strong>CCT:</strong> {os?.cct || 'N/A'}</div>
            </div>
          </div>
        </div>
        
        <div className="metadata">
          <p><strong>Method:</strong> Universal Hybrid (OCR + LLaVA)</p>
          <p><strong>Status:</strong> ✅ Successfully parsed</p>
        </div>
      </div>
    );
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>🧠 Universal Biometry Parser</h1>
        <p>Upload any biometry report (PDF, image, or text) for universal parsing</p>
      </header>

      <main className="App-main">
        <form onSubmit={handleSubmit} className="upload-form">
          <div className="file-input-container">
            <input
              type="file"
              id="file"
              onChange={handleFileChange}
              accept=".pdf,.png,.jpg,.jpeg,.txt"
              className="file-input"
            />
            <label htmlFor="file" className="file-label">
              {file ? file.name : 'Choose Biometry File'}
            </label>
          </div>
          
          <button 
            type="submit" 
            disabled={!file || loading}
            className="submit-button"
          >
            {loading ? 'Processing...' : 'Parse Biometry'}
          </button>
        </form>

        {error && (
          <div className="error-message">
            <h3>❌ Error</h3>
            <p>{error}</p>
          </div>
        )}

        {result && (
          <div className="success-message">
            <h3>✅ Success</h3>
            {formatResult(result)}
          </div>
        )}
      </main>
    </div>
  );
}

export default App;






