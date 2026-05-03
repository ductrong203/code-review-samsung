import { useState, useCallback, useRef, useEffect } from 'react';
import { sendChatMessage } from '../api/chatApi';

/**
 * Custom hook for managing chat state.
 * Handles message history, sending, loading state, and auto-scroll.
 */
export function useChat() {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      role: 'bot',
      content: '👋 Welcome to **CodeReview Bot**!\n\nPaste a GitHub Pull Request URL and I\'ll review the code changes for you.\n\n**Example:**\n`https://github.com/facebook/react/pull/28000`',
      timestamp: new Date(),
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isLoading) return;

    // Add user message
    const userMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await sendChatMessage(text.trim());

      const botMessage = {
        id: `bot-${Date.now()}`,
        role: 'bot',
        content: response.message || 'No response received.',
        comments: response.comments || [],
        prUrl: response.pr_url || null,
        metadata: response.metadata || null,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      const errorMessage = {
        id: `error-${Date.now()}`,
        role: 'bot',
        content: `❌ **Error:** ${error.message}\n\nPlease check that the backend is running and try again.`,
        isError: true,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  }, [isLoading]);

  const clearChat = useCallback(() => {
    setMessages([
      {
        id: 'welcome',
        role: 'bot',
        content: '👋 Chat cleared! Paste a GitHub PR URL to start a new review.',
        timestamp: new Date(),
      },
    ]);
  }, []);

  return {
    messages,
    isLoading,
    sendMessage,
    clearChat,
    messagesEndRef,
  };
}
