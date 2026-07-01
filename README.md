
# DocsInsightFlow

A **high-performance document intelligence SaaS platform** powered by Retrieval-Augmented Generation (RAG). DocsInsightFlow enables intelligent semantic search and chat-based document analysis through advanced intent routing, vector embeddings, and large language model synthesis.

**Core Mission:** Ingest multi-format documents (PDF, DOCX, TXT) and provide context-aware, document-grounded responses using semantic retrieval and AI-driven synthesis.

---

## 🏗️ Architecture Overview

### Stack
- **Backend:** Python 3.11 | FastAPI 0.115 + Uvicorn
- **Frontend:** React 19 | Vite bundler | TypeScript-ready
- **Languages:** Python (39.4%) | JavaScript (33.2%) | CSS (27.2%)

### Core Technologies
| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Vector Database** | Pinecone (serverless) | Semantic search & chunk storage with metadata filtering |
| **Embeddings** | OpenRouter API (text-embedding-3-small, 1536 dims) | Convert text to dense vectors |
| **LLM** | OpenRouter (DeepSeek v4 Flash) | Intelligent answer generation & query routing |
| **Document Processing** | PyMuPDF, python-docx, LangChain text-splitters | Extract & chunk multi-format documents |
| **Authentication** | Firebase Admin SDK | User identity & session management |
| **Storage** | Firebase Firestore + Cloudinary | Metadata + asset hosting |
| **Frontend UI** | React Router, React Markdown, Lucide, react-dropzone | Rich UI with file upload & markdown rendering |

---

## 📁 Repository Structure

```
backend/
  ├── core/
  │   ├── config.py                Settings & environment variables (Pydantic)
  │   ├── firebase.py              Firebase DB initialization & queries
  │   ├── pinecone_client.py        Vector DB client (upsert, query, delete)
  │   └── cloudinary_client.py      Asset upload & management
  │
  ├── modules/
  │   ├── rag_pipeline.py           ⭐ Master orchestrator (gatekeeper + generation)
  │   ├── document_processor.py      Text extraction & semantic chunking
  │   ├── embeddings.py             OpenRouter embedding client
  │   ├── retriever.py              Vector search + context window expansion
  │   └── generator.py              LLM-powered summaries & chat titles
  │
  ├── routes/
  │   ├── chat.py                   Chat CRUD & streaming endpoints
  │   ├── documents.py              Document upload & deletion (background tasks)
  │   └── auth.py                   Firebase authentication middleware
  │
  ├── schemas/                      Pydantic request/response models
  ├── main.py                       FastAPI app entry point
  └── requirements.txt              Python dependencies

frontend/
  ├── src/
  │   ├── pages/                    Page components (chat, documents, etc.)
  │   ├── components/               Reusable UI components
  │   ├── contexts/                 React Context providers (state management)
  │   ├── lib/                      API clients & utilities
  │   ├── App.jsx                   Root component & routing
  │   ├── main.jsx                  React entry point
  │   └── index.css                 Global styles (~49KB)
  │
  ├── public/                       Static assets
  ├── package.json                  Dependencies & scripts
  ├── vite.config.js                Vite bundler config
  └── index.html                    HTML entry
```

---

## 🚀 Getting Started

### Prerequisites
- **Python 3.11+** (backend)
- **Node.js 18+** (frontend)
- Firebase project with Admin SDK credentials
- Pinecone account with API key
- OpenRouter API key
- Cloudinary account

### Backend Setup

```bash
cd backend
pip install -r requirements.txt
```

Create `.env` file with required environment variables:

```env
# Firebase
FIREBASE_PROJECT_ID=your-project-id
FIREBASE_PRIVATE_KEY_ID=your-key-id
FIREBASE_PRIVATE_KEY=your-private-key
FIREBASE_CLIENT_EMAIL=your-email@firebase.iam.gserviceaccount.com
FIREBASE_CLIENT_ID=your-client-id
FIREBASE_CLIENT_CERT_URL=https://...

# Pinecone
PINECONE_API_KEY=your-pinecone-key
PINECONE_INDEX_NAME=docsinsightflow

# Cloudinary
CLOUDINARY_CLOUD_NAME=your-cloud-name
CLOUDINARY_API_KEY=your-api-key
CLOUDINARY_API_SECRET=your-api-secret

# OpenRouter (LLM & Embeddings)
OPENROUTER_API_KEY=your-openrouter-key
OPENROUTER_MODEL=deepseek/deepseek-v4-flash

# App Settings
CORS_ORIGINS=http://localhost:5173
MAX_PDF_SIZE_MB=20
MAX_PDFS_PER_CHAT=3
DEFAULT_CHUNK_SIZE=500
DEFAULT_CHUNK_OVERLAP=50
DEFAULT_TOP_K=5
DEFAULT_THRESHOLD=0.5
EMBEDDING_MODEL=openai/text-embedding-3-small
EMBEDDING_DIMENSION=1536
```

