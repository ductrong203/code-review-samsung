import React from 'react';

/**
 * Loading dots animation component — shows while waiting for LLM response.
 */
export default function LoadingDots() {
  return (
    <div className="chat-message chat-message--bot" style={{ animation: 'fadeIn 0.3s ease' }}>
      <div className="chat-message__avatar chat-message__avatar--bot">SSCR</div>
      <div className="chat-message__body">
        <div className="chat-message__content" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
          <span style={{ color: 'var(--text-secondary)', fontSize: '14px' }}>Reviewing code</span>
          <span className="loading-dots">
            <span className="loading-dot" style={dotStyle(0)}>.</span>
            <span className="loading-dot" style={dotStyle(1)}>.</span>
            <span className="loading-dot" style={dotStyle(2)}>.</span>
          </span>
          <style>{`
            .loading-dot {
              animation: pulse 1.4s infinite;
              font-weight: bold;
              font-size: 20px;
              color: var(--accent-primary);
            }
          `}</style>
        </div>
      </div>
    </div>
  );
}

function dotStyle(index) {
  return {
    animationDelay: `${index * 0.2}s`,
  };
}
