import { FileText, X, Loader2 } from "lucide-react";
import { documentsApi } from "../../lib/api";
import { useState } from "react";
import toast from "react-hot-toast";

export function DocumentChip({ doc, chatId, onRemove }) {
  const [removing, setRemoving] = useState(false);

  const handleRemove = async () => {
    setRemoving(true);
    try {
      await documentsApi.delete(chatId, doc.doc_id);
      onRemove(doc.doc_id);
      toast.success(`Removed ${doc.file_name}`);
    } catch (err) {
      toast.error(err.message || "Failed to remove document");
    } finally {
      setRemoving(false);
    }
  };

  const confirmRemove = () => {
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
              onClick={() => {
                toast.dismiss(t.id);
                handleRemove();
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

  return (
    <div className="doc-chip" title={doc.file_name}>
      <FileText size={12} className="doc-chip-icon" />
      <span className="doc-chip-name">{doc.file_name}</span>
      <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>
        {doc.page_count}p
      </span>
      <button
        className="doc-chip-remove"
        onClick={confirmRemove}
        disabled={removing}
        title="Remove document"
      >
        {removing ? <Loader2 size={11} className="spin" /> : <X size={11} />}
      </button>
    </div>
  );
}