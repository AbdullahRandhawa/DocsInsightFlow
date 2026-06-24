import { useState, useEffect } from "react";
import { Sidebar } from "../components/layout/Sidebar";
import { ChatWindow } from "../components/chat/ChatWindow";
import { ChatInput } from "../components/chat/ChatInput";
import { UploadModal } from "../components/documents/UploadModal";
import { SettingsPanel } from "../components/chat/SettingsPanel";
import { chatApi, documentsApi } from "../lib/api";
import { Settings } from "lucide-react";
import toast from "react-hot-toast";

export function ChatPage() {
  const [chats, setChats] = useState([]);
  const [activeChatId, setActiveChatId] = useState(null);
  const [messages, setMessages] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState(0.5);

  useEffect(() => { loadChats(); }, []);

  useEffect(() => {
    if (activeChatId) {
      loadMessagesAndDocs(activeChatId);
    } else {
      setMessages([]);
      setDocuments([]);
    }
  }, [activeChatId]);

  const loadChats = async () => {
    try {
      const res = await chatApi.listChats();
      setChats(res.data.chats);
      if (res.data.chats.length > 0 && !activeChatId) {
        setActiveChatId(res.data.chats[0].chat_id);
      }
    } catch {
      toast.error("Failed to load chats");
    } finally {
      setLoadingChats(false);
    }
  };

  const loadMessagesAndDocs = async (chatId) => {
    setLoadingMessages(true);
    try {
      const [msgRes, docRes] = await Promise.all([
        chatApi.getMessages(chatId),
        documentsApi.list(chatId),
      ]);
      setMessages(msgRes.data.messages);
      setDocuments(docRes.data.documents);
    } catch {
      toast.error("Failed to load chat data");
    } finally {
      setLoadingMessages(false);
    }
  };

  const handleNewChat = async () => {
    try {
      const res = await chatApi.createChat();
      const newChat = { ...res.data, document_count: 0 };
      setChats([newChat, ...chats]);
      setActiveChatId(newChat.chat_id);
    } catch {
      toast.error("Failed to create chat");
    }
  };

  const handleDeleteChat = (chatId) => {
    const remaining = chats.filter((c) => c.chat_id !== chatId);
    setChats(remaining);
    if (activeChatId === chatId) {
      setActiveChatId(remaining[0]?.chat_id || null);
      setMessages([]);
      setDocuments([]);
    }
  };

  const handleSend = async (query, fileId = null) => {
    if (!activeChatId) {
      try {
        const res = await chatApi.createChat();
        const newChat = { ...res.data, document_count: 0 };
        setChats([newChat, ...chats]);
        setActiveChatId(newChat.chat_id);
        await performQuery(newChat.chat_id, query, fileId);
      } catch {
        toast.error("Failed to start chat");
      }
      return;
    }
    await performQuery(activeChatId, query, fileId);
  };

  const performQuery = async (chatId, query, fileId = null) => {
    const tempId = Date.now().toString();
    setMessages((prev) => [...prev, { message_id: tempId, role: "user", content: query }]);
    setIsQuerying(true);
    try {
      const res = await chatApi.query(chatId, {
        query,
        top_k: topK,
        threshold,
        file_id: fileId || undefined,
      });
      setMessages((prev) => [
        ...prev,
        {
          message_id: res.data.message_id,
          role: "assistant",
          content: res.data.answer,
          sources: res.data.sources,
          has_context: res.data.has_context,
          _query: query,
          _fileId: fileId,
        },
      ]);
      loadChats();
    } catch (err) {
      toast.error(err.message || "Failed to get answer");
      setMessages((prev) => prev.filter((m) => m.message_id !== tempId));
    } finally {
      setIsQuerying(false);
    }
  };

  // Retry: re-send the user message that preceded this assistant message
  const handleRetry = (assistantIndex) => {
    const msg = messages[assistantIndex];
    if (!msg || msg.role !== "assistant") return;
    // Remove this assistant message and re-query
    setMessages((prev) => prev.filter((_, i) => i !== assistantIndex));
    performQuery(activeChatId, msg._query, msg._fileId || null);
  };

  const handleDocumentAdded = (doc) => {
    setDocuments((prev) => [...prev, doc]);
    loadChats();
  };

  const hasDocuments = documents.length > 0;

  return (
    <div className="dashboard">
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        onSelectChat={setActiveChatId}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
        loading={loadingChats}
      />

      <div className="main-content">
        {activeChatId ? (
          <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
            <ChatWindow
              messages={messages}
              isLoading={loadingMessages || isQuerying}
              hasDocuments={hasDocuments}
              onRetry={handleRetry}
            />

            {showSettings && (
              <div style={{ 
                margin: "0 var(--space-6) var(--space-3)", 
                padding: "var(--space-4)", 
                background: "var(--color-bg-secondary)", 
                border: "1px solid var(--color-border)", 
                borderRadius: "var(--radius-lg)",
                boxShadow: "var(--shadow-md)"
              }}>
                <SettingsPanel
                  topK={topK}
                  threshold={threshold}
                  onTopKChange={setTopK}
                  onThresholdChange={setThreshold}
                />
              </div>
            )}

            <ChatInput
              onSend={handleSend}
              onUploadClick={() => setShowUploadModal(true)}
              onSettingsClick={() => setShowSettings(!showSettings)}
              disabled={isQuerying}
              documents={documents}
            />
          </div>
        ) : (
          <div className="welcome-screen">
            <div className="welcome-icon">
              <Settings size={32} color="#fff" />
            </div>
            <h2 className="welcome-title">Welcome to DocsInsightFlow</h2>
            <p className="welcome-subtitle">Select a chat or start a new one to begin.</p>
            <button className="btn btn-primary" onClick={handleNewChat}>
              Start New Chat
            </button>
          </div>
        )}
      </div>

      {showUploadModal && activeChatId && (
        <UploadModal
          chatId={activeChatId}
          documents={documents}
          onDocumentAdded={handleDocumentAdded}
          onClose={() => setShowUploadModal(false)}
        />
      )}
    </div>
  );
}
