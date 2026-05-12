"""
Enhanced GraphContextEnricher - Extract functions from diff hunks, not file paths.

NEW APPROACH:
1. Parse diff hunks to extract line ranges for each file
2. Identify function boundaries at those line ranges
3. Query graph for impact of those specific functions
4. Return compact impact analysis (callers, flows, risks)

This avoids the path-matching problem entirely.
"""
import logging
import re
from typing import Any, Optional, Dict, List, Set, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ChangedFunction:
    """A function detected as changed in the diff."""
    name: str
    file_path: str
    language: str
    start_line: int
    end_line: int
    change_type: str  # "added", "modified", "deleted"
    code_snippet: str = ""


class DiffFunctionExtractor:
    """
    Extracts function definitions from diff hunks.
    Uses heuristics based on language patterns.
    """
    
    # Patterns to detect function definitions by language
    FUNCTION_PATTERNS = {
        "typescript": r"^\s*(export\s+)?(async\s+)?(function|const|let|var)\s+(\w+)",
        "javascript": r"^\s*(export\s+)?(async\s+)?(function|const|let|var)\s+(\w+)",
        "python": r"^\s*(async\s+)?def\s+(\w+)",
        "java": r"^\s*(public|private|protected)?\s*(static\s+)?(async\s+)?\w+\s+(\w+)\s*\(",
        "go": r"^\s*func\s+(\w+)",
        "rust": r"^\s*(pub\s+)?(async\s+)?fn\s+(\w+)",
        "cpp": r"^\s*\w+[\s\*&]+(\w+)\s*\(",
        "c": r"^\s*\w+[\s\*&]+(\w+)\s*\(",
        "csharp": r"^\s*(public|private|protected)?\s*(static\s+)?(async\s+)?\w+\s+(\w+)\s*\(",
        "ruby": r"^\s*def\s+(\w+)",
        "php": r"^\s*(public|private|protected)?\s*(static\s+)?function\s+(\w+)",
    }

    def __init__(self):
        self.compiled_patterns = {
            lang: re.compile(pattern, re.MULTILINE)
            for lang, pattern in self.FUNCTION_PATTERNS.items()
        }

    def detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext = file_path.split(".")[-1].lower()
        lang_map = {
            "ts": "typescript", "tsx": "typescript",
            "js": "javascript", "jsx": "javascript",
            "py": "python",
            "java": "java",
            "go": "go",
            "rs": "rust",
            "cpp": "cpp", "cc": "cpp", "c": "c", "h": "cpp",
            "cs": "csharp",
            "rb": "ruby",
            "php": "php",
        }
        return lang_map.get(ext, "unknown")

    def extract_from_hunk(
        self,
        file_path: str,
        hunk_content: str,  # All lines in this hunk (with +/- prefix)
        new_start_line: int,  # Starting line number in new version
    ) -> List[ChangedFunction]:
        """
        Extract functions from a diff hunk.
        
        Args:
            file_path: The file being modified
            hunk_content: Raw hunk lines (with +/- prefix)
            new_start_line: Starting line number in new version
            
        Returns:
            List of ChangedFunction objects
        """
        language = self.detect_language(file_path)
        if language == "unknown":
            logger.debug(f"Unknown language for {file_path}, skipping function extraction")
            return []

        pattern = self.compiled_patterns.get(language)
        if not pattern:
            return []

        changed_functions = []
        lines = hunk_content.split("\n")
        
        current_line_num = new_start_line
        added_lines = []
        removed_lines = []
        
        # Separate added vs removed lines
        for line in lines:
            if line.startswith("+") and not line.startswith("+++"):
                added_lines.append((current_line_num, line[1:]))
            elif line.startswith("-") and not line.startswith("---"):
                removed_lines.append((current_line_num, line[1:]))
            elif line.startswith(" "):
                added_lines.append((current_line_num, line[1:]))
            # Skip +++/--- markers
            
            # Update line counter for added lines
            if not line.startswith("-"):
                current_line_num += 1

        # Look for function definitions in added/modified lines
        for line_num, line_content in added_lines:
            match = pattern.search(line_content)
            if match:
                # Extract function name (group varies by language)
                # Most patterns: last group is the function name
                groups = match.groups()
                func_name = groups[-1] if groups else None
                
                if func_name:
                    changed_functions.append(ChangedFunction(
                        name=func_name,
                        file_path=file_path,
                        language=language,
                        start_line=line_num,
                        end_line=line_num + 10,  # Estimate; refined later
                        change_type="added" if any(
                            l[0] == "+" for l in added_lines if l[0] == line_num
                        ) else "modified",
                        code_snippet=line_content,
                    ))

        return changed_functions


