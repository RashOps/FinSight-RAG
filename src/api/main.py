from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from contextlib import asynccontextmanager
from typing import List
import time

from src.api.schemas import (
    QueryRequest, QueryResponse, ArticleSchema,
    HealthResponse, DatabaseStatusResponse, ArticleStatusResponse
)
from src.config import settings
from src.utils.db_client import get_db
from src.utils.logger import get_logger
from src.rag.engine import get_query_engine
from src.ingestion.collector import (
    fetch_link, parse_news, create_payload, save_news_to_db,
    run_ingestion_pipeline, process_dlq
)
from src.utils.http_client import StealthHttpClient
from src.ingestion.vectorizer import get_article, convert_to_doc, vectorize_articles
from src.ingestion.source import RSS_FEEDS

logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting FinSight RAG API...")
    try:
        logger.info("Initializing Query Engine...")
        app.state.query_engine = get_query_engine()
        logger.info("Query Engine initialized successfully")
    except Exception as e:
        logger.error("Failed to initialize Query Engine: %s", e)
        raise

    yield

    # Shutdown
    logger.info("Shutting down FinSight RAG API...")

app = FastAPI(
    title="FinSight RAG API",
    description="Financial RAG system for news analysis and querying",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Middleware to log all requests"""
    start_time = time.time()

    logger.info("Request: %s %s", request.method, request.url.path)

    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        logger.info(
            "Response: %s %s - Status: %d - Time: %.3fs",
            request.method,
            request.url.path,
            response.status_code,
            process_time
        )
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(
            "Request failed: %s %s - Error: %s - Time: %.3fs",
            request.method,
            request.url.path,
            str(e),
            process_time
        )
        raise

@app.get("/", include_in_schema=False)
async def root():
    """Redirige automatiquement vers la documentation Swagger"""
    return RedirectResponse(url="/docs")

@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """Comprehensive health check endpoint"""
    try:
        # Check database connection
        db = get_db()
        db.command('ping')

        # Check if query engine is initialized
        query_engine = getattr(app.state, 'query_engine', None)
        if query_engine is None:
            raise HTTPException(status_code=503, detail="Query engine not initialized")

        return HealthResponse(
            status="healthy",
            message="All systems operational"
        )
    except Exception as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=503, detail=f"Service unhealthy: {str(e)}")

@app.get("/status", response_model=HealthResponse, tags=["Health"])
async def get_status():
    """Legacy status endpoint for backward compatibility"""
    return await health_check()

@app.get("/db/status", response_model=DatabaseStatusResponse, tags=["Database"])
async def test_database_connection():
    """Test MongoDB connection and return status"""
    try:
        db = get_db()
        collection = db["news-scraped"]

        # Get collection stats
        doc_count = collection.count_documents({})

        # Get last document
        last_doc = collection.find_one(sort=[("published_at", -1)])
        last_updated = None
        if last_doc and "published_at" in last_doc:
            last_updated = last_doc["published_at"].isoformat()

        logger.info("Database connection successful - Collection: %s, Documents: %d",
                   collection.name, doc_count)

        return DatabaseStatusResponse(
            message="MongoDB connection successful",
            collection=collection.name,
            document_count=doc_count,
            last_updated=last_updated
        )
    except Exception as e:
        logger.error("Database connection failed: %s", e)
        raise HTTPException(status_code=500, detail=f"Database connection failed: {str(e)}")

@app.get("/articles", response_model=List[ArticleSchema], tags=["Articles"])
async def get_articles(
    status: str = "all",
    limit: int = 50,
    skip: int = 0
):
    """
    Get articles with filtering and pagination

    - **status**: Filter by vectorization status ("all", "vectorized", "non-vectorized")
    - **limit**: Maximum number of articles to return (1-100)
    - **skip**: Number of articles to skip for pagination
    """
    try:
        # Validate parameters
        if limit < 1 or limit > 100:
            raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")
        if skip < 0:
            raise HTTPException(status_code=400, detail="Skip must be non-negative")

        db = get_db()
        collection = db["news-scraped"]

        # Build query filter
        query_filter = {}
        if status == "vectorized":
            query_filter["vectorized"] = True
        elif status == "non-vectorized":
            query_filter["vectorized"] = False
        elif status not in ["all"]:
            raise HTTPException(status_code=400, detail="Invalid status filter")

        # Execute query with pagination
        cursor = collection.find(query_filter)

        # Apply pagination if cursor supports it (real MongoDB), otherwise slice list (mocked)
        if hasattr(cursor, 'skip') and hasattr(cursor, 'limit'):
            cursor = cursor.skip(skip).limit(limit)
        elif isinstance(cursor, list):
            cursor = cursor[skip:skip + limit]
        else:
            # Fallback for other mock types
            try:
                cursor = cursor[skip:skip + limit]
            except (TypeError, AttributeError):
                cursor = []

        articles = []
        for article in cursor:
            try:
                article_data = {
                    "_id": str(article["_id"]),
                    "source": article.get("source", "Unknown"),
                    "title": article.get("title", "Untitled"),
                    "summary": article.get("summary"),
                    "content": article.get("content", ""),
                    "url": article.get("url", ""),
                    "published_at": article["published_at"].isoformat() if article.get("published_at") else "",
                    "language": article.get("language", "en"),
                    "vectorized": article.get("vectorized", False),
                    "vectorized_at": article.get("vectorized_at").isoformat() if article.get("vectorized_at") else None,
                    "qdrant_chunk_ids": article.get("qdrant_chunk_ids", [])
                }
                articles.append(ArticleSchema(**article_data))
            except Exception as e:
                logger.warning("Failed to parse article %s: %s", article.get("_id"), e)
                continue

        logger.info("Retrieved %d articles (status: %s, limit: %d, skip: %d)",
                   len(articles), status, limit, skip)

        return articles

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve articles: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve articles: {str(e)}")

@app.get("/articles/status", response_model=ArticleStatusResponse, tags=["Articles"])
async def get_articles_status():
    """Get comprehensive article statistics"""
    try:
        db = get_db()
        collection = db["news-scraped"]

        total = collection.count_documents({})
        vectorized = collection.count_documents({"vectorized": True})
        non_vectorized = collection.count_documents({"vectorized": False})

        # Get last ingestion timestamp
        last_doc = collection.find_one(sort=[("published_at", -1)])
        last_ingestion = None
        if last_doc and "published_at" in last_doc:
            published_at = last_doc["published_at"]
            # Handle both datetime objects and ISO strings
            if hasattr(published_at, 'isoformat'):
                last_ingestion = published_at.isoformat()
            else:
                last_ingestion = str(published_at)

        return ArticleStatusResponse(
            total_articles=total,
            vectorized_articles=vectorized,
            non_vectorized_articles=non_vectorized,
            last_ingestion=last_ingestion
        )

    except Exception as e:
        logger.error("Failed to get article status: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to get article status: {str(e)}")

@app.post("/query", response_model=QueryResponse, tags=["RAG"])
async def query_financial_data(request: QueryRequest):
    """
    Query the financial RAG system

    Submit a question about financial data and receive an AI-generated answer
    based on the indexed news articles.
    """
    start_time = time.time()

    try:
        # Get query engine
        query_engine = getattr(app.state, 'query_engine', None)
        if query_engine is None:
            raise HTTPException(status_code=503, detail="Query engine not available")

        # Execute query
        logger.info("Processing query: %s", request.query[:100] + "..." if len(request.query) > 100 else request.query)

        response = query_engine.query(request.query)

        processing_time = time.time() - start_time

        # Extract sources if available (this depends on LlamaIndex implementation)
        sources_used = []
        if hasattr(response, 'source_nodes'):
            sources_used = [node.metadata.get('url', '') for node in response.source_nodes if node.metadata.get('url')]

        result = QueryResponse(
            answer=str(response),
            processing_time=round(processing_time, 3),
            sources_used=sources_used
        )

        logger.info("Query processed successfully in %.3fs", processing_time)

        return result

    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error("Query processing failed after %.3fs: %s", processing_time, e)
        error_msg = str(e)
        if "Vector dimension error" in error_msg or "expected dim" in error_msg:
            detail = (
                "Query processing failed due to a vector dimension mismatch. "
                "Please verify that ingestion and query use the same embedding model, "
                "and rebuild/reindex the Qdrant collection if the collection was created with a different embedding dimension."
            )
        else:
            detail = f"Query processing failed: {error_msg}"
        raise HTTPException(status_code=500, detail=detail)

@app.post("/query/async", tags=["RAG"])
async def query_financial_data_async(request: QueryRequest, background_tasks: BackgroundTasks):
    """
    Asynchronous query endpoint (for future implementation)

    This endpoint will allow long-running queries to be processed in the background.
    """
    # Placeholder for future async implementation
    raise HTTPException(status_code=501, detail="Async queries not yet implemented")

# Error handlers
@app.exception_handler(ValidationError)
async def validation_exception_handler(request, exc):
    """Handle Pydantic validation errors"""
    logger.warning("Validation error for %s: %s", request.url.path, exc)
    raise HTTPException(status_code=422, detail=str(exc))

@app.exception_handler(Exception)
async def general_exception_handler(request, exc):
    """Handle unexpected errors"""
    logger.error("Unexpected error for %s: %s", request.url.path, exc)
    raise HTTPException(status_code=500, detail="Internal server error")

# Utility functions for background tasks
async def fetch_articles(num_articles: int = 3):
    """Load new articles from RSS feeds using stealth HTTP client."""
    try:
        async with StealthHttpClient() as client:
            for feed_name, feed_url in RSS_FEEDS.items():
                logger.info("Fetching articles from %s", feed_name)
                rss_content = await fetch_link(client, feed_url)
                entries, feed_info = parse_news(rss_content)
                news = await create_payload(client, entries, feed_info, num_articles)
                if news:
                    save_news_to_db(news)
                    logger.info("Saved %d articles from %s", len(news), feed_name)
        logger.info("Article fetching completed successfully")
    except Exception as e:
        logger.error("Failed to fetch new articles: %s", e)
        raise RuntimeError(f"Failed to fetch new articles: {e}") from e

async def run_vectorization(limit: int = 10):
    """Run vectorization pipeline for non-vectorized articles"""
    try:
        logger.info("Starting vectorization pipeline with limit %d", limit)
        result = vectorize_articles(num_articles=limit)
        logger.info("Vectorization completed: %s", result)
        return result
    except Exception as e:
        logger.error("Vectorization failed: %s", e)
        raise RuntimeError(f"Vectorization failed: {e}") from e

async def run_dlq_processing():
    """Run DLQ processing for failed articles"""
    try:
        logger.info("Starting DLQ background processing")
        async with StealthHttpClient() as client:
            result = await process_dlq(client)
        logger.info("DLQ processing completed: %s", result)
        return result
    except Exception as e:
        logger.error("DLQ processing failed: %s", e)
        raise RuntimeError(f"DLQ processing failed: {e}") from e

# Background task endpoints
@app.post("/fetch-articles", tags=["Ingestion"])
async def run_fetch_articles(background_tasks: BackgroundTasks, limit: int = 3):
    """
    Launch background article fetching from RSS feeds

    - **limit**: Maximum articles to fetch per feed
    """
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 50")

    background_tasks.add_task(fetch_articles, limit)
    logger.info("Started background article fetching with limit %d", limit)

    return {
        "status": "processing",
        "message": f"Fetching up to {limit} articles per feed in background"
    }

@app.post("/run-vectorizer", tags=["Ingestion"])
async def run_article_vectorizer(background_tasks: BackgroundTasks, limit: int = 10):
    """
    Launch background vectorization pipeline

    - **limit**: Maximum articles to vectorize per batch
    """
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 100")

    background_tasks.add_task(run_vectorization, limit)
    logger.info("Started background vectorization with limit %d", limit)

    return {
        "status": "processing",
        "message": f"Vectorizing up to {limit} articles per batch in background"
    }

@app.post("/dlq/retry", tags=["Ingestion"])
async def retry_dlq_articles(background_tasks: BackgroundTasks):
    """
    Launch background processing of the Dead Letter Queue (DLQ).
    
    Attempts to fetch and parse articles that previously failed.
    """
    background_tasks.add_task(run_dlq_processing)
    logger.info("Started background DLQ processing")

    return {
        "status": "processing",
        "message": "Processing Dead Letter Queue in background"
    }
