"""
Review Service — Orchestrates the full code review pipeline via Multi-Agent System.

Upgraded from single LLM+prompt pipeline to a multi-agent architecture:
- 4 specialized agents (Defect, Security, Performance, Maintainability)
- Parallel execution with consensus verification
- Rich context gathering (diff + full files)
- Structured output with category, severity, confidence
"""
import re
import logging
from typing import List, Dict, Any, Optional

from app.core.config import Settings
from app.services.github_service import GitHubService, parse_pr_url, extract_pr_url
from app.services.diff_parser import parse_diff, format_diff_for_llm
from app.services.llm_service import get_llm
from app.agents.orchestrator import ReviewOrchestrator
from app.agents.agent_base import Finding, ReviewReport

logger = logging.getLogger(__name__)


def format_findings_for_display(report: ReviewReport) -> str:
    """
    Format review report into a human-readable string for chat display.

    Generates a rich markdown output with:
    - Risk assessment header
    - Category statistics
    - File-by-file findings with severity badges
    - Actionable summary
    """
    if not report.findings:
        return "✅ **No issues found.** The code changes look good!"

    lines = []

    # ── Header ──────────────────────────────────────────────
    risk_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}
    risk_icon = risk_emoji.get(report.risk_level, "⚪")

    lines.append(f"## 🔍 Code Review — {len(report.findings)} issue(s) found\n")
    lines.append(f"**Overall Risk:** {risk_icon} **{report.risk_level.upper()}**")

    if report.blast_radius_files > 0:
        lines.append(f"**Blast Radius:** {report.blast_radius_files} file(s) affected")

    lines.append("")

    # ── Category Stats ──────────────────────────────────────
    if report.total_by_category:
        cat_emojis = {
            "Code Defect": "🐛",
            "Security Vulnerability": "🔒",
            "Performance": "⚡",
            "Maintainability and Readability": "📖",
        }
        lines.append("### Issue Breakdown")
        for cat, count in sorted(report.total_by_category.items()):
            emoji = cat_emojis.get(cat, "📋")
            lines.append(f"- {emoji} **{cat}**: {count}")
        lines.append("")

    # ── File-by-File Findings ───────────────────────────────
    severity_badge = {
        "critical": "🔴 CRITICAL",
        "high": "🟠 HIGH",
        "medium": "🟡 MEDIUM",
        "low": "🔵 LOW",
        "info": "⚪ INFO",
    }

    # Group findings by file
    by_file: Dict[str, List[Finding]] = {}
    for f in report.findings:
        path = f.path or "unknown"
        by_file.setdefault(path, []).append(f)

    for path, findings in by_file.items():
        lines.append(f"### 📄 `{path}`\n")

        for i, finding in enumerate(findings, 1):
            badge = severity_badge.get(finding.severity.value, "⚪ INFO")
            cat_short = {
                "Code Defect": "🐛 Defect",
                "Security Vulnerability": "🔒 Security",
                "Performance": "⚡ Perf",
                "Maintainability and Readability": "📖 Maintain",
            }.get(finding.category.value, finding.category.value)

            line_info = ""
            if finding.from_line and finding.to_line:
                line_info = f" (lines {finding.from_line}–{finding.to_line})"
            elif finding.from_line:
                line_info = f" (line {finding.from_line})"

            lines.append(f"**{badge}** | {cat_short}{line_info}")
            lines.append(f"{finding.note}")

            if finding.suggested_fix:
                lines.append(f"\n💡 **Fix:** {finding.suggested_fix}")

            lines.append("")

        lines.append("---\n")

    # ── Agent Metadata ──────────────────────────────────────
    meta = report.agent_metadata
    if meta.get("review_time_seconds"):
        lines.append(f"*Review completed in {meta['review_time_seconds']}s "
                     f"by {len(meta.get('agents_used', []))} agents*")

    return "\n".join(lines)


