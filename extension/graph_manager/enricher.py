"""
Graph Manager — Enricher that queries graph and produces GraphContext JSON.

Takes a PR's graph database and list of changed files, queries the graph
for risk scores, affected flows, test gaps, and review priorities.

Produces a compact JSON dict (~400 tokens) that gets sent to the server
and injected into agent prompts.
"""
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class GraphContextEnricher:
    """
    Query a graph database to produce a compact GraphContext for review.

    Uses code_review_graph.changes.analyze_changes() to get:
    - changed_functions with risk scores
    - affected_flows
    - test_gaps
    - overall risk score
    - review priorities
    """

    def __init__(self, db_path: str):
        """
        Initialize the enricher with a graph database path.

        Args:
            db_path: Path to the SQLite graph database (e.g., pr_42.db)
        """
        from code_review_graph.graph import GraphStore
        self.store = GraphStore(db_path)

    def close(self):
        """Close the graph store connection."""
        self.store.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def get_context(self, changed_files: list[str]) -> dict[str, Any]:
        """
        Query the graph and produce a compact GraphContext JSON.

        Args:
            changed_files: List of file paths changed in the PR
                           (new_path from diff, excluding deleted files)

        Returns:
            Dict with:
                - changed_functions: top 10 changed functions with risk scores
                - affected_flows: top 5 affected code flows
                - test_gaps: top 10 functions without tests
                - overall_risk: overall risk score (0.0-1.0)
                - review_priorities: top 5 highest-risk items
        """
        from code_review_graph.changes import analyze_changes

        logger.info(f"Enriching context for {len(changed_files)} changed files")

        # Map GitHub paths to whatever path format the graph stored (absolute vs relative, slashes)
        normalized_files = set()
        for f in changed_files:
            matched = self.store.get_files_matching(f)
            if matched:
                logger.debug(f"Matched file '{f}' to: {matched}")
                normalized_files.update(matched)
            else:
                logger.debug(f"No match found for file: {f}, using original path")
                normalized_files.add(f)

        logger.info(f"Normalized files for graph query: {normalized_files}")
        
        # Diagnostic: Check what files exist in the graph
        try:
            all_files_in_graph = self.store.get_all_files()
            logger.debug(f"Total files in graph: {len(all_files_in_graph) if all_files_in_graph else 0}")
            if all_files_in_graph:
                logger.debug(f"Sample files in graph: {list(all_files_in_graph)[:5]}")
        except Exception as e:
            logger.debug(f"Could not list files in graph: {e}")

        try:
            result = analyze_changes(
                store=self.store,
                changed_files=list(normalized_files),
            )
            logger.debug(f"analyze_changes returned: {result}")
        except Exception as e:
            logger.error(f"Error analyzing changes: {e}", exc_info=True)
            result = {}

        # Build compact context (limit arrays to keep tokens low)
        context = {
            "changed_functions": self._format_functions(
                result.get("changed_functions", [])[:10]
            ),
            "affected_flows": self._format_flows(
                result.get("affected_flows", [])[:5]
            ),
            "test_gaps": self._format_test_gaps(
                result.get("test_gaps", [])[:10]
            ),
            "overall_risk": round(result.get("risk_score", 0.0), 4),
            "review_priorities": self._format_priorities(
                result.get("review_priorities", [])[:5]
            ),
        }

        logger.info(
            f"GraphContext: {len(context['changed_functions'])} functions, "
            f"{len(context['affected_flows'])} flows, "
            f"{len(context['test_gaps'])} test gaps, "
            f"risk={context['overall_risk']}"
        )

        return context

    def _format_functions(self, functions: list[dict]) -> list[dict]:
        """Format changed functions into compact dicts."""
        result = []
        for fn in functions:
            # Get callers for this function
            callers = self._get_callers(fn.get("qualified_name", ""))
            is_untested = self._is_untested(fn.get("qualified_name", ""))

            result.append({
                "name": fn.get("name", ""),
                "file": fn.get("file_path", ""),
                "risk_score": round(fn.get("risk_score", 0.0), 4),
                "callers": callers[:5],  # Top 5 callers
                "is_untested": is_untested,
                "kind": fn.get("kind", "Function"),
            })
        return result

    def _format_flows(self, flows: list[dict]) -> list[dict]:
        """Format affected flows into compact dicts."""
        result = []
        for flow in flows:
            result.append({
                "name": flow.get("name", ""),
                "entry_point": flow.get("entry_point", ""),
                "nodes_count": flow.get("node_count", 0),
            })
        return result

    def _format_test_gaps(self, gaps: list[dict]) -> list[dict]:
        """Format test gaps into compact dicts."""
        return [
            {
                "name": g.get("name", ""),
                "file": g.get("file", ""),
                "line_start": g.get("line_start"),
            }
            for g in gaps
        ]

    def _format_priorities(self, priorities: list[dict]) -> list[dict]:
        """Format review priorities into compact dicts."""
        return [
            {
                "name": p.get("name", ""),
                "file": p.get("file_path", ""),
                "risk_score": round(p.get("risk_score", 0.0), 4),
            }
            for p in priorities
        ]

    def _get_callers(self, qualified_name: str) -> list[str]:
        """Get names of functions that call this function."""
        if not qualified_name:
            return []
        try:
            edges = self.store.get_edges_by_target(qualified_name)
            callers = [
                e.source_qualified.split("::")[-1]
                for e in edges
                if e.kind == "CALLS"
            ]
            return list(set(callers))  # Deduplicate
        except Exception:
            return []

    def _is_untested(self, qualified_name: str) -> bool:
        """Check if a function has no TESTED_BY edges."""
        if not qualified_name:
            return True
        try:
            edges = self.store.get_edges_by_target(qualified_name)
            return not any(e.kind == "TESTED_BY" for e in edges)
        except Exception:
            return True
