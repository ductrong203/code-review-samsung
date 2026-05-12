"""
Agent Base — Core classes, enums, and dataclasses for the multi-agent review system.

Defines the foundational types used across all specialized agents:
- Category, Severity, ContextLevel enums
- Finding, ReviewContext dataclasses
- ReviewAgent abstract base class
"""
import re
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger(__name__)


# ─── Enums ──────────────────────────────────────────────────────────────────


class Category(str, Enum):
    """AACR-Bench issue categories."""
    CODE_DEFECT = "Code Defect"
    SECURITY = "Security Vulnerability"
    PERFORMANCE = "Performance"
    MAINTAINABILITY = "Maintainability and Readability"


class Severity(str, Enum):
    """Issue severity levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class ContextLevel(str, Enum):
    """Context scope required to detect the issue."""
    DIFF = "diff"
    FILE = "file"
    REPO = "repo"


# ─── Data Classes ───────────────────────────────────────────────────────────


@dataclass
class Finding:
    """A single code review finding from an agent."""
    path: str
    from_line: Optional[int]
    to_line: Optional[int]
    category: Category
    severity: Severity
    confidence: float  # 0.0 - 1.0
    note: str
    context_level: ContextLevel = ContextLevel.DIFF
    side: str = "right"
    suggested_fix: str = ""
    agent_name: str = ""
    code_snippet: str = ""
    # Used by consensus engine
    consensus_score: float = 0.0
    duplicate_of: Optional[int] = None


@dataclass
class FileContext:
    """Full context for a single changed file."""
    path: str
    diff_content: str  # Raw diff for this file
    full_content: str = ""  # Full file content (new version)
    old_content: str = ""  # Full file content (old version)
    language: str = ""
    is_new: bool = False
    is_deleted: bool = False


@dataclass
class ReviewContext:
    """Complete context for a code review session."""
    pr_url: str
    title: str = ""
    description: str = ""
    raw_diff: str = ""
    formatted_diff: str = ""
    files: List[FileContext] = field(default_factory=list)
    repo_structure: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    language: str = ""  # Primary language detected
    graph_context: Optional[Dict[str, Any]] = None  # Graph context from extension


@dataclass
class ReviewReport:
    """Complete review report from the orchestrator."""
    findings: List[Finding] = field(default_factory=list)
    risk_level: str = "low"  # low, medium, high, critical
    blast_radius_files: int = 0
    blast_radius_functions: int = 0
    total_by_category: Dict[str, int] = field(default_factory=dict)
    total_by_severity: Dict[str, int] = field(default_factory=dict)
    summary: str = ""
    agent_metadata: Dict[str, Any] = field(default_factory=dict)


# ─── Abstract Agent ─────────────────────────────────────────────────────────


class ReviewAgent(ABC):
    """
    Abstract base class for specialized review agents.

    Each agent focuses on one AACR-Bench category and uses a specialized
    prompt to maximize detection accuracy for that category.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        category: Category,
        name: str = "",
    ):
        self.llm = llm
        self.category = category
        self.name = name or f"{category.value} Agent"
        self._chain = None

    @property
    def chain(self):
        """Lazy-build the LangChain chain."""
        if self._chain is None:
            prompt = ChatPromptTemplate.from_messages([
                ("system", self.get_system_prompt()),
                ("human", self.get_review_prompt()),
            ])
            self._chain = prompt | self.llm | StrOutputParser()
        return self._chain

    @abstractmethod
    def get_system_prompt(self) -> str:
        """Return the specialized system prompt for this agent."""
        ...

    @abstractmethod
    def get_review_prompt(self) -> str:
        """Return the human review prompt template."""
        ...

    def analyze(self, context: ReviewContext) -> List[Finding]:
        """
        Run analysis on the review context.

        Args:
            context: Complete review context with diff, files, metadata

        Returns:
            List of findings specific to this agent's category
        """
        logger.info(f"[{self.name}] Starting analysis...")

        try:
            # Build input variables for the prompt
            prompt_vars = self._build_prompt_vars(context)

            # Invoke LLM
            raw_output = self.chain.invoke(prompt_vars)

            # Debug: log raw output to diagnose parsing issues
            logger.info(f"[{self.name}] Raw LLM output length: {len(raw_output)} chars")
            logger.debug(f"[{self.name}] Raw output (first 1000 chars):\n{raw_output[:1000]}")

            # Parse findings from output
            findings = self._parse_findings(raw_output, context)

            if not findings:
                logger.warning(f"[{self.name}] Parser returned 0 findings. Raw output preview: {raw_output[:500]}")

            logger.info(f"[{self.name}] Found {len(findings)} issues")
            return findings

        except Exception as e:
            logger.error(f"[{self.name}] Analysis failed: {e}", exc_info=True)
            return []

    def _build_prompt_vars(self, context: ReviewContext) -> Dict[str, str]:
        """Build prompt template variables from context with optimized token usage."""
        # OPTIMIZED: Truncate aggressively to stay under quota
        # Diff: limit to 2000 chars (enough for most hunks)
        truncated_diff = context.formatted_diff[:2000]
        
        # Compose file context with reduced size
        file_context_parts = []
        for fc in context.files:
            part = f"\n### {fc.path}"
            if fc.language:
                part += f" ({fc.language})"
            # Only include diff, truncate heavily
            part += f"\n```\n{fc.diff_content[:1500]}\n```"
            # Only include file content for critical sections (truncate to 2000)
            if fc.full_content:
                part += f"\n```\n{fc.full_content[:2000]}\n```"
            file_context_parts.append(part)

        file_context = "\n".join(file_context_parts) if file_context_parts else truncated_diff

        # Limit repo structure to top 20 dirs (was 50)
        repo_structure = "\n".join(context.repo_structure[:20]) if context.repo_structure else "No structure."

        # ── S3: Build graph context section (empty string when not available) ──
        graph_section = ""
        if context.graph_context:
            gc = context.graph_context
            parts = ["### Graph Analysis"]
            for fn in gc.get("changed_functions", [])[:8]:
                callers = self._format_graph_nodes(fn.get("callers", []), limit=3)
                callees = self._format_graph_nodes(fn.get("callees", []), limit=3)
                tests = self._format_graph_nodes(fn.get("tests", []), limit=3)
                parts.append(
                    f"- Changed `{fn.get('name', '')}` [{fn.get('file', '')}:"
                    f"{fn.get('line_start', '?')}-{fn.get('line_end', '?')}] "
                    f"risk={fn.get('risk_score', 0):.2f} "
                    f"untested={fn.get('is_untested', False)}"
                )
                if callers:
                    parts.append(f"  callers: {callers}")
                if callees:
                    parts.append(f"  callees: {callees}")
                if tests:
                    parts.append(f"  tests: {tests}")
            if gc.get("affected_flows"):
                flow_names = [f.get("name", "") for f in gc["affected_flows"][:5]]
                parts.append(f"Affected flows: {flow_names}")
            if gc.get("test_gaps"):
                gaps = [
                    f"{g.get('name', '')} [{g.get('file', '')}:{g.get('line_start', '?')}]"
                    for g in gc["test_gaps"][:5]
                ]
                parts.append(f"Untested changed functions: {gaps}")
            if gc.get("related_context"):
                related = self._format_graph_nodes(gc["related_context"], limit=10)
                parts.append(f"Related repo context: {related}")
            if gc.get("overall_risk") is not None:
                parts.append(f"Overall risk score: {gc['overall_risk']:.2f}")
            if gc.get("review_priorities"):
                priorities = [
                    f"{p.get('name', '')} [{p.get('file', '')}:{p.get('line_start', '?')}]"
                    for p in gc["review_priorities"][:5]
                ]
                parts.append(f"Review priorities: {priorities}")
            graph_section = "\n".join(parts)
        else:
            graph_section = (
                "DIFF-ONLY BASELINE MODE. No graph, full-file, caller, callee, "
                "test, or repo context is available. Report only issues that are "
                "directly visible from added/changed diff lines. Set "
                'context_level to "diff" for every reported issue. If an issue '
                "would require file or repo context to verify, do not report it."
            )

        return {
            "title": context.title or "No title",
            "description": context.description or "No description",
            "diff_content": truncated_diff,
            "file_context": file_context,
            "repo_structure": repo_structure,
            "language": context.language or "unknown",
            "graph_context": graph_section,
        }

    def _format_graph_nodes(self, nodes: List[Any], limit: int = 5) -> List[str]:
        """Format graph node summaries compactly for prompt context."""
        formatted = []
        for node in nodes[:limit]:
            if isinstance(node, dict):
                name = node.get("name") or node.get("qualified_name") or ""
                file_path = node.get("file") or node.get("file_path") or ""
                line = node.get("line_start")
                relation = node.get("relation")
                prefix = f"{relation} " if relation else ""
                location = f" [{file_path}:{line}]" if file_path or line else ""
                formatted.append(f"{prefix}{name}{location}")
            else:
                formatted.append(str(node))
        return formatted

    def _parse_findings(self, raw_output: str, context: ReviewContext) -> List[Finding]:
        """
        Parse LLM output into structured Finding objects.

        Supports three formats (tried in order):
        1. JSON array format (preferred)
        2. XML-tag format (notesplit compatible)
        3. Markdown/freetext format (robust fallback)
        """
        findings = []

        if not raw_output or not raw_output.strip():
            logger.warning(f"[{self.name}] Empty LLM output")
            return findings

        # Check for "no issues" response — only if output is very short
        # (avoids false trigger when the LLM says "no issues" in intro but then lists issues)
        lower_output = raw_output.strip().lower()
        if len(lower_output) < 100:
            no_issues = ["no issues found", "no issues detected", "lgtm", "code looks good",
                         "no significant issues", "the code changes look good", "[]"]
            if any(p in lower_output for p in no_issues):
                logger.info(f"[{self.name}] LLM reported no issues")
                return findings

        # Try JSON format first
        json_findings = self._parse_json_output(raw_output)
        if json_findings:
            logger.info(f"[{self.name}] Parsed {len(json_findings)} findings via JSON")
            return json_findings

        # Fallback to XML-tag format
        xml_findings = self._parse_xml_output(raw_output)
        if xml_findings:
            logger.info(f"[{self.name}] Parsed {len(xml_findings)} findings via XML")
            return xml_findings

        # Fallback to markdown/freetext parsing
        text_findings = self._parse_freetext_output(raw_output, context)
        if text_findings:
            logger.info(f"[{self.name}] Parsed {len(text_findings)} findings via freetext")
            return text_findings

        logger.warning(f"[{self.name}] All parsers failed. Output format not recognized.")
        return findings

    def _parse_json_output(self, raw_output: str) -> List[Finding]:
        """Parse JSON array format output."""
        findings = []

        # Extract JSON array from output
        json_match = re.search(r'\[[\s\S]*\]', raw_output)
        if not json_match:
            return findings

        try:
            items = json.loads(json_match.group())
            for item in items:
                if not isinstance(item, dict):
                    continue

                severity_str = item.get("severity", "medium").lower()
                try:
                    severity = Severity(severity_str)
                except ValueError:
                    severity = Severity.MEDIUM

                confidence = float(item.get("confidence", 0.7))
                confidence = max(0.0, min(1.0, confidence))

                context_str = item.get("context_level", "diff").lower()
                try:
                    ctx_level = ContextLevel(context_str)
                except ValueError:
                    ctx_level = ContextLevel.DIFF

                finding = Finding(
                    path=item.get("path", ""),
                    from_line=self._safe_int(item.get("from_line")),
                    to_line=self._safe_int(item.get("to_line")),
                    category=self.category,
                    severity=severity,
                    confidence=confidence,
                    note=item.get("note", ""),
                    context_level=ctx_level,
                    side=item.get("side", "right"),
                    suggested_fix=item.get("suggested_fix", ""),
                    agent_name=self.name,
                )
                if finding.note.strip():
                    findings.append(finding)

        except (json.JSONDecodeError, TypeError) as e:
            logger.debug(f"[{self.name}] JSON parsing failed: {e}")

        return findings

    def _parse_xml_output(self, raw_output: str) -> List[Finding]:
        """Parse XML-tag format output (notesplit compatible)."""
        findings = []

        blocks = re.split(r'</?notesplit\s*/?>', raw_output, flags=re.IGNORECASE)

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            try:
                path_match = re.search(r'<path>(.*?)</path>', block, re.DOTALL)
                from_match = re.search(r'<from>(.*?)</from>', block, re.DOTALL)
                to_match = re.search(r'<to>(.*?)</to>', block, re.DOTALL)
                note_match = re.search(r'<note>(.*?)</note>', block, re.DOTALL)
                severity_match = re.search(r'<severity>(.*?)</severity>', block, re.DOTALL)
                confidence_match = re.search(r'<confidence>(.*?)</confidence>', block, re.DOTALL)
                fix_match = re.search(r'<fix>(.*?)</fix>', block, re.DOTALL)

                if not note_match or not note_match.group(1).strip():
                    continue

                severity_str = severity_match.group(1).strip().lower() if severity_match else "medium"
                try:
                    severity = Severity(severity_str)
                except ValueError:
                    severity = Severity.MEDIUM

                confidence = 0.7
                if confidence_match:
                    try:
                        confidence = float(confidence_match.group(1).strip())
                    except ValueError:
                        pass

                finding = Finding(
                    path=path_match.group(1).strip() if path_match else "",
                    from_line=self._safe_int(from_match.group(1).strip() if from_match else None),
                    to_line=self._safe_int(to_match.group(1).strip() if to_match else None),
                    category=self.category,
                    severity=severity,
                    confidence=max(0.0, min(1.0, confidence)),
                    note=note_match.group(1).strip(),
                    side="right",
                    suggested_fix=fix_match.group(1).strip() if fix_match else "",
                    agent_name=self.name,
                )
                findings.append(finding)

            except Exception as e:
                logger.warning(f"[{self.name}] Failed to parse block: {e}")
                continue

        return findings

    def _parse_freetext_output(self, raw_output: str, context: ReviewContext) -> List[Finding]:
        """
        Parse markdown/freetext output as a last resort.

        Many LLMs return findings in markdown format like:
        ### Issue 1: path/to/file.py (lines 42-45)
        **[HIGH]** Description of the issue...

        Or numbered lists, bullet points, etc.
        This parser extracts what it can from any text structure.
        """
        findings = []

        # Strategy 1: Look for file paths and line numbers in the text
        # Common patterns: "file.py", "line 42", "lines 42-45", "L42-L45"
        # Split by common section markers
        sections = re.split(
            r'(?:^|\n)(?:#{1,4}\s+|\d+[\.\)]\s+|[\-\*]\s+(?=\*\*)|Issue\s+\d+)',
            raw_output
        )

        # Also try splitting by double newlines for paragraph-style output
        if len(sections) <= 1:
            sections = re.split(r'\n\n+', raw_output)

        # Known file paths from context
        known_paths = {fc.path for fc in context.files}

        for section in sections:
            section = section.strip()
            if not section or len(section) < 20:
                continue

            # Try to extract a file path
            path = ""
            for kp in known_paths:
                if kp in section:
                    path = kp
                    break
            # Fallback: look for path-like strings
            if not path:
                path_match = re.search(r'[`"\']?([\w/\\]+\.\w{1,10})[`"\']?', section)
                if path_match:
                    candidate = path_match.group(1).replace('\\', '/')
                    # Check if it looks like a real file path
                    if '/' in candidate or '.' in candidate:
                        path = candidate

            # Try to extract line numbers
            from_line = None
            to_line = None
            line_match = re.search(
                r'(?:lines?|L)\s*(\d+)\s*[-–—to]+\s*(\d+)', section, re.IGNORECASE
            )
            if line_match:
                from_line = int(line_match.group(1))
                to_line = int(line_match.group(2))
            else:
                line_match = re.search(r'(?:line|L)\s*(\d+)', section, re.IGNORECASE)
                if line_match:
                    from_line = int(line_match.group(1))
                    to_line = from_line

            # Extract severity from text
            severity = Severity.MEDIUM
            section_lower = section.lower()
            if 'critical' in section_lower:
                severity = Severity.CRITICAL
            elif 'high' in section_lower or 'severe' in section_lower:
                severity = Severity.HIGH
            elif 'low' in section_lower or 'minor' in section_lower:
                severity = Severity.LOW
            elif 'info' in section_lower or 'suggestion' in section_lower:
                severity = Severity.INFO

            # Clean up the note text — remove file/line references already captured
            note = section.strip()
            # Remove markdown headers
            note = re.sub(r'^#{1,4}\s+', '', note)
            # Remove leading bullets/numbers
            note = re.sub(r'^[\d\.\)\-\*]+\s+', '', note)

            # Only keep if the note has substance
            if len(note) < 15:
                continue

            # Skip sections that are just headers or metadata
            skip_patterns = ['summary', 'overview', 'conclusion', 'recommendation',
                           'file-by-file', 'issue breakdown']
            if any(p in note[:50].lower() for p in skip_patterns):
                continue

            finding = Finding(
                path=path,
                from_line=from_line,
                to_line=to_line,
                category=self.category,
                severity=severity,
                confidence=0.5,  # Lower confidence for freetext-parsed findings
                note=note[:1000],  # Truncate very long notes
                context_level=ContextLevel.DIFF,
                side="right",
                suggested_fix="",
                agent_name=self.name,
            )
            findings.append(finding)

        return findings

    @staticmethod
    def _safe_int(value) -> Optional[int]:
        """Safely convert a value to int, returning None on failure."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None
