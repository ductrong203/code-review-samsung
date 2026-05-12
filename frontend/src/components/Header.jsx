import React from 'react';
import '../styles/Header.css';

export default function Header() {
  return (
    <header className="header" id="header">
      <div className="header__brand">
        <img className="header__logo" src="/sscr-bot-logo.png" alt="SSCR-BOT logo" />
        <div>
          <div className="header__title">SSCR-BOT</div>
          <div className="header__subtitle">Diff-only review baseline</div>
        </div>
      </div>
      <div className="header__actions">
        <div className="header__pill">Mode: Diff-only</div>
        <div className="header__badge">
          <span className="header__badge-dot"></span>
          Live
        </div>
      </div>
    </header>
  );
}
