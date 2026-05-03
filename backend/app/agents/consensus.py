"""
Consensus Engine — Aggregates, deduplicates, scores, and filters findings.

Processes raw findings from multiple specialized agents into a final,
high-quality set of review comments with:
- Deduplication (line overlap + text similarity)
- Confidence boosting (multi-agent agreement)
- False positive filtering (low confidence removal)
- Severity & risk assessment
- Blast radius analysis
"""
import logging
from typing import List, Dict, Tuple
from collections import defaultdict

from app.agents.agent_base import (
    Finding, ReviewReport, Category, Severity,
)

logger = logging.getLogger(__name__)


class ConsensusEngine:
    """
    Aggregates findings from multiple agents into a verified review report.

    Key features:
    - Detects duplicate findings across agents (same file/line range)
    - Boosts confidence when multiple agents flag the same area
    - Filters low-confidence findings to reduce noise
    - Computes overall risk assessment
    """

    def __init__(
        self,
        confidence_threshold: float = 0.3,
        line_overlap_threshold: int = 3,
    ):
        self.confidence_threshold = confidence_threshold
        self.line_overlap_threshold = line_overlap_threshold

    def process(self, all_findings: List[Finding]) -> ReviewReport:
        """
        Process raw findings from all agents into a final ReviewReport.

        Pipeline:
        1. Deduplicate overlapping findings
        2. Boost confidence for multi-agent agreement
        3. Filter low-confidence findings
        4. Sort by severity and confidence
        5. Compute statistics and risk assessment
        """
        if not all_findings:
            return ReviewReport(
                summary="✅ No issues found. The code changes look good!",
                risk_level="low",
            )

        logger.info(f"Consensus: processing {len(all_findings)} raw findings")

        # Step 1: Deduplicate
        deduped = self._deduplicate(all_findings)
        logger.info(f"After dedup: {len(deduped)} findings")

        # Step 2: Filter by confidence
        filtered = [f for f in deduped if f.confidence >= self.confidence_threshold]
        logger.info(f"After confidence filter (>={self.confidence_threshold}): {len(filtered)} findings")

        # Step 3: Sort by severity then confidence
        severity_order = {
            Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2,
            Severity.LOW: 3, Severity.INFO: 4,
        }
        filtered.sort(key=lambda f: (severity_order.get(f.severity, 5), -f.confidence))

        # Step 4: Compute statistics
        cat_counts = defaultdict(int)
        sev_counts = defaultdict(int)
        for f in filtered:
            cat_counts[f.category.value] += 1
            sev_counts[f.severity.value] += 1

        # Step 5: Risk assessment
        risk_level = self._assess_risk(filtered)

        # Step 6: Blast radius
        affected_files = set(f.path for f in filtered if f.path)

        # Step 7: Generate summary
        summary = self._generate_summary(filtered, risk_level, cat_counts)

        return ReviewReport(
            findings=filtered,
            risk_level=risk_level,
            blast_radius_files=len(affected_files),
            blast_radius_functions=0,  # Would need AST analysis
            total_by_category=dict(cat_counts),
            total_by_severity=dict(sev_counts),
            summary=summary,
            agent_metadata={
                "total_raw_findings": len(all_findings),
                "after_dedup": len(deduped),
                "after_filter": len(filtered),
                "agents_used": list(set(f.agent_name for f in all_findings)),
            },
        )

    def _deduplicate(self, findings: List[Finding]) -> List[Finding]:
        """
        Deduplicate findings by detecting overlapping line ranges in the same file.

        When two findings overlap:
        - Keep the one with higher confidence
        - Boost its confidence (multi-agent agreement signal)
        - Merge notes if they provide different information
        """
        if len(findings) <= 1:
            return findings

        # Group by file path
        by_file: Dict[str, List[Finding]] = defaultdict(list)
        for f in findings:
            by_file[f.path].append(f)

        result = []

        for path, file_findings in by_file.items():
            # Sort by from_line for overlap detection
            file_findings.sort(key=lambda f: f.from_line or 0)

            merged = []
            used = set()

            for i, f1 in enumerate(file_findings):
                if i in used:
                    continue

                # Find overlapping findings
                overlapping = [f1]
                for j, f2 in enumerate(file_findings):
                    if j <= i or j in used:
                        continue
                    if self._lines_overlap(f1, f2):
                        overlapping.append(f2)
                        used.add(j)

                if len(overlapping) == 1:
                    merged.append(f1)
                else:
                    # Merge overlapping findings
                    merged_finding = self._merge_findings(overlapping)
                    merged.append(merged_finding)

                used.add(i)

            result.extend(merged)

        return result

    def _lines_overlap(self, f1: Finding, f2: Finding) -> bool:
        """Check if two findings have overlapping line ranges."""
        if f1.path != f2.path:
            return False

        # Handle missing line numbers
        f1_from = f1.from_line or 0
        f1_to = f1.to_line or f1_from
        f2_from = f2.from_line or 0
        f2_to = f2.to_line or f2_from

        # Check overlap with tolerance
        return (
            f1_from <= f2_to + self.line_overlap_threshold and
            f2_from <= f1_to + self.line_overlap_threshold
        )

    def _merge_findings(self, findings: List[Finding]) -> Finding:
        """
        Merge overlapping findings, keeping the best information.

        - Use the highest severity
        - Boost confidence (agreement signal)
        - Combine notes from different categories
        """
        # Sort by confidence descending
        findings.sort(key=lambda f: -f.confidence)
        primary = findings[0]

        # Severity: use the highest
        severity_order = {
            Severity.CRITICAL: 0, Severity.HIGH: 1, Severity.MEDIUM: 2,
            Severity.LOW: 3, Severity.INFO: 4,
        }
        highest_severity = min(findings, key=lambda f: severity_order.get(f.severity, 5))

        # Confidence boost: each additional agent agreeing adds 0.1
        boosted_confidence = min(1.0, primary.confidence + 0.1 * (len(findings) - 1))

        # Combine notes if from different categories
        categories_seen = set()
        combined_notes = []
        for f in findings:
            if f.category not in categories_seen:
                prefix = f"**[{f.category.value}]** "
                combined_notes.append(prefix + f.note)
                categories_seen.add(f.category)
            elif f.note not in combined_notes:
                # Same category but different insight
                combined_notes.append(f.note)

        # Combine suggested fixes
        fixes = [f.suggested_fix for f in findings if f.suggested_fix]
        combined_fix = fixes[0] if fixes else ""

        # Use the widest line range
        all_from = [f.from_line for f in findings if f.from_line is not None]
        all_to = [f.to_line for f in findings if f.to_line is not None]

        return Finding(
            path=primary.path,
            from_line=min(all_from) if all_from else None,
            to_line=max(all_to) if all_to else None,
            category=primary.category,
            severity=highest_severity.severity,
            confidence=boosted_confidence,
            note="\n\n".join(combined_notes),
            context_level=primary.context_level,
            side=primary.side,
            suggested_fix=combined_fix,
            agent_name=", ".join(set(f.agent_name for f in findings)),
            consensus_score=boosted_confidence,
        )

    def _assess_risk(self, findings: List[Finding]) -> str:
        """
        Assess overall risk level based on findings.

        Factors:
        - Number and severity of findings
        - Presence of critical/high severity issues
        - Security vulnerabilities weight more heavily
        """
        if not findings:
            return "low"

        severity_weights = {
            Severity.CRITICAL: 10,
            Severity.HIGH: 5,
            Severity.MEDIUM: 2,
            Severity.LOW: 1,
            Severity.INFO: 0,
        }

        # Security findings get extra weight
        total_score = 0
        for f in findings:
            weight = severity_weights.get(f.severity, 0)
            if f.category == Category.SECURITY:
                weight *= 1.5
            total_score += weight * f.confidence

        # Critical findings always bump to at least "high"
        has_critical = any(f.severity == Severity.CRITICAL for f in findings)
        has_security_high = any(
            f.category == Category.SECURITY and f.severity in (Severity.CRITICAL, Severity.HIGH)
            for f in findings
        )

        if has_critical or total_score >= 30:
            return "critical"
        elif has_security_high or total_score >= 15:
            return "high"
        elif total_score >= 5:
            return "medium"
        else:
            return "low"

    def _generate_summary(
        self,
        findings: List[Finding],
        risk_level: str,
        cat_counts: Dict[str, int],
    ) -> str:
        """Generate a human-readable review summary."""
        if not findings:
            return "✅ No issues found. The code changes look good!"

        risk_emoji = {
            "critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"
        }

        parts = [
            f"## 🔍 Code Review — Found {len(findings)} issue(s)\n",
            f"**Risk Level:** {risk_emoji.get(risk_level, '⚪')} {risk_level.upper()}\n",
        ]

        # Category breakdown
        if cat_counts:
            parts.append("**Issues by Category:**")
            cat_emojis = {
                "Code Defect": "🐛",
                "Security Vulnerability": "🔒",
                "Performance": "⚡",
                "Maintainability and Readability": "📖",
            }
            for cat, count in sorted(cat_counts.items()):
                emoji = cat_emojis.get(cat, "📋")
                parts.append(f"- {emoji} {cat}: {count}")
            parts.append("")

        return "\n".join(parts)
