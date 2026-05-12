"""
Chat Endpoint — Main code review chat API.

Accepts a message (containing a GitHub PR URL), runs the multi-agent review
pipeline, and returns structured review comments with full agent metadata.
"""
import logging
from fastapi import APIRouter, HTTPException

from app.schemas.chat import (
    ChatRequest, ChatResponse, ReviewComment, PRMetadata,
    RiskAssessment, CategoryStats, AgentMetadata,
)
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
    Process a chat message and return a multi-agent code review response.

    If the message contains a GitHub PR URL, it will:
    1. Fetch the PR diff and full file contents from GitHub
    2. Build rich context (diff + files + metadata)
    3. Run 4 specialized agents in parallel (Defect, Security, Performance, Maintainability)
    4. Deduplicate, verify, and score findings via consensus engine
    5. Return structured review comments with risk assessment

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
                "👋 Hi! I'm **SSCR-BOT** — an AI Code Review Agent powered by "
                "**4 specialized agents**.\n\n"
                "Paste a GitHub Pull Request URL and I'll analyze it for:\n"
                "- 🐛 **Code Defects** — bugs, logic errors, null safety\n"
                "- 🔒 **Security Vulnerabilities** — OWASP Top 10, injection, auth\n"
                "- ⚡ **Performance Issues** — N+1, complexity, resource leaks\n"
                "- 📖 **Maintainability** — SOLID, duplication, clarity\n\n"
                "**Example:**\n"
                "`https://github.com/owner/repo/pull/123`\n\n"
                "Each issue gets a **severity rating**, **confidence score**, "
                "and **suggested fix**."
            ),
            comments=[],
        )

    # Run multi-agent review pipeline
    try:
        service = _get_review_service()
        result = service.review_pr(pr_url, graph_context=request.graph_context)

        # Convert to response model
        comments = [
            ReviewComment(
                path=c.get("path", ""),
                side=c.get("side", "right"),
                from_line=c.get("from_line"),
                to_line=c.get("to_line"),
                note=c.get("note", ""),
                category=c.get("category", ""),
                severity=c.get("severity", "medium"),
                confidence=c.get("confidence", 0.7),
                context_level=c.get("context_level", "diff"),
                suggested_fix=c.get("suggested_fix", ""),
                agent_name=c.get("agent_name", ""),
                code_snippet=c.get("code_snippet", ""),
            )
            for c in result.get("comments", [])
        ]

        # PR Metadata
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

        # Risk Assessment
        risk_assessment = None
        report = result.get("report", {})
        if report:
            risk_assessment = RiskAssessment(
                level=report.get("risk_level", "low"),
                blast_radius_files=report.get("blast_radius_files", 0),
                blast_radius_functions=report.get("blast_radius_functions", 0),
            )

        # Category Stats
        category_stats = None
        if report:
            category_stats = CategoryStats(
                total_by_category=report.get("total_by_category", {}),
                total_by_severity=report.get("total_by_severity", {}),
            )

        # Agent Metadata
        agent_metadata = None
        agent_meta = report.get("agent_metadata", {})
        if agent_meta:
            agent_metadata = AgentMetadata(
                review_time_seconds=agent_meta.get("review_time_seconds", 0.0),
                agents_used=agent_meta.get("agents_used", []),
                total_raw_findings=agent_meta.get("total_raw_findings", 0),
                after_dedup=agent_meta.get("after_dedup", 0),
                after_filter=agent_meta.get("after_filter", 0),
                files_analyzed=agent_meta.get("files_analyzed", 0),
                language=agent_meta.get("language", ""),
                parallel=agent_meta.get("parallel", True),
            )

        return ChatResponse(
            message=result.get("message", ""),
            comments=comments,
            pr_url=pr_url,
            metadata=metadata,
            risk_assessment=risk_assessment,
            category_stats=category_stats,
            review_summary=report.get("summary", ""),
            agent_metadata=agent_metadata,
        )

    except Exception as e:
        logger.error(f"Review failed for {pr_url}: {e}", exc_info=True)
        return ChatResponse(
            message=f"❌ **Error reviewing PR:** {str(e)}",
            comments=[],
            pr_url=pr_url,
            error=str(e),
        )
