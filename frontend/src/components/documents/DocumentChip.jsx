import { FileText, X } from "lucide-react";
import { documentsApi } from "../../lib/api";
import { useState } from "react";
import toast from "react-hot-toast";

export function DocumentChip({ doc, chatId, onRemove }) {
  const [removing, setRemoving] = useState(false);

  const handleRemove = async () => {
    if (!confirm(`Remove "${doc.file_name}" from this chat?`)) return;
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

  return (
    <div className="doc-chip" title={doc.file_name}>
      <FileText size={12} className="doc-chip-icon" />
      <span className="doc-chip-name">{doc.file_name}</span>
      <span style={{ fontSize: "var(--text-xs)", color: "var(--color-text-muted)" }}>
        {doc.page_count}p
      </span>
      <button
        className="doc-chip-remove"
        onClick={handleRemove}
        disabled={removing}
        title="Remove document"
      >
        {removing ? <div className="spinner spinner-sm" /> : <X size={11} />}
      </button>
    </div>
  );
}
