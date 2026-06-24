import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, FileText, AlertCircle } from "lucide-react";
import { documentsApi } from "../../lib/api";
import { Spinner } from "../ui/Spinner";
import toast from "react-hot-toast";

const MAX_DOCS = 3;
const MAX_SIZE_MB = 20;

export function UploadModal({ chatId, documents, onDocumentAdded, onClose }) {
  const [chunkSize, setChunkSize] = useState(500);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState("");

  const onDrop = useCallback((accepted, rejected) => {
    if (rejected.length > 0) {
      toast.error("File not accepted. Use PDF, TXT, or DOCX under 20MB.");
      return;
    }
    if (accepted[0]) setSelectedFile(accepted[0]);
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "text/plain": [".txt"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    maxSize: MAX_SIZE_MB * 1024 * 1024,
    maxFiles: 1,
    disabled: uploading,
  });

  const handleUpload = async () => {
    if (!selectedFile || uploading) return;
    setUploading(true);
    setProgress("Uploading...");
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("chunk_size", chunkSize);
      setProgress("Extracting & embedding text...");
      const res = await documentsApi.upload(chatId, formData);
      onDocumentAdded(res.data);
      toast.success(`"${selectedFile.name}" processed — ${res.data.chunk_count} chunks`);
      onClose();
    } catch (err) {
      toast.error(err.message || "Upload failed");
    } finally {
      setUploading(false);
      setProgress("");
    }
  };

  const slotsLeft = MAX_DOCS - documents.length;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <span className="modal-title">Upload Document</span>
          <button className="btn-icon" onClick={onClose} disabled={uploading}>
            <X size={16} />
          </button>
        </div>

        {/* Drop zone */}
        <div
          {...getRootProps()}
          className={`modal-dropzone ${isDragActive ? "drag-active" : ""} ${selectedFile ? "has-file" : ""}`}
        >
          <input {...getInputProps()} />
          {selectedFile ? (
            <div className="modal-file-selected">
              <FileText size={20} style={{ color: "var(--color-accent)" }} />
              <span className="modal-file-name">{selectedFile.name}</span>
              <button
                className="modal-file-clear"
                onClick={(e) => { e.stopPropagation(); setSelectedFile(null); }}
                disabled={uploading}
              >
                <X size={13} />
              </button>
            </div>
          ) : (
            <>
              <Upload size={24} style={{ color: "var(--color-accent)", marginBottom: 8 }} />
              <p className="modal-drop-label">
                {isDragActive ? "Drop it here" : "Drag & drop or click to browse"}
              </p>
              <p className="modal-drop-hint">PDF, TXT, DOCX · max {MAX_SIZE_MB}MB · {slotsLeft} slot{slotsLeft !== 1 ? "s" : ""} left</p>
            </>
          )}
        </div>

        {/* Chunk size */}
        <div className="modal-settings">
          <label className="modal-settings-label">Chunk size: <strong>{chunkSize}</strong> words</label>
          <input
            type="range"
            min={100}
            max={1000}
            step={50}
            value={chunkSize}
            onChange={(e) => setChunkSize(Number(e.target.value))}
            className="chunk-slider"
            disabled={uploading}
          />
          <div className="modal-settings-range">
            <span>100</span><span>1000</span>
          </div>
        </div>

        {/* Actions */}
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose} disabled={uploading}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={!selectedFile || uploading}
          >
            {uploading ? <><Spinner size="sm" />{progress}</> : "Upload"}
          </button>
        </div>
      </div>
    </div>
  );
}
