from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

class Settings(BaseSettings):
    """
    Centralized configuration management for FinSight RAG.
    Loads variables from the .env file and environment.
    
    """

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore")
    
    # Database - MongoDB
    mongo_uri: str = Field(default="mongodb://localhost:27017/", description="MongoDB connection URI")
    mongo_db_name: str = Field(default="finsight-news", description="Main database name")

    # Database - Qdrant Cloud (Vector Database)
    qdrant_url: str = Field(..., description="Qdrant Database Link")
    qdrant_api_key: str = Field(..., description="Qdrant API Key - Connection")

    # Embbeding LLM
    cohere_api_key: str = Field(default="sentence-transformers/all-minilm-l6-v2", description="COHERE API KEY")
    embedding_model: str = Field(default="sentence-transformers/all-minilm-l6-v2", description="HuggingFace Embedding Model")

    # Groq LLM 
    groq_api_key: str = Field(..., description="GROQ API KEY")

    # Chunks size
    chunks : int = Field(default=512, description="The size of the chunks")

    # Log
    logs_dir: Path = Field(default=PROJECT_ROOT / "logs", description="Log Folder Directory")

    # Cors API Settings
    cors_origins: list[str] = Field(
        default=["http://localhost:3000"],
        description="Allowed CORS origins"
    )

settings = Settings()
