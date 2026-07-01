import axios from "axios";
import { auth } from "./firebase";

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1",
  timeout: 120000, // 2 min timeout for LLM calls
});

// Attach Firebase ID token to every request
api.interceptors.request.use(async (config) => {
  const user = auth.currentUser;
  if (user) {
    const token = await user.getIdToken();
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Global response error interceptor
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.message ||
      "An unexpected error occurred.";
    return Promise.reject(new Error(message));
  }
);

// ─── Chat API ────────────────────────────────────────────────────────────────
export const chatApi = {
  createChat: (title = null) => api.post("/chats", { title }),
  listChats: () => api.get("/chats"),
  deleteChat: (chatId) => api.delete(`/chats/${chatId}`),
  query: (chatId, payload) => api.post(`/chats/${chatId}/query`, payload),
  getMessages: (chatId) => api.get(`/chats/${chatId}/messages`),

  /**
   * Streaming SSE query. Calls callbacks as events arrive.
   * @param {string} chatId
   * @param {object} payload  - { query, top_k, threshold, file_id }
   * @param {object} handlers - { onStatus, onToken, onDone, onSaved, onError }
   */
  stream: async (chatId, payload, handlers = {}) => {
    const { auth } = await import("./firebase");
    const user = auth.currentUser;
    const token = user ? await user.getIdToken() : null;
    const baseURL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

    const res = await fetch(`${baseURL}/chats/${chatId}/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "Stream request failed");
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buf = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop(); // keep incomplete last line

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const ev = JSON.parse(line.slice(6));
          if (ev.type === "status")  handlers.onStatus?.(ev.message);
          else if (ev.type === "token")  handlers.onToken?.(ev.text);
          else if (ev.type === "done")   handlers.onDone?.(ev);
          else if (ev.type === "saved")  handlers.onSaved?.(ev);
          else if (ev.type === "error")  handlers.onError?.(new Error(ev.message));
        } catch { /* skip malformed */ }
      }
    }
  },
};

// ─── Documents API ────────────────────────────────────────────────────────────
export const documentsApi = {
  upload: (chatId, formData) =>
    api.post(`/chats/${chatId}/documents`, formData, {
      headers: { "Content-Type": "multipart/form-data" },
    }),
  list: (chatId) => api.get(`/chats/${chatId}/documents`),
  delete: (chatId, docId) => api.delete(`/chats/${chatId}/documents/${docId}`),
};

export default api;
