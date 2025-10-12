# Parser Strategy & Architecture Documentation

## 🎯 **Vision: Universal Biometry Parser**

### **Core Philosophy**
- **Flexible > Predictive**: Don't try to predict formats, adapt to whatever is uploaded
- **Multi-layered Fallback**: Text extraction → OCR → LLM → Manual review
- **Device Agnostic**: Works with any biometer, any format, any quality
- **User-Friendly**: Drag & drop → Review & edit → Calculate
- **Cost-Conscious**: Track usage and optimize for efficiency

## 📊 **Device Support Matrix**

### **Critical Support (MVP Launch)**
| Device | Manufacturer | Models | Priority |
|--------|--------------|--------|----------|
| IOLMaster | Zeiss | 500, 700 | 🔴 Critical |
| Lenstar | Haag-Streit | LS 900, Eyestar 900 | 🔴 Critical |
| Pentacam | Oculus | AXL, AXL Wave | 🔴 Critical |

### **Important Support (Post-Launch)**
| Device | Manufacturer | Models | Priority |
|--------|--------------|--------|----------|
| Galilei | Ziemer | G6 | 🟡 Important |
| Anterion | Heidelberg Engineering | - | 🟡 Important |
| Aladdin | Topcon | HW3.0/3.5/3.6 | 🟡 Important |
| AL-Scan | Nidek | AL-Scan, AL-Scan 2 | 🟡 Important |

### **Future Support**
| Device | Manufacturer | Models | Priority |
|--------|--------------|--------|----------|
| OA-2000 | Tomey | - | 🟢 Future |
| HBM-1 | Huvitz/Rexxam | AL-2000 | 🟢 Future |
| Others | Canon, Medmont, Righton, Takagi | Various | 🟢 Future |

## 🏗️ **Architecture Design**

### **Multi-Layer Parser System**

```
┌─────────────────────────────────────────────────────────────┐
│                    User Upload                              │
│              (PDF, Image, Text, etc.)                      │
└─────────────────────┬───────────────────────────────────────┘
                      │
┌─────────────────────▼───────────────────────────────────────┐
│                Layer 1: Text Extraction                    │
│  • PDF text extraction (PyPDF2, pdfplumber)               │
│  • Quality assessment & confidence scoring                 │
│  • Fast, free, high accuracy for clean PDFs               │
└─────────────────────┬───────────────────────────────────────┘
                      │ (if confidence < 0.8)
┌─────────────────────▼───────────────────────────────────────┐
│                Layer 2: OCR Processing                     │
│  • Tesseract (free) / EasyOCR (paid)                      │
│  • Image preprocessing & enhancement                       │
│  • Multi-language support                                  │
│  • Cost: ~$0.01-0.05 per page                             │
└─────────────────────┬───────────────────────────────────────┘
                      │ (if confidence < 0.7)
┌─────────────────────▼───────────────────────────────────────┐
│                Layer 3: LLM Fallback                       │
│  • GPT-4/Claude for complex parsing                       │
│  • Structured prompts for biometry extraction             │
│  • Cost: ~$0.10-0.50 per document                        │
│  • Only used when absolutely necessary                    │
└─────────────────────┬───────────────────────────────────────┘
                      │ (if confidence < 0.6)
┌─────────────────────▼───────────────────────────────────────┐
│                Layer 4: Manual Review                      │
│  • User-friendly editing interface                        │
│  • Highlight uncertain values                             │
│  • Save corrections for future learning                   │
└─────────────────────────────────────────────────────────────┘
```

## 💰 **Cost Management Strategy**

### **Cost Tracking & Budgeting**

#### **Usage Monitoring**
```python
# Cost tracking decorator
@track_usage(cost_per_unit=0.05, service="ocr")
def process_with_ocr(document):
    # OCR processing logic
    pass

# Budget limits
MONTHLY_BUDGET = {
    "ocr": 50.00,      # $50/month for OCR
    "llm": 100.00,     # $100/month for LLM
    "total": 150.00    # $150/month total
}
```

#### **Cost Optimization**
- **Smart Fallback**: Only use expensive services when necessary
- **Batch Processing**: Process multiple documents together
- **Caching**: Store results for similar documents
- **User Limits**: Implement usage quotas per user
- **Quality Gates**: Use confidence thresholds to avoid unnecessary processing

### **Cost Estimates**
| Service | Cost per Document | Monthly Budget | Documents/Month |
|---------|------------------|----------------|-----------------|
| Text Extraction | $0.00 | $0 | Unlimited |
| OCR (Tesseract) | $0.00 | $0 | Unlimited |
| OCR (EasyOCR) | $0.01-0.05 | $25 | 500-2500 |
| LLM (GPT-4) | $0.10-0.50 | $75 | 150-750 |
| **Total** | **$0.11-0.55** | **$100** | **150-750** |

## 🚀 **Implementation Roadmap**

### **Phase 1: Foundation (Month 1-2)**
- [ ] **Text Extraction Engine**
  - [ ] PDF text extraction (PyPDF2, pdfplumber)
  - [ ] Quality assessment and confidence scoring
  - [ ] Multi-language support

- [ ] **Cost Tracking System**
  - [ ] Usage monitoring decorators
  - [ ] Budget limits and alerts
  - [ ] User quota management

- [ ] **Basic OCR Integration**
  - [ ] Tesseract (free) implementation
  - [ ] Image preprocessing pipeline
  - [ ] Confidence scoring

