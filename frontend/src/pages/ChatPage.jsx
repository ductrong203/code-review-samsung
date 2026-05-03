import React from 'react';
import Sidebar from '../components/Sidebar';
import Header from '../components/Header';
import ChatWindow from '../components/ChatWindow';
import ChatInput from '../components/ChatInput';
import { useChat } from '../hooks/useChat';

/**
 * ChatPage — Main chat page layout assembling all components.
 */
export default function ChatPage() {
  const { messages, isLoading, sendMessage, clearChat, messagesEndRef } = useChat();

  return (
    <>
      <Sidebar onNewChat={clearChat} />
      <div className="app-main">
        <Header />
        <ChatWindow
          messages={messages}
          isLoading={isLoading}
          messagesEndRef={messagesEndRef}
        />
        <ChatInput onSend={sendMessage} isLoading={isLoading} />
      </div>
    </>
  );
}