Run the server:

```bash
uvicorn main:app --reload
# API docs: http://localhost:8000/docs
# Health check: http://localhost:8000/health
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
# Dev server: http://localhost:5173
```

---

## 🎯 Core Features & Technical Deep Dives

### 1. **Intelligent Query Routing (Gatekeeper Pattern)**

**Question:** *How does the gatekeeper pattern in rag_pipeline.py decide between answering directly vs. performing vector search?*

#### Overview
The **gatekeeper LLM** (`route_query()` in `rag_pipeline.py`) acts as intelligent traffic control before expensive vector database queries. It analyzes the user's message in context of chat history and document summaries to decide:
- **Direct Answer Path:** Bypass vector search and answer from history/summary
- **Vector Search Path:** Fetch relevant document chunks from Pinecone

#### Decision Logic
The gatekeeper sets `needs_vector_search = true` if:
- User is asking for **specific facts, metrics, tools, names, or technical details** requiring deep document inspection
- Query contains **ambiguity** or uncertainty (default to search to avoid missing context)

Sets `needs_vector_search = false` if:
- User is making **small talk, greetings, meta-questions** about the app
- Query is **fully covered by Global Document Summary** or recent chat history
- User is asking a **direct follow-up** with 100% matching context already visible

#### Fallback Behaviors for Malformed JSON

If the LLM returns invalid JSON:

1. **JSON Parse Error** (`json.JSONDecodeError`):
   - Caught at line 152 in `rag_pipeline.py`
   - Defaults to: `{"needs_vector_search": True, "optimized_query": query}`
   - Logs warning with raw LLM output for debugging

2. **Missing Fields** (e.g., no `optimized_query` when `needs_vector_search=true`):
   - Detected at line 141
   - Falls back to raw user query: `final_result["optimized_query"] = query`

3. **Unexpected Exception**:
   - Caught at line 155
   - Logs error and defaults to vector search
   - Ensures system continues gracefully

```python
# Fallback behavior in rag_pipeline.py (lines 152-157)
except json.JSONDecodeError as e:
    logger.error(f"[Gatekeeper] JSON parse error: {e} | raw_output='{raw_output[:200]}'")
    return {"needs_vector_search": True, "optimized_query": query}
except Exception as e:
    logger.error(f"[Gatekeeper] Routing failed, defaulting to search: {e}")
    return {"needs_vector_search": True, "optimized_query": query}
```

