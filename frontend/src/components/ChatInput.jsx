import React, { useState, useRef, useEffect } from 'react';
import '../styles/ChatInput.css';

/**
 * ChatInput — Chat input bar with auto-resize textarea and send button.
 */
export default function ChatInput({ onSend, isLoading }) {
  const [text, setText] = useState('');
  const textareaRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = 'auto';
      textarea.style.height = Math.min(textarea.scrollHeight, 120) + 'px';
    }
  }, [text]);

  const handleSend = () => {
    if (text.trim() && !isLoading) {
      onSend(text);
      setText('');
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-input" id="chat-input">
      <div className="chat-input__wrapper">
        <textarea
          ref={textareaRef}
          className="chat-input__textarea"
          placeholder="Paste a GitHub PR URL to review... (e.g. https://github.com/owner/repo/pull/123)"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={isLoading}
          rows={1}
          id="chat-input-textarea"
        />
        <button
          className="chat-input__send-btn"
          onClick={handleSend}
          disabled={!text.trim() || isLoading}
          title="Send message"
          id="send-btn"
        >
          ➤
        </button>
      </div>
      <div className="chat-input__hint">
        Press Enter to send • Shift+Enter for new line
      </div>
    </div>
  );
}
