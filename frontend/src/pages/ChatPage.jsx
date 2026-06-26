import { useState, useEffect, useRef } from "react";
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
  const [pendingNewChat, setPendingNewChat] = useState(false); // chat UI open but not yet in Firestore
  const [messages, setMessages] = useState([]);
  const [documents, setDocuments] = useState([]);
  const [loadingChats, setLoadingChats] = useState(true);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [isQuerying, setIsQuerying] = useState(false);

  const [showUploadModal, setShowUploadModal] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [topK, setTopK] = useState(5);
  const [threshold, setThreshold] = useState(0.5);

  // Track if we're already creating a chat to prevent double-creation
  const creatingChatRef = useRef(false);

  useEffect(() => { loadChats(); }, []);

  useEffect(() => {
    if (activeChatId) {
      setPendingNewChat(false);
      loadMessagesAndDocs(activeChatId);
    } else if (!pendingNewChat) {
      setMessages([]);
      setDocuments([]);
    }
  }, [activeChatId]);

  // Poll documents every 3s while any are processing
  useEffect(() => {
    const isProcessing = documents.some((d) => d.status === "processing");
    if (!isProcessing || !activeChatId) return;
    const interval = setInterval(async () => {
      try {
        const docRes = await documentsApi.list(activeChatId);
        setDocuments(docRes.data.documents);
      } catch (err) {
        console.error("Polling docs failed", err);
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [documents, activeChatId]);

  const loadChats = async () => {
    try {
      const res = await chatApi.listChats();
      setChats(res.data.chats);
      if (res.data.chats.length > 0 && !activeChatId && !pendingNewChat) {
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
    setMessages([]); // Clear immediately to avoid stale temp messages showing
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

  // Just show an empty chat UI — don't touch Firestore until first message
  const handleNewChat = () => {
    setActiveChatId(null);
    setMessages([]);
    setDocuments([]);
    setPendingNewChat(true);
  };

  const handleSelectChat = (chatId) => {
    setPendingNewChat(false);
    setActiveChatId(chatId);
  };

  const handleDeleteChat = (chatId) => {
    const remaining = chats.filter((c) => c.chat_id !== chatId);
    setChats(remaining);
    if (activeChatId === chatId) {
      setPendingNewChat(false);
      setActiveChatId(remaining[0]?.chat_id || null);
      setMessages([]);
      setDocuments([]);
    }
  };

  /**
   * Ensures a real Firestore chat exists before doing anything that needs one.
   * Returns the chatId (either existing or freshly created).
   */
  const ensureChatExists = async () => {
    if (activeChatId) return activeChatId;
    if (creatingChatRef.current) return null; // prevent double creation
    creatingChatRef.current = true;
    try {
      const res = await chatApi.createChat();
      const newChat = { ...res.data, document_count: 0 };
      setChats((prev) => [newChat, ...prev]);
      setActiveChatId(newChat.chat_id);
      setPendingNewChat(false);
      return newChat.chat_id;
    } catch {
      toast.error("Failed to start chat");
      return null;
    } finally {
      creatingChatRef.current = false;
    }
  };

  const handleSend = async (query, fileId = null) => {
    const chatId = await ensureChatExists();
    if (!chatId) return;
    await performQuery(chatId, query, fileId);
  };

  const handleUploadClick = async () => {
    // If no real chat yet, create one first — upload needs a Firestore chat
    const chatId = await ensureChatExists();
    if (!chatId) return;
    setShowUploadModal(true);
  };

  const performQuery = async (chatId, query, fileId = null) => {
    const tempId = `temp-${Date.now()}`;
    // Optimistically add the user message
    const userMsg = { message_id: tempId, role: "user", content: query, _temp: true };
    setMessages((prev) => [...prev, userMsg]);
    setIsQuerying(true);
    try {
      const res = await chatApi.query(chatId, {
        query,
        top_k: topK,
        threshold,
        file_id: fileId || undefined,
      });
      const aiMsg = {
        message_id: res.data.message_id,
        role: "assistant",
        content: res.data.answer,
        sources: res.data.sources,
        has_context: res.data.has_context,
        _query: query,
        _fileId: fileId,
      };
      // Replace the temp user message with a permanent one + assistant reply
      setMessages((prev) => {
        const withoutTemp = prev.filter((m) => m.message_id !== tempId);
        // Avoid duplicating if message already exists (e.g. from a reload)
        const alreadyHasAI = withoutTemp.some((m) => m.message_id === aiMsg.message_id);
        const permanentUser = { ...userMsg, message_id: `user-${res.data.message_id}`, _temp: false };
        return alreadyHasAI
          ? withoutTemp
          : [...withoutTemp, permanentUser, aiMsg];
      });
      loadChats();
    } catch (err) {
      toast.error(err.message || "Failed to get answer");
      setMessages((prev) => prev.filter((m) => m.message_id !== tempId));
    } finally {
      setIsQuerying(false);
    }
  };

  const handleRetry = (assistantIndex) => {
    const msg = messages[assistantIndex];
    if (!msg || msg.role !== "assistant") return;
    setMessages((prev) => prev.filter((_, i) => i !== assistantIndex));
    performQuery(activeChatId, msg._query, msg._fileId || null);
  };

  const handleDocumentAdded = (doc) => {
    setDocuments((prev) => {
      // Replace if same doc_id, otherwise append
      const exists = prev.some((d) => d.doc_id === doc.doc_id);
      return exists ? prev.map((d) => (d.doc_id === doc.doc_id ? doc : d)) : [...prev, doc];
    });
    if (doc.status === "ready") loadChats();
  };

  // Chat UI shows when we have an active chat OR a pending new chat
  const showChatUI = !!activeChatId || pendingNewChat;

  return (
    <div className="dashboard">
      <Sidebar
        chats={chats}
        activeChatId={activeChatId}
        pendingNewChat={pendingNewChat}
        onSelectChat={handleSelectChat}
        onNewChat={handleNewChat}
        onDeleteChat={handleDeleteChat}
        loading={loadingChats}
      />

      <div className="main-content">
        {showChatUI ? (
          <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
            <ChatWindow
              messages={messages}
              isLoading={loadingMessages || isQuerying}
              hasDocuments={documents.length > 0}
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
              onUploadClick={handleUploadClick}
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
