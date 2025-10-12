# Local LLM Parser Implementation Plan

## Phase 1: Setup & Testing

### 1. Install Ollama (Local LLM Runner)
```bash
# macOS
brew install ollama

# Start Ollama service
ollama serve
```

### 2. Download Base Models
```bash
# Download Llama 2 7B (good for general tasks)
ollama pull llama2:7b

# Download Code Llama 7B (better for structured data)
ollama pull codellama:7b

# Download Mistral 7B (alternative)
ollama pull mistral:7b
```

### 3. Test Basic Inference
```python
import requests
import json

def test_local_llm(prompt):
    response = requests.post('http://localhost:11434/api/generate',
        json={
            'model': 'llama2:7b',
            'prompt': prompt,
            'stream': False
        })
    return response.json()['response']

# Test with biometry text
biometry_text = """
k1: 40,95 d @100° ˂k: -2,79 d @100° k2: 43,74 d @ 10°
AL: 23,73 mm
ACD: 2,89 mm
"""

prompt = f"""
Extract biometry data from this text and return as JSON:
{biometry_text}

Expected format:
{{
  "axial_length": number,
  "k1": number,
  "k2": number,
  "k_axis_1": number,
  "k_axis_2": number,
  "eye": "OD" or "OS"
}}
"""

result = test_local_llm(prompt)
print(result)
```

## Phase 2: Fine-Tuning Pipeline

### 1. Training Data Format
```json
[
  {
    "input": "k1: 40,95 d @100° k2: 43,74 d @ 10° AL: 23,73 mm ACD: 2,89 mm",
    "output": "{\"axial_length\": 23.73, \"k1\": 40.95, \"k2\": 43.74, \"k_axis_1\": 100, \"k_axis_2\": 10, \"eye\": \"OD\"}"
  }
]
```

### 2. Fine-Tuning Script
```python
from transformers import AutoTokenizer, AutoModelForCausalLM
from peft import LoraConfig, get_peft_model, TaskType
import torch

def setup_fine_tuning():
    model_name = "meta-llama/Llama-2-7b-hf"
    
    # Load tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForCausalLM.from_pretrained(model_name)
    
    # Configure LoRA
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16,
        lora_alpha=32,
        lora_dropout=0.1,
        target_modules=["q_proj", "v_proj"]
    )
    
    model = get_peft_model(model, lora_config)
    return model, tokenizer
```

## Phase 3: Integration with Parser

### 1. Local LLM Processor
```python
class LocalLLMProcessor(BaseParser):
    def __init__(self, model_name="biometry-parser"):
        self.model_name = model_name
        self.client = requests.Session()
    
    def parse(self, document_path: str, user_id: str = None, raw_text: str = None):
        if not raw_text:
            # Extract text first
            raw_text = self._extract_text(document_path)
        
        prompt = self._build_prompt(raw_text)
        result = self._query_local_model(prompt)
        
        return self._parse_response(result)
    
    def _query_local_model(self, prompt):
        response = self.client.post('http://localhost:11434/api/generate',
            json={
                'model': self.model_name,
                'prompt': prompt,
                'stream': False,
                'options': {
                    'temperature': 0.1,  # Low temperature for consistent output
                    'top_p': 0.9
                }
            })
        return response.json()['response']
```

## Phase 4: Continuous Learning

### 1. Feedback Loop
- Store successful extractions
- Retrain model monthly with new data
- A/B test against regex parsers

### 2. Performance Monitoring
- Track accuracy per device type
- Monitor parsing speed
- Cost comparison (compute vs API calls)

## Benefits

1. **Zero ongoing costs** after setup
2. **Improves over time** with more data
3. **Handles new devices** automatically
4. **Complete privacy** - no external calls
5. **Faster inference** - no network latency
