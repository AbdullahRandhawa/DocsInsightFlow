from pydantic import BaseModel, Field
from typing import Optional


class CreateChatRequest(BaseModel):
    title: Optional[str] = None  # If None, auto-generated after first message


class CreateChatResponse(BaseModel):
    chat_id: str
    title: str
    created_at: str


class ChatInfo(BaseModel):
    chat_id: str
    title: str
    created_at: str
    updated_at: str
    document_count: int


class ChatListResponse(BaseModel):
    chats: list[ChatInfo]
    total: int


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=10)
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    file_id: Optional[str] = None  # Optional: restrict retrieval to one doc


class SourceReference(BaseModel):
    file_id: str
    file_name: str
    page: int
    score: float
    excerpt: str  # First 300 chars of the chunk
    full_text: Optional[str] = None


class QueryResponse(BaseModel):
    answer: str
    sources: list[SourceReference]
    query: str
    message_id: str
    has_context: bool  # False if no chunks above threshold


class MessageInfo(BaseModel):
    message_id: str
    role: str  # "user" | "assistant"
    content: str
    timestamp: str
    sources: Optional[list[SourceReference]] = None
    query_settings: Optional[dict] = None


class MessageHistoryResponse(BaseModel):
    chat_id: str
    messages: list[MessageInfo]
    total: int


class DeleteChatResponse(BaseModel):
    chat_id: str
    message: str