### **Phase 2: Smart Fallback (Month 2-3)**
- [ ] **LLM Fallback System**
  - [ ] GPT-4/Claude integration
  - [ ] Structured prompts for biometry extraction
  - [ ] Cost optimization (only when needed)

- [ ] **Data Curation Logic**
  - [ ] Multi-file support (Pentacam + IOLMaster)
  - [ ] Data merging and conflict resolution
  - [ ] User review interface

### **Phase 3: Device Optimization (Month 3-4)**
- [ ] **Critical Device Support**
  - [ ] Zeiss IOLMaster (500, 700)
  - [ ] Haag-Streit Lenstar (LS 900, Eyestar 900)
  - [ ] Oculus Pentacam (AXL, AXL Wave)

- [ ] **Pattern Recognition**
  - [ ] Learn common formats per device
  - [ ] Device-specific validation rules
  - [ ] Confidence scoring per device

### **Phase 4: Advanced Features (Month 4-5)**
- [ ] **Important Device Support**
  - [ ] Ziemer Galilei G6
  - [ ] Heidelberg Anterion
  - [ ] Topcon Aladdin
  - [ ] Nidek AL-Scan

- [ ] **Machine Learning Enhancement**
  - [ ] Learn from user corrections
  - [ ] Improve confidence scoring
  - [ ] Reduce LLM usage over time

## 🔧 **Technical Implementation**

### **Parser Module Structure**
```
app/services/parsing/
├── __init__.py
├── base_parser.py          # Abstract base class
├── text_extractor.py       # PDF/text extraction
├── ocr_processor.py        # OCR processing
├── llm_fallback.py         # LLM-based parsing
├── cost_tracker.py         # Usage and cost tracking
├── device_parsers/
│   ├── zeiss_parser.py     # IOLMaster specific
│   ├── haag_streit_parser.py # Lenstar specific
│   ├── oculus_parser.py    # Pentacam specific
│   └── universal_parser.py # Fallback parser
└── utils/
    ├── confidence.py       # Confidence scoring
    ├── validation.py       # Data validation
    └── merge.py           # Multi-file merging
```

### **Data Flow**
```python
class UniversalParser:
    def __init__(self):
        self.text_extractor = TextExtractor()
        self.ocr_processor = OCRProcessor()
        self.llm_fallback = LLMFallback()
        self.cost_tracker = CostTracker()
    
    def parse(self, document, user_id):
        # Layer 1: Text extraction
        result = self.text_extractor.extract(document)
        if result.confidence > 0.8:
            return result
        
        # Layer 2: OCR (if budget allows)
        if self.cost_tracker.can_use_ocr(user_id):
            result = self.ocr_processor.process(document)
            if result.confidence > 0.7:
                return result
        
        # Layer 3: LLM (if budget allows)
        if self.cost_tracker.can_use_llm(user_id):
            result = self.llm_fallback.process(document)
            if result.confidence > 0.6:
                return result
        
        # Layer 4: Manual review
        return self.request_manual_review(document)
```

## 🎨 **UI/UX Considerations**

### **Upload Interface**
- **Drag & Drop**: Multiple file support
- **Progress Indicators**: Show processing status
- **Cost Awareness**: Display estimated costs
- **Preview**: Show extracted data before processing

### **Review Interface**
- **Highlighted Values**: Show confidence levels
- **Easy Editing**: Inline editing of extracted values
- **Validation**: Real-time validation of inputs
- **Save Corrections**: Learn from user inputs

### **Multi-File Support**
- **File Association**: Link related files (Pentacam + IOLMaster)
- **Data Merging**: Automatic conflict resolution
- **User Override**: Manual selection when conflicts occur

## 📈 **Success Metrics**

### **Technical Metrics**
- **Parsing Accuracy**: >95% for critical devices
- **Cost Efficiency**: <$0.20 per document average
- **Processing Time**: <30 seconds per document
- **User Satisfaction**: >90% successful extractions

### **Business Metrics**
- **User Adoption**: Track parser usage
- **Cost per User**: Monitor expenses per user
- **Support Requests**: Reduce manual data entry
- **Conversion Rate**: Parser → Calculation → Suggestion

## 🔮 **Future Enhancements**

### **Advanced Features**
- **Machine Learning**: Learn from user corrections
- **Device Updates**: Automatic parser updates
- **Quality Scoring**: Predict document quality
- **Batch Processing**: Process multiple documents

### **Integration Opportunities**
- **EHR Integration**: Direct hospital system connection
- **API Access**: Third-party integrations
- **Mobile App**: Camera-based document capture
- **Cloud Storage**: Secure document storage

## 🚨 **Risk Mitigation**

### **Technical Risks**
- **Cost Overrun**: Implement strict budget limits
- **Quality Issues**: Multi-layer validation
- **Performance**: Optimize for speed and accuracy
- **Scalability**: Design for growth

### **Business Risks**
- **User Adoption**: Focus on user experience
- **Competition**: Maintain technical advantage
- **Regulatory**: Ensure medical data compliance
- **Support**: Plan for user assistance

---

## 📝 **Next Steps**

1. **Immediate**: Set up cost tracking infrastructure
2. **Week 1**: Implement text extraction engine
3. **Week 2**: Add OCR processing with cost controls
4. **Week 3**: Integrate LLM fallback system
5. **Week 4**: Build user review interface
6. **Month 2**: Add critical device support
7. **Month 3**: Launch MVP with 3 critical devices

This strategy balances flexibility, cost-effectiveness, and user experience while building a truly unique product in the IOL calculation space.
