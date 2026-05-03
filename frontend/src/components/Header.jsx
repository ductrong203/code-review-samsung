import React from 'react';
import '../styles/Header.css';

export default function Header() {
  return (
    <header className="header" id="header">
      <div className="header__brand">
        <div className="header__logo">AI</div>
        <div>
          <div className="header__title">SSCR-BOT</div>
          <div className="header__subtitle">Ship safer code, faster</div>
        </div>
      </div>
      <div className="header__actions">
        <div className="header__pill">Model: Review-v1</div>
        <div className="header__badge">
          <span className="header__badge-dot"></span>
          Live
        </div>
      </div>
    </header>
  );
}
