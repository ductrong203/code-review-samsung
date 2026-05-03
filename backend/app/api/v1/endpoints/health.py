"""
Health Check Endpoint
"""
from fastapi import APIRouter

router = APIRouter()


@router.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "codeReviewBot"}
