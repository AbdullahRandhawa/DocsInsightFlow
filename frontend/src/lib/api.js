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
