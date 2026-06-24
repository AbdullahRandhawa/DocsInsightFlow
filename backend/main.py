from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from core.config import settings
from core.firebase import init_firebase
from core.pinecone_client import init_pinecone
from core.cloudinary_client import init_cloudinary
from modules.embeddings import load_model
from routes import chat, documents
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize all services on startup."""
    logger.info("DocsInsightFlow starting up...")
    try:
        init_firebase()
        init_pinecone()
        init_cloudinary()
        load_model()  # Pre-load embedding model to avoid first-request latency
        logger.info("All services initialized successfully")
    except Exception as e:
        logger.critical(f"Startup failed: {e}")
        raise
    yield
    logger.info("DocsInsightFlow shutting down...")


app = FastAPI(
    title="DocsInsightFlow API",
    description="RAG system powered by Pinecone, OpenRouter embeddings, and DeepSeek LLM",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(chat.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")

# Global Error Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "An internal server error occurred."},
    )


# Health Check
@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "DocsInsightFlow API", "version": "1.0.0"}


@app.get("/", tags=["Health"])
def root():
    return {"message": "Welcome to DocsInsightFlow API. Visit /docs for API documentation."}
