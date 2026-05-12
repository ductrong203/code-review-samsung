"""Main code review chat API."""
import json
import logging
import queue
import threading

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.core.config import get_settings
from app.schemas.chat import (
    AgentMetadata,
    CategoryStats,
    ChatRequest,
    ChatResponse,
    PRMetadata,
    ReviewComment,
    RiskAssessment,
)
from app.services.github_service import extract_pr_url
from app.services.review_service import ReviewService, findings_to_comment_dicts

logger = logging.getLogger(__name__)

router = APIRouter()
_review_service = None


def _get_review_service() -> ReviewService:
    """Get or create the ReviewService singleton."""
    global _review_service
    if _review_service is None:
        _review_service = ReviewService(get_settings())
    return _review_service


def _sse(event: str, data: dict) -> str:
    """Format one server-sent event."""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _to_chat_response(result: dict, pr_url: str) -> ChatResponse:
    """Convert internal review dict to API response model."""
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

    report = result.get("report", {})
    risk_assessment = None
    category_stats = None
    agent_metadata = None

    if report:
        risk_assessment = RiskAssessment(
            level=report.get("risk_level", "low"),
            blast_radius_files=report.get("blast_radius_files", 0),
            blast_radius_functions=report.get("blast_radius_functions", 0),
        )
        category_stats = CategoryStats(
            total_by_category=report.get("total_by_category", {}),
            total_by_severity=report.get("total_by_severity", {}),
        )

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


def _help_response() -> ChatResponse:
    return ChatResponse(
        message=(
            "Hi! I'm **SSCR-BOT**.\n\n"
            "Paste a GitHub Pull Request URL and I'll stream review progress, "
            "graph stats, and findings as they are detected.\n\n"
            "**Example:** `https://github.com/owner/repo/pull/123`"
        ),
        comments=[],
    )


@router.post("/chat", response_model=ChatResponse, tags=["chat"])
async def chat(request: ChatRequest):
    """Process a chat message and return a complete review response."""
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    pr_url = extract_pr_url(message)
    if not pr_url:
        return _help_response()

    try:
        result = _get_review_service().review_pr(
            pr_url,
            graph_context=request.graph_context,
        )
        return _to_chat_response(result, pr_url)
    except Exception as e:
        logger.error("Review failed for %s: %s", pr_url, e, exc_info=True)
        return ChatResponse(
            message=f"**Error reviewing PR:** {str(e)}",
            comments=[],
            pr_url=pr_url,
            error=str(e),
        )


@router.post("/chat/stream", tags=["chat"])
async def chat_stream(request: ChatRequest):
    """Stream progress, graph stats, raw findings, and final review response."""
    message = request.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    pr_url = extract_pr_url(message)
    if not pr_url:
        return StreamingResponse(
            iter([_sse("final", _help_response().model_dump())]),
            media_type="text/event-stream",
        )

    event_queue: "queue.Queue[tuple[object, dict]]" = queue.Queue()
    done = object()

    def progress_callback(stage: str, progress: float):
        event_queue.put(("progress", {"stage": stage, "progress": progress}))

    def finding_callback(finding):
        comments = findings_to_comment_dicts([finding])
        if comments:
            event_queue.put(("finding", {"comment": comments[0]}))

    def graph_callback(summary: dict):
        event_queue.put(("graph", summary))

    def worker():
        try:
            service = ReviewService(
                get_settings(),
                progress_callback=progress_callback,
                finding_callback=finding_callback,
                graph_callback=graph_callback,
            )
            result = service.review_pr(pr_url, graph_context=request.graph_context)
            response = _to_chat_response(result, pr_url)
            event_queue.put(("final", response.model_dump()))
        except Exception as e:
            logger.error("Streaming review failed for %s: %s", pr_url, e, exc_info=True)
            event_queue.put(("error", {"error": str(e)}))
        finally:
            event_queue.put(("done", {"ok": True}))
            event_queue.put((done, {}))

    threading.Thread(target=worker, daemon=True).start()

    def event_generator():
        yield _sse("progress", {"stage": "Starting review...", "progress": 0.02})
        while True:
            event, data = event_queue.get()
            if event is done:
                break
            yield _sse(str(event), data)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
