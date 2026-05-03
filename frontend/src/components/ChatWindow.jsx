import React from 'react';
import ChatMessage from './ChatMessage';
import LoadingDots from './LoadingDots';
import '../styles/ChatWindow.css';

/**
 * ChatWindow — Scrollable container for chat messages.
 */
export default function ChatWindow({ messages, isLoading, messagesEndRef }) {
  return (
    <div className="chat-window" id="chat-window">
      {messages.length === 0 && (
        <div className="chat-window__empty">
          <div className="chat-window__empty-title">How can I help with your pull request?</div>
          <div className="chat-window__empty-hint">
            Paste a PR URL, then ask for code quality, security, performance, or maintainability feedback.
          </div>
          <div className="chat-window__suggestions">
            <div className="chat-window__suggestion">Review this PR for critical bugs and security risks</div>
            <div className="chat-window__suggestion">Summarize important changes file by file</div>
            <div className="chat-window__suggestion">Give me a prioritized action checklist before merge</div>
          </div>
        </div>
      )}

      {messages.map((msg) => (
        <ChatMessage key={msg.id} message={msg} />
      ))}

      {isLoading && <LoadingDots />}

      <div ref={messagesEndRef} />
    </div>
  );
}
