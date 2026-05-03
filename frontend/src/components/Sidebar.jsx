import React from 'react';
import '../styles/Sidebar.css';

export default function Sidebar({ onNewChat }) {
  return (
    <aside className="sidebar" id="sidebar">
      <div className="sidebar__header">
        <button
          className="sidebar__new-chat-btn"
          onClick={onNewChat}
          id="new-chat-btn"
        >
          ＋ New Review
        </button>
      </div>

      <div className="sidebar__conversations">
        <div className="sidebar__section-title">How to use</div>
        <div className="sidebar__item">
          1. Paste a GitHub PR URL
        </div>
        <div className="sidebar__item">
          2. Get AI code review
        </div>
        <div className="sidebar__item">
          3. Review file-by-file comments
        </div>

        <div className="sidebar__section-title">Supported</div>
        <div className="sidebar__item">🐍 Python, Java, Go</div>
        <div className="sidebar__item">🦀 Rust, C++, C#</div>
        <div className="sidebar__item">📜 JS, TS, PHP, Ruby</div>
      </div>

      <div className="sidebar__footer">
        CodeReview Bot v1.0 • LangChain
      </div>
    </aside>
  );
}
