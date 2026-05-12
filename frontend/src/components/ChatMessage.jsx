import React from "react";
import ReviewComment from "./ReviewComment";
import ReviewSummary from "./ReviewSummary";
import "../styles/ChatMessage.css";

function OutlineIcon({ name }) {
  const common = {
    width: 17,
    height: 17,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round",
    strokeLinejoin: "round",
    "aria-hidden": "true",
  };
  const paths = {
    user: <path d="M20 21a8 8 0 0 0-16 0M12 13a5 5 0 1 0 0-10 5 5 0 0 0 0 10z" />,
    bot: <path d="M7 8h10v8H7zM12 4v4M9 12h.01M15 12h.01M9 20h6M5 10H3M21 10h-2" />,
    pr: <path d="M7 7a3 3 0 1 0 0 6h10a3 3 0 1 0 0-6H7zM8 12l8-4" />,
  };
  return <svg {...common}>{paths[name]}</svg>;
}

function renderMarkdown(text) {
  if (!text) return null;

  const lines = text.split("\n");
  const elements = [];
  let listItems = [];

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`list-${elements.length}`}>
          {listItems.map((item, i) => (
            <li key={i} dangerouslySetInnerHTML={{ __html: inlineFormat(item) }} />
          ))}
        </ul>,
      );
      listItems = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    if (line.startsWith("## ")) {
      flushList();
      elements.push(<h2 key={i}>{line.slice(3)}</h2>);
    } else if (line.startsWith("### ")) {
      flushList();
      elements.push(<h3 key={i} dangerouslySetInnerHTML={{ __html: inlineFormat(line.slice(4)) }} />);
    } else if (line.trim() === "---") {
      flushList();
      elements.push(<hr key={i} />);
    } else if (line.startsWith("- ")) {
      listItems.push(line.slice(2));
    } else if (line.trim() === "") {
      flushList();
    } else {
      flushList();
      elements.push(<p key={i} dangerouslySetInnerHTML={{ __html: inlineFormat(line) }} />);
    }
  }
  flushList();

  return elements;
}

function inlineFormat(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/`(.*?)`/g, "<code>$1</code>");
}

function stripLegacyIcons(text) {
  return (text || "")
    .replace(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/gu, "")
    .replace(/—/g, "-")
    .replace(/[ \t]{2,}/g, " ");
}

export default function ChatMessage({ message }) {
  const {
    role,
    content,
    comments,
    prUrl,
    metadata,
    isError,
    riskAssessment,
    categoryStats,
    agentMetadata,
  } = message;
  const isUser = role === "user";

  return (
    <div className={`chat-message chat-message--${role} ${isError ? "chat-message--error" : ""}`}>
      <div className={`chat-message__avatar chat-message__avatar--${role}`}>
        {isUser ? <OutlineIcon name="user" /> : <OutlineIcon name="bot" />}
      </div>
      <div className="chat-message__body">
        {prUrl && metadata && (
          <div className="chat-message__pr-badge">
            <OutlineIcon name="pr" />
            <a href={prUrl} target="_blank" rel="noopener noreferrer">
              {metadata.title || prUrl}
            </a>
            {metadata.changed_files > 0 && (
              <span>| {metadata.changed_files} files | +{metadata.additions} -{metadata.deletions}</span>
            )}
          </div>
        )}

        {(riskAssessment || categoryStats) && (
          <ReviewSummary
            riskAssessment={riskAssessment}
            categoryStats={categoryStats}
            agentMetadata={agentMetadata}
          />
        )}

        <div className="chat-message__content">{renderMarkdown(stripLegacyIcons(content))}</div>

        {comments && comments.length > 0 && (
          <div className="review-comments">
            {comments.map((comment, idx) => (
              <ReviewComment key={idx} comment={comment} />
            ))}
          </div>
        )}

        <div className="chat-message__timestamp">
          {message.timestamp?.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
        </div>
      </div>
    </div>
  );
}
