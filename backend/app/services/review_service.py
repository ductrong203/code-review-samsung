"""
Review Service — Orchestrates the full code review pipeline.

Fetches PR diff → parses diff → builds prompt → calls LLM → parses output.
"""
import re
import logging
from typing import List, Dict, Any, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from app.core.config import Settings
from app.services.github_service import GitHubService, parse_pr_url, extract_pr_url
from app.services.diff_parser import parse_diff, format_diff_for_llm
from app.services.llm_service import get_llm
from app.prompts.system_prompt import SYSTEM_PROMPT
from app.prompts.review_prompt import REVIEW_PROMPT_TEMPLATE

logger = logging.getLogger(__name__)


def parse_review_output(raw_output: str) -> List[Dict[str, Any]]:
    """
    Parse LLM output into structured review comments.

    Expects the <notesplit /> tag format used by AACR-Bench.

    Args:
        raw_output: Raw LLM response text

    Returns:
        List of comment dicts with path, side, from_line, to_line, note
    """
    comments = []

    if not raw_output or not raw_output.strip():
        return comments

    # Check if the response indicates no issues
    no_issues_patterns = [
        "no issues found",
        "the code changes look good",
        "no significant issues",
        "lgtm",
    ]
    lower_output = raw_output.strip().lower()
    if any(pattern in lower_output for pattern in no_issues_patterns):
        return comments

    # Split by <notesplit> tags
    blocks = re.split(r'</?notesplit\s*/?>', raw_output, flags=re.IGNORECASE)

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        try:
            path_match = re.search(r'<path>(.*?)</path>', block, re.DOTALL)
            side_match = re.search(r'<side>(.*?)</side>', block, re.DOTALL)
            from_match = re.search(r'<from>(.*?)</from>', block, re.DOTALL)
            to_match = re.search(r'<to>(.*?)</to>', block, re.DOTALL)
            note_match = re.search(r'<note>(.*?)</note>', block, re.DOTALL)

            if note_match and note_match.group(1).strip():
                from_line = None
                to_line = None

                if from_match:
                    try:
                        from_line = int(from_match.group(1).strip())
                    except ValueError:
                        pass

                if to_match:
                    try:
                        to_line = int(to_match.group(1).strip())
                    except ValueError:
                        pass

                comment = {
                    "path": path_match.group(1).strip() if path_match else "",
                    "side": side_match.group(1).strip() if side_match else "right",
                    "from_line": from_line,
                    "to_line": to_line,
                    "note": note_match.group(1).strip(),
                }
                comments.append(comment)
        except Exception as e:
            logger.warning(f"Failed to parse review comment block: {e}")
            continue

    return comments


def format_comments_for_display(comments: List[Dict[str, Any]]) -> str:
    """
    Format review comments into a human-readable string for chat display.

    Args:
        comments: List of parsed review comment dicts

    Returns:
        Formatted string for display in chat
    """
    if not comments:
        return "✅ **No issues found.** The code changes look good!"

    lines = [f"## 🔍 Code Review — Found {len(comments)} issue(s)\n"]

    for i, comment in enumerate(comments, 1):
        path = comment.get("path", "unknown")
        from_line = comment.get("from_line", "?")
        to_line = comment.get("to_line", "?")
        note = comment.get("note", "")

        lines.append(f"### Issue {i}: `{path}` (lines {from_line}–{to_line})")
        lines.append(f"{note}\n")
        lines.append("---\n")

    return "\n".join(lines)


def save_comments_to_file(comments: List[Dict[str, Any]], output_path: str):
    """
    Save comments in AACR-Bench compatible format.

    Args:
        comments: List of review comment dicts
        output_path: Path to save the .txt file
    """
    parts = []
    for comment in comments:
        block = ""
        block += f"<path>{comment.get('path', '')}</path>\n"
        block += f"<side>{comment.get('side', 'right')}</side>\n"
        if comment.get("from_line") is not None:
            block += f"<from>{comment['from_line']}</from>\n"
        if comment.get("to_line") is not None:
            block += f"<to>{comment['to_line']}</to>\n"
        block += f"<note>{comment.get('note', '')}</note>\n"
        block += "<notesplit />"
        parts.append(block)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(parts))


class ReviewService:
    """Orchestrates the full code review pipeline."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.github = GitHubService(github_token=settings.GITHUB_TOKEN)
        self.llm = get_llm(settings)
        self.chain = self._build_chain()

    def _build_chain(self):
        """Build the LangChain review chain: prompt → LLM → string output."""
        prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("human", REVIEW_PROMPT_TEMPLATE),
        ])
        return prompt | self.llm | StrOutputParser()

    def review_pr(self, pr_url: str) -> Dict[str, Any]:
        """
        Run full code review pipeline on a PR.

        Args:
            pr_url: GitHub PR URL

        Returns:
            Dict with:
                - message: formatted review string for display
                - comments: list of structured review comment dicts
                - pr_url: the reviewed PR URL
                - metadata: PR metadata dict
                - raw_output: raw LLM response
        """
        logger.info(f"Starting review for: {pr_url}")

        # 1. Fetch PR diff and metadata
        raw_diff = self.github.fetch_pr_diff(pr_url)
        metadata = self.github.fetch_pr_metadata(pr_url)

        # 2. Parse diff into structured format
        diff_files = parse_diff(raw_diff)
        formatted_diff = format_diff_for_llm(diff_files)

        if not formatted_diff.strip():
            return {
                "message": "⚠️ No code changes found in this PR.",
                "comments": [],
                "pr_url": pr_url,
                "metadata": metadata,
                "raw_output": "",
            }

        # 3. Build prompt and call LLM
        logger.info(f"Sending to LLM ({self.settings.LLM_PROVIDER}): {len(formatted_diff)} chars of diff")

        raw_output = self.chain.invoke({
            "title": metadata.get("title", "No title"),
            "description": metadata.get("description", "No description provided"),
            "diff_content": formatted_diff,
        })

        # 4. Parse LLM output into structured comments
        comments = parse_review_output(raw_output)

        # 5. Format for display
        display_message = format_comments_for_display(comments)

        logger.info(f"Review complete: {len(comments)} comments found")

        return {
            "message": display_message,
            "comments": comments,
            "pr_url": pr_url,
            "metadata": metadata,
            "raw_output": raw_output,
        }
