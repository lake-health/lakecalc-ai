# Universal Biometry Parser Frontend

A clean React frontend for testing the universal biometry parser that can extract data from any biometry report format.

## Features

- **Universal File Support**: PDF, PNG, JPG, JPEG, TXT files
- **Real-time Processing**: Upload and get instant results
- **Dual Eye Extraction**: Separate OD and OS data display
- **Axis Data**: K1/K2 axis extraction with confidence scores
- **Beautiful UI**: Modern, responsive design

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm start
```

## Testing

1. **Upload any biometry file** (PDF, image, or text)
2. **Get instant results** with extracted data
3. **View confidence scores** and processing method
4. **Test with various formats** to verify universal parsing

## API Integration

The frontend connects to the RunPod LLM API:
- **Endpoint**: `https://nko8ymjws3px2s-8003.proxy.runpod.net/parse`
- **Method**: POST with file upload
- **Response**: JSON with extracted biometry data

## Supported Formats

- **Text-based PDFs**: Processed with Llama 7B
- **Image-based PDFs**: Converted to images and processed with LLaVA
- **Image files**: Direct processing with LLaVA vision model
- **Text files**: Direct processing with Llama 7B

## Data Extracted

- Patient information (name, age)
- OD (Right Eye) measurements
- OS (Left Eye) measurements
- K1/K2 values with axis data
- Axial length, ACD, LT, WTW, CCT
- Confidence scores and processing metadata






