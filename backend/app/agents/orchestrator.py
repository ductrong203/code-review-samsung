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
from concurrent.futures import ThreadPoolExecutor
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
        confidence_threshold: float = 0.3,
        max_file_chars: int = 10000,
        progress_callback: Optional[Callable[[str, float], None]] = None,
    ):
        self.llm = llm
        self.github = github
        self.parallel = parallel
        self.progress_callback = progress_callback

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

        # Inject code snippets from diff context
        for finding in report.findings:
            if not finding.code_snippet and finding.path and finding.from_line:
                fc = _file_context_for_path(context, finding.path)
                if fc and fc.diff_content:
                    snippet = []
                    lines = fc.diff_content.split('\n')
                    # Very simple diff parser to grab lines around from_line
                    # In a real diff, lines with '+' are additions. We just try to extract
                    # +/- 3 lines around the target line number. 
                    # For a robust implementation, we map diff line numbers, but here
                    # we do a simple substring extraction or format the raw diff.
                    current_new_line = 0
                    for line in lines:
                        if line.startswith('@@'):
                            try:
                                # @@ -a,b +c,d @@
                                parts = line.split(' ')
                                if len(parts) >= 3:
                                    plus_part = parts[2]
                                    current_new_line = int(plus_part.split(',')[0].replace('+', ''))
                            except:
                                pass
                        elif line.startswith('+'):
                            if current_new_line >= finding.from_line - 2 and current_new_line <= (finding.to_line or finding.from_line) + 2:
                                snippet.append(f">{line[1:]}" if current_new_line >= finding.from_line and current_new_line <= (finding.to_line or finding.from_line) else f" {line[1:]}")
                            current_new_line += 1
                        elif line.startswith(' '):
                            if current_new_line >= finding.from_line - 2 and current_new_line <= (finding.to_line or finding.from_line) + 2:
                                snippet.append(f" {line[1:]}")
                            current_new_line += 1
                        elif line.startswith('-'):
                            pass
                    if snippet:
                        finding.code_snippet = '\n'.join(snippet)

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

            for future in futures:
                agent = futures[future]
                try:
                    findings = future.result(timeout=120)  # 2min timeout per agent
                    all_findings.extend(findings)
                    completed += 1
                    progress = 0.3 + (0.5 * completed / total)
                    self._report_progress(
                        f"{agent.name} done — {len(findings)} findings",
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
                all_findings.extend(findings)
                logger.info(f"{agent.name}: {len(findings)} findings")
            except Exception as e:
                logger.error(f"{agent.name} failed: {e}")

        return all_findings
