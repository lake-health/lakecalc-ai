from pydantic import BaseModel, Field, validator
from typing import Optional, Literal

Eye = Literal["OD", "OS"]

class ExtractedKs(BaseModel):
    k1_power: Optional[float] = Field(None, description="D")
    k1_axis: Optional[float] = Field(None, description="degrees")
    k2_power: Optional[float] = Field(None, description="D")
    k2_axis: Optional[float] = Field(None, description="degrees")
    delta_k: Optional[float] = Field(None, description="D")

class ExtractedBiometry(BaseModel):
    device: Optional[str]
    eye: Optional[Eye]
    al_mm: Optional[float]
    acd_mm: Optional[float]
    cct_um: Optional[int]
    wtw_mm: Optional[float]
    lt_mm: Optional[float]
    ks: ExtractedKs = ExtractedKs()
    notes: Optional[str]
    confidence: dict = {}

class UploadResponse(BaseModel):
    file_id: str
    filename: str

class ReviewPayload(ExtractedBiometry):
    pass

class SuggestionRequest(BaseModel):
    data: ExtractedBiometry
    sia_d: Optional[float] = 0.0

class SuggestionResponse(BaseModel):
    recommend_toric: bool
    rationale: str
    suggested_families: list[str] = []
    image_hint_url: Optional[str] = None

    @validator("suggested_families", pre=True, always=True)
    def default_families(cls, v):
        return v or []
