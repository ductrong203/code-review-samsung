"""
Chat Schemas — Pydantic models for API request/response.
"""
from pydantic import BaseModel, Field
from typing import List, Optional


class ChatRequest(BaseModel):
    """Incoming chat message from the frontend."""
    message: str = Field(..., description="User message (may contain a PR URL)")
    conversation_id: Optional[str] = Field(
        default=None, description="Conversation ID for context tracking"
    )


class ReviewComment(BaseModel):
    """A single code review comment."""
    path: str = Field(default="", description="File path")
    side: str = Field(default="right", description="Diff side (left/right)")
    from_line: Optional[int] = Field(default=None, description="Start line number")
    to_line: Optional[int] = Field(default=None, description="End line number")
    note: str = Field(..., description="Review comment text")


class PRMetadata(BaseModel):
    """PR metadata from GitHub."""
    title: str = ""
    description: str = ""
    state: str = ""
    labels: List[str] = Field(default_factory=list)
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0


class ChatResponse(BaseModel):
    """Response from the chat endpoint."""
    message: str = Field(..., description="Formatted review message for display")
    comments: List[ReviewComment] = Field(
        default_factory=list, description="Structured review comments"
    )
    pr_url: Optional[str] = Field(default=None, description="Reviewed PR URL")
    metadata: Optional[PRMetadata] = Field(default=None, description="PR metadata")
    error: Optional[str] = Field(default=None, description="Error message if any")
