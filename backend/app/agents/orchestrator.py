"""
Review Orchestrator — Coordinates the multi-agent code review pipeline.

Pipeline:
1. Context Gathering → Build rich ReviewContext
2. Analysis → Dispatch to 4 specialized agents (parallel or sequential)
3. Consensus → Deduplicate, score, filter findings
4. Output → Generate structured ReviewReport

Supports both parallel execution (asyncio) and sequential fallback.
"""
import time
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional, Callable

from langchain_core.language_models.chat_models import BaseChatModel

from app.agents.agent_base import (
    ReviewAgent,
    Finding,
    FileContext,
    ContextLevel,
    ReviewContext,
    ReviewReport,
)
from app.agents.defect_agent import DefectAgent
from app.agents.security_agent import SecurityAgent
from app.agents.performance_agent import PerformanceAgent
from app.agents.maintainability_agent import MaintainabilityAgent
from app.agents.consensus import ConsensusEngine
from app.services.context_builder import ContextBuilder
from app.services.github_service import GitHubService

logger = logging.getLogger(__name__)


def _normalize_repo_path(p: str) -> str:
    """Normalize path for comparison (GitHub / agent output may differ slightly)."""
    if not p:
        return ""
    s = p.replace("\\", "/").strip()
    if s.startswith("./"):
        s = s[2:]
    return s


def _file_context_for_path(
    context: ReviewContext, path: str
) -> Optional[FileContext]:
    """Resolve FileContext for a finding path."""
    want = _normalize_repo_path(path)
    if not want:
        return None
    for fc in context.files:
        fc_path = _normalize_repo_path(fc.path)
        if fc_path == want or want.endswith(fc_path) or fc_path.endswith(want):
            return fc
    return None


def _clean_code_lines(code: str) -> List[str]:
    """Normalize LLM-provided code snippets for matching against diff lines."""
    text = (code or "").strip()
    if not text:
        return []
    if text.startswith("```"):
        parts = text.split("\n")
        if len(parts) >= 3 and parts[-1].strip() == "```":
            text = "\n".join(parts[1:-1])

    lines = []
    for line in text.splitlines():
        cleaned = line.rstrip()
        if cleaned.startswith(("+", ">")):
            cleaned = cleaned[1:].lstrip(" ")
        lines.append(cleaned.rstrip())

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


