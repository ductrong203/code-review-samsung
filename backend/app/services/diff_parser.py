"""
Diff Parser — Parses unified diff format into structured data.

Converts raw GitHub diff text into a list of DiffFile objects,
each containing hunks with line-level change information.
"""
import re
import logging
from dataclasses import dataclass, field
from typing import List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class LineType(str, Enum):
    """Type of diff line."""
    ADD = "add"
    REMOVE = "remove"
    CONTEXT = "context"


@dataclass
class DiffLine:
    """A single line in a diff hunk."""
    content: str
    line_type: LineType
    old_line_number: Optional[int] = None
    new_line_number: Optional[int] = None


@dataclass
class DiffHunk:
    """A single hunk in a diff file."""
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    header: str = ""
    lines: List[DiffLine] = field(default_factory=list)


@dataclass
class DiffFile:
    """A single file's diff."""
    old_path: str
    new_path: str
    hunks: List[DiffHunk] = field(default_factory=list)
    is_new: bool = False
    is_deleted: bool = False
    is_renamed: bool = False


def parse_diff(raw_diff: str) -> List[DiffFile]:
    """
    Parse a unified diff string into structured DiffFile objects.

    Args:
        raw_diff: Raw unified diff text from GitHub

    Returns:
        List of DiffFile objects with parsed hunks and lines
    """
    if not raw_diff or not raw_diff.strip():
        return []

    files: List[DiffFile] = []
    current_file: Optional[DiffFile] = None
    current_hunk: Optional[DiffHunk] = None
    old_line = 0
    new_line = 0

    for line in raw_diff.split("\n"):
        # New file header: diff --git a/path b/path
        if line.startswith("diff --git"):
            match = re.match(r"diff --git a/(.*?) b/(.*)", line)
            if match:
                current_file = DiffFile(
                    old_path=match.group(1),
                    new_path=match.group(2),
                )
                files.append(current_file)
                current_hunk = None
            continue

        if current_file is None:
            continue

        # Detect new/deleted files
        if line.startswith("new file mode"):
            current_file.is_new = True
            continue
        if line.startswith("deleted file mode"):
            current_file.is_deleted = True
            continue
        if line.startswith("rename from") or line.startswith("rename to"):
            current_file.is_renamed = True
            continue

        # Skip --- and +++ lines
        if line.startswith("---") or line.startswith("+++"):
            continue

        # Hunk header: @@ -old_start,old_count +new_start,new_count @@ context
        hunk_match = re.match(
            r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)", line
        )
        if hunk_match:
            current_hunk = DiffHunk(
                old_start=int(hunk_match.group(1)),
                old_count=int(hunk_match.group(2) or 1),
                new_start=int(hunk_match.group(3)),
                new_count=int(hunk_match.group(4) or 1),
                header=hunk_match.group(5).strip(),
            )
            current_file.hunks.append(current_hunk)
            old_line = current_hunk.old_start
            new_line = current_hunk.new_start
            continue

        if current_hunk is None:
            continue

        # Parse diff lines
        if line.startswith("+"):
            current_hunk.lines.append(DiffLine(
                content=line[1:],
                line_type=LineType.ADD,
                new_line_number=new_line,
            ))
            new_line += 1
        elif line.startswith("-"):
            current_hunk.lines.append(DiffLine(
                content=line[1:],
                line_type=LineType.REMOVE,
                old_line_number=old_line,
            ))
            old_line += 1
        elif line.startswith(" "):
            current_hunk.lines.append(DiffLine(
                content=line[1:],
                line_type=LineType.CONTEXT,
                old_line_number=old_line,
                new_line_number=new_line,
            ))
            old_line += 1
            new_line += 1
        # Binary file or other metadata — skip
        elif line.startswith("\\"):
            continue

    return files


def format_diff_for_llm(
    diff_files: List[DiffFile],
    max_chars: int = 30000,
) -> str:
    """
    Format parsed diff files into a readable string for LLM consumption.

    Includes line numbers for accurate review positioning.
    Truncates if exceeding max_chars.

    Args:
        diff_files: List of parsed DiffFile objects
        max_chars: Maximum character limit for the output

    Returns:
        Formatted diff string with line numbers
    """
    output_parts = []
    total_chars = 0
    truncated_files = []

    for diff_file in diff_files:
        file_header = f"\n{'='*60}\n"
        file_header += f"File: {diff_file.new_path}"
        if diff_file.is_new:
            file_header += " (NEW FILE)"
        elif diff_file.is_deleted:
            file_header += " (DELETED)"
        elif diff_file.is_renamed:
            file_header += f" (renamed from {diff_file.old_path})"
        file_header += f"\n{'='*60}\n"

        file_content = file_header

        for hunk in diff_file.hunks:
            hunk_header = f"\n--- Hunk: @@ -{hunk.old_start},{hunk.old_count} +{hunk.new_start},{hunk.new_count} @@ {hunk.header}\n"
            file_content += hunk_header

            for line in hunk.lines:
                if line.line_type == LineType.ADD:
                    file_content += f"  {line.new_line_number:>4} | + {line.content}\n"
                elif line.line_type == LineType.REMOVE:
                    file_content += f"  {line.old_line_number:>4} | - {line.content}\n"
                else:
                    line_num = line.new_line_number or line.old_line_number or 0
                    file_content += f"  {line_num:>4} |   {line.content}\n"

        # Check truncation
        if total_chars + len(file_content) > max_chars:
            truncated_files.append(diff_file.new_path)
            # Include at least the header for truncated files
            output_parts.append(file_header + "  [TRUNCATED — file too large for context window]\n")
            continue

        output_parts.append(file_content)
        total_chars += len(file_content)

    result = "".join(output_parts)

    if truncated_files:
        result += f"\n⚠️ Truncated {len(truncated_files)} file(s): {', '.join(truncated_files)}\n"

    return result
