import { FileText, X, Trash2, MessageSquare, Plus, LogOut, Settings } from "lucide-react";
import { useAuth } from "../../contexts/AuthContext";
import { chatApi } from "../../lib/api";
import { useState } from "react";
import toast from "react-hot-toast";

function formatChatTime(isoString) {
  if (!isoString) return "";
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now - date;
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  } else if (diffDays === 1) {
    return "Yesterday";
  } else if (diffDays < 7) {
    return date.toLocaleDateString([], { weekday: "short" });
  } else {
    return date.toLocaleDateString([], { month: "short", day: "numeric" });
  }
}

export function Sidebar({ chats, activeChatId, pendingNewChat, onSelectChat, onNewChat, onDeleteChat, loading }) {
  const { user, logout } = useAuth();
  const [deletingId, setDeletingId] = useState(null);

  const handleDelete = async (e, chatId) => {
    e.stopPropagation();
    if (!confirm("Delete this chat and all its documents?")) return;
    setDeletingId(chatId);
    try {
      await chatApi.deleteChat(chatId);
      onDeleteChat(chatId);
      toast.success("Chat deleted");
    } catch (err) {
      toast.error(err.message || "Failed to delete chat");
    } finally {
      setDeletingId(null);
    }
  };

  const handleLogout = async () => {
    await logout();
    toast.success("Logged out");
  };

  const userInitial = (user?.displayName || user?.email || "U")[0].toUpperCase();
  const userName = user?.displayName || user?.email?.split("@")[0] || "User";

  return (
    <div className="sidebar">
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <div className="sidebar-logo-icon">
            <FileText size={16} color="#fff" />
          </div>
          <span className="sidebar-logo-text">DocsInsight</span>
        </div>
      </div>

      {/* New Chat Button */}
      <div style={{ padding: "0 var(--space-3)" }}>
        <button
          className={`sidebar-new-chat ${pendingNewChat ? "active" : ""}`}
          onClick={onNewChat}
          id="new-chat-btn"
        >
          <Plus size={16} />
          New Chat
        </button>
      </div>

      {/* Chat List */}
      <div className="sidebar-chat-list">
        {loading ? (
          <div style={{ padding: "var(--space-4)", textAlign: "center" }}>
            <div className="spinner spinner-sm" style={{ margin: "0 auto" }} />
          </div>
        ) : chats.length === 0 ? (
          <div style={{ padding: "var(--space-4)", textAlign: "center" }}>
            <p style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>
              No chats yet. Create one!
            </p>
          </div>
        ) : (
          <>
            <div className="sidebar-section-label">Recent Chats</div>
            {chats.map((chat) => (
              <div
                key={chat.chat_id}
                className={`sidebar-chat-item ${activeChatId === chat.chat_id ? "active" : ""} ${deletingId === chat.chat_id ? "deleting" : ""}`}
                onClick={() => onSelectChat(chat.chat_id)}
                id={`chat-item-${chat.chat_id}`}
              >
                <MessageSquare size={14} className="sidebar-chat-item-icon" />
                <div className="sidebar-chat-item-content">
                  <div className="sidebar-chat-item-title">{chat.title}</div>
                  <div className="sidebar-chat-item-meta">
                    <span>{chat.document_count} doc{chat.document_count !== 1 ? "s" : ""}</span>
                    {chat.updated_at && (
                      <span className="sidebar-chat-timestamp">
                        {formatChatTime(chat.updated_at)}
                      </span>
                    )}
                  </div>
                </div>
                <button
                  className="sidebar-chat-item-delete"
                  style={{
                    opacity: deletingId === chat.chat_id ? 1 : undefined,
                    pointerEvents: deletingId === chat.chat_id ? "none" : undefined,
                  }}
                  onClick={(e) => handleDelete(e, chat.chat_id)}
                  disabled={deletingId === chat.chat_id}
                  title="Delete chat"
                >
                  {deletingId === chat.chat_id ? (
                    <div className="spinner spinner-sm" />
                  ) : (
                    <Trash2 size={13} />
                  )}
                </button>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Footer */}
      <div className="sidebar-footer">
        <div className="sidebar-user-avatar">{userInitial}</div>
        <div className="sidebar-user-info">
          <div className="sidebar-user-name">{userName}</div>
          <div className="sidebar-user-email">{user?.email}</div>
        </div>
        <button className="btn-icon" onClick={handleLogout} title="Log out">
          <LogOut size={15} />
        </button>
      </div>
    </div>
  );
}
