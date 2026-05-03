import React from 'react';
import ReviewComment from './ReviewComment';
import '../styles/ChatMessage.css';

/**
 * Minimal markdown-like renderer for chat messages.
 * Handles bold, code, headings, lists, and line breaks.
 */
function renderMarkdown(text) {
  if (!text) return null;

  const lines = text.split('\n');
  const elements = [];
  let listItems = [];

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`list-${elements.length}`}>
          {listItems.map((item, i) => (
            <li key={i} dangerouslySetInnerHTML={{ __html: inlineFormat(item) }} />
          ))}
        </ul>
      );
      listItems = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Headings
    if (line.startsWith('## ')) {
      flushList();
      elements.push(<h2 key={i}>{line.slice(3)}</h2>);
    } else if (line.startsWith('### ')) {
      flushList();
      elements.push(<h3 key={i} dangerouslySetInnerHTML={{ __html: inlineFormat(line.slice(4)) }} />);
    }
    // Horizontal rule
    else if (line.trim() === '---') {
      flushList();
      elements.push(<hr key={i} />);
    }
    // List items
    else if (line.startsWith('- ')) {
      listItems.push(line.slice(2));
    }
    // Empty lines
    else if (line.trim() === '') {
      flushList();
    }
    // Regular text
    else {
      flushList();
      elements.push(
        <p key={i} dangerouslySetInnerHTML={{ __html: inlineFormat(line) }} />
      );
    }
  }
  flushList();

  return elements;
}

/**
 * Inline formatting: bold, code, links.
 */
function inlineFormat(text) {
  return text
    .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
    .replace(/`(.*?)`/g, '<code>$1</code>');
}

/**
 * ChatMessage — Renders a single chat message (user or bot).
 */
export default function ChatMessage({ message }) {
  const { role, content, comments, prUrl, metadata, isError } = message;
  const isUser = role === 'user';

  return (
    <div className={`chat-message chat-message--${role} ${isError ? 'chat-message--error' : ''}`}>
      <div className={`chat-message__avatar chat-message__avatar--${role}`}>
        {isUser ? '👤' : '🔍'}
      </div>
      <div className="chat-message__body">
        {/* PR badge */}
        {prUrl && metadata && (
          <div className="chat-message__pr-badge">
            📋 <a href={prUrl} target="_blank" rel="noopener noreferrer">
              {metadata.title || prUrl}
            </a>
            {metadata.changed_files > 0 && (
              <span>• {metadata.changed_files} files • +{metadata.additions} −{metadata.deletions}</span>
            )}
          </div>
        )}

        {/* Message content */}
        <div className="chat-message__content">
          {renderMarkdown(content)}
        </div>

        {/* Review comment cards */}
        {comments && comments.length > 0 && (
          <div className="review-comments">
            {comments.map((comment, idx) => (
              <ReviewComment key={idx} comment={comment} />
            ))}
          </div>
        )}

        <div className="chat-message__timestamp">
          {message.timestamp?.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>
    </div>
  );
}
