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
      {messages.map((msg) => (
        <ChatMessage key={msg.id} message={msg} />
      ))}

      {isLoading && <LoadingDots />}

      <div ref={messagesEndRef} />
    </div>
  );
}
