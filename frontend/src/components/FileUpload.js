import React, { useState } from 'react';

const FileUpload = ({ onUploadSuccess }) => {
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  // const [uploadedFiles, setUploadedFiles] = useState([]); // For future multiple file support

  const validateFile = (file) => {
    const allowedTypes = ['application/pdf', 'image/png', 'image/jpeg', 'image/jpg'];
    if (!allowedTypes.includes(file.type)) {
      return `File "${file.name}" is not a supported format. Please upload PDF, PNG, or JPEG files.`;
    }

    const maxSize = 30 * 1024 * 1024; // 30MB
    if (file.size > maxSize) {
      return `File "${file.name}" is too large. Maximum size is 30MB.`;
    }

    return null;
  };

  const handleFileUpload = async (files) => {
    const fileArray = Array.from(files);
    if (fileArray.length === 0) return;

    // Validate all files first
    const validationErrors = [];
    const validFiles = [];

    fileArray.forEach(file => {
      const error = validateFile(file);
      if (error) {
        validationErrors.push(error);
      } else {
        validFiles.push(file);
      }
    });

    if (validationErrors.length > 0) {
      setUploadError(validationErrors.join(' '));
      return;
    }

    if (validFiles.length === 0) {
      setUploadError('No valid files to upload.');
      return;
    }

    setIsUploading(true);
    setUploadError(null);

    try {
      // For now, we'll process the first valid file
      // In a full implementation, you might want to process multiple files
      const file = validFiles[0];
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch('http://localhost:8000/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Upload failed');
      }

      const result = await response.json();
      // setUploadedFiles(prev => [...prev, { ...result, file }]); // For future multiple file support
      onUploadSuccess(result);
    } catch (error) {
      setUploadError(error.message || 'Upload failed. Please try again.');
    } finally {
      setIsUploading(false);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileUpload(e.dataTransfer.files);
    }
  };

  const handleFileInput = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      handleFileUpload(e.target.files);
    }
  };

  return (
    <div className="file-upload-container">
      <div className="upload-header">
        <h2>Upload IOL Data Document</h2>
        <p>Upload a PDF or image file containing intraocular lens measurements</p>
      </div>

      <div
        className={`upload-area ${dragActive ? 'drag-active' : ''} ${isUploading ? 'uploading' : ''}`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        {isUploading ? (
          <div className="upload-status">
            <div className="spinner"></div>
            <p>Processing your file...</p>
          </div>
        ) : (
          <div className="upload-content">
            <div className="upload-icon">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                <polyline points="7,10 12,15 17,10"></polyline>
                <line x1="12" y1="15" x2="12" y2="3"></line>
              </svg>
            </div>
            <h3>Drop your files here</h3>
            <p>or click to browse</p>
            <div className="file-types">
              <span className="file-type">PDF</span>
              <span className="file-type">PNG</span>
              <span className="file-type">JPEG</span>
            </div>
            <p className="file-size-limit">Maximum file size: 30MB each</p>
            <p className="multiple-files-note">Multiple files supported</p>
            <input
              type="file"
              accept=".pdf,.png,.jpg,.jpeg"
              onChange={handleFileInput}
              className="file-input"
              disabled={isUploading}
              multiple
            />
          </div>
        )}
      </div>

      {uploadError && (
        <div className="error-message">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10"></circle>
            <line x1="15" y1="9" x2="9" y2="15"></line>
            <line x1="9" y1="9" x2="15" y2="15"></line>
          </svg>
          {uploadError}
        </div>
      )}
    </div>
  );
};

export default FileUpload;
