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
    affected_code: str = ""
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
            findings = self._invoke_and_parse(context)
            logger.info(f"[{self.name}] Found {len(findings)} issues")
            return findings

        except Exception as e:
            logger.error(f"[{self.name}] Analysis failed: {e}", exc_info=True)
            return []

    def _invoke_and_parse(
        self,
        context: ReviewContext,
        label: str = "",
    ) -> List[Finding]:
        """Invoke the LLM once and parse its findings."""
        prompt_vars = self._build_prompt_vars(context)
        raw_output = self.chain.invoke(prompt_vars)
        label_text = f" ({label})" if label else ""

        logger.info(
            f"[{self.name}]{label_text} Raw LLM output length: "
            f"{len(raw_output)} chars"
        )
        logger.debug(
            f"[{self.name}]{label_text} Raw output (first 1000 chars):\n"
            f"{raw_output[:1000]}"
        )

        findings = self._parse_findings(raw_output, context)
        if not findings:
            logger.warning(
                f"[{self.name}]{label_text} Parser returned 0 findings. "
                f"Raw output preview: {raw_output[:500]}"
            )
        return findings

    def _build_prompt_vars(self, context: ReviewContext) -> Dict[str, str]:
        """Build prompt template variables from context with optimized token usage."""
        # Keep enough diff for multi-hunk PRs. Many benchmark issues sit in
        # later hunks, so overly aggressive truncation directly hurts recall.
        max_total_diff_chars = 30000
        max_file_diff_chars = max(
            6000,
            min(16000, max_total_diff_chars // max(1, len(context.files))),
        )
        truncated_diff = context.formatted_diff[:max_total_diff_chars]
        
        # Compose file context with reduced size
        file_context_parts = []
        for fc in context.files:
            part = f"\n### {fc.path}"
            if fc.language:
                part += f" ({fc.language})"
            part += f"\n```diff\n{fc.diff_content[:max_file_diff_chars]}\n```"
            # Full file content is optional and secondary to complete changed hunks.
            if fc.full_content:
                part += f"\n```\n{fc.full_content[:4000]}\n```"
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

        if self._looks_like_structured_json(raw_output):
            logger.warning(
                f"[{self.name}] Output looked like JSON but could not be parsed; "
                "skipping freetext fallback to avoid exposing raw model output."
            )
            return findings

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

        json_text = self._extract_json_array(raw_output)
        if not json_text:
            json_text = self._extract_json_candidate(raw_output)
            if not json_text:
                return findings

        items = None
        try:
            items = json.loads(json_text)
        except (json.JSONDecodeError, TypeError) as e:
            repaired = self._repair_json_text(json_text)
            try:
                items = json.loads(repaired)
            except (json.JSONDecodeError, TypeError):
                logger.debug(f"[{self.name}] JSON parsing failed: {e}")
                items = self._parse_json_objects_lenient(json_text)

        for item in items or []:
            finding = self._finding_from_json_item(item)
            if finding and finding.note.strip():
                findings.append(finding)

        return findings

    def _finding_from_json_item(self, item: Any) -> Optional[Finding]:
        """Convert one JSON object to a Finding, returning None for invalid items."""
        if not isinstance(item, dict):
            return None

        severity_str = str(item.get("severity", "medium")).lower()
        try:
            severity = Severity(severity_str)
        except ValueError:
            severity = Severity.MEDIUM

        try:
            confidence = float(item.get("confidence", 0.7))
        except (TypeError, ValueError):
            confidence = 0.7
        confidence = max(0.0, min(1.0, confidence))

        context_str = str(item.get("context_level", "diff")).lower()
        try:
            ctx_level = ContextLevel(context_str)
        except ValueError:
            ctx_level = ContextLevel.DIFF

        return Finding(
            path=item.get("path", ""),
            from_line=self._safe_int(item.get("from_line")),
            to_line=self._safe_int(item.get("to_line")),
            category=self.category,
            severity=severity,
            confidence=confidence,
            note=item.get("note", ""),
            context_level=ctx_level,
            side=item.get("side", "right"),
            affected_code=item.get("affected_code", ""),
            suggested_fix=item.get("suggested_fix", "") or self._fallback_fix_from_note(
                item.get("note", "")
            ),
            agent_name=self.name,
        )

    @staticmethod
    def _fallback_fix_from_note(note: str) -> str:
        """Extract concise fix guidance when the model omits suggested_fix."""
        text = str(note or "").strip()
        if not text:
            return ""

        markers = (
            "To fix this,",
            "To fix,",
            "Fix by",
            "Use ",
            "Move ",
            "Consider ",
            "The resolution should",
            "It should",
        )
        for marker in markers:
            idx = text.find(marker)
            if idx >= 0:
                return text[idx:].strip()

        sentences = re.split(r"(?<=[.!?])\s+", text)
        return sentences[-1].strip() if len(sentences) > 1 else ""

    @staticmethod
    def _repair_json_text(text: str) -> str:
        """Repair common LLM JSON mistakes without accepting prose as data."""
        repaired = re.sub(r",\s*([}\]])", r"\1", text.strip())
        output = []
        in_string = False
        escaped = False
        for char in repaired:
            if in_string:
                if escaped:
                    output.append(char)
                    escaped = False
                    continue
                if char == "\\":
                    output.append(char)
                    escaped = True
                    continue
                if char == '"':
                    output.append(char)
                    in_string = False
                    continue
                if char == "\n":
                    output.append("\\n")
                    continue
                if char == "\r":
                    output.append("\\r")
                    continue
                if char == "\t":
                    output.append("\\t")
                    continue
                output.append(char)
                continue

            output.append(char)
            if char == '"':
                in_string = True
        return "".join(output)

    @classmethod
    def _parse_json_objects_lenient(cls, json_text: str) -> List[dict]:
        """Salvage valid objects from a malformed JSON array."""
        items = []
        for object_text in cls._extract_json_objects(json_text):
            try:
                items.append(json.loads(cls._repair_json_text(object_text)))
            except (json.JSONDecodeError, TypeError):
                continue
        if not items:
            partial = cls._extract_partial_json_object(json_text)
            if partial:
                items.append(partial)
        return items

    @classmethod
    def _extract_partial_json_object(cls, text: str) -> Optional[dict]:
        """Salvage key fields from a truncated first JSON object."""
        object_start = text.find("{")
        if object_start < 0:
            return None
        fragment = text[object_start:]

        def string_field(name: str) -> str:
            match = re.search(
                rf'"{re.escape(name)}"\s*:\s*"((?:\\.|[^"\\])*)"',
                fragment,
                re.DOTALL,
            )
            if not match:
                return ""
            try:
                return json.loads(f'"{match.group(1)}"')
            except json.JSONDecodeError:
                return match.group(1)

        def int_field(name: str) -> Optional[int]:
            match = re.search(rf'"{re.escape(name)}"\s*:\s*(\d+)', fragment)
            return int(match.group(1)) if match else None

        def float_field(name: str) -> Optional[float]:
            match = re.search(rf'"{re.escape(name)}"\s*:\s*(\d+(?:\.\d+)?)', fragment)
            return float(match.group(1)) if match else None

        item = {
            "path": string_field("path"),
            "from_line": int_field("from_line"),
            "to_line": int_field("to_line"),
            "side": string_field("side") or "right",
            "severity": string_field("severity") or "medium",
            "confidence": float_field("confidence") or 0.6,
            "context_level": string_field("context_level") or "diff",
            "note": string_field("note"),
            "affected_code": string_field("affected_code"),
            "suggested_fix": string_field("suggested_fix"),
        }
        if item["path"] and item["note"]:
            return item
        return None

    @staticmethod
    def _extract_json_objects(text: str) -> List[str]:
        """Extract balanced JSON object candidates from text."""
        objects = []
        start = None
        depth = 0
        in_string = False
        escaped = False

        for idx, char in enumerate(text):
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                if depth == 0:
                    start = idx
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0 and start is not None:
                    objects.append(text[start:idx + 1])
                    start = None

        return objects

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        """Remove markdown code fences, including unterminated fences."""
        stripped = (text or "").strip()
        fenced = re.match(r"^```(?:json)?\s*\n([\s\S]*?)\n```$", stripped, re.IGNORECASE)
        if fenced:
            return fenced.group(1).strip()
        if stripped.startswith("```"):
            lines = stripped.splitlines()
            if lines:
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            return "\n".join(lines).strip()
        return stripped

    @classmethod
    def _extract_json_candidate(cls, raw_output: str) -> str:
        """Return the JSON-looking suffix for lenient object salvage."""
        text = cls._strip_markdown_fence(raw_output)
        array_start = text.find("[")
        object_start = text.find("{")
        starts = [idx for idx in (array_start, object_start) if idx >= 0]
        if not starts:
            return ""
        return text[min(starts):].strip()

    @classmethod
    def _extract_json_array(cls, raw_output: str) -> str:
        """Extract the first balanced JSON array, ignoring brackets inside strings."""
        text = cls._strip_markdown_fence(raw_output)
        start = text.find("[")
        if start < 0:
            return ""

        depth = 0
        in_string = False
        escaped = False
        for idx in range(start, len(text)):
            char = text[idx]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "[":
                depth += 1
            elif char == "]":
                depth -= 1
                if depth == 0:
                    return text[start:idx + 1]

        return ""

    @classmethod
    def _looks_like_structured_json(cls, raw_output: str) -> bool:
        """Detect model responses that should not be parsed as prose comments."""
        text = cls._strip_markdown_fence(raw_output).lstrip()
        if text.startswith("[") or text.startswith("{"):
            return True
        lowered = text[:1000].lower()
        return (
            "```json" in raw_output.lower()
            or '"path"' in lowered
            or '"from_line"' in lowered
            or '"suggested_fix"' in lowered
            or '"affected_code"' in lowered
        )

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
                affected_match = re.search(r'<affected_code>(.*?)</affected_code>', block, re.DOTALL)

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
                    affected_code=affected_match.group(1).strip() if affected_match else "",
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
            if self._looks_like_structured_json(section):
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
                affected_code="",
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
