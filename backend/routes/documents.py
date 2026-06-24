from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, Form, status
from core.firebase import get_db
from core.cloudinary_client import upload_pdf, delete_pdf
from core.pinecone_client import upsert_vectors, delete_vectors_by_filter
from modules.document_processor import chunk_document, get_page_count
from modules.embeddings import embed_texts
from routes.auth import get_current_user
from schemas.document import (
    DocumentUploadResponse,
    DocumentListResponse,
    DocumentInfo,
    DeleteDocumentResponse,
)
from core.config import settings
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chats/{chat_id}/documents", tags=["Documents"])


def _ensure_chat_belongs_to_user(chat_id: str, uid: str) -> dict:
    """Fetch chat doc from Firestore and verify ownership."""
    db = get_db()
    chat_ref = db.collection("chats").document(chat_id)
    chat = chat_ref.get()
    if not chat.exists:
        raise HTTPException(status_code=404, detail="Chat not found.")
    data = chat.to_dict()
    if data.get("userId") != uid:
        raise HTTPException(status_code=403, detail="Not authorized to access this chat.")
    return data


@router.post("", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    chat_id: str,
    file: UploadFile = File(...),
    chunk_size: int = Form(default=500, ge=100, le=1000),
    current_user: dict = Depends(get_current_user),
):
    """Upload a PDF, process it, embed it, and store vectors in Pinecone."""
    uid = current_user["uid"]

    # --- Validate ownership ---
    _ensure_chat_belongs_to_user(chat_id, uid)

    # --- Validate file type ---
    ext = file.filename.split(".")[-1].lower()
    if ext not in ["pdf", "txt", "docx"]:
        raise HTTPException(status_code=400, detail="Only PDF, TXT, and DOCX files are accepted.")

    # --- Read file bytes ---
    file_bytes = await file.read()

    # --- Validate file size ---
    if len(file_bytes) > settings.max_pdf_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File exceeds maximum size of {settings.MAX_PDF_SIZE_MB}MB.",
        )

    # --- Check doc count limit ---
    db = get_db()
    existing_docs = (
        db.collection("chats").document(chat_id).collection("documents")
        .where("status", "!=", "deleted")
        .get()
    )
    if len(existing_docs) >= settings.MAX_PDFS_PER_CHAT:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {settings.MAX_PDFS_PER_CHAT} documents allowed per chat.",
        )

    doc_id = str(uuid.uuid4())
    public_id = f"chat_{chat_id}/{doc_id}"

    try:
        # --- Upload to Cloudinary ---
        cloudinary_result = upload_pdf(file_bytes, public_id=public_id, filename=file.filename)

        # --- Extract + chunk text ---
        chunks = chunk_document(
            file_bytes=file_bytes,
            filename=file.filename,
            chunk_size=chunk_size,
            chunk_overlap=settings.DEFAULT_CHUNK_OVERLAP,
        )
        if not chunks:
            raise HTTPException(status_code=422, detail="Document contains no extractable text.")

        page_count = get_page_count(file_bytes, file.filename)

        # --- Generate embeddings ---
        texts = [c.text for c in chunks]
        embeddings = embed_texts(texts)

        # --- Prepare vectors for Pinecone ---
        vectors = []
        for chunk, embedding in zip(chunks, embeddings):
            vectors.append(
                {
                    "id": f"{doc_id}_chunk_{chunk.chunk_id}",
                    "values": embedding,
                    "metadata": {
                        "file_id": doc_id,
                        "file_name": file.filename,
                        "page": chunk.page,
                        "chunk_id": chunk.chunk_id,
                        "text": chunk.text[:1000],  # Pinecone metadata limit
                    },
                }
            )

        # --- Upsert to Pinecone (namespace = chat_id) ---
        upsert_vectors(namespace=chat_id, vectors=vectors)

        # --- Save document metadata to Firestore ---
        now = datetime.now(timezone.utc).isoformat()
        doc_data = {
            "fileId": doc_id,
            "fileName": file.filename,
            "cloudinaryUrl": cloudinary_result["url"],
            "cloudinaryPublicId": public_id,
            "pageCount": page_count,
            "chunkCount": len(chunks),
            "chunkSize": chunk_size,
            "uploadedAt": now,
            "status": "ready",
            "userId": uid,
        }
        db.collection("chats").document(chat_id).collection("documents").document(doc_id).set(doc_data)

        # --- Update chat document count ---
        chat_ref = db.collection("chats").document(chat_id)
        chat_ref.update({"documentCount": len(existing_docs) + 1, "updatedAt": now})

        logger.info(f"Document '{file.filename}' uploaded: {len(chunks)} chunks → Pinecone namespace '{chat_id}'")

        return DocumentUploadResponse(
            doc_id=doc_id,
            file_name=file.filename,
            page_count=page_count,
            chunk_count=len(chunks),
            chunk_size=chunk_size,
            cloudinary_url=cloudinary_result["url"],
            uploaded_at=now,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Document upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.get("", response_model=DocumentListResponse)
def list_documents(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
):
    """List all documents attached to a chat."""
    uid = current_user["uid"]
    _ensure_chat_belongs_to_user(chat_id, uid)

    db = get_db()
    docs = (
        db.collection("chats").document(chat_id).collection("documents")
        .where("status", "!=", "deleted")
        .get()
    )

    document_list = []
    for doc in docs:
        d = doc.to_dict()
        document_list.append(
            DocumentInfo(
                doc_id=d.get("fileId", doc.id),
                file_name=d.get("fileName", ""),
                page_count=d.get("pageCount", 0),
                chunk_count=d.get("chunkCount", 0),
                chunk_size=d.get("chunkSize", settings.DEFAULT_CHUNK_SIZE),
                cloudinary_url=d.get("cloudinaryUrl", ""),
                uploaded_at=d.get("uploadedAt", ""),
                status=d.get("status", "ready"),
            )
        )

    return DocumentListResponse(chat_id=chat_id, documents=document_list, total=len(document_list))


@router.delete("/{doc_id}", response_model=DeleteDocumentResponse)
def delete_document(
    chat_id: str,
    doc_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Remove a document from a chat — deletes from Pinecone, Cloudinary, and Firestore."""
    uid = current_user["uid"]
    _ensure_chat_belongs_to_user(chat_id, uid)

    db = get_db()
    doc_ref = (
        db.collection("chats").document(chat_id).collection("documents").document(doc_id)
    )
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Document not found.")

    d = doc.to_dict()

    try:
        # Delete from Pinecone
        delete_vectors_by_filter(namespace=chat_id, filter_dict={"file_id": {"$eq": doc_id}})

        # Delete from Cloudinary
        public_id = d.get("cloudinaryPublicId")
        if public_id:
            delete_pdf(public_id)

        # Soft-delete in Firestore
        doc_ref.update({"status": "deleted"})

        # Update chat count
        chat_ref = db.collection("chats").document(chat_id)
        remaining = (
            db.collection("chats").document(chat_id).collection("documents")
            .where("status", "!=", "deleted")
            .get()
        )
        chat_ref.update({"documentCount": len(remaining)})

        return DeleteDocumentResponse(doc_id=doc_id, message="Document deleted successfully.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete document failed: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")
