"""
Context Builder — Gathers rich context for code review beyond just the diff.

Builds ReviewContext by collecting:
- Parsed diff (existing functionality)
- Full file content for changed files (via GitHub raw content)
- Language detection
- Repository structure hints
"""
import re
import logging
from typing import List, Optional, Dict
from pathlib import PurePosixPath

from app.agents.agent_base import FileContext, ReviewContext
from app.services.github_service import GitHubService, parse_pr_url
from app.services.diff_parser import parse_diff, format_diff_for_llm, DiffFile

logger = logging.getLogger(__name__)

# Language detection by file extension
EXTENSION_TO_LANGUAGE = {
    ".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript",
    ".ts": "TypeScript", ".tsx": "TypeScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".cpp": "C++", ".cc": "C++",
    ".c": "C", ".h": "C", ".hpp": "C++", ".cs": "C#",
    ".rb": "Ruby", ".php": "PHP", ".swift": "Swift",
    ".kt": "Kotlin", ".scala": "Scala", ".r": "R",
    ".sh": "Shell", ".bash": "Shell", ".yml": "YAML",
    ".yaml": "YAML", ".json": "JSON", ".xml": "XML",
    ".sql": "SQL", ".html": "HTML", ".css": "CSS",
    ".scss": "SCSS", ".dart": "Dart", ".lua": "Lua",
}


def detect_language(file_path: str) -> str:
    """Detect programming language from file extension."""
    ext = PurePosixPath(file_path).suffix.lower()
    return EXTENSION_TO_LANGUAGE.get(ext, "")


def detect_primary_language(files: List[FileContext]) -> str:
    """Detect the primary language of the PR from changed files."""
    lang_counts: Dict[str, int] = {}
    for fc in files:
        if fc.language:
            lang_counts[fc.language] = lang_counts.get(fc.language, 0) + 1

    if not lang_counts:
        return "unknown"

    return max(lang_counts, key=lang_counts.get)


class ContextBuilder:
    """
    Builds rich ReviewContext for the multi-agent system.

    Gathers diff, full file content, metadata, and structural context
    to provide agents with maximum information for accurate analysis.
    """

    def __init__(self, github: GitHubService, max_file_chars: int = 10000):
        self.github = github
        self.max_file_chars = max_file_chars

    def build_context(self, pr_url: str) -> ReviewContext:
        """
        Build complete ReviewContext from a PR URL.

        Steps:
        1. Fetch and parse diff
        2. Fetch PR metadata
        3. Build file contexts with full content
        4. Detect languages
        5. Assemble ReviewContext
        """
        logger.info(f"Building context for: {pr_url}")

        # 1. Fetch raw diff
        raw_diff = self.github.fetch_pr_diff(pr_url)

        # 2. Parse diff
        diff_files = parse_diff(raw_diff)
        formatted_diff = format_diff_for_llm(diff_files)

        # 3. Fetch metadata
        metadata = self.github.fetch_pr_metadata(pr_url)

        # 4. Build file contexts
        file_contexts = self._build_file_contexts(pr_url, diff_files)

        # 5. Detect primary language
        primary_language = detect_primary_language(file_contexts)

        # 6. Build repo structure hints from file paths
        repo_structure = self._extract_structure(diff_files)

        context = ReviewContext(
            pr_url=pr_url,
            title=metadata.get("title", ""),
            description=metadata.get("description", ""),
            raw_diff=raw_diff,
            formatted_diff=formatted_diff,
            files=file_contexts,
            repo_structure=repo_structure,
            metadata=metadata,
            language=primary_language,
        )

        logger.info(
            f"Context built: {len(file_contexts)} files, "
            f"language={primary_language}, "
            f"diff_chars={len(formatted_diff)}"
        )

        return context

    def _build_file_contexts(
        self, pr_url: str, diff_files: List[DiffFile]
    ) -> List[FileContext]:
        """Build FileContext for each changed file."""
        file_contexts = []

        owner, repo, pr_number = parse_pr_url(pr_url)

        for diff_file in diff_files:
            path = diff_file.new_path
            language = detect_language(path)

            # Build diff content for this file
            diff_content = self._format_single_file_diff(diff_file)

            # Try to fetch full file content (public raw content, no token needed)
            full_content = ""
            if not diff_file.is_deleted:
                full_content = self._fetch_file_content_public(
                    owner, repo, path, pr_number
                )

            fc = FileContext(
                path=path,
                diff_content=diff_content,
                full_content=full_content[:self.max_file_chars] if full_content else "",
                language=language,
                is_new=diff_file.is_new,
                is_deleted=diff_file.is_deleted,
            )
            file_contexts.append(fc)

        return file_contexts

    def _fetch_file_content_public(
        self, owner: str, repo: str, path: str, pr_number: str
    ) -> str:
        """
        Fetch file content via GitHub's public raw content URL.
        No token needed for public repos.
        """
        # Try the PR's head ref via raw.githubusercontent.com
        # This works for public repos without authentication
        raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/refs/pull/{pr_number}/head/{path}"

        try:
            response = self.github.session.get(raw_url, timeout=10)
            if response.status_code == 200:
                return response.text
        except Exception as e:
            logger.debug(f"Failed to fetch {path} from PR ref: {e}")

        # Fallback: try main branch
        for branch in ["main", "master"]:
            raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{path}"
            try:
                response = self.github.session.get(raw_url, timeout=10)
                if response.status_code == 200:
                    return response.text
            except Exception:
                continue

        logger.debug(f"Could not fetch full content for {path}")
        return ""

    def _format_single_file_diff(self, diff_file: DiffFile) -> str:
        """Format a single file's diff for agent consumption."""
        parts = []
        for hunk in diff_file.hunks:
            parts.append(
                f"@@ -{hunk.old_start},{hunk.old_count} "
                f"+{hunk.new_start},{hunk.new_count} @@ {hunk.header}"
            )
            for line in hunk.lines:
                if line.line_type.value == "add":
                    parts.append(f"+{line.content}")
                elif line.line_type.value == "remove":
                    parts.append(f"-{line.content}")
                else:
                    parts.append(f" {line.content}")

        return "\n".join(parts)

    def _extract_structure(self, diff_files: List[DiffFile]) -> List[str]:
        """Extract directory structure from changed files."""
        dirs = set()
        for f in diff_files:
            parts = PurePosixPath(f.new_path).parts
            for i in range(1, len(parts)):
                dirs.add("/".join(parts[:i]))

        return sorted(dirs)
