import React, { useState } from 'react';
import '../styles/ReviewComment.css';

/**
 * Category info mappings for icons and display.
 */
const CATEGORY_MAP = {
  'Code Defect': { key: 'defect', icon: '🐛', label: 'Defect' },
  'Security Vulnerability': { key: 'security', icon: '🔒', label: 'Security' },
  'Performance': { key: 'performance', icon: '⚡', label: 'Performance' },
  'Maintainability and Readability': { key: 'maintainability', icon: '📖', label: 'Maintainability' },
};

/**
 * Severity info mappings for display.
 */
const SEVERITY_MAP = {
  critical: { color: '#f85149', bg: 'rgba(248,81,73,0.15)', label: 'CRITICAL' },
  high: { color: '#f0883e', bg: 'rgba(240,136,62,0.15)', label: 'HIGH' },
  medium: { color: '#d29922', bg: 'rgba(210,153,34,0.15)', label: 'MEDIUM' },
  low: { color: '#58a6ff', bg: 'rgba(88,166,255,0.15)', label: 'LOW' },
  info: { color: '#8b949e', bg: 'rgba(139,148,158,0.15)', label: 'INFO' },
};

/**
 * Fallback category detection from note text (backward compatibility).
 */
function detectCategory(note) {
  const lower = (note || '').toLowerCase();
  if (lower.includes('[security') || lower.includes('security vulnerability')) return 'Security Vulnerability';
  if (lower.includes('[defect') || lower.includes('code defect') || lower.includes('[bug')) return 'Code Defect';
  if (lower.includes('[performance') || lower.includes('performance')) return 'Performance';
  return 'Maintainability and Readability';
}

/**
 * Confidence bar component.
 */
function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 80 ? '#3fb950' : pct >= 50 ? '#d29922' : '#f85149';

  return (
    <div className="confidence-bar" title={`Confidence: ${pct}%`}>
      <div className="confidence-bar__track">
        <div
          className="confidence-bar__fill"
          style={{ width: `${pct}%`, background: color }}
        />
      </div>
      <span className="confidence-bar__label">{pct}%</span>
    </div>
  );
}

/**
 * ReviewComment — Renders a single code review finding with full agent metadata.
 *
 * Displays:
 * - Category badge with icon
 * - Severity badge
 * - File path and line numbers
 * - Confidence indicator
 * - Review note
 * - Expandable suggested fix
 * - Agent attribution
 */
export default function ReviewComment({ comment }) {
  const [showFix, setShowFix] = useState(false);

  const { path, from_line, to_line, note, category, severity, confidence, suggested_fix, agent_name, context_level } = comment;

  // Use category from agent data, or detect from note text
  const resolvedCategory = category || detectCategory(note);
  const catInfo = CATEGORY_MAP[resolvedCategory] || { key: 'maintainability', icon: '📋', label: resolvedCategory };
  const sevInfo = SEVERITY_MAP[severity] || SEVERITY_MAP.medium;

  return (
    <div className={`review-comment review-comment--severity-${severity || 'medium'}`}>
      <div className="review-comment__header">
        {/* Category badge */}
        <span className={`review-comment__category review-comment__category--${catInfo.key}`}>
          {catInfo.icon} {catInfo.label}
        </span>

        {/* Severity badge */}
        <span
          className="review-comment__severity"
          style={{
            background: sevInfo.bg,
            color: sevInfo.color,
            border: `1px solid ${sevInfo.color}33`,
          }}
        >
          {sevInfo.label}
        </span>

        {/* File path */}
        <span className="review-comment__file-path">{path || 'unknown'}</span>

        {/* Line numbers */}
        <span className="review-comment__lines">
          L{from_line || '?'}–{to_line || '?'}
        </span>
      </div>

      {/* Note body */}
      <div className="review-comment__body">
        {note}
      </div>

      {/* Footer with confidence, context level, agent */}
      <div className="review-comment__footer">
        {confidence != null && (
          <ConfidenceBar value={confidence} />
        )}
        {context_level && (
          <span className="review-comment__context-level" title="Context level needed to detect this issue">
            📍 {context_level}
          </span>
        )}
        {agent_name && (
          <span className="review-comment__agent" title="Agent(s) that detected this issue">
            {agent_name}
          </span>
        )}
      </div>

      {/* Suggested fix (expandable) */}
      {suggested_fix && (
        <div className="review-comment__fix-section">
          <button
            className="review-comment__fix-toggle"
            onClick={() => setShowFix(!showFix)}
          >
            💡 {showFix ? 'Hide Fix' : 'Show Suggested Fix'}
          </button>
          {showFix && (
            <div className="review-comment__fix-content">
              {suggested_fix}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
