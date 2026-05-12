/**
 * API Client — Handles communication with the FastAPI backend.
 */

const API_BASE = '/api/v1';

/**
 * Send a chat message to the backend for code review.
 * @param {string} message - User message (typically a PR URL)
 * @returns {Promise<Object>} Chat response with review comments
 */
export async function sendChatMessage(message) {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    // Frontend is the diff-only baseline path. Graph context is only supplied
    // by the extension service so results can be compared side by side.
    body: JSON.stringify({ message, graph_context: null }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

function parseSseBlock(block) {
  let event = "message";
  const dataLines = [];
  block.split("\n").forEach((line) => {
    if (line.startsWith("event:")) event = line.slice(6).trim();
    if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
  });
  if (!dataLines.length) return null;
  return { event, data: JSON.parse(dataLines.join("\n")) };
}

/**
 * Stream a chat review request. The diff-only frontend uses progress, final,
 * error, and done events.
 */
export async function streamChatMessage(message, handlers = {}) {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
    },
    body: JSON.stringify({ message, graph_context: null }),
  });

  if (!response.ok || !response.body) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let finalData = null;

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      const parsed = parseSseBlock(block.trim());
      if (!parsed) continue;

      if (parsed.event === "progress") handlers.onProgress?.(parsed.data);
      if (parsed.event === "final") {
        finalData = parsed.data;
        handlers.onFinal?.(parsed.data);
      }
      if (parsed.event === "error") {
        throw new Error(parsed.data.error || "Streaming review failed");
      }
    }
  }

  return finalData;
}

/**
 * Check backend health.
 * @returns {Promise<Object>} Health status
 */
export async function checkHealth() {
  const response = await fetch(`${API_BASE}/health`);
  return response.json();
}
