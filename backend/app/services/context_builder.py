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
from app.services.diff_parser import (
    parse_diff,
    format_diff_for_llm,
    DiffFile,
    LineType,
)

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

    def build_context(self, pr_url: str,
                      graph_context: Optional[Dict] = None) -> ReviewContext:
        """
        Build SIMPLIFIED ReviewContext from a PR URL.

        SIMPLIFIED APPROACH:
        1. Fetch and parse diff only
        2. Build FileContext objects with diff_content (for code snippets)
        3. Fetch PR metadata
        4. (NO full file content - diff is sufficient)
        5. Assemble ReviewContext with diff + graph_context

        Args:
            pr_url: GitHub PR URL
            graph_context: Graph analysis context from extension.
                           Contains: changed_functions, affected_flows, 
                                    test_gaps, overall_risk
        """
        logger.info(f"Building context for: {pr_url}")
        if graph_context:
            logger.info(f"Graph context provided: {len(graph_context.get('changed_functions', []))} functions")

        # 1. Fetch raw diff
        raw_diff = self.github.fetch_pr_diff(pr_url)

        # 2. Parse diff
        diff_files = parse_diff(raw_diff)
        formatted_diff = format_diff_for_llm(diff_files)
        
        # Store diff_files paths for later context_level calculation
        diff_file_paths = {df.new_path or df.old_path for df in diff_files}

        # 3. Fetch metadata
        metadata = self.github.fetch_pr_metadata(pr_url)

        # 4. Detect primary language from diff
        primary_language = self._detect_language_from_diff(diff_files)

        file_contexts = self._build_file_contexts_from_diff(diff_files)

        context = ReviewContext(
            pr_url=pr_url,
            title=metadata.get("title", ""),
            description=metadata.get("description", ""),
            raw_diff=raw_diff,
            formatted_diff=formatted_diff,
            files=file_contexts,
            metadata=metadata,
            language=primary_language,
            graph_context=graph_context or {},
        )
        
        # Store diff_file_paths for context_level determination later
        context.metadata['diff_file_paths'] = diff_file_paths

        logger.info(
            f"Context built: {len(diff_file_paths)} files changed, "
            f"language={primary_language}, "
            f"diff_chars={len(formatted_diff)}, "
            f"graph_functions={len(graph_context.get('changed_functions', []) if graph_context else [])}"
        )

        return context

    def _detect_language_from_diff(self, diff_files: List[DiffFile]) -> str:
        """Detect primary language from changed files."""
        lang_counts: Dict[str, int] = {}
        for df in diff_files:
            lang = detect_language(df.new_path)
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
        
        if not lang_counts:
            return "unknown"
        
        return max(lang_counts, key=lang_counts.get)

    def _build_file_contexts(
        self, pr_url: str, diff_files: List[DiffFile]
    ) -> List[FileContext]:
        """
        DEPRECATED: No longer used.
        
        We don't fetch full file content anymore - diff is sufficient.
        Graphs provide impact analysis instead.
        """
        return []

    def _build_file_contexts_from_diff(self, diff_files: List[DiffFile]) -> List[FileContext]:
        """
        Build FileContext objects from parsed diff files.
        
        Populates:
        - path: File path
        - diff_content: Raw diff for this file
        - language: Detected language from extension
        - is_new: Whether file is newly created
        - is_deleted: Whether file is deleted
        
        NOTE: full_content and old_content are NOT populated (simplified approach).
        They can be extracted from diff if needed by agents.
        """
        file_contexts = []
        
        for df in diff_files:
            # Reconstruct diff content for this file
            # Format: file header + hunks
            diff_lines = []
            
            # Add file header
            diff_lines.append(f"--- a/{df.old_path or df.new_path}")
            diff_lines.append(f"+++ b/{df.new_path or df.old_path}")
            
            # Add hunks (unified diff: lines must start with +, -, or space)
            for hunk in df.hunks:
                diff_lines.append(
                    f"@@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@"
                )
                for line in hunk.lines:
                    if line.line_type == LineType.ADD:
                        diff_lines.append("+" + line.content)
                    elif line.line_type == LineType.REMOVE:
                        diff_lines.append("-" + line.content)
                    else:
                        diff_lines.append(" " + line.content)

            diff_content = "\n".join(diff_lines)
            
            fc = FileContext(
                path=df.new_path or df.old_path,
                diff_content=diff_content,
                full_content="",  # Not populated in simplified approach
                old_content="",   # Not populated in simplified approach
                language=detect_language(df.new_path or df.old_path),
                is_new=df.is_new,
                is_deleted=df.is_deleted,
            )
            file_contexts.append(fc)

        return file_contexts
