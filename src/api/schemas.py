from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Optional, List
from datetime import datetime
from urllib.parse import urlparse

class QueryRequest(BaseModel):
    """Schema for RAG query requests"""
    query: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="The user's question about financial data"
    )

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize query"""
        v = v.strip()
        if not v:
            raise ValueError('Query cannot be empty')

        # Convert to lowercase for case-insensitive checking
        lower_v = v.lower()

        # SQL injection protection - check for dangerous keywords
        dangerous_keywords = [
            'select', 'insert', 'update', 'delete', 'drop', 'create', 'alter',
            'exec', 'execute', 'union', 'script', 'javascript', 'vbscript',
            'onload', 'onerror', 'eval', 'alert', 'document.cookie'
        ]

        for keyword in dangerous_keywords:
            if keyword in lower_v:
                raise ValueError(f'Query contains potentially dangerous content: {keyword}')

        # Basic character-based protection
        dangerous_chars = [';', '--', '/*', '*/', 'xp_', 'sp_']
        for char in dangerous_chars:
            if char in lower_v:
                raise ValueError(f'Query contains potentially dangerous characters: {char}')

        return v

class QueryResponse(BaseModel):
    """Schema for RAG query responses"""
    answer: str = Field(
        ...,
        description="The AI-generated answer based on retrieved documents"
    )
    confidence_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Confidence score of the answer (0.0 to 1.0)"
    )
    sources_used: Optional[List[str]] = Field(
        default_factory=list,
        description="List of source URLs used to generate the answer"
    )
    processing_time: Optional[float] = Field(
        default=None,
        ge=0.0,
        description="Time taken to process the query in seconds"
    )

class ArticleSchema(BaseModel):
    """Schema for article data"""
    id: str = Field(..., alias="_id", description="MongoDB document ID")
    source: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="News source name"
    )
    title: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Article title"
    )
    summary: Optional[str] = Field(
        default=None,
        max_length=2000,
        description="Article summary"
    )
    content: str = Field(
        ...,
        min_length=10,
        max_length=50000,
        description="Full article content"
    )
    url: str = Field(
        ...,
        description="Article URL"
    )
    published_at: str = Field(
        ...,
        description="Publication date in ISO format"
    )
    language: str = Field(
        default="en",
        min_length=2,
        max_length=5,
        description="Article language code"
    )
    vectorized: bool = Field(
        default=False,
        description="Whether the article has been vectorized"
    )
    vectorized_at: Optional[str] = Field(
        default=None,
        description="Vectorization timestamp in ISO format"
    )
    qdrant_chunk_ids: List[str] = Field(
        default_factory=list,
        description="IDs of chunks stored in Qdrant"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={
            datetime: lambda v: v.isoformat()
        }
    )

    @field_validator('url')
    @classmethod
    def validate_url(cls, v: str) -> str:
        """Validate URL format"""
        try:
            parsed = urlparse(v)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError('Invalid URL format')
            if parsed.scheme not in ['http', 'https']:
                raise ValueError('URL must use HTTP or HTTPS protocol')
        except Exception:
            raise ValueError('Invalid URL format')
        return v

    @field_validator('published_at', 'vectorized_at')
    @classmethod
    def validate_datetime(cls, v: Optional[str]) -> Optional[str]:
        """Validate datetime string format"""
        if v is None:
            return v
        try:
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError('Datetime must be in ISO format')
        return v

class HealthResponse(BaseModel):
    """Schema for health check responses"""
    status: str = Field(..., description="Service status")
    message: str = Field(..., description="Status message")
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    version: str = Field(default="1.0.0", description="API version")

class DatabaseStatusResponse(BaseModel):
    """Schema for database status responses"""
    message: str
    collection: str
    document_count: Optional[int] = None
    last_updated: Optional[str] = None

class ArticleStatusResponse(BaseModel):
    """Schema for article status summary"""
    total_articles: int
    vectorized_articles: int
    non_vectorized_articles: int
    last_ingestion: Optional[str] = None