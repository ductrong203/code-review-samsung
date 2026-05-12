import React, { useState } from "react";
import "../styles/ReviewComment.css";

const CATEGORY_MAP = {
  "Code Defect": { key: "defect", icon: "bug", label: "Defect" },
  "Security Vulnerability": { key: "security", icon: "shield", label: "Security" },
  Performance: { key: "performance", icon: "gauge", label: "Performance" },
  "Maintainability and Readability": {
    key: "maintainability",
    icon: "book",
    label: "Maintainability",
  },
};

const SEVERITY_MAP = {
  critical: { color: "#d92d20", bg: "#fff1f0", label: "CRITICAL" },
  high: { color: "#c2410c", bg: "#fff7ed", label: "HIGH" },
  medium: { color: "#a16207", bg: "#fefce8", label: "MEDIUM" },
  low: { color: "#0b5cff", bg: "#eef5ff", label: "LOW" },
  info: { color: "#475569", bg: "#f8fafc", label: "INFO" },
};

const CONTEXT_SCOPE_LABELS = {
  diff: "Issue visible from changed lines only",
  file: "Needs full-file context to judge",
  repo: "Needs cross-file / repo context",
};

function OutlineIcon({ name }) {
  const common = {
    width: 15,
    height: 15,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true",
  };

  const paths = {
    bug: (
      <>
        <path d="M8 2l2 3h4l2-3" />
        <path d="M12 5v17" />
        <path d="M8 8H5" />
        <path d="M19 8h-3" />
        <path d="M7 13H4" />
        <path d="M20 13h-3" />
        <path d="M8 18H5" />
        <path d="M19 18h-3" />
        <path d="M8 5h8v10a4 4 0 0 1-8 0V5z" />
      </>
    ),
    shield: <path d="M12 3l7 3v5c0 5-3.2 8.7-7 10-3.8-1.3-7-5-7-10V6l7-3z" />,
    gauge: (
      <>
        <path d="M4 14a8 8 0 1 1 16 0" />
        <path d="M12 14l4-4" />
        <path d="M6.5 18h11" />
      </>
    ),
    book: (
      <>
        <path d="M5 4h7a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4z" />
        <path d="M15 7h4v13h-4" />
      </>
    ),
    clipboard: (
      <>
        <path d="M9 4h6l1 2h3v15H5V6h3l1-2z" />
        <path d="M9 11h6" />
        <path d="M9 15h4" />
      </>
    ),
    target: (
      <>
        <circle cx="12" cy="12" r="8" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
    lightbulb: (
      <>
        <path d="M9 18h6" />
        <path d="M10 22h4" />
        <path d="M8 14a6 6 0 1 1 8 0c-1 1-1 2-1 4H9c0-2 0-3-1-4z" />
      </>
    ),
  };

  return (
    <svg className="outline-icon" {...common}>
      {paths[name] || paths.clipboard}
    </svg>
  );
}

function detectCategory(note) {
  const lower = (note || "").toLowerCase();
  if (lower.includes("[security") || lower.includes("security vulnerability")) return "Security Vulnerability";
  if (lower.includes("[defect") || lower.includes("code defect") || lower.includes("[bug")) return "Code Defect";
  if (lower.includes("[performance") || lower.includes("performance")) return "Performance";
  return "Maintainability and Readability";
}

function ConfidenceBar({ value }) {
  const pct = Math.round((value || 0) * 100);
  const color = pct >= 80 ? "#0b5cff" : pct >= 50 ? "#a16207" : "#d92d20";

  return (
    <div className="confidence-bar" title={`Confidence: ${pct}%`}>
      <div className="confidence-bar__track">
        <div className="confidence-bar__fill" style={{ width: `${pct}%`, background: color }} />
      </div>
      <span className="confidence-bar__label">{pct}%</span>
    </div>
  );
}

function parseReviewNote(note) {
  const text = (note || "").trim();
  if (!text) return [];

  const markerRe = /\*\*\[([^\]]+)\]\*\*/g;
  const matches = [...text.matchAll(markerRe)];
  if (!matches.length) {
    return [{ label: "", text }];
  }

  return matches
    .map((match, idx) => {
      const start = match.index + match[0].length;
      const end = idx + 1 < matches.length ? matches[idx + 1].index : text.length;
      return {
        label: match[1].trim(),
        text: text.slice(start, end).trim(),
      };
    })
    .filter((part) => part.text);
}

