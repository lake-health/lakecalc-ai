import React, { useState } from 'react';
import './App.css';
import FileUpload from './components/FileUpload';
import DataExtraction from './components/DataExtraction';
import DataReview from './components/DataReview';
import IOLSuggestion from './components/IOLSuggestion';
import IOLCalculation from './components/IOLCalculation';

function App() {
  const [currentStep, setCurrentStep] = useState('upload');
  const [fileId, setFileId] = useState(null);
  const [extractedData, setExtractedData] = useState(null);
  const [reviewedData, setReviewedData] = useState(null);
  const [selectedFamilies, setSelectedFamilies] = useState({});

  const handleUploadSuccess = (uploadResponse) => {
    setFileId(uploadResponse.file_id);
    setCurrentStep('extract');
  };

  const handleExtractionSuccess = (data) => {
    setExtractedData(data);
    setCurrentStep('review');
  };

  const handleReviewSuccess = (data) => {
    setReviewedData(data);
    setCurrentStep('suggest');
  };

  const handleSuggestionSuccess = (families) => {
    setSelectedFamilies(families);
    setCurrentStep('calculate');
  };

  const handleSuggestionComplete = () => {
    setCurrentStep('calculate');
  };

  const resetFlow = () => {
    setCurrentStep('upload');
    setFileId(null);
    setExtractedData(null);
    setReviewedData(null);
  };

  return (
    <div className="App">
      <header className="app-header">
        <div className="header-content">
          <div className="logo-section">
                    <img src="/logo.svg?v=1" alt="LakeCalc.ai" className="header-logo" />
            <div className="header-text">
              <h1>LakeCalc.ai</h1>
              <p>Intraocular Lens AI Agent</p>
            </div>
          </div>
        </div>
        {currentStep !== 'upload' && (
          <button className="reset-button" onClick={resetFlow}>
            Start Over
          </button>
        )}
      </header>

      <main className="app-main">
        <div className="step-indicator">
          <div className={`step ${currentStep === 'upload' ? 'active' : ['extract', 'review', 'suggest', 'calculate'].includes(currentStep) ? 'completed' : ''}`}>
            <span className="step-number">1</span>
            <span className="step-label">Upload</span>
          </div>
          <div className={`step ${currentStep === 'extract' ? 'active' : ['review', 'suggest', 'calculate'].includes(currentStep) ? 'completed' : ''}`}>
            <span className="step-number">2</span>
            <span className="step-label">Extract</span>
          </div>
          <div className={`step ${currentStep === 'review' ? 'active' : ['suggest', 'calculate'].includes(currentStep) ? 'completed' : ''}`}>
            <span className="step-number">3</span>
            <span className="step-label">Review</span>
          </div>
          <div className={`step ${currentStep === 'suggest' ? 'active' : currentStep === 'calculate' ? 'completed' : ''}`}>
            <span className="step-number">4</span>
            <span className="step-label">Suggest</span>
          </div>
          <div className={`step ${currentStep === 'calculate' ? 'active' : ''}`}>
            <span className="step-number">5</span>
            <span className="step-label">Calculate</span>
          </div>
        </div>

        <div className="content-area">
          {currentStep === 'upload' && (
            <FileUpload onUploadSuccess={handleUploadSuccess} />
          )}
          
          {currentStep === 'extract' && fileId && (
            <DataExtraction 
              fileId={fileId} 
              onExtractionSuccess={handleExtractionSuccess}
            />
          )}
          
          {currentStep === 'review' && extractedData && (
            <DataReview 
              fileId={fileId}
              extractedData={extractedData}
              onReviewSuccess={handleReviewSuccess}
            />
          )}
          
          {currentStep === 'suggest' && reviewedData && (
            <IOLSuggestion 
              reviewedData={reviewedData}
              onSuggestionComplete={handleSuggestionComplete}
              onSuggestionSuccess={handleSuggestionSuccess}
            />
          )}
          
          {currentStep === 'calculate' && reviewedData && (
            <IOLCalculation 
              reviewedData={reviewedData}
              selectedFamilies={selectedFamilies}
            />
          )}
        </div>
      </main>
      
      {/* Discreet corner logo */}
      <div className="corner-logo">
        <img src="/logo-small.svg?v=1" alt="Lakecalc AI" />
      </div>
    </div>
  );
}

export default App;
