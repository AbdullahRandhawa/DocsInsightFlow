from fastapi import APIRouter, HTTPException, Depends, status, Query
from fastapi.responses import StreamingResponse
from core.firebase import get_db
from core.pinecone_client import delete_namespace
from modules.retriever import retrieve_relevant_chunks, build_context_string
from modules.generator import generate_chat_title
from modules.rag_pipeline import execute_chat_pipeline, stream_chat_pipeline
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
from datetime import datetime, timezone, timedelta

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

    # --- Retrieve Global Summary ---
    # We fetch this unconditionally because the Generator needs it regardless of vector search
    docs_ref = chat_ref.collection("documents").where("status", "==", "ready").get()
    summaries = []
    selected_file_name = None
    for d in docs_ref:
        doc_data = d.to_dict()
        if body.file_id and doc_data.get("fileId") != body.file_id:
            continue
        if body.file_id and doc_data.get("fileId") == body.file_id:
            selected_file_name = doc_data.get("fileName", "Unknown")
        if "summary" in doc_data and doc_data["summary"]:
            summaries.append(f"Document: {doc_data.get('fileName', 'Unknown')}\nSummary: {doc_data['summary']}")
    
    global_summary = "\n\n".join(summaries) if summaries else None

    # --- Execute RAG Pipeline ---
    try:
        answer, sources = execute_chat_pipeline(
            query=query,
            chat_history=chat_history,
            global_summary=global_summary,
            chat_id=chat_id,
            top_k=body.top_k,
            threshold=body.threshold,
            file_id=body.file_id,
            selected_file_name=selected_file_name,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    # --- Build Source References ---
    # Use core_text (the original matched chunk) for the excerpt display,
    # not the expanded text which is only for LLM context.
    source_refs = [
        SourceReference(
            file_id=s["file_id"],
            file_name=s["file_name"],
            page=s["page"],
            score=s["score"],
            excerpt=s.get("core_text", s["text"])[:300],
        )
        for s in sources
    ]

    # --- Save messages to Firestore ---
    user_now = datetime.now(timezone.utc)
    ai_now = user_now + timedelta(milliseconds=10)
    
    user_msg_id = str(uuid.uuid4())
    ai_msg_id = str(uuid.uuid4())

    messages_ref = chat_ref.collection("messages")
    messages_ref.document(user_msg_id).set(
        {"messageId": user_msg_id, "role": "user", "content": query, "timestamp": user_now.isoformat()}
    )
    messages_ref.document(ai_msg_id).set(
        {
            "messageId": ai_msg_id,
            "role": "assistant",
            "content": answer,
            "timestamp": ai_now.isoformat(),
            "sources": [s.model_dump() for s in source_refs],
            "querySettings": {
                "topK": body.top_k,
                "threshold": body.threshold,
                "fileId": body.file_id,
            },
        }
    )

    # --- Update Chat Metadata ---
    chat_update_data = {"updatedAt": user_now.isoformat()}
    
    # If this is the very first message, set the chat title
    if chat.to_dict().get("title") == "New Chat":
        new_title = generate_chat_title(query)
        chat_update_data["title"] = new_title

    # If it's a new chat, try to link documents from a temp list
    if not chat.to_dict().get("documents"):
        try:
            pending_docs = db.collection("temp_docs").document(uid).get()
            if pending_docs.exists:
                docs_list = pending_docs.to_dict().get("docs", [])
                for d in docs_list:
                    # just move them over conceptually or copy them
                    pass
        except Exception:
            pass

    chat_ref.update(chat_update_data)

    # Logging block removed

    has_context = len(source_refs) > 0
    logger.info(f"Query answered: {len(source_refs)} sources, has_context={has_context}")

    return QueryResponse(
        answer=answer,
        sources=source_refs,
        query=query,
        message_id=ai_msg_id,
        has_context=has_context,
    )


# ─── Streaming Endpoint ───────────────────────────────────────────────────────

@router.post("/chats/{chat_id}/stream")
def stream_chat(
    chat_id: str,
    body: QueryRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Streaming RAG pipeline via Server-Sent Events.
    Yields JSON events: status | token | done | error.
    Firestore persistence is triggered when the 'done' event fires.
    """
    uid = current_user["uid"]
    db = get_db()

    chat_ref = db.collection("chats").document(chat_id)
    chat = chat_ref.get()
    if not chat.exists:
        raise HTTPException(status_code=404, detail="Chat not found.")
    if chat.to_dict().get("userId") != uid:
        raise HTTPException(status_code=403, detail="Not authorized.")

    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty.")

    # --- Chat history ---
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

    # --- Global Summary ---
    docs_ref = chat_ref.collection("documents").where("status", "==", "ready").get()
    summaries = []
    selected_file_name = None
    for d in docs_ref:
        doc_data = d.to_dict()
        if body.file_id and doc_data.get("fileId") != body.file_id:
            continue
        if body.file_id and doc_data.get("fileId") == body.file_id:
            selected_file_name = doc_data.get("fileName", "Unknown")
        if "summary" in doc_data and doc_data["summary"]:
            summaries.append(f"Document: {doc_data.get('fileName', 'Unknown')}\nSummary: {doc_data['summary']}")
    global_summary = "\n\n".join(summaries) if summaries else None

    def event_stream():
        import json
        full_answer_parts = []
        final_sources = []
        has_context = False

        try:
            for event_str in stream_chat_pipeline(
                query=query,
                chat_history=chat_history,
                global_summary=global_summary,
                chat_id=chat_id,
                top_k=body.top_k,
                threshold=body.threshold,
                file_id=body.file_id,
                selected_file_name=selected_file_name,
            ):
                # Parse event to accumulate the full answer and capture done metadata
                if event_str.startswith("data: "):
                    try:
                        ev = json.loads(event_str[6:])
                        if ev.get("type") == "token":
                            full_answer_parts.append(ev.get("text", ""))
                        elif ev.get("type") == "done":
                            final_sources = ev.get("sources", [])
                            has_context = ev.get("has_context", False)
                    except json.JSONDecodeError:
                        pass

                yield event_str

        except Exception as e:
            logger.error(f"[Stream] Unexpected error in event_stream: {e}")
            yield f'data: {{"type": "error", "message": "Internal server error"}}\n\n'
            return

        # --- Persist to Firestore after stream completes ---
        try:
            full_answer = "".join(full_answer_parts)
            now = datetime.now(timezone.utc)
            ai_now = now + timedelta(milliseconds=10)
            user_msg_id = str(uuid.uuid4())
            ai_msg_id = str(uuid.uuid4())

            messages_ref = chat_ref.collection("messages")
            messages_ref.document(user_msg_id).set(
                {"messageId": user_msg_id, "role": "user", "content": query, "timestamp": now.isoformat()}
            )
            messages_ref.document(ai_msg_id).set(
                {
                    "messageId": ai_msg_id,
                    "role": "assistant",
                    "content": full_answer,
                    "timestamp": ai_now.isoformat(),
                    "sources": final_sources,
                    "querySettings": {
                        "topK": body.top_k,
                        "threshold": body.threshold,
                        "fileId": body.file_id,
                    },
                }
            )

            chat_update = {"updatedAt": now.isoformat()}
            if chat.to_dict().get("title") == "New Chat":
                chat_update["title"] = generate_chat_title(query)
            chat_ref.update(chat_update)

            # Send final event with message_id so frontend can track the message
            yield f'data: {{"type": "saved", "message_id": "{ai_msg_id}", "user_message_id": "{user_msg_id}"}}\n\n'

        except Exception as e:
            logger.error(f"[Stream] Firestore save failed: {e}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
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
