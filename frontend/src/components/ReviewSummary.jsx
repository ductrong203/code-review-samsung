import React from "react";
import "../styles/ReviewSummary.css";

const RISK_CONFIG = {
  critical: { icon: "alert", color: "#d92d20", bg: "#fff1f0" },
  high: { icon: "alert", color: "#c2410c", bg: "#fff7ed" },
  medium: { icon: "activity", color: "#a16207", bg: "#fefce8" },
  low: { icon: "check", color: "#0b5cff", bg: "#eef5ff" },
};

const CATEGORY_ICONS = {
  "Code Defect": "bug",
  "Security Vulnerability": "shield",
  Performance: "gauge",
  "Maintainability and Readability": "book",
};

function OutlineIcon({ name }) {
  const common = {
    width: 18,
    height: 18,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true",
  };
  const paths = {
    check: <path d="M20 6L9 17l-5-5" />,
    alert: (
      <>
        <path d="M12 3l10 18H2L12 3z" />
        <path d="M12 9v5" />
        <path d="M12 18h.01" />
      </>
    ),
    activity: <path d="M4 12h4l2-6 4 12 2-6h4" />,
    bug: <path d="M8 5h8v10a4 4 0 0 1-8 0V5zM8 2l2 3h4l2-3M4 13h4M16 13h4" />,
    shield: <path d="M12 3l7 3v5c0 5-3.2 8.7-7 10-3.8-1.3-7-5-7-10V6l7-3z" />,
    gauge: <path d="M4 14a8 8 0 1 1 16 0M12 14l4-4M6.5 18h11" />,
    book: <path d="M5 4h7a3 3 0 0 1 3 3v13H8a3 3 0 0 1-3-3V4zM15 7h4v13h-4" />,
    clock: <path d="M12 8v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0z" />,
  };

  return <svg className="review-summary__icon" {...common}>{paths[name] || paths.activity}</svg>;
}

export default function ReviewSummary({ riskAssessment, categoryStats, agentMetadata }) {
  if (!riskAssessment && !categoryStats) return null;

  const risk = riskAssessment || {};
  const stats = categoryStats || {};
  const meta = agentMetadata || {};
  const riskCfg = RISK_CONFIG[risk.level] || RISK_CONFIG.low;
  const totalIssues = Object.values(stats.total_by_category || {}).reduce((a, b) => a + b, 0);

  return (
    <div className="review-summary">
      <div className="review-summary__risk" style={{ background: riskCfg.bg, borderColor: `${riskCfg.color}33` }}>
        <span className="review-summary__risk-mark" style={{ color: riskCfg.color }}>
          <OutlineIcon name={riskCfg.icon} />
        </span>
        <div className="review-summary__risk-info">
          <span className="review-summary__risk-level" style={{ color: riskCfg.color }}>
            {(risk.level || "low").toUpperCase()} RISK
          </span>
          <span className="review-summary__risk-detail">
            {totalIssues} issue{totalIssues !== 1 ? "s" : ""} found
            {risk.blast_radius_files > 0 && ` | ${risk.blast_radius_files} file${risk.blast_radius_files !== 1 ? "s" : ""} affected`}
          </span>
        </div>
      </div>

      {stats.total_by_category && Object.keys(stats.total_by_category).length > 0 && (
        <div className="review-summary__categories">
          {Object.entries(stats.total_by_category).map(([cat, count]) => (
            <div key={cat} className="review-summary__cat-row">
              <span className="review-summary__cat-label">
                <OutlineIcon name={CATEGORY_ICONS[cat] || "activity"} />
                {cat}
              </span>
              <div className="review-summary__cat-bar">
                <div className="review-summary__cat-fill" style={{ width: `${Math.min(100, (count / Math.max(totalIssues, 1)) * 100)}%` }} />
              </div>
              <span className="review-summary__cat-count">{count}</span>
            </div>
          ))}
        </div>
      )}

      {stats.total_by_severity && Object.keys(stats.total_by_severity).length > 0 && (
        <div className="review-summary__severity-pills">
          {Object.entries(stats.total_by_severity).map(([sev, count]) => {
            const sevCfg = RISK_CONFIG[sev] || { color: "#475569", bg: "#f8fafc" };
            return (
              <span key={sev} className="review-summary__sev-pill" style={{ background: sevCfg.bg, color: sevCfg.color }}>
                {sev.toUpperCase()}: {count}
              </span>
            );
          })}
        </div>
      )}

      {meta.review_time_seconds > 0 && (
        <div className="review-summary__meta">
          <OutlineIcon name="clock" />
          <span>{meta.review_time_seconds}s</span>
          {meta.agents_used?.length > 0 && <span>{meta.agents_used.length} agents</span>}
          {meta.files_analyzed > 0 && <span>{meta.files_analyzed} files</span>}
          {meta.language && <span>{meta.language}</span>}
        </div>
      )}
    </div>
  );
}
