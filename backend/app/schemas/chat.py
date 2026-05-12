"""
Chat Schemas — Pydantic models for API request/response.

Extended with multi-agent review output: category, severity, confidence,
risk assessment, and structured review summary.
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class ChatRequest(BaseModel):
    """Incoming chat message from the frontend."""
    message: str = Field(..., description="User message (may contain a PR URL)")
    conversation_id: Optional[str] = Field(
        default=None, description="Conversation ID for context tracking"
    )
    graph_context: Optional[Dict[str, Any]] = Field(
        default=None, description="Graph context from extension (optional)"
    )


class ReviewComment(BaseModel):
    """A single code review comment with full agent metadata."""
    path: str = Field(default="", description="File path")
    side: str = Field(default="right", description="Diff side (left/right)")
    from_line: Optional[int] = Field(default=None, description="Start line number")
    to_line: Optional[int] = Field(default=None, description="End line number")
    note: str = Field(..., description="Review comment text")
    # ── Multi-agent extensions ──
    category: str = Field(
        default="", description="Issue category: Code Defect, Security Vulnerability, Performance, Maintainability and Readability"
    )
    severity: str = Field(
        default="medium", description="Issue severity: critical, high, medium, low, info"
    )
    confidence: float = Field(
        default=0.7, description="Confidence score (0.0-1.0)", ge=0.0, le=1.0
    )
    context_level: str = Field(
        default="diff",
        description='Minimum detection scope (not file location): "diff" | "file" | "repo"',
    )
    suggested_fix: str = Field(
        default="", description="Suggested code fix"
    )
    agent_name: str = Field(
        default="", description="Name of the agent(s) that found this issue"
    )
    code_snippet: str = Field(
        default="", description="Code snippet with error lines highlighted (prefix '> ')"
    )


class RiskAssessment(BaseModel):
    """Overall risk assessment for the PR."""
    level: str = Field(default="low", description="Risk level: low, medium, high, critical")
    blast_radius_files: int = Field(default=0, description="Number of affected files")
    blast_radius_functions: int = Field(default=0, description="Number of affected functions")


class CategoryStats(BaseModel):
    """Issue statistics by category."""
    total_by_category: Dict[str, int] = Field(
        default_factory=dict, description="Count per category"
    )
    total_by_severity: Dict[str, int] = Field(
        default_factory=dict, description="Count per severity level"
    )


class PRMetadata(BaseModel):
    """PR metadata from GitHub."""
    title: str = ""
    description: str = ""
    state: str = ""
    labels: List[str] = Field(default_factory=list)
    changed_files: int = 0
    additions: int = 0
    deletions: int = 0


class AgentMetadata(BaseModel):
    """Metadata about the agent review process."""
    review_time_seconds: float = Field(default=0.0, description="Total review time")
    agents_used: List[str] = Field(default_factory=list, description="Agent names used")
    total_raw_findings: int = Field(default=0, description="Raw findings before filtering")
    after_dedup: int = Field(default=0, description="Findings after deduplication")
    after_filter: int = Field(default=0, description="Final findings count")
    files_analyzed: int = Field(default=0, description="Number of files analyzed")
    language: str = Field(default="", description="Primary language detected")
    parallel: bool = Field(default=True, description="Whether agents ran in parallel")


class ChatResponse(BaseModel):
    """Response from the chat endpoint — extended with multi-agent data."""
    message: str = Field(..., description="Formatted review message for display")
    comments: List[ReviewComment] = Field(
        default_factory=list, description="Structured review comments"
    )
    pr_url: Optional[str] = Field(default=None, description="Reviewed PR URL")
    metadata: Optional[PRMetadata] = Field(default=None, description="PR metadata")
    error: Optional[str] = Field(default=None, description="Error message if any")
    # ── Multi-agent extensions ──
    risk_assessment: Optional[RiskAssessment] = Field(
        default=None, description="Overall risk assessment"
    )
    category_stats: Optional[CategoryStats] = Field(
        default=None, description="Issue statistics by category"
    )
    review_summary: str = Field(
        default="", description="Structured review summary"
    )
    agent_metadata: Optional[AgentMetadata] = Field(
        default=None, description="Agent execution metadata"
    )
