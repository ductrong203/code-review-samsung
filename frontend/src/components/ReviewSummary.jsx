import React from 'react';
import '../styles/ReviewSummary.css';

/**
 * Risk level visual configurations.
 */
const RISK_CONFIG = {
  critical: { emoji: '🔴', color: '#f85149', bg: 'rgba(248,81,73,0.12)' },
  high: { emoji: '🟠', color: '#f0883e', bg: 'rgba(240,136,62,0.12)' },
  medium: { emoji: '🟡', color: '#d29922', bg: 'rgba(210,153,34,0.12)' },
  low: { emoji: '🟢', color: '#3fb950', bg: 'rgba(63,185,80,0.12)' },
};

const CATEGORY_EMOJIS = {
  'Code Defect': '🐛',
  'Security Vulnerability': '🔒',
  'Performance': '⚡',
  'Maintainability and Readability': '📖',
};

/**
 * ReviewSummary — Displays a structured overview of the review results.
 *
 * Shows:
 * - Risk level badge
 * - Blast radius
 * - Category breakdown with progress bars
 * - Agent execution metadata
 */
export default function ReviewSummary({ riskAssessment, categoryStats, agentMetadata }) {
  if (!riskAssessment && !categoryStats) return null;

  const risk = riskAssessment || {};
  const stats = categoryStats || {};
  const meta = agentMetadata || {};

  const riskCfg = RISK_CONFIG[risk.level] || RISK_CONFIG.low;
  const totalIssues = Object.values(stats.total_by_category || {}).reduce((a, b) => a + b, 0);

  return (
    <div className="review-summary">
      {/* Risk Badge */}
      <div className="review-summary__risk" style={{ background: riskCfg.bg, borderColor: riskCfg.color }}>
        <span className="review-summary__risk-emoji">{riskCfg.emoji}</span>
        <div className="review-summary__risk-info">
          <span className="review-summary__risk-level" style={{ color: riskCfg.color }}>
            {(risk.level || 'low').toUpperCase()} RISK
          </span>
          <span className="review-summary__risk-detail">
            {totalIssues} issue{totalIssues !== 1 ? 's' : ''} found
            {risk.blast_radius_files > 0 && ` • ${risk.blast_radius_files} file${risk.blast_radius_files !== 1 ? 's' : ''} affected`}
          </span>
        </div>
      </div>

      {/* Category Breakdown */}
      {stats.total_by_category && Object.keys(stats.total_by_category).length > 0 && (
        <div className="review-summary__categories">
          {Object.entries(stats.total_by_category).map(([cat, count]) => (
            <div key={cat} className="review-summary__cat-row">
              <span className="review-summary__cat-label">
                {CATEGORY_EMOJIS[cat] || '📋'} {cat}
              </span>
              <div className="review-summary__cat-bar">
                <div
                  className="review-summary__cat-fill"
                  style={{ width: `${Math.min(100, (count / Math.max(totalIssues, 1)) * 100)}%` }}
                />
              </div>
              <span className="review-summary__cat-count">{count}</span>
            </div>
          ))}
        </div>
      )}

      {/* Severity Breakdown */}
      {stats.total_by_severity && Object.keys(stats.total_by_severity).length > 0 && (
        <div className="review-summary__severity-pills">
          {Object.entries(stats.total_by_severity).map(([sev, count]) => {
            const sevCfg = RISK_CONFIG[sev] || { color: '#8b949e', bg: 'rgba(139,148,158,0.15)' };
            return (
              <span
                key={sev}
                className="review-summary__sev-pill"
                style={{ background: sevCfg.bg, color: sevCfg.color }}
              >
                {sev.toUpperCase()}: {count}
              </span>
            );
          })}
        </div>
      )}

      {/* Agent Metadata */}
      {meta.review_time_seconds > 0 && (
        <div className="review-summary__meta">
          ⏱ {meta.review_time_seconds}s
          {meta.agents_used?.length > 0 && ` • ${meta.agents_used.length} agents`}
          {meta.files_analyzed > 0 && ` • ${meta.files_analyzed} files`}
          {meta.language && ` • ${meta.language}`}
        </div>
      )}
    </div>
  );
}
