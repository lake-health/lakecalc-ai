from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    notes: str | None = None

class EyeData(BaseModel):
    axial_length: Optional[str] = ""
    acd: Optional[str] = ""
    lt: Optional[str] = ""
    cct: Optional[str] = ""
    wtw: Optional[str] = ""
    k1: Optional[str] = ""
    k2: Optional[str] = ""
    ak: Optional[str] = ""
    axis: Optional[str] = ""
    source: Optional[str] = ""

class ExtractResult(BaseModel):
    file_id: str
    text_hash: str
    od: EyeData = Field(default_factory=EyeData)
    os: EyeData = Field(default_factory=EyeData)
    confidence: Dict[str, float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

class ReviewPayload(BaseModel):
    file_id: str
    edits: Dict[str, Any]

class SuggestQuery(BaseModel):
    deltaK: float
    sia: Optional[float] = None

class SuggestResponse(BaseModel):
    recommend_toric: bool
    effective_astig: float
    threshold: float
    rationale: str
    families: list[dict]
```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    notes: str | None = None

class EyeData(BaseModel):
    axial_length: Optional[str] = ""
    acd: Optional[str] = ""
    lt: Optional[str] = ""
    cct: Optional[str] = ""
    wtw: Optional[str] = ""
    k1: Optional[str] = ""
    k2: Optional[str] = ""
    ak: Optional[str] = ""
    axis: Optional[str] = ""
    source: Optional[str] = ""

class ExtractResult(BaseModel):
    file_id: str
    text_hash: str
    od: EyeData = Field(default_factory=EyeData)
    os: EyeData = Field(default_factory=EyeData)
    confidence: Dict[str, float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

class ReviewPayload(BaseModel):
    file_id: str
    edits: Dict[str, Any]

class SuggestQuery(BaseModel):
    deltaK: float
    sia: Optional[float] = None

class SuggestResponse(BaseModel):
    recommend_toric: bool
    effective_astig: float
    threshold: float
    rationale: str
    families: list[dict]
```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    notes: str | None = None

class EyeData(BaseModel):
    axial_length: Optional[str] = ""
    acd: Optional[str] = ""
    lt: Optional[str] = ""
    cct: Optional[str] = ""
    wtw: Optional[str] = ""
    k1: Optional[str] = ""
    k2: Optional[str] = ""
    ak: Optional[str] = ""  # astig magnitude (e.g., “-2.35 D”) or deltaK
    axis: Optional[str] = ""  # degrees if available
    source: Optional[str] = ""

class ExtractResult(BaseModel):
    file_id: str
    text_hash: str
    od: EyeData = Field(default_factory=EyeData)
    os: EyeData = Field(default_factory=EyeData)
    confidence: Dict[str, float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

class ReviewPayload(BaseModel):
    file_id: str
    edits: Dict[str, Any]

class SuggestQuery(BaseModel):
    deltaK: float
    sia: Optional[float] = None

class SuggestResponse(BaseModel):
    recommend_toric: bool
    effective_astig: float
    threshold: float
    rationale: str
    families: list[dict]
```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class UploadResponse(BaseModel):
    file_id: str
    filename: str
    notes: str | None = None

class EyeData(BaseModel):
    axial_length: Optional[str] = ""
    acd: Optional[str] = ""
    lt: Optional[str] = ""
    cct: Optional[str] = ""
    wtw: Optional[str] = ""
    k1: Optional[str] = ""
    k2: Optional[str] = ""
    ak: Optional[str] = ""  # astig magnitude (e.g., “-2.35 D”) or deltaK
    axis: Optional[str] = ""  # degrees if available
    source: Optional[str] = ""

class ExtractResult(BaseModel):
    file_id: str
    text_hash: str
    od: EyeData = Field(default_factory=EyeData)
    os: EyeData = Field(default_factory=EyeData)
    confidence: Dict[str, float] = Field(default_factory=dict)
    flags: list[str] = Field(default_factory=list)
    notes: Optional[str] = None

class ReviewPayload(BaseModel):
    file_id: str
    edits: Dict[str, Any]

class SuggestQuery(BaseModel):
    deltaK: float
    sia: Optional[float] = None

class SuggestResponse(BaseModel):
    recommend_toric: bool
    effective_astig: float
    threshold: float
    rationale: str
    families: list[dict]
