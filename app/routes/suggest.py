from fastapi import APIRouter
from app.models.schema import SuggestionRequest, SuggestionResponse

router = APIRouter()
TORIC_THRESHOLD_D = 1.0

@router.post("/", response_model=SuggestionResponse)
async def suggest_iol(req: SuggestionRequest):
    k = req.data.ks
    sia = req.sia_d or 0.0

    recommend_toric = False
    rationale_lines = []

    if k.delta_k is not None:
        effective_astig = max(0.0, (k.delta_k or 0.0) - abs(sia))
        recommend_toric = effective_astig >= TORIC_THRESHOLD_D
        rationale_lines.append(
            f"deltaK={k.delta_k:.2f}D; SIA={sia:.2f}D → effective ~{effective_astig:.2f}D"
        )
    else:
        rationale_lines.append("Insufficient K data to compute deltaK; defaulting to non-toric.")

    families = [
        "Alcon AcrySof IQ Toric / Non-Toric",
        "J&J Tecnis Toric / Non-Toric",
        "Rayner Toric / Non-Toric",
        "Hoya Toric / Non-Toric",
    ]

    return SuggestionResponse(
        recommend_toric=recommend_toric,
        rationale="; ".join(rationale_lines),
        suggested_families=families,
        image_hint_url=None,
    )
