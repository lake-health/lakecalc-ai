from fastapi import APIRouter
from app.models.schema import ReviewPayload

router = APIRouter()

@router.post("/", response_model=ReviewPayload)
async def review_confirm(payload: ReviewPayload):
    return payload
