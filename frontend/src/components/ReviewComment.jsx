import React from 'react';
import '../styles/ReviewComment.css';

/**
 * Detects the category from a review note text.
 */
function detectCategory(note) {
  const lower = note.toLowerCase();
  if (lower.includes('[security') || lower.includes('security vulnerability')) return 'security';
  if (lower.includes('[defect') || lower.includes('code defect') || lower.includes('[bug')) return 'defect';
  if (lower.includes('[performance') || lower.includes('performance')) return 'performance';
  return 'maintainability';
}

/**
 * Label for category badge.
 */
const categoryLabels = {
  defect: 'Defect',
  security: 'Security',
  performance: 'Performance',
  maintainability: 'Maintainability',
};

/**
 * ReviewComment — Renders a single code review comment as a styled card.
 */
export default function ReviewComment({ comment }) {
  const { path, from_line, to_line, note } = comment;
  const category = detectCategory(note || '');

  return (
    <div className="review-comment">
      <div className="review-comment__header">
        <span className={`review-comment__category review-comment__category--${category}`}>
          {categoryLabels[category]}
        </span>
        <span className="review-comment__file-path">{path || 'unknown'}</span>
        <span className="review-comment__lines">
          L{from_line || '?'}–{to_line || '?'}
        </span>
      </div>
      <div className="review-comment__body">
        {note}
      </div>
    </div>
  );
}
