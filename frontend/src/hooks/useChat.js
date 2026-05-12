import { useState, useCallback, useRef, useEffect } from "react";
import { sendChatMessage } from "../api/chatApi";

const WELCOME_MESSAGE =
  "Welcome to **SSCR-BOT** - AI Code Review Agent.\n\n" +
  "This frontend runs the **diff-only baseline**. It does not send graph context to the agents.\n\n" +
  "I use **4 specialized agents** to analyze your PR:\n" +
  "- **Defect Agent** - bugs and logic errors\n" +
  "- **Security Agent** - vulnerabilities and OWASP Top 10\n" +
  "- **Performance Agent** - bottlenecks and resource leaks\n" +
  "- **Maintainability Agent** - code quality and SOLID\n\n" +
  "Paste a GitHub PR URL to start.";

export function useChat() {
  const [messages, setMessages] = useState([
    {
      id: "welcome",
      role: "bot",
      content: WELCOME_MESSAGE,
      timestamp: new Date(),
    },
  ]);
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async (text) => {
    if (!text.trim() || isLoading) return;

    const userMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      const response = await sendChatMessage(text.trim());

      const botMessage = {
        id: `bot-${Date.now()}`,
        role: "bot",
        content: response.message || "No response received.",
        comments: response.comments || [],
        prUrl: response.pr_url || null,
        metadata: response.metadata || null,
        riskAssessment: response.risk_assessment || null,
        categoryStats: response.category_stats || null,
        agentMetadata: response.agent_metadata || null,
        reviewSummary: response.review_summary || "",
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, botMessage]);
    } catch (error) {
      const errorMessage = {
        id: `error-${Date.now()}`,
        role: "bot",
        content: `**Error:** ${error.message}\n\nPlease check that the backend is running and try again.`,
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
        id: "welcome",
        role: "bot",
        content: "Chat cleared. Paste a GitHub PR URL to start a new multi-agent review.",
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
