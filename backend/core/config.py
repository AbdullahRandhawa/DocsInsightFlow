from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    # Firebase Admin SDK
    FIREBASE_PROJECT_ID: str
    FIREBASE_PRIVATE_KEY_ID: str
    FIREBASE_PRIVATE_KEY: str
    FIREBASE_CLIENT_EMAIL: str
    FIREBASE_CLIENT_ID: str
    FIREBASE_CLIENT_CERT_URL: str

    # Pinecone
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "docsinsightflow"

    # Cloudinary
    CLOUDINARY_CLOUD_NAME: str
    CLOUDINARY_API_KEY: str
    CLOUDINARY_API_SECRET: str

    # OpenRouter
    OPENROUTER_API_KEY: str
    OPENROUTER_MODEL: str = "deepseek/deepseek-v4-flash"

    # App Settings
    CORS_ORIGINS: str = "http://localhost:5173"
    MAX_PDF_SIZE_MB: int = 20
    MAX_PDFS_PER_CHAT: int = 3
    DEFAULT_CHUNK_SIZE: int = 500
    DEFAULT_CHUNK_OVERLAP: int = 50
    DEFAULT_TOP_K: int = 5
    DEFAULT_THRESHOLD: float = 0.5

    # Embedding model (OpenRouter)
    EMBEDDING_MODEL: str = "openai/text-embedding-3-small"
    EMBEDDING_DIMENSION: int = 1536

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def max_pdf_size_bytes(self) -> int:
        return self.MAX_PDF_SIZE_MB * 1024 * 1024

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
