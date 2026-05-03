"""
Chat Endpoint — Main code review chat API.

Accepts a message (containing a GitHub PR URL), runs the review pipeline,
and returns structured review comments.
"""
import logging
from fastapi import APIRouter, HTTPException

from app.schemas.chat import ChatRequest, ChatResponse, ReviewComment, PRMetadata
from app.services.review_service import ReviewService
from app.services.github_service import extract_pr_url, is_github_pr_url
from app.core.config import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Lazy-initialized service singleton
_review_service = None


def _get_review_service() -> ReviewService:
    """Get or create the ReviewService singleton."""
    global _review_service
    if _review_service is None:
        settings = get_settings()
        _review_service = ReviewService(settings)
    return _review_service


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(request: ChatRequest):
    """
    Process a chat message and return a code review response.

    If the message contains a GitHub PR URL, it will:
    1. Fetch the PR diff from GitHub
    2. Parse the diff into structured format
    3. Send to LLM for review via LangChain
    4. Return structured review comments

    If no PR URL is found, returns a help message.
    """
    message = request.message.strip()

    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    # Check if message contains a GitHub PR URL
    pr_url = extract_pr_url(message)

    if not pr_url:
        return ChatResponse(
            message=(
                "👋 Hi! I'm **CodeReview Bot** — paste a GitHub Pull Request URL "
                "and I'll review the code changes for you.\n\n"
                "**Example:**\n"
                "`https://github.com/owner/repo/pull/123`\n\n"
                "I'll analyze the diff and provide comments on:\n"
                "- 🐛 Code Defects\n"
                "- 🔒 Security Vulnerabilities\n"
                "- ⚡ Performance Issues\n"
                "- 📖 Maintainability & Readability"
            ),
            comments=[],
        )

    # Run review pipeline
    try:
        service = _get_review_service()
        result = service.review_pr(pr_url)

        # Convert to response model
        comments = [
            ReviewComment(
                path=c.get("path", ""),
                side=c.get("side", "right"),
                from_line=c.get("from_line"),
                to_line=c.get("to_line"),
                note=c.get("note", ""),
            )
            for c in result.get("comments", [])
        ]

        metadata = None
        if result.get("metadata"):
            meta = result["metadata"]
            metadata = PRMetadata(
                title=meta.get("title", ""),
                description=meta.get("description", ""),
                state=meta.get("state", ""),
                labels=meta.get("labels", []),
                changed_files=meta.get("changed_files", 0),
                additions=meta.get("additions", 0),
                deletions=meta.get("deletions", 0),
            )

        return ChatResponse(
            message=result.get("message", ""),
            comments=comments,
            pr_url=pr_url,
            metadata=metadata,
        )

    except Exception as e:
        logger.error(f"Review failed for {pr_url}: {e}")
        return ChatResponse(
            message=f"❌ **Error reviewing PR:** {str(e)}",
            comments=[],
            pr_url=pr_url,
            error=str(e),
        )
