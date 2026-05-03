import React from 'react';
import '../styles/Header.css';

export default function Header() {
  return (
    <header className="header" id="header">
      <div className="header__brand">
        <div className="header__logo">🔍</div>
        <div>
          <div className="header__title">CodeReview Bot</div>
          <div className="header__subtitle">AI-Powered Code Review</div>
        </div>
      </div>
      <div className="header__actions">
        <div className="header__badge">
          <span className="header__badge-dot"></span>
          Online
        </div>
      </div>
    </header>
  );
}