**Key Resilience Features:**
- ✅ Markdown code fence stripping (handles ```json wrappers)
- ✅ Automatic JSON format validation
- ✅ Conservative fallback to vector search (safety-first)
- ✅ Detailed logging for debugging

---

### 2. **Multi-Page PDF Processing with Page Preservation**

**Question:** *What is the complete flow when a user uploads a multi-page PDF—how are page boundaries preserved through chunking and retrieved in source citations?*

#### Complete Upload & Indexing Flow

**Step 1: Upload & Validation** (routes/documents.py, lines 119–206)
```
User uploads PDF → Backend validates:
  ├─ File type (PDF, DOCX, TXT)
  ├─ File size (< 20 MB default)
  ├─ Document count limit (3 per chat)
  └─ Returns immediately with "processing" status
```

**Step 2: Background Document Processing** (routes/documents.py, lines 38–117)
```
Background task spawned:
  ├─ 1. PDF Extraction (PyMuPDF)
  │    └─ Reads PDF binary → page-by-page text extraction
  │       └─ Each page maintains: {"page": int, "text": str}
  │
  ├─ 2. Text Chunking (LangChain RecursiveCharacterTextSplitter)
  │    └─ Splits each page's text into 500-char chunks (default)
  │    └─ Overlap: 50 chars (prevents context loss at boundaries)
  │    └─ Each chunk preserves: TextChunk(text, page, chunk_id)
  │
  ├─ 3. Embedding Generation (OpenRouter API)
  │    └─ All chunks → 1536-dimensional vectors
  │
  ├─ 4. Pinecone Upsert
  │    └─ Vector ID format: "{doc_id}_chunk_{chunk_id}"
  │    └─ Metadata stored with each vector:
  │        {
  │          "file_id": "doc_id",
  │          "file_name": "document.pdf",
  │          "page": 3,              ← PAGE PRESERVED HERE
  │          "chunk_id": 5,
  │          "text": "chunk content"
  │        }
  │
  └─ 5. Document Summary & Firestore Update
       └─ Mark status = "ready"
```

#### Page Boundary Preservation Strategy

**During Extraction (document_processor.py, lines 28–46):**
```python
def extract_text_from_pdf(pdf_bytes: bytes) -> list[dict]:
    """
    Returns:
    [
      {"page": 1, "text": "page 1 content"},
      {"page": 2, "text": "page 2 content"},
      ...
    ]
    """
    for page_num in range(len(doc)):
        page = doc[page_num]
        text = page.get_text("text")
        cleaned = _clean_text(text)
        if cleaned:
            pages.append({"page": page_num + 1, "text": cleaned})
```

**During Chunking (document_processor.py, lines 94–108):**
```python
# Each TextChunk preserves original page number
chunks.append(
    TextChunk(
        text=text,
        page=page_num,  # ← Original PDF page preserved
        chunk_id=chunk_id_counter,
    )
)
```

**During Vector Storage (routes/documents.py, lines 78–93):**
```python
vectors.append(
    {
        "id": f"{doc_id}_chunk_{chunk.chunk_id}",
        "values": embedding,
        "metadata": {
            "file_id": doc_id,
            "file_name": filename,
            "page": chunk.page,      # ← Stored in Pinecone metadata
            "chunk_id": chunk.chunk_id,
            "text": chunk.text,
        },
    }
)
```

#### Retrieval with Page Citations

**Step 1: Vector Search** (retriever.py, lines 9–110)
```python
# Query returns matches with metadata
raw_matches = query_vectors(
    namespace=chat_id,
    query_vector=query_vector,
    top_k=5,
)
# Returns: [{"id": "...", "score": 0.87, "metadata": {...page: 3...}}]
```

**Step 2: Context Window Expansion** (retriever.py, lines 56–104)
```
For each matched chunk:
  ├─ Extract file_id & chunk_id from metadata
  ├─ Fetch neighboring chunks: chunk_id-1 and chunk_id+1
  ├─ Stitch context: [before] + [core] + [after]
  └─ Return with ORIGINAL page number preserved
      {
        "file_id": "doc_123",
        "file_name": "report.pdf",
        "page": 3,              ← Page preserved for citation
        "chunk_id": 5,
        "text": "expanded context...",
        "core_text": "original match...",
        "score": 0.87
      }
```

**Step 3: Source Citation Display** (routes/chat.py, lines 213–222)
```python
source_refs = [
    SourceReference(
        file_id=s["file_id"],
        file_name=s["file_name"],
        page=s["page"],          # ← Used for citation display
        score=s["score"],
        excerpt=s.get("core_text")[:300],  # Original match text
    )
    for s in sources
]
```

**Frontend Citation Display:**
```
[Context Block 1 | File: report.pdf | Page: 3 | Relevance: 87%]
"The quarterly results show a 15% increase in revenue..."
```

#### Key Design Decisions
- ✅ **Page preservation at extraction time:** Maintains integrity throughout pipeline
- ✅ **Overlap between chunks:** Prevents context loss at page boundaries
- ✅ **Context window expansion:** Retrieves neighboring chunks for richer context
- ✅ **Separate core_text storage:** Original match displayed in citations, expanded text sent to LLM
- ✅ **Metadata filtering:** Users can search within specific documents via `file_id` filter

---

### 3. **Server-Sent Events (SSE) Streaming with Backpressure Handling**

**Question:** *How does the streaming chat endpoint emit SSE events and handle backpressure if the OpenRouter LLM response is slow?*

#### Streaming Architecture

**Endpoint:** `POST /api/v1/chats/{chat_id}/stream`

The streaming endpoint (`routes/chat.py`, lines 288–416) follows this pattern:

```
User sends query
    ↓
[event_stream() generator]
    ├─ Route query via gatekeeper
    ├─ Retrieve vectors (if needed)
    ├─ Stream LLM tokens from OpenRouter
    └─ Persist to Firestore after completion
    ↓
FastAPI StreamingResponse
    ├─ Media type: text/event-stream
    ├─ Headers: Cache-Control, X-Accel-Buffering
    └─ Yields SSE-formatted JSON
    ↓
Client receives real-time tokens
```

#### SSE Event Types Emitted

```python
# From rag_pipeline.py stream_chat_pipeline() (lines 386–460)

# 1. Status events
emit({"type": "status", "message": "Analyzing query..."})
emit({"type": "status", "message": "Searching your documents..."})
emit({"type": "status", "message": "Found 5 relevant sections. Generating answer..."})

# 2. Token events (streamed from LLM)
emit({"type": "token", "text": "The"})
emit({"type": "token", "text": " quarterly"})
emit({"type": "token", "text": " results"})
# ... one token at a time

# 3. Done event (signals completion)
emit({"type": "done", "sources": [...], "has_context": true})

# 4. Error event (if something fails)
emit({"type": "error", "message": "Failed to search documents. Please try again."})
```



#### Backpressure Resilience Features

| Feature | Mechanism | Benefit |
|---------|-----------|---------|
| **Stream Timeouts** | 60-second httpx timeout | Prevents indefinite hangs if OpenRouter is slow |
| **Token-by-Token Yielding** | Generator pattern | Client gets data immediately; no full-response buffering |
| **Non-Blocking Client Processing** | Event stream parsed incrementally | UI updates in real-time without blocking |
| **Error Isolation** | Try-catch around event parsing | Single malformed event doesn't crash stream |
| **Post-Stream Persistence** | Firestore write after completion | Resilient to network interruptions during streaming |
| **Status Events** | Intermediate "Searching...", "Found X sources" | User feedback during long operations |



## 📊 Configuration & Tuning

### Document Processing Settings
```python
# backend/core/config.py
DEFAULT_CHUNK_SIZE=500          # Tokens per chunk
DEFAULT_CHUNK_OVERLAP=50        # Overlap for context
MAX_PDF_SIZE_MB=20              # Max file size
MAX_PDFS_PER_CHAT=3             # Docs per session
```

### Retrieval Parameters
```python
DEFAULT_TOP_K=5                 # Top-k vectors to retrieve
DEFAULT_THRESHOLD=0.5           # Min similarity score (0-1)
EMBEDDING_DIMENSION=1536        # Vector dimensionality
```

### LLM & Routing
```python
OPENROUTER_MODEL=deepseek/deepseek-v4-flash
EMBEDDING_MODEL=openai/text-embedding-3-small
```

---

## 🔒 Security & Authentication

- **Firebase Admin SDK** for user identity verification
- **JWT tokens** via Firebase Auth
- **Ownership checks** on all chat/document operations
- **CORS configuration** via environment variables
- **File type validation** at upload

---

## 📈 Performance Optimization

### Vector Search
- **Namespace partitioning** by chat ID for multi-tenancy
- **Metadata filtering** to limit search scope
- **Context window expansion** for richer retrieval without increasing top_k

### Document Processing
- **Background task dispatch** for non-blocking uploads
- **Batch embedding** via OpenRouter API
- **Batch vector upsert** in Pinecone (100-vector batches)

### Streaming
- **Generator-based event emission** for low-latency token delivery
- **Server-Sent Events** (SSE) for efficient HTTP streaming
- **No buffering** of full responses before streaming begins

---

## 🚨 Error Handling & Resilience

| Scenario | Handling |
|----------|----------|
| Malformed LLM JSON | Defaults to vector search |
| PDF extraction failure | Logs error, marks doc as "failed" |
| Pinecone unavailable | Raises RuntimeError with detail |
| OpenRouter timeout | 60-second timeout fallback |
| Embedding API error | Caught and re-raised with context |
| Stream interruption | Firestore save triggered on completion |

---

## 🧪 Testing & Debugging

### Health Check
```bash
curl http://localhost:8000/health
# Response: {"status": "ok", "service": "DocsInsightFlow API", "version": "1.0.0"}
```

### API Documentation
- **OpenAPI Docs:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

### Logging
All modules log to `INFO` level with structured format:
```
TIMESTAMP | LEVEL | MODULE | MESSAGE
2026-01-15 10:23:45 | INFO | modules.rag_pipeline | [Gatekeeper] needs_search=true | query='What is...'
```

---

## 🤝 Contributing

1. **Backend changes:** Update `backend/requirements.txt` and test with `uvicorn main:app --reload`
2. **Frontend changes:** Test with `npm run dev` (Vite HMR enabled)
3. **Schema changes:** Update Pydantic models in `backend/schemas/`
4. **New endpoints:** Add route in appropriate `backend/routes/*.py` file

---

## 📝 License

[Add your license here]

---

## 🔗 Resources

- **FastAPI:** https://fastapi.tiangolo.com/
- **Pinecone:** https://docs.pinecone.io/
- **OpenRouter:** https://openrouter.ai/docs
- **Firebase Admin SDK:** https://firebase.google.com/docs/admin/setup
- **React 19:** https://react.dev/

---

## 📞 Support

For issues or questions:
1. Check the API docs at `/docs`
2. Review logs in the backend terminal
3. Verify environment variables are set correctly
4. Ensure Pinecone, Firebase, and OpenRouter credentials are valid

---

**Built by Abdullah Naeem**