class ReviewOrchestrator:
    """
    Orchestrates the complete multi-agent code review pipeline.

    Creates and coordinates 4 specialized agents, gathers context,
    runs parallel analysis, and produces a verified review report.
    """

    def __init__(
        self,
        llm: BaseChatModel,
        github: GitHubService,
        parallel: bool = False,  # CHANGED: Default to sequential (was True)
        confidence_threshold: Optional[float] = None,
        max_file_chars: int = 10000,
        progress_callback: Optional[Callable[[str, float], None]] = None,
        finding_callback: Optional[Callable[[Finding], None]] = None,
        graph_callback: Optional[Callable[[dict], None]] = None,
    ):
        self.llm = llm
        self.github = github
        self.parallel = parallel
        self.progress_callback = progress_callback
        self.finding_callback = finding_callback
        self.graph_callback = graph_callback

        # Build agents
        self.agents: List[ReviewAgent] = [
            DefectAgent(llm),
            SecurityAgent(llm),
            PerformanceAgent(llm),
            MaintainabilityAgent(llm),
        ]

        # Build supporting components
        self.context_builder = ContextBuilder(
            github=github,
            max_file_chars=max_file_chars,
        )
        self.consensus = ConsensusEngine(
            confidence_threshold=confidence_threshold,
        )

    def _report_progress(self, stage: str, progress: float):
        """Report progress to callback if available."""
        if self.progress_callback:
            try:
                self.progress_callback(stage, progress)
            except Exception:
                pass
        logger.info(f"Progress: [{progress:.0%}] {stage}")

    def _report_graph_context(self, graph_context: Optional[dict]):
        """Report compact graph stats to streaming clients."""
        if not self.graph_callback:
            return
        graph_context = graph_context or {}
        summary = {
            "changed_functions": len(graph_context.get("changed_functions", []) or []),
            "affected_flows": len(graph_context.get("affected_flows", []) or []),
            "test_gaps": len(graph_context.get("test_gaps", []) or []),
            "review_priorities": len(graph_context.get("review_priorities", []) or []),
            "related_context": len(graph_context.get("related_context", []) or []),
            "overall_risk": graph_context.get("overall_risk", 0.0),
            "error": graph_context.get("_error"),
        }
        try:
            self.graph_callback(summary)
        except Exception:
            pass

    def _report_findings(self, findings: List[Finding]):
        """Report findings as soon as an agent has produced them."""
        if not self.finding_callback:
            return
        for finding in findings:
            try:
                self.finding_callback(finding)
            except Exception:
                pass

    def review(self, pr_url: str,
               graph_context: Optional[dict] = None) -> ReviewReport:
        """
        Run the complete multi-agent review pipeline.

        Args:
            pr_url: GitHub PR URL
            graph_context: Optional graph analysis context from extension

        Returns:
            ReviewReport with all verified findings
        """
        start_time = time.time()
        logger.info(f"{'='*60}")
        logger.info(f"Starting multi-agent review: {pr_url}")
        logger.info(f"Agents: {[a.name for a in self.agents]}")
        logger.info(f"Mode: {'parallel' if self.parallel else 'sequential'}")
        if graph_context:
            logger.info(f"Graph context: provided (risk={graph_context.get('overall_risk', 'N/A')})")
        logger.info(f"{'='*60}")

        # ── Phase 1: Context Gathering ──────────────────────────────
        self._report_progress("📥 Fetching PR data and building context...", 0.1)
        context = self.context_builder.build_context(pr_url, graph_context=graph_context)
        self._report_graph_context(context.graph_context)

        if not context.formatted_diff.strip():
            return ReviewReport(
                summary="⚠️ No code changes found in this PR.",
                risk_level="low",
            )

        # ── Phase 2: Multi-Agent Analysis ───────────────────────────
        self._report_progress("🔍 Running specialized agents...", 0.3)

        if self.parallel:
            all_findings = self._run_agents_parallel(context)
        else:
            all_findings = self._run_agents_sequential(context)

        if graph_context is None:
            before = len(all_findings)
            all_findings = [
                finding for finding in all_findings
                if finding.context_level == ContextLevel.DIFF
            ]
            removed = before - len(all_findings)
            if removed:
                logger.info(
                    "Diff-only baseline: filtered %s file/repo-context findings",
                    removed,
                )

        # ── Phase 3: Consensus & Verification ───────────────────────
        self._report_progress("🔄 Verifying and consolidating findings...", 0.8)
        report = self.consensus.process(all_findings)

        self._inject_code_snippets(report.findings, context)

        # ── Phase 4: Finalize ───────────────────────────────────────
        elapsed = time.time() - start_time
        report.agent_metadata["review_time_seconds"] = round(elapsed, 2)
        report.agent_metadata["pr_url"] = pr_url
        report.agent_metadata["parallel"] = self.parallel
        report.agent_metadata["files_analyzed"] = len(context.files)
        report.agent_metadata["language"] = context.language
        report.agent_metadata["graph_context_used"] = graph_context is not None

        self._report_progress("✅ Review complete!", 1.0)

        logger.info(f"{'='*60}")
        logger.info(f"Review complete in {elapsed:.1f}s")
        logger.info(f"Total findings: {len(report.findings)}")
        logger.info(f"Risk level: {report.risk_level}")
        logger.info(f"{'='*60}")

        return report

    def _inject_code_snippets(
        self,
        findings: List[Finding],
        context: ReviewContext,
    ) -> None:
        """Attach a small changed-code snippet around each finding."""
        for finding in findings:
            if finding.code_snippet or not finding.path:
                continue

            fc = _file_context_for_path(context, finding.path)
            if not fc or not fc.diff_content:
                continue

            target_lines = None
            if finding.affected_code:
                target_lines = self._find_affected_lines(fc, finding.affected_code)
                if target_lines:
                    finding.from_line = min(target_lines)
                    finding.to_line = max(target_lines)

            if not finding.from_line:
                continue

            target_to = finding.to_line or finding.from_line
            if target_lines is None:
                target_lines = set(range(finding.from_line, target_to + 1))

            snippet = self._build_code_snippet(fc, finding.from_line, target_to, target_lines)
            if snippet:
                finding.code_snippet = snippet

    def _find_affected_lines(
        self,
        fc: FileContext,
        affected_code: str,
    ) -> Optional[set[int]]:
        """Find the exact new-file lines that match an affected_code snippet."""
        wanted = _clean_code_lines(affected_code)
        if not wanted:
            return None

        new_lines = []
        current_new_line = 0
        for raw_line in fc.diff_content.split("\n"):
            if raw_line.startswith("@@"):
                try:
                    parts = raw_line.split(" ")
                    if len(parts) >= 3:
                        plus_part = parts[2]
                        current_new_line = int(plus_part.split(",")[0].replace("+", ""))
                except Exception:
                    current_new_line = 0
                continue

            if raw_line.startswith(("+", " ")):
                line_kind = raw_line[0]
                new_lines.append((current_new_line, line_kind, raw_line[1:].rstrip()))
                current_new_line += 1
            elif raw_line.startswith("-"):
                continue

        span_len = len(wanted)
        for idx in range(0, len(new_lines) - span_len + 1):
            candidate = new_lines[idx:idx + span_len]
            candidate_text = [line[2] for line in candidate]
            candidate_stripped = [line.strip() for line in candidate_text]
            wanted_stripped = [line.strip() for line in wanted]
            if candidate_text != wanted and candidate_stripped != wanted_stripped:
                continue
            if not any(line_kind == "+" for _, line_kind, _ in candidate):
                continue
            return {line_no for line_no, _, _ in candidate if line_no}

        return None

    def _build_code_snippet(
        self,
        fc: FileContext,
        target_from: int,
        target_to: int,
        target_lines: set[int],
    ) -> str:
        """Build a display snippet with target lines prefixed by '>'."""
        snippet = []
        current_new_line = 0

        for line in fc.diff_content.split('\n'):
            if line.startswith('@@'):
                try:
                    parts = line.split(' ')
                    if len(parts) >= 3:
                        plus_part = parts[2]
                        current_new_line = int(
                            plus_part.split(',')[0].replace('+', '')
                        )
                except Exception:
                    pass
                continue

            in_window = target_from - 2 <= current_new_line <= target_to + 2
            in_target = current_new_line in target_lines

            if line.startswith('+'):
                if in_window:
                    snippet.append(f">{line[1:]}" if in_target else f" {line[1:]}")
                current_new_line += 1
            elif line.startswith(' '):
                if in_window:
                    snippet.append(f">{line[1:]}" if in_target else f" {line[1:]}")
                current_new_line += 1

        return '\n'.join(snippet)

    def _run_agents_parallel(self, context: ReviewContext) -> List[Finding]:
        """Run all agents in parallel using ThreadPoolExecutor."""
        all_findings: List[Finding] = []

        def run_agent(agent: ReviewAgent) -> List[Finding]:
            try:
                return agent.analyze(context)
            except Exception as e:
                logger.error(f"Agent {agent.name} failed: {e}")
                return []

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = {
                executor.submit(run_agent, agent): agent
                for agent in self.agents
            }

            completed = 0
            total = len(self.agents)

            for future in as_completed(futures):
                agent = futures[future]
                try:
                    findings = future.result(timeout=120)  # 2min timeout per agent
                    self._inject_code_snippets(findings, context)
                    all_findings.extend(findings)
                    self._report_findings(findings)
                    completed += 1
                    progress = 0.3 + (0.5 * completed / total)
                    self._report_progress(
                        f"{agent.name} done - {len(findings)} findings",
                        progress,
                    )
                except Exception as e:
                    completed += 1
                    logger.error(f"Agent {agent.name} timed out or failed: {e}")

        return all_findings

    def _run_agents_sequential(self, context: ReviewContext) -> List[Finding]:
        """Run all agents sequentially (fallback for debugging)."""
        all_findings: List[Finding] = []

        for i, agent in enumerate(self.agents):
            progress = 0.3 + (0.5 * i / len(self.agents))
            self._report_progress(f"Running {agent.name}...", progress)

            try:
                findings = agent.analyze(context)
                self._inject_code_snippets(findings, context)
                all_findings.extend(findings)
                self._report_findings(findings)
                done_progress = 0.3 + (0.5 * (i + 1) / len(self.agents))
                self._report_progress(
                    f"{agent.name} done - {len(findings)} findings",
                    done_progress,
                )
                logger.info(f"{agent.name}: {len(findings)} findings")
            except Exception as e:
                logger.error(f"{agent.name} failed: {e}")
                done_progress = 0.3 + (0.5 * (i + 1) / len(self.agents))
                self._report_progress(
                    f"{agent.name} failed - 0 findings",
                    done_progress,
                )

        return all_findings
