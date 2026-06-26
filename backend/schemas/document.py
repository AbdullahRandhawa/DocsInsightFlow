from pydantic import BaseModel, Field
from typing import Optional


class DocumentUploadResponse(BaseModel):
    doc_id: str
    file_name: str
    page_count: int
    chunk_count: int
    chunk_size: int
    cloudinary_url: str
    uploaded_at: str
    status: str = "processing"


class DocumentInfo(BaseModel):
    doc_id: str
    file_name: str
    page_count: int
    chunk_count: int
    chunk_size: int
    cloudinary_url: str
    uploaded_at: str
    status: str  # "ready" | "processing" | "error"


class DocumentListResponse(BaseModel):
    chat_id: str
    documents: list[DocumentInfo]
    total: int


class DeleteDocumentResponse(BaseModel):
    doc_id: str
    message: str
