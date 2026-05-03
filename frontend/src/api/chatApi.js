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
    body: JSON.stringify({ message }),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.detail || `Request failed: ${response.status}`);
  }

  return response.json();
}

/**
 * Check backend health.
 * @returns {Promise<Object>} Health status
 */
export async function checkHealth() {
  const response = await fetch(`${API_BASE}/health`);
  return response.json();
}
