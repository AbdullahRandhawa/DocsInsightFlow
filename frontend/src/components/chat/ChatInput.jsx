import { useRef, useState, useEffect } from "react";
import { Send, Loader2, Paperclip, FileText, X, Settings } from "lucide-react";
import { documentsApi } from "../../lib/api";
import toast from "react-hot-toast";

export function ChatInput({ onSend, onUploadClick, onSettingsClick, disabled, documents = [], chatId, onDocumentRemoved }) {
  const [value, setValue] = useState("");
  const [selectedFileId, setSelectedFileId] = useState(null);
  const [removingId, setRemovingId] = useState(null);
  const textareaRef = useRef(null);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (ta) {
      ta.style.height = "auto";
      ta.style.height = Math.min(ta.scrollHeight, 200) + "px";
    }
  }, [value]);

  const handleSend = () => {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed, selectedFileId || null);
    setValue("");
    setSelectedFileId(null);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const toggleFile = (fileId) => {
    setSelectedFileId((prev) => (prev === fileId ? null : fileId));
  };

  const confirmRemove = (doc) => {
    toast(
      (t) => (
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <span>Remove <strong>{doc.file_name}</strong> from this chat?</span>
          <div style={{ display: "flex", gap: "8px", justifyContent: "flex-end" }}>
            <button
              className="btn btn-sm"
              onClick={() => toast.dismiss(t.id)}
              style={{ fontSize: "0.8rem" }}
            >
              Cancel
            </button>
            <button
              className="btn btn-sm btn-danger"
              onClick={async () => {
                toast.dismiss(t.id);
                if (!chatId) return;
                setRemovingId(doc.doc_id);
                try {
                  await documentsApi.delete(chatId, doc.doc_id);
                  onDocumentRemoved(doc.doc_id);
                  toast.success(`Removed ${doc.file_name}`);
                } catch (err) {
                  toast.error(err.message || "Failed to remove document");
                } finally {
                  setRemovingId(null);
                }
              }}
              style={{ fontSize: "0.8rem" }}
            >
              Remove
            </button>
          </div>
        </div>
      ),
      { duration: 10000 }
    );
  };

  const hasDocuments = documents.length > 0;
  const canSend = value.trim().length > 0 && !disabled;
  const placeholder = !hasDocuments
    ? "Say hi, or click the paperclip to upload a document..."
    : disabled
    ? "Generating answer..."
    : "Ask a question about your documents...";

  return (
    <div className="chat-input-area">
      {/* File pills — clickable to filter query to a specific file */}
      {hasDocuments && (
        <div className="input-file-pills">
          {documents.map((doc) => {
            const isActive = selectedFileId === doc.doc_id;
            return (
              <div
                key={doc.doc_id}
                className={`input-file-pill ${isActive ? "active" : ""}`}
                style={{ display: "inline-flex", alignItems: "center", gap: "4px" }}
              >
                <button
                  onClick={() => doc.status !== "processing" && toggleFile(doc.doc_id)}
                  title={doc.status === "processing" ? "Document is processing..." : isActive ? "Click to search all docs" : `Search only in ${doc.file_name}`}
                  type="button"
                  disabled={doc.status === "processing"}
                  style={{ display: "flex", alignItems: "center", gap: "4px", background: "none", border: "none", cursor: "pointer", padding: 0, color: "inherit", fontSize: "inherit" }}
                >
                  <FileText size={11} />
                  <span>{doc.file_name.length > 22 ? doc.file_name.slice(0, 22) + "…" : doc.file_name}</span>
                  {doc.status === "processing" && <Loader2 size={11} className="spin" />}
                </button>
                {doc.status !== "processing" && chatId && (
                  <button
                    onClick={() => confirmRemove(doc)}
                    disabled={removingId === doc.doc_id}
                    title="Remove document"
                    type="button"
                    style={{ background: "none", border: "none", cursor: "pointer", padding: 0, display: "flex", color: "inherit", opacity: 0.6 }}
                  >
                    {removingId === doc.doc_id ? <Loader2 size={10} className="spin" /> : <X size={10} />}
                  </button>
                )}
              </div>
            );
          })}
          {selectedFileId && (
            <span className="input-file-hint">Searching in selected file only</span>
          )}
        </div>
      )}

      <div className="chat-input-wrapper">
        {/* Attach button */}
        <div className="chat-attach-btn-wrapper" title="Upload PDF, TXT or DOCX">
          <button
            id="upload-trigger-btn"
            className="chat-attach-btn"
            onClick={onUploadClick}
            disabled={disabled}
            type="button"
          >
            <Paperclip size={16} />
          </button>
        </div>

        <textarea
          ref={textareaRef}
          id="chat-input"
          className="chat-textarea"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          rows={1}
          disabled={disabled}
        />

        <div className="chat-input-actions">
          <button
            type="button"
            className="chat-attach-btn"
            onClick={onSettingsClick}
            title="Query Settings"
          >
            <Settings size={16} />
          </button>
          
          <button
            id="send-btn"
            className="chat-send-btn"
            onClick={handleSend}
            disabled={!canSend}
            title="Send"
          >
            {disabled ? <Loader2 size={16} className="spin" /> : <Send size={16} />}
          </button>
        </div>
      </div>
    </div>
  );
}
