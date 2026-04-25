from pydantic import BaseModel, Field
from typing import Optional, List

class QueryRequest(BaseModel):
    query: str

class QueryResponse(BaseModel):
    answer: str

class ArticleSchema(BaseModel):
    id: str = Field(..., alias="_id") 
    source: str
    title: str
    summary: Optional[str] = None
    content: str
    url: str
    published_at: str
    language: str = "en"
    vectorized: bool = False
    vectorized_at: Optional[str] = None
    qdrant_chunk_ids: List[str] = []

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True
    }