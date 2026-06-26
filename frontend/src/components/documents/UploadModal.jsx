import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, FileText } from "lucide-react";
import { documentsApi } from "../../lib/api";
import toast from "react-hot-toast";

const MAX_DOCS = 3;
const MAX_SIZE_MB = 20;

export function UploadModal({ chatId, documents, onDocumentAdded, onClose }) {
  const [chunkSize, setChunkSize] = useState(500);
  const [selectedFile, setSelectedFile] = useState(null);

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
  });

  const handleUpload = async () => {
    if (!selectedFile) return;

    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("chunk_size", chunkSize);

    // Close the modal immediately — don't make user wait
    onDocumentAdded({
      doc_id: `temp_${Date.now()}`,
      file_name: selectedFile.name,
      page_count: 0,
      chunk_count: 0,
      chunk_size: chunkSize,
      cloudinary_url: "",
      uploaded_at: new Date().toISOString(),
      status: "processing",
    });
    onClose();

    // Fire upload in background
    try {
      const res = await documentsApi.upload(chatId, formData);
      // Replace temp doc with the real one from the server
      onDocumentAdded(res.data);
      toast.success(`"${selectedFile.name}" uploaded — processing in background`);
    } catch (err) {
      toast.error(err.message || "Upload failed");
    }
  };

  const slotsLeft = MAX_DOCS - documents.length;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-box" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="modal-header">
          <span className="modal-title">Upload Document</span>
          <button className="btn-icon" onClick={onClose}>
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
          />
          <div className="modal-settings-range">
            <span>100</span><span>1000</span>
          </div>
        </div>

        {/* Actions */}
        <div className="modal-actions">
          <button className="btn btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn btn-primary"
            onClick={handleUpload}
            disabled={!selectedFile}
          >
            Upload
          </button>
        </div>
      </div>
    </div>
  );
}
