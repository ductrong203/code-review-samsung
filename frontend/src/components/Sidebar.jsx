import React from 'react';
import '../styles/Sidebar.css';

export default function Sidebar({ onNewChat }) {
  return (
    <aside className="sidebar" id="sidebar">
      <div className="sidebar__header">
        <div className="sidebar__brand">
          <span className="sidebar__brand-logo">SS</span>
          <div className="sidebar__brand-meta">
            <div className="sidebar__brand-title">SSCR-BOT</div>
            <div className="sidebar__brand-subtitle">Assistant Workspace</div>
          </div>
        </div>
        <button
          className="sidebar__new-chat-btn"
          onClick={onNewChat}
          id="new-chat-btn"
        >
          + New review
        </button>
      </div>

      <div className="sidebar__conversations">
        <div className="sidebar__section-title">Quick start</div>
        <button className="sidebar__item sidebar__item--active">
          Analyze pull request URL
        </button>
        <button className="sidebar__item">
          Ask for architecture feedback
        </button>
        <button className="sidebar__item">
          Review security and performance
        </button>

        <div className="sidebar__section-title">Supported languages</div>
        <div className="sidebar__item sidebar__item--info">Python, Java, Go</div>
        <div className="sidebar__item sidebar__item--info">Rust, C++, C#</div>
        <div className="sidebar__item sidebar__item--info">JavaScript, TypeScript, Ruby, PHP</div>
      </div>

      <div className="sidebar__footer">
        Ready for production reviews
      </div>
    </aside>
  );
}
