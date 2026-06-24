from fastapi import APIRouter, HTTPException, Depends, status
from core.firebase import get_db
from core.pinecone_client import delete_namespace
from modules.retriever import retrieve_relevant_chunks, build_context_string
from modules.generator import generate_answer, generate_chat_title
from modules.agentic_router import route_query
from routes.auth import get_current_user
from schemas.chat import (
    CreateChatRequest,
    CreateChatResponse,
    ChatListResponse,
    ChatInfo,
    QueryRequest,
    QueryResponse,
    SourceReference,
    MessageHistoryResponse,
    MessageInfo,
    DeleteChatResponse,
)
import uuid
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chats"])


# Chat CRUD

@router.post("/chats", response_model=CreateChatResponse, status_code=status.HTTP_201_CREATED)
def create_chat(
    body: CreateChatRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a new chat session."""
    uid = current_user["uid"]
    chat_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    title = body.title or "New Chat"

    db = get_db()
    db.collection("chats").document(chat_id).set(
        {
            "chatId": chat_id,
            "userId": uid,
            "title": title,
            "createdAt": now,
            "updatedAt": now,
            "documentCount": 0,
        }
    )

    # Ensure user profile exists
    user_ref = db.collection("users").document(uid)
    if not user_ref.get().exists:
        user_ref.set(
            {
                "uid": uid,
                "email": current_user.get("email", ""),
                "name": current_user.get("name", ""),
                "createdAt": now,
            }
        )

    logger.info(f"Created chat '{chat_id}' for user '{uid}'")
    return CreateChatResponse(chat_id=chat_id, title=title, created_at=now)


@router.get("/chats", response_model=ChatListResponse)
def list_chats(current_user: dict = Depends(get_current_user)):
    """List all chats for the current user, ordered by most recent."""
    uid = current_user["uid"]
    db = get_db()

    chats_query = (
        db.collection("chats")
        .where("userId", "==", uid)
        .get()
    )

    chat_list = []
    for doc in chats_query:
        d = doc.to_dict()
        chat_list.append(
            ChatInfo(
                chat_id=d.get("chatId", doc.id),
                title=d.get("title", "Untitled"),
                created_at=d.get("createdAt", ""),
                updated_at=d.get("updatedAt", ""),
                document_count=d.get("documentCount", 0),
            )
        )
        
    # Sort in memory by updatedAt DESCENDING to avoid requiring a composite index
    chat_list.sort(key=lambda x: x.updated_at, reverse=True)
    chat_list = chat_list[:50]

    return ChatListResponse(chats=chat_list, total=len(chat_list))


@router.delete("/chats/{chat_id}", response_model=DeleteChatResponse)
def delete_chat(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a chat and all its data (Pinecone namespace + Firestore)."""
    uid = current_user["uid"]
    db = get_db()

    chat_ref = db.collection("chats").document(chat_id)
    chat = chat_ref.get()
    if not chat.exists:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if chat.to_dict().get("userId") != uid:
        raise HTTPException(status_code=403, detail="Not authorized.")

    try:
        # Delete Pinecone namespace
        delete_namespace(namespace=chat_id)

        # Delete Firestore subcollections (documents + messages)
        for sub in ["documents", "messages"]:
            sub_docs = chat_ref.collection(sub).get()
            for sub_doc in sub_docs:
                sub_doc.reference.delete()

        # Delete chat document
        chat_ref.delete()

        logger.info(f"Deleted chat '{chat_id}' for user '{uid}'")
        return DeleteChatResponse(chat_id=chat_id, message="Chat deleted successfully.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete chat failed: {e}")
        raise HTTPException(status_code=500, detail=f"Delete failed: {str(e)}")


# Query (RAG)

@router.post("/chats/{chat_id}/query", response_model=QueryResponse)
def query_chat(
    chat_id: str,
    body: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Full RAG pipeline:
    1. Retrieve relevant chunks from Pinecone
    2. Build context
    3. Generate answer via LLM
    4. Save to Firestore + log
    5. Return answer with sources
    """
    uid = current_user["uid"]
    db = get_db()

    # Verify chat ownership
    chat_ref = db.collection("chats").document(chat_id)
    chat = chat_ref.get()
    if not chat.exists:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if chat.to_dict().get("userId") != uid:
        raise HTTPException(status_code=403, detail="Not authorized.")

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # --- Retrieve chat history for session memory (last 6 exchanges) ---
    history_docs = (
        chat_ref.collection("messages")
        .order_by("timestamp", direction="ASCENDING")
        .limit_to_last(12)
        .get()
    )
    chat_history = [
        {"role": d.to_dict().get("role"), "content": d.to_dict().get("content")}
        for d in history_docs
    ]

    # --- Intent Routing & Query Optimization ---
    routing_result = route_query(query, chat_history)
    
    if routing_result.get("type") == "chat":
        # Chitchat intent: bypass Pinecone and generation entirely
        answer = routing_result.get("response", "I'm here to help you analyze your documents.")
        sources = []
        has_context = False
    else:
        # Search intent: use the optimized query for retrieval
        search_query = routing_result.get("optimized_query", query)
        logger.info(f"Original query: '{query}' | Optimized query: '{search_query}'")
        
        # --- RAG Retrieval ---
        try:
            sources = retrieve_relevant_chunks(
                chat_id=chat_id,
                query=search_query,
                top_k=body.top_k,
                threshold=body.threshold,
                file_id=body.file_id,
            )
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

        has_context = len(sources) > 0
        context = build_context_string(sources)

        # --- Generate Answer ---
        try:
            answer = generate_answer(query=query, context=context, chat_history=chat_history)
        except RuntimeError as e:
            raise HTTPException(status_code=503, detail=str(e))

    # --- Build Source References ---
    source_refs = [
        SourceReference(
            file_id=s["file_id"],
            file_name=s["file_name"],
            page=s["page"],
            score=s["score"],
            excerpt=s["text"][:300],
        )
        for s in sources
    ]

    # --- Save messages to Firestore ---
    now = datetime.now(timezone.utc).isoformat()
    user_msg_id = str(uuid.uuid4())
    ai_msg_id = str(uuid.uuid4())

    messages_ref = chat_ref.collection("messages")
    messages_ref.document(user_msg_id).set(
        {"messageId": user_msg_id, "role": "user", "content": query, "timestamp": now}
    )
    messages_ref.document(ai_msg_id).set(
        {
            "messageId": ai_msg_id,
            "role": "assistant",
            "content": answer,
            "timestamp": now,
            "sources": [s.model_dump() for s in source_refs],
            "querySettings": {
                "topK": body.top_k,
                "threshold": body.threshold,
                "fileId": body.file_id,
            },
        }
    )

    # --- Auto-generate title on first message ---
    chat_data = chat.to_dict()
    if chat_data.get("title") == "New Chat":
        try:
            title = generate_chat_title(query)
            chat_ref.update({"title": title, "updatedAt": now})
        except Exception:
            chat_ref.update({"updatedAt": now})
    else:
        chat_ref.update({"updatedAt": now})

    # Logging block removed

    logger.info(f"Query answered: {len(source_refs)} sources, has_context={has_context}")

    return QueryResponse(
        answer=answer,
        sources=source_refs,
        query=query,
        message_id=ai_msg_id,
        has_context=has_context,
    )


# Message History

@router.get("/chats/{chat_id}/messages", response_model=MessageHistoryResponse)
def get_chat_history(
    chat_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get all messages in a chat, ordered chronologically."""
    uid = current_user["uid"]
    db = get_db()

    chat_ref = db.collection("chats").document(chat_id)
    chat = chat_ref.get()
    if not chat.exists:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if chat.to_dict().get("userId") != uid:
        raise HTTPException(status_code=403, detail="Not authorized.")

    messages_docs = (
        chat_ref.collection("messages")
        .order_by("timestamp", direction="ASCENDING")
        .get()
    )

    messages = []
    for doc in messages_docs:
        d = doc.to_dict()
        raw_sources = d.get("sources", [])
        parsed_sources = None
        if raw_sources:
            try:
                parsed_sources = [SourceReference(**s) for s in raw_sources]
            except Exception:
                parsed_sources = None

        messages.append(
            MessageInfo(
                message_id=d.get("messageId", doc.id),
                role=d.get("role", "user"),
                content=d.get("content", ""),
                timestamp=d.get("timestamp", ""),
                sources=parsed_sources,
                query_settings=d.get("querySettings"),
            )
        )

    return MessageHistoryResponse(chat_id=chat_id, messages=messages, total=len(messages))