function ReviewNote({ note }) {
  const parts = parseReviewNote(note);
  if (!parts.length) return null;

  return (
    <div className="review-comment__body">
      {parts.map((part, idx) => (
        <div className="review-comment__note-point" key={idx}>
          {part.label && <div className="review-comment__note-label">{part.label}</div>}
          <div className="review-comment__note-text">{part.text}</div>
        </div>
      ))}
    </div>
  );
}

export default function ReviewComment({ comment }) {
  const [showFix, setShowFix] = useState(false);
  const {
    path,
    from_line,
    to_line,
    note,
    category,
    severity,
    confidence,
    suggested_fix,
    agent_name,
    context_level,
    code_snippet,
  } = comment;

  const resolvedCategory = category || detectCategory(note);
  const catInfo = CATEGORY_MAP[resolvedCategory] || {
    key: "maintainability",
    icon: "clipboard",
    label: resolvedCategory,
  };
  const sevInfo = SEVERITY_MAP[severity] || SEVERITY_MAP.medium;
  const rawScope = (context_level || "").toLowerCase().trim();
  const scopeLabel = CONTEXT_SCOPE_LABELS[rawScope] || (rawScope ? `Detection scope: ${rawScope}` : "");
  const snippetLines = code_snippet ? code_snippet.split("\n") : [];
  const firstErrorIndex = snippetLines.findIndex((line) => /^\s*>/.test(line));
  const snippetStartLine =
    from_line && firstErrorIndex >= 0
      ? from_line - firstErrorIndex
      : from_line || 1;

  return (
    <div className={`review-comment review-comment--severity-${severity || "medium"}`}>
      <div className="review-comment__header">
        <span className={`review-comment__category review-comment__category--${catInfo.key}`}>
          <OutlineIcon name={catInfo.icon} />
          {catInfo.label}
        </span>
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
        <span className="review-comment__file-path">{path || "unknown"}</span>
        <span className="review-comment__lines">L{from_line || "?"}-{to_line || "?"}</span>
      </div>

      {code_snippet && (
        <div className="review-comment__code-snippet">
          <div className="review-comment__code-snippet-label">Affected code</div>
          <pre>
            {snippetLines.map((line, i) => {
              const isError = /^\s*>/.test(line);
              const display = isError ? line.replace(/^\s*> ?/, "") : line;
              const actualLine = snippetStartLine + i;
              return (
                <div key={i} className={`code-line ${isError ? "code-line--error" : ""}`}>
                  <span className="code-line__number">{actualLine}</span>
                  <span className="code-line__text">{display}</span>
                </div>
              );
            })}
          </pre>
        </div>
      )}

      <ReviewNote note={note} />

      <div className="review-comment__footer">
        {confidence != null && <ConfidenceBar value={confidence} />}
        {scopeLabel && (
          <span className="review-comment__context-level" title="Minimum scope needed to recognize this issue.">
            <OutlineIcon name="target" />
            {scopeLabel}
          </span>
        )}
        {agent_name && <span className="review-comment__agent">{agent_name}</span>}
      </div>

      {suggested_fix && (
        <div className="review-comment__fix-section">
          <button className="review-comment__fix-toggle" onClick={() => setShowFix(!showFix)}>
            <OutlineIcon name="lightbulb" />
            {showFix ? "Hide Fix" : "Show Suggested Fix"}
          </button>
          {showFix && <div className="review-comment__fix-content">{suggested_fix}</div>}
        </div>
      )}
    </div>
  );
}
