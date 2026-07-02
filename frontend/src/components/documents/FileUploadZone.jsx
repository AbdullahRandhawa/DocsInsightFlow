import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, FileText, AlertCircle } from "lucide-react";
import { documentsApi } from "../../lib/api";
import { UploadSettings } from "./UploadSettings";
import { DocumentChip } from "./DocumentChip";
import toast from "react-hot-toast";
import { Spinner } from "../ui/Spinner";

const MAX_DOCS = 3;
const MAX_SIZE_MB = 20;

export function FileUploadZone({ chatId, documents, onDocumentAdded, onDocumentRemoved }) {
  const [uploading, setUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState("");
  const [chunkSize, setChunkSize] = useState(500);

  const onDrop = useCallback(
    async (acceptedFiles, rejectedFiles) => {
      // Handle rejections
      if (rejectedFiles.length > 0) {
        const reasons = rejectedFiles.map((f) => f.errors[0]?.message).join(", ");
        toast.error(`File rejected: ${reasons}`);
        return;
      }

      if (documents.length >= MAX_DOCS) {
        toast.error(`Maximum ${MAX_DOCS} PDFs allowed per chat.`);
        return;
      }

      const file = acceptedFiles[0];
      if (!file) return;

      setUploading(true);
      setUploadProgress("Uploading to Cloudinary...");

      try {
        const formData = new FormData();
        formData.append("file", file);
        formData.append("chunk_size", chunkSize);

        setUploadProgress("Extracting & embedding text...");
        const res = await documentsApi.upload(chatId, formData);
        onDocumentAdded(res.data);
      } catch (err) {
        toast.error(err.message || "Upload failed");
      } finally {
        setUploading(false);
        setUploadProgress("");
      }
    },
    [chatId, documents.length, chunkSize, onDocumentAdded]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "text/plain": [".txt"],
      "application/vnd.openxmlformats-officedocument.wordprocessingml.document": [".docx"],
    },
    maxSize: MAX_SIZE_MB * 1024 * 1024,
    maxFiles: 1,
    disabled: uploading || documents.length >= MAX_DOCS,
  });

  const canUpload = documents.length < MAX_DOCS;

  return (
    <div className="upload-zone-wrapper">
      {/* Dropzone */}
      {canUpload && (
        <div
          {...getRootProps()}
          className={`upload-zone ${isDragActive ? "drag-active" : ""}`}
          id="file-upload-dropzone"
        >
          <input {...getInputProps()} id="file-input" />
          <div className="upload-zone-icon">
            {uploading ? <Spinner size="sm" /> : <Upload size={22} />}
          </div>
          {uploading ? (
            <>
              <p className="upload-zone-title">Processing file...</p>
              <p className="upload-zone-subtitle">{uploadProgress}</p>
            </>
          ) : isDragActive ? (
            <>
              <p className="upload-zone-title">Drop your file here</p>
              <p className="upload-zone-subtitle">Release to start upload</p>
            </>
          ) : (
            <>
              <p className="upload-zone-title">
                {documents.length === 0 ? "Upload your first document" : "Add another document"}
              </p>
              <p className="upload-zone-subtitle">
                Drag & drop or <span style={{ color: "var(--color-accent)", fontWeight: 600 }}>click to browse</span>
              </p>
              <p className="upload-zone-limit">
                PDF, TXT, DOCX · max {MAX_SIZE_MB}MB · {MAX_DOCS - documents.length} slot{MAX_DOCS - documents.length !== 1 ? "s" : ""} remaining
              </p>
            </>
          )}
        </div>
      )}

      {/* Chunk size slider */}
      {canUpload && !uploading && (
        <UploadSettings chunkSize={chunkSize} onChunkSizeChange={setChunkSize} />
      )}

      {/* Document chips */}
      {documents.length > 0 && (
        <div className="doc-chips-row">
          {documents.map((doc) => (
            <DocumentChip
              key={doc.doc_id}
              doc={doc}
              chatId={chatId}
              onRemove={onDocumentRemoved}
            />
          ))}
          {documents.length >= MAX_DOCS && (
            <span style={{ fontSize: "var(--text-xs)", color: "var(--color-warning)", display: "flex", alignItems: "center", gap: 4 }}>
              <AlertCircle size={11} /> Max docs reached
            </span>
          )}
        </div>
      )}
    </div>
  );
}
