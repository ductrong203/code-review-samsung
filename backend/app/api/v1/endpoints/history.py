"""Review history endpoints."""
from fastapi import APIRouter, Depends

from app.api.deps import get_current_user
from app.core.database import get_database
from app.schemas.auth import ReviewHistoryItem, ReviewHistoryResponse

router = APIRouter(prefix="/history", tags=["history"])


@router.get("/reviews", response_model=ReviewHistoryResponse)
async def list_review_history(
    current_user: dict = Depends(get_current_user),
    limit: int = 50,
):
    db = get_database()
    bounded_limit = max(1, min(limit, 100))
    cursor = (
        db.review_history.find({"user_id": str(current_user["_id"])})
        .sort("created_at", -1)
        .limit(bounded_limit)
    )
    items = []
    async for item in cursor:
        review = item.get("review", {})
        comments = review.get("comments") or []
        risk = review.get("risk_assessment") or {}
        items.append(
            ReviewHistoryItem(
                id=str(item["_id"]),
                pr_url=item.get("pr_url"),
                message=item.get("message", ""),
                comments_count=len(comments),
                risk_level=risk.get("level"),
                review=review,
                created_at=item["created_at"],
            ),
        )
    return ReviewHistoryResponse(items=items)
