import { useState, useCallback, useRef, useEffect } from "react";
import { sendChatMessage, streamChatMessage } from "../api/chatApi";

const WELCOME_MESSAGE =
  "Welcome to **SSCR-BOT** - AI Code Review Agent.\n\n" +
  "This frontend runs the **diff-only baseline**.\n\n" +
  "I use **4 specialized agents** to analyze your PR:\n" +
  "- **Defect Agent** - bugs and logic errors\n" +
  "- **Security Agent** - vulnerabilities and OWASP Top 10\n" +
  "- **Performance Agent** - bottlenecks and resource leaks\n" +
  "- **Maintainability Agent** - code quality and SOLID\n\n" +
  "Paste a GitHub PR URL to start.";

function normalizeProgressStage(stage) {
  return String(stage || "")
    .replace(/[\u{1F300}-\u{1FAFF}\u2600-\u27BF]/gu, "")
    .replace(/â€”|—/g, "-")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

function agentUpdateFromStage(stage) {
  const normalized = normalizeProgressStage(stage);
  const match = normalized.match(/^(.*?)\s+(done|failed)\s+-\s+(\d+)\s+findings?/i);
  if (!match) return null;

  return {
    name: match[1].trim(),
    status: match[2].toLowerCase(),
    findings: Number(match[3]) || 0,
  };
}

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
    const streamId = `stream-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      {
        id: streamId,
        role: "bot",
        content: "Starting review...",
        comments: [],
        isStreaming: true,
        progress: 0.02,
        streamStage: "Starting review...",
        progressLog: ["Starting review..."],
        agentRuns: [],
        timestamp: new Date(),
      },
    ]);

    try {
      let response = null;
      try {
        response = await streamChatMessage(text.trim(), {
          onProgress: ({ stage, progress }) => {
            const nextStage = stage || "";
            const agentUpdate = agentUpdateFromStage(nextStage);
            setMessages((prev) =>
              prev.map((msg) =>
                msg.id === streamId
                  ? (() => {
                      const agentRuns = agentUpdate
                        ? [
                            ...(msg.agentRuns || []).filter(
                              (run) => run.name !== agentUpdate.name,
                            ),
                            agentUpdate,
                          ]
                        : msg.agentRuns || [];

                      return {
                        ...msg,
                        content: nextStage || msg.content,
                        streamStage: nextStage || msg.streamStage,
                        progress: typeof progress === "number" ? progress : msg.progress,
                        progressLog:
                          nextStage && !(msg.progressLog || []).includes(nextStage)
                            ? [...(msg.progressLog || []), nextStage]
                            : msg.progressLog || [],
                        agentRuns,
                      };
                    })()
                  : msg,
              ),
            );
          },
          onFinal: (data) => {
            response = data;
          },
        });
      } catch (streamError) {
        response = await sendChatMessage(text.trim());
      }

      const botMessage = {
        id: streamId,
        role: "bot",
        content: response.message || "No response received.",
        comments: response.comments || [],
        prUrl: response.pr_url || null,
        metadata: response.metadata || null,
        riskAssessment: response.risk_assessment || null,
        categoryStats: response.category_stats || null,
        agentMetadata: response.agent_metadata || null,
        reviewSummary: response.review_summary || "",
        isStreaming: false,
        progress: 1,
        timestamp: new Date(),
      };

      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === streamId ? botMessage : msg,
        ),
      );
    } catch (error) {
      const errorMessage = {
        id: streamId,
        role: "bot",
        content: `**Error:** ${error.message}\n\nPlease check that the backend is running and try again.`,
        isError: true,
        timestamp: new Date(),
      };
      setMessages((prev) => prev.map((msg) => (msg.id === streamId ? errorMessage : msg)));
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
