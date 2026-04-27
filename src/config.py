from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator, ValidationError
from pathlib import Path
from typing import List
import os

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    """
    Centralized configuration management for FinSight RAG.
    Loads variables from the .env file and environment with validation.
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Database - MongoDB
    mongo_uri: str = Field(
        default="mongodb://localhost:27017/",
        description="MongoDB connection URI",
        min_length=10
    )
    mongo_db_name: str = Field(
        default="finsight-news",
        description="Main database name",
        min_length=1,
        max_length=64
    )

    # Database - Qdrant Cloud (Vector Database)
    qdrant_url: str = Field(
        ...,
        description="Qdrant Database URL",
        pattern=r"^https?://.+$"
    )
    qdrant_api_key: str = Field(
        ...,
        description="Qdrant API Key",
        min_length=20
    )

    # Embedding LLM
    cohere_api_key: str = Field(
        default="",
        description="Cohere API Key for cloud embeddings"
    )
    cohere_embedding_model: str = Field(
        default="embed-multilingual-light-v3.0",
        description="Cohere embedding model name"
    )
    embedding_model: str = Field(
        default="sentence-transformers/all-MiniLM-L6-v2",
        description="HuggingFace Embedding Model name"
    )

    # Groq LLM
    groq_api_key: str = Field(
        ...,
        description="Groq API Key",
        min_length=20
    )

    # Chunk size
    chunks: int = Field(
        default=512,
        description="The size of the chunks",
        ge=100,
        le=2048
    )

    # Log
    logs_dir: Path = Field(
        default=PROJECT_ROOT / "logs",
        description="Log Folder Directory"
    )

    # API Settings
    cors_origins: List[str] = Field(
        default=["http://localhost:3000", "http://localhost:8000"],
        description="Allowed CORS origins"
    )

    # Processing settings
    max_articles_per_batch: int = Field(
        default=10,
        description="Maximum articles to process in a single batch",
        ge=1,
        le=100
    )

    request_timeout: int = Field(
        default=30,
        description="HTTP request timeout in seconds",
        ge=5,
        le=300
    )

    # HTTP Stealth settings
    http_max_retries: int = Field(
        default=3,
        description="Maximum retry attempts per request",
        ge=1,
        le=10
    )
    http_min_delay: float = Field(
        default=1.0,
        description="Minimum delay between requests (seconds)",
        ge=0.5,
        le=10.0
    )
    http_max_delay: float = Field(
        default=5.0,
        description="Maximum delay between requests (seconds)",
        ge=1.0,
        le=30.0
    )
    http_impersonate: str = Field(
        default="chrome",
        description="Browser to impersonate for TLS fingerprinting"
    )

    # Scrape.do API Integration
    scrape_do_api_key: str = Field(
        default="",
        description="Scrape.do API token for proxy fallback"
    )

    # DLQ Settings
    dlq_max_retries: int = Field(
        default=3,
        description="Maximum number of retries for articles in the DLQ",
        ge=1,
        le=10
    )

    @field_validator('mongo_uri')
    @classmethod
    def validate_mongo_uri(cls, v: str) -> str:
        """Validate MongoDB URI format"""
        if not (v.startswith('mongodb://') or v.startswith('mongodb+srv://')):
            raise ValueError('MongoDB URI must start with mongodb:// or mongodb+srv://')
        return v

    @field_validator('qdrant_url')
    @classmethod
    def validate_qdrant_url(cls, v: str) -> str:
        """Validate Qdrant URL format"""
        if not v.startswith(('http://', 'https://')):
            raise ValueError('Qdrant URL must be a valid HTTP/HTTPS URL')
        return v

    @field_validator('logs_dir')
    @classmethod
    def ensure_logs_dir(cls, v: Path) -> Path:
        """Ensure logs directory exists"""
        v.mkdir(parents=True, exist_ok=True)
        return v

    @field_validator('embedding_model')
    @classmethod
    def validate_embedding_model(cls, v: str) -> str:
        """Validate embedding model name"""
        valid_models = [
            'sentence-transformers/all-MiniLM-L6-v2',
            'sentence-transformers/all-mpnet-base-v2',
            'sentence-transformers/paraphrase-MiniLM-L6-v2'
        ]
        if v not in valid_models and not v.startswith('sentence-transformers/'):
            raise ValueError(f'Embedding model must be one of {valid_models} or a valid sentence-transformers model')
        return v

    @field_validator('cohere_embedding_model')
    @classmethod
    def validate_cohere_embedding_model(cls, v: str) -> str:
        """Validate Cohere embedding model name"""
        if not v or not isinstance(v, str):
            raise ValueError('Cohere embedding model name must be a valid string')
        return v

    def is_cloud_embedding_enabled(self) -> bool:
        """Check if cloud embeddings are configured"""
        return bool(self.cohere_api_key and len(self.cohere_api_key) > 20)

    def get_embedding_provider(self) -> str:
        """Get the current embedding provider"""
        return "cohere" if self.is_cloud_embedding_enabled() else "huggingface"

# Global settings instance
try:
    settings = Settings()
except ValidationError as e:
    print(f"Configuration validation error: {e}")
    raise
