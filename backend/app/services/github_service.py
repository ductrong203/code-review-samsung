"""
GitHub Service — Fetches PR diff and metadata from GitHub.

Supports both authenticated (token) and unauthenticated requests.
Public repos work fine without a token.
"""
import re
import logging
import requests
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


def parse_pr_url(pr_url: str) -> Tuple[str, str, str]:
    """
    Extract owner, repo, and PR number from a GitHub PR URL.

    Args:
        pr_url: e.g. "https://github.com/owner/repo/pull/123"

    Returns:
        Tuple of (owner, repo, pr_number)

    Raises:
        ValueError: If URL doesn't match expected format
    """
    pattern = r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)"
    match = re.match(pattern, pr_url.strip())
    if not match:
        raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
    return match.group(1), match.group(2), match.group(3)


def is_github_pr_url(text: str) -> bool:
    """Check if the given text contains a valid GitHub PR URL."""
    pattern = r"https?://github\.com/[^/]+/[^/]+/pull/\d+"
    return bool(re.search(pattern, text.strip()))


def extract_pr_url(text: str) -> Optional[str]:
    """Extract the first GitHub PR URL from text."""
    pattern = r"(https?://github\.com/[^/]+/[^/]+/pull/\d+)"
    match = re.search(pattern, text.strip())
    return match.group(1) if match else None


class GitHubService:
    """Service for interacting with GitHub API."""

    def __init__(self, github_token: str = ""):
        self.token = github_token
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github.v3+json",
            })
        self.session.headers.update({
            "User-Agent": "CodeReviewBot/1.0",
        })

    def fetch_pr_diff(self, pr_url: str) -> str:
        """
        Fetch the raw unified diff for a PR.

        Uses the public {PR_URL}.diff endpoint — no auth needed for public repos.

        Args:
            pr_url: GitHub PR URL

        Returns:
            Raw unified diff string

        Raises:
            requests.HTTPError: If the request fails
        """
        diff_url = pr_url.rstrip("/") + ".diff"
        logger.info(f"Fetching diff from: {diff_url}")

        response = self.session.get(diff_url, timeout=30)
        response.raise_for_status()

        diff_content = response.text
        logger.info(f"Fetched diff: {len(diff_content)} characters")
        return diff_content

    def fetch_pr_metadata(self, pr_url: str) -> dict:
        """
        Fetch PR metadata (title, description) from GitHub API.

        Args:
            pr_url: GitHub PR URL

        Returns:
            Dict with title, description, labels, state
        """
        owner, repo, pr_number = parse_pr_url(pr_url)
        api_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"

        logger.info(f"Fetching PR metadata from: {api_url}")

        try:
            response = self.session.get(api_url, timeout=15)
            response.raise_for_status()
            data = response.json()

            return {
                "title": data.get("title", ""),
                "description": data.get("body", "") or "",
                "state": data.get("state", ""),
                "labels": [label["name"] for label in data.get("labels", [])],
                "changed_files": data.get("changed_files", 0),
                "additions": data.get("additions", 0),
                "deletions": data.get("deletions", 0),
            }
        except requests.HTTPError as e:
            logger.warning(f"Failed to fetch PR metadata: {e}")
            # Return minimal metadata — diff-based review can still proceed
            return {
                "title": "",
                "description": "",
                "state": "unknown",
                "labels": [],
            }