class GraphContextEnricher:
    """
    Enhanced enricher that:
    1. Extracts functions from diff hunks (not file matching)
    2. Queries graph for those specific functions
    3. Returns impact analysis
    """

    def __init__(self, db_path: str):
        """Initialize with PR graph database path."""
        from code_review_graph.graph import GraphStore
        self.store = GraphStore(db_path)

    def close(self):
        """Close the graph store connection."""
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_context_from_diff(self, diff_files: List) -> Dict[str, Any]:
        """
        Build graph context from diff files.
        
        Args:
            diff_files: List of DiffFile objects from diff parser
            
        Returns:
            GraphContext with changed_functions, affected_flows, etc.
        """
        from code_review_graph.changes import analyze_changes

        logger.info(f"Extracting graph context from {len(diff_files)} changed files")

        changed_files, changed_ranges = self._extract_changed_ranges(diff_files)
        normalized_files, normalized_ranges = self._normalize_changed_paths(
            changed_files,
            changed_ranges,
        )

        context = {
            "changed_functions": [],
            "affected_flows": [],
            "test_gaps": [],
            "overall_risk": 0.0,
            "review_priorities": [],
            "related_context": [],
            "changed_ranges": changed_ranges,
        }

        if not normalized_files:
            logger.warning("No changed files found in diff for graph enrichment")
            return context

        try:
            result = analyze_changes(
                store=self.store,
                changed_files=normalized_files,
                changed_ranges=normalized_ranges,
            )
        except Exception as e:
            logger.error(f"Graph analyze_changes failed: {e}", exc_info=True)
            result = {}

        changed_functions = self._prioritize_changed_functions(
            result.get("changed_functions", []),
            limit=12,
        )
        if not changed_functions:
            changed_functions = self._fallback_changed_functions(
                normalized_files,
                normalized_ranges,
            )
            if changed_functions:
                logger.info(
                    "Graph analyze_changes returned 0 functions; "
                    "fallback mapped %d changed functions/classes",
                    len(changed_functions),
                )

        context["changed_functions"] = [
            self._format_changed_function(fn) for fn in changed_functions
        ]
        context["affected_flows"] = self._format_flows(
            result.get("affected_flows", [])[:5]
        )
        context["test_gaps"] = self._format_test_gaps(
            result.get("test_gaps", [])[:10]
        )
        context["overall_risk"] = round(result.get("risk_score", 0.0), 4)
        if context["overall_risk"] == 0 and changed_functions:
            context["overall_risk"] = round(
                max((fn.get("risk_score", 0.0) for fn in changed_functions), default=0.0),
                4,
            )
        context["review_priorities"] = self._format_priorities(
            result.get("review_priorities", [])[:5]
        )
        context["related_context"] = self._build_related_context(changed_functions)

        logger.info(
            f"GraphContext: {len(context['changed_functions'])} functions, "
            f"{len(context['related_context'])} related nodes, "
            f"risk={context['overall_risk']}"
        )
        if not context["changed_functions"]:
            logger.warning(
                "GraphContext is empty. changed_files=%s normalized_files=%s "
                "changed_ranges=%s",
                changed_files,
                normalized_files,
                changed_ranges,
            )

        return context

    def _extract_changed_ranges(self, diff_files: List) -> Tuple[List[str], Dict[str, List[Tuple[int, int]]]]:
        """Extract compact new-file line ranges from parsed diff objects."""
        changed_files: List[str] = []
        changed_ranges: Dict[str, List[Tuple[int, int]]] = {}

        for diff_file in diff_files:
            if diff_file.is_deleted:
                continue

            path = diff_file.new_path or diff_file.old_path
            if not path:
                continue

            ranges: List[Tuple[int, int]] = []
            for hunk in diff_file.hunks:
                added_lines = sorted(
                    line.new_line_number
                    for line in hunk.lines
                    if self._line_type_value(line) == "add"
                    and line.new_line_number is not None
                )
                ranges.extend(self._coalesce_lines(added_lines))

            # If a hunk only modifies context metadata or parser missed line types,
            # keep the hunk range so graph mapping can still find enclosing nodes.
            if not ranges:
                ranges = [
                    (hunk.new_start, hunk.new_start + max(hunk.new_count - 1, 0))
                    for hunk in diff_file.hunks
                ]

            changed_files.append(path)
            changed_ranges[path] = ranges

        return changed_files, changed_ranges

    def _line_type_value(self, line: Any) -> str:
        line_type = getattr(line, "line_type", "")
        return getattr(line_type, "value", line_type)

    def _normalize_changed_paths(
        self,
        changed_files: List[str],
        changed_ranges: Dict[str, List[Tuple[int, int]]],
    ) -> Tuple[List[str], Dict[str, List[Tuple[int, int]]]]:
        """Map GitHub diff paths to graph DB file paths, preserving line ranges."""
        normalized_files: List[str] = []
        normalized_ranges: Dict[str, List[Tuple[int, int]]] = {}

        for path in changed_files:
            matches = self._match_graph_files(path)
            targets = matches or [path]
            for target in targets:
                if target not in normalized_files:
                    normalized_files.append(target)
                normalized_ranges[target] = changed_ranges.get(path, [])

        return normalized_files, normalized_ranges

    def _match_graph_files(self, diff_path: str) -> List[str]:
        """Match a GitHub diff path to graph file paths across OS path styles."""
        if not diff_path:
            return []

        candidates = {
            diff_path,
            diff_path.replace("/", "\\"),
            diff_path.replace("\\", "/"),
            diff_path.lstrip("./"),
        }

        matches: List[str] = []
        seen: Set[str] = set()
        for candidate in candidates:
            try:
                for path in self.store.get_files_matching(candidate):
                    if path not in seen:
                        seen.add(path)
                        matches.append(path)
            except Exception:
                continue

        if matches:
            return matches

        # Fallback for Windows absolute paths stored in SQLite while diffs use POSIX.
        wanted = self._norm_path(diff_path)
        try:
            all_files = self.store.get_all_files()
        except Exception:
            all_files = []

        for graph_path in all_files:
            normalized = self._norm_path(graph_path)
            if normalized.endswith(wanted):
                matches.append(graph_path)

        if not matches:
            logger.warning("No graph file matched diff path: %s", diff_path)
        return matches

    def _norm_path(self, path: str) -> str:
        return path.replace("\\", "/").lower().lstrip("./")

    def _coalesce_lines(self, lines: List[int]) -> List[Tuple[int, int]]:
        """Convert sorted line numbers into contiguous ranges."""
        if not lines:
            return []

        ranges: List[Tuple[int, int]] = []
        start = prev = lines[0]
        for line in lines[1:]:
            if line == prev + 1:
                prev = line
                continue
            ranges.append((start, prev))
            start = prev = line
        ranges.append((start, prev))
        return ranges

    def _format_changed_function(self, fn: Dict[str, Any]) -> Dict[str, Any]:
        """Format an analyze_changes function result with direct graph context."""
        qualified_name = fn.get("qualified_name", "")
        callers = self._get_related_nodes(qualified_name, incoming=True, limit=5)
        callees = self._get_related_nodes(qualified_name, incoming=False, limit=5)
        tests = self._get_tests(qualified_name, limit=5)

        return {
            "name": fn.get("name", ""),
            "qualified_name": qualified_name,
            "file": self._display_path(fn.get("file_path", "")),
            "line_start": fn.get("line_start"),
            "line_end": fn.get("line_end"),
            "risk_score": round(fn.get("risk_score", 0.0), 4),
            "callers": callers,
            "callees": callees,
            "tests": tests,
            "is_untested": not tests,
            "kind": fn.get("kind", "Function"),
            "language": fn.get("language", ""),
        }

    def _prioritize_changed_functions(
        self,
        functions: List[Dict[str, Any]],
        limit: int,
    ) -> List[Dict[str, Any]]:
        """Keep source functions visible even when large test files change first."""
        if not functions:
            return []

        def risk(item: Dict[str, Any]) -> float:
            return float(item.get("risk_score", 0.0) or 0.0)

        source_nodes = [
            fn for fn in functions
            if not fn.get("is_test") and fn.get("kind") in ("Function", "Class")
        ]
        test_nodes = [fn for fn in functions if fn not in source_nodes]
        ordered = sorted(source_nodes, key=risk, reverse=True)
        ordered.extend(sorted(test_nodes, key=risk, reverse=True))
        return ordered[:limit]

    def _fallback_changed_functions(
        self,
        normalized_files: List[str],
        normalized_ranges: Dict[str, List[Tuple[int, int]]],
    ) -> List[Dict[str, Any]]:
        """Map changed ranges to nodes directly, with a small line-window fallback."""
        from code_review_graph.changes import compute_risk_score, node_to_dict

        selected: List[Any] = []
        seen: Set[str] = set()

        for file_path in normalized_files:
            try:
                nodes = [
                    node for node in self.store.get_nodes_by_file(file_path)
                    if node.kind in ("Function", "Test", "Class")
                ]
            except Exception:
                nodes = []

            ranges = normalized_ranges.get(file_path, [])
            for node in nodes:
                if node.qualified_name in seen:
                    continue
                if self._node_overlaps_ranges(node, ranges, margin=0):
                    selected.append(node)
                    seen.add(node.qualified_name)

            # If exact overlap failed due stale line numbers, include nearby nodes.
            if not any(node.file_path == file_path for node in selected):
                for node in nodes:
                    if node.qualified_name in seen:
                        continue
                    if self._node_overlaps_ranges(node, ranges, margin=20):
                        selected.append(node)
                        seen.add(node.qualified_name)

        formatted = []
        for node in selected[:10]:
            item = node_to_dict(node)
            item["risk_score"] = compute_risk_score(self.store, node)
            formatted.append(item)
        return formatted

    def _node_overlaps_ranges(
        self,
        node: Any,
        ranges: List[Tuple[int, int]],
        margin: int = 0,
    ) -> bool:
        if not ranges:
            return True
        if node.line_start is None or node.line_end is None:
            return False
        for start, end in ranges:
            if node.line_start <= end + margin and node.line_end >= start - margin:
                return True
        return False

    def _format_flows(self, flows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "name": flow.get("name", ""),
                "entry_point": flow.get("entry_point", ""),
                "nodes_count": flow.get("node_count", 0),
                "criticality": flow.get("criticality", 0),
            }
            for flow in flows
        ]

    def _format_test_gaps(self, gaps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "name": gap.get("name", ""),
                "file": self._display_path(gap.get("file", "")),
                "line_start": gap.get("line_start"),
                "line_end": gap.get("line_end"),
            }
            for gap in gaps
        ]

    def _format_priorities(self, priorities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "name": item.get("name", ""),
                "file": self._display_path(item.get("file_path", "")),
                "line_start": item.get("line_start"),
                "line_end": item.get("line_end"),
                "risk_score": round(item.get("risk_score", 0.0), 4),
            }
            for item in priorities
        ]

    def _build_related_context(self, changed_functions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Return a compact caller/callee summary for repo-scope reasoning."""
        related: List[Dict[str, Any]] = []
        seen: Set[str] = set()

        for fn in changed_functions[:5]:
            qn = fn.get("qualified_name", "")
            for relation, incoming in (("caller", True), ("callee", False)):
                for node in self._get_related_nodes(qn, incoming=incoming, limit=3):
                    key = f"{relation}:{node.get('qualified_name')}"
                    if key in seen:
                        continue
                    seen.add(key)
                    related.append({"relation": relation, **node})

        return related[:20]

    def _get_related_nodes(
        self,
        qualified_name: str,
        incoming: bool,
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not qualified_name:
            return []

        try:
            edges = (
                self.store.get_edges_by_target(qualified_name)
                if incoming
                else self.store.get_edges_by_source(qualified_name)
            )
        except Exception:
            return []

        result: List[Dict[str, Any]] = []
        seen: Set[str] = set()
        for edge in edges:
            if edge.kind != "CALLS":
                continue
            qn = edge.source_qualified if incoming else edge.target_qualified
            if qn in seen:
                continue
            seen.add(qn)
            node = self.store.get_node(qn)
            result.append(self._node_summary(node, qn))
            if len(result) >= limit:
                break

        return result

    def _get_tests(self, qualified_name: str, limit: int) -> List[Dict[str, Any]]:
        if not qualified_name:
            return []
        try:
            tests = self.store.get_transitive_tests(qualified_name, max_depth=1)
        except Exception:
            return []
        return [
            {
                "name": test.get("name", ""),
                "qualified_name": test.get("qualified_name", ""),
                "file": self._display_path(test.get("file_path", "")),
                "kind": test.get("kind", "Test"),
                "indirect": test.get("indirect", False),
            }
            for test in tests[:limit]
        ]

    def _node_summary(self, node: Any, qualified_name: str) -> Dict[str, Any]:
        if not node:
            return {
                "name": qualified_name.rsplit("::", 1)[-1],
                "qualified_name": qualified_name,
                "file": "",
                "line_start": None,
                "line_end": None,
                "kind": "",
            }

        return {
            "name": node.name,
            "qualified_name": node.qualified_name,
            "file": self._display_path(node.file_path),
            "line_start": node.line_start,
            "line_end": node.line_end,
            "kind": node.kind,
        }

    def _display_path(self, path: str) -> str:
        """Convert absolute graph paths into compact repo-relative paths."""
        normalized = (path or "").replace("\\", "/")
        for marker in (
            "/packages/",
            "/evals/",
            "/docs/",
            "/scripts/",
            "/integration-tests/",
            "/benchmark/",
        ):
            if marker in normalized:
                return f"{marker.strip('/')}/{normalized.split(marker, 1)[1]}"
        return normalized