def findings_to_comment_dicts(findings: List[Finding]) -> List[Dict[str, Any]]:
    """Convert Finding objects to serializable dicts."""
    return [
        {
            "path": f.path,
            "side": f.side,
            "from_line": f.from_line,
            "to_line": f.to_line,
            "note": f.note,
            "category": f.category.value,
            "severity": f.severity.value,
            "confidence": f.confidence,
            "context_level": f.context_level.value,
            "suggested_fix": f.suggested_fix,
            "agent_name": f.agent_name,
        }
        for f in findings
    ]


def save_comments_to_file(comments: List[Dict[str, Any]], output_file: str) -> None:
    """
    Save generated comments in AACR-Bench parser format.

    Format per comment block:
      <notesplit>
      <path>...</path>
      <side>right</side>
      <from>10</from>
      <to>12</to>
      <note>...</note>
      </notesplit>
    """
    lines: List[str] = []

    for comment in comments or []:
        if not isinstance(comment, dict):
            continue

        note = (comment.get("note") or "").strip()
        if not note:
            continue

        path = str(comment.get("path") or "").strip().replace("\\", "/")
        side_raw = str(comment.get("side") or "right").strip()
        side = side_raw.lower() if side_raw else "right"
        from_line = comment.get("from_line")
        to_line = comment.get("to_line")

        lines.append("<notesplit>")
        lines.append(f"<path>{path}</path>")
        lines.append(f"<side>{side}</side>")

        if from_line is not None:
            lines.append(f"<from>{from_line}</from>")
        if to_line is not None:
            lines.append(f"<to>{to_line}</to>")

        lines.append(f"<note>{note}</note>")
        lines.append("</notesplit>")

    with open(output_file, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


class ReviewService:
    """
    Orchestrates the full multi-agent code review pipeline.

    Architecture:
        PR URL → Context Builder → 4 Agents (parallel) → Consensus → Report

    Replaces the previous single-LLM pipeline with a multi-agent system
    that specializes in the 4 AACR-Bench categories.
    """

    def __init__(self, settings: Settings):
        self.settings = settings
        self.github = GitHubService(github_token=settings.GITHUB_TOKEN)
        self.llm = get_llm(settings)
        self.orchestrator = ReviewOrchestrator(
            llm=self.llm,
            github=self.github,
            parallel=settings.AGENT_PARALLEL,
            confidence_threshold=settings.AGENT_CONFIDENCE_THRESHOLD,
            max_file_chars=settings.MAX_FILE_CONTEXT_CHARS,
        )

    def review_pr(self, pr_url: str) -> Dict[str, Any]:
        """
        Run full multi-agent code review pipeline on a PR.

        Args:
            pr_url: GitHub PR URL

        Returns:
            Dict with:
                - message: formatted review string for display
                - comments: list of structured review comment dicts
                - pr_url: the reviewed PR URL
                - metadata: PR metadata dict
                - report: full ReviewReport data
        """
        logger.info(f"Starting multi-agent review for: {pr_url}")

        # Run the multi-agent pipeline
        report = self.orchestrator.review(pr_url)

        # Format for display
        display_message = format_findings_for_display(report)

        # Convert findings to comment dicts
        comments = findings_to_comment_dicts(report.findings)

        # Get metadata from orchestrator context
        metadata = {
            "title": report.agent_metadata.get("title", ""),
            "description": report.agent_metadata.get("description", ""),
            "state": "",
            "labels": [],
            "changed_files": report.agent_metadata.get("files_analyzed", 0),
            "additions": 0,
            "deletions": 0,
        }

        # Try to get metadata from GitHub
        try:
            gh_meta = self.github.fetch_pr_metadata(pr_url)
            metadata.update(gh_meta)
        except Exception:
            pass

        logger.info(f"Review complete: {len(comments)} findings")

        return {
            "message": display_message,
            "comments": comments,
            "pr_url": pr_url,
            "metadata": metadata,
            "report": {
                "risk_level": report.risk_level,
                "blast_radius_files": report.blast_radius_files,
                "blast_radius_functions": report.blast_radius_functions,
                "total_by_category": report.total_by_category,
                "total_by_severity": report.total_by_severity,
                "summary": report.summary,
                "agent_metadata": report.agent_metadata,
            },
        }
