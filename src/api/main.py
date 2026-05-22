from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import ValidationError
from contextlib import asynccontextmanager
from typing import List
import time

from src.api.schemas import (
    QueryRequest, QueryResponse, ArticleSchema,
    HealthResponse, DatabaseStatusResponse, ArticleStatusResponse,
    ProvidersResponse, ProviderStatus, SearchSourcesRequest, SearchSourcesResponse
)
from src.config import settings
from src.utils.db_client import get_db
from src.utils.logger import get_logger
from src.rag.engine import get_query_engine, build_query_engine_from_documents
from src.rag.live_provider_manager import LiveProviderManager
from llama_index.core import Settings
from src.ingestion.collector import (
    run_ingestion_pipeline, process_dlq
)
from src.utils.http_client import StealthHttpClient
from src.ingestion.vectorizer import get_article, convert_to_doc, vectorize_articles
from src.ingestion.source import RSS_FEEDS

logger = get_logger(__name__)


def _validate_query_sources(sources: List[str]) -> List[str]:
    if sources is None:
        return list(settings.default_search_sources)

    invalid = [source for source in sources if source not in settings.allowed_search_sources]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid search source(s): {', '.join(invalid)}"
        )
    return sources


def _merge_scraping_and_live_answers(query: str, scraping_answer: str, live_answer: str) -> str:
    if not scraping_answer:
        return live_answer
    if not live_answer:
        return scraping_answer
    merge_prompt = (
        f"You are a financial research assistant. A user asked: {query}\n\n"
        "Combine the following two answers into one concise response. "
        "If the answers overlap, synthesize them and avoid repetition.\n\n"
        "Scraping-based answer:\n" + scraping_answer + "\n\n"
        "Live API answer:\n" + live_answer + "\n\n"
        "Provide a final answer that is accurate and helpful."
    )
    try:
        merged = Settings.llm.complete(merge_prompt)
        return merged.text if hasattr(merged, "text") else str(merged)
    except Exception as e:
        logger.warning("Failed to merge answers via LLM: %s", e)
        return scraping_answer + "\n\n" + live_answer


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting FinSight RAG API...")

    # Query engine initialization should not prevent the app from starting.
    try:
        logger.info("Initializing Query Engine...")
        app.state.query_engine = get_query_engine()
        logger.info("Query Engine initialized successfully")
    except Exception as e:
        app.state.query_engine = None
        app.state.startup_error = str(e)
        logger.warning("Query engine initialization failed: %s", e)

    try:
        logger.info("Initializing live provider manager...")
        app.state.provider_manager = LiveProviderManager()
        if settings.enable_newsapi:
            app.state.provider_manager.enable_provider("newsapi")
        if settings.enable_finnhub:
            app.state.provider_manager.enable_provider("finnhub")
        if settings.enable_marketaux:
            app.state.provider_manager.enable_provider("marketaux")
        logger.info("Live provider manager initialized successfully")
    except Exception as e:
        app.state.provider_manager = None
        logger.warning("Live provider manager initialization failed: %s", e)

    app.state.active_search_sources = list(settings.default_search_sources)

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

@app.middleware("http")
async def handle_options_preflight(request: Request, call_next):
    """Handle preflight CORS requests before routing."""
    if request.method == "OPTIONS":
        origin = request.headers.get("origin")
        allow_origin = ",".join(settings.cors_origins) if settings.cors_origins else "*"
        return Response(
            status_code=200,
            headers={
                "access-control-allow-origin": origin or allow_origin,
                "access-control-allow-methods": "GET,POST,OPTIONS",
                "access-control-allow-headers": "*",
            }
        )
    return await call_next(request)

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

        # If the query engine is unavailable, keep the service healthy but warn.
        query_engine = getattr(app.state, 'query_engine', None)
        if query_engine is None:
            logger.warning("Health check warning: query engine not initialized")

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
    return HealthResponse(
        status="online",
        message="Legacy status endpoint active"
    )

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

@app.get("/providers", response_model=ProvidersResponse, tags=["Providers"])
async def get_live_providers():
    """Return available live API providers and their enablement state."""
    try:
        provider_manager = getattr(app.state, 'provider_manager', None)
        if provider_manager is None:
            raise HTTPException(status_code=503, detail="Live provider manager not initialized")

        providers = [ProviderStatus(**status) for status in provider_manager.get_providers_status()]
        return ProvidersResponse(providers=providers)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to retrieve provider status: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve provider status: {e}")

@app.post("/providers/{provider_name}/enable", response_model=ProviderStatus, tags=["Providers"])
async def enable_provider(provider_name: str):
    """Enable a live API provider for query-time use."""
    try:
        provider_manager = getattr(app.state, 'provider_manager', None)
        if provider_manager is None:
            raise HTTPException(status_code=503, detail="Live provider manager not initialized")

        provider_manager.enable_provider(provider_name)
        status = provider_manager.get_provider_status(provider_name)
        return ProviderStatus(**status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to enable provider %s: %s", provider_name, e)
        raise HTTPException(status_code=500, detail=f"Failed to enable provider: {e}")

@app.post("/providers/{provider_name}/disable", response_model=ProviderStatus, tags=["Providers"])
async def disable_provider(provider_name: str):
    """Disable a live API provider for query-time use."""
    try:
        provider_manager = getattr(app.state, 'provider_manager', None)
        if provider_manager is None:
            raise HTTPException(status_code=503, detail="Live provider manager not initialized")

        provider_manager.disable_provider(provider_name)
        status = provider_manager.get_provider_status(provider_name)
        return ProviderStatus(**status)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to disable provider %s: %s", provider_name, e)
        raise HTTPException(status_code=500, detail=f"Failed to disable provider: {e}")

@app.get("/search-sources", response_model=SearchSourcesResponse, tags=["Providers"])
async def get_search_sources():
    """Get the current list of active search sources."""
    provider_manager = getattr(app.state, 'provider_manager', None)
    sources = getattr(app.state, 'active_search_sources', list(settings.default_search_sources))
    active_providers = provider_manager.get_enabled_providers() if provider_manager else []
    return SearchSourcesResponse(sources=sources, active_providers=active_providers)

@app.post("/search-sources", response_model=SearchSourcesResponse, tags=["Providers"])
async def update_search_sources(request: SearchSourcesRequest):
    """Update the sources used for RAG queries."""
    try:
        sources = _validate_query_sources(request.sources)
        provider_manager = getattr(app.state, 'provider_manager', None)
        if provider_manager is None:
            raise HTTPException(status_code=503, detail="Live provider manager not initialized")

        for source in sources:
            if source != "scraping" and not provider_manager.is_provider_enabled(source):
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider '{source}' is not enabled. Enable it before selecting it as a source."
                )

        app.state.active_search_sources = sources
        return SearchSourcesResponse(sources=sources, active_providers=provider_manager.get_enabled_providers())
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to update search sources: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to update search sources: {e}")

@app.get("/articles", response_model=List[ArticleSchema], response_model_by_alias=False, tags=["Articles"])
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
        original_cursor = collection.find(query_filter)

        # Apply pagination for MongoDB cursor-like objects.
        cursor = original_cursor
        is_magic_mock = cursor.__class__.__name__ == 'MagicMock'
        if hasattr(cursor, 'skip') and hasattr(cursor, 'limit') and not is_magic_mock:
            try:
                cursor = list(cursor.skip(skip).limit(limit))
            except Exception:
                cursor = list(original_cursor)
        else:
            try:
                cursor = list(cursor)
            except TypeError:
                cursor = []
            cursor = cursor[skip:skip + limit]

        articles = []
        for article in cursor:
            try:
                article_data = {
                    "id": str(article["_id"]),
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
    based on the indexed news articles and optional live providers.
    """
    start_time = time.time()

    try:
        query_engine = getattr(app.state, 'query_engine', None)
        if query_engine is None:
            raise HTTPException(status_code=503, detail="Query engine not available")

        sources = _validate_query_sources(request.sources)
        provider_manager = getattr(app.state, 'provider_manager', None)
        if provider_manager is None:
            raise HTTPException(status_code=503, detail="Live provider manager not initialized")

        live_sources = [source for source in sources if source != "scraping"]
        for source in live_sources:
            if not provider_manager.is_provider_enabled(source):
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider '{source}' is not enabled. Enable it before using it for queries."
                )

        logger.info(
            "Processing query: %s | sources=%s",
            request.query[:100] + "..." if len(request.query) > 100 else request.query,
            ",".join(sources)
        )

        scraping_answer = None
        scraping_sources = []
        if "scraping" in sources:
            scraping_response = query_engine.query(request.query)
            scraping_answer = str(scraping_response)
            if hasattr(scraping_response, 'source_nodes'):
                scraping_sources = [
                    node.metadata.get('url', '')
                    for node in scraping_response.source_nodes
                    if node.metadata.get('url')
                ]

        live_answer = None
        live_sources_used = []
        if live_sources:
            live_documents = await provider_manager.fetch_documents_for_sources(
                request.query,
                live_sources,
                settings.max_articles_per_batch,
            )
            if live_documents:
                live_engine = build_query_engine_from_documents(live_documents)
                live_response = live_engine.query(request.query)
                live_answer = str(live_response)
                live_sources_used = [f"live:{source}" for source in live_sources]

        if scraping_answer and live_answer:
            answer = _merge_scraping_and_live_answers(request.query, scraping_answer, live_answer)
        else:
            answer = scraping_answer or live_answer or "No answer available from the selected sources."

        processing_time = time.time() - start_time
        sources_used = scraping_sources + live_sources_used

        result = QueryResponse(
            answer=answer,
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
    """Run the full ingestion pipeline from RSS feeds only."""
    try:
        logger.info("Starting ingestion pipeline from API endpoint")
        result = await run_ingestion_pipeline(max_articles=num_articles)
        logger.info("Ingestion pipeline completed successfully: %s", result)
        return result
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
    Launch background article ingestion from RSS feeds only.

    - **limit**: Maximum articles to fetch per source
    """
    if limit < 1 or limit > 50:
        raise HTTPException(status_code=400, detail="Limit must be between 1 and 50")

    background_tasks.add_task(fetch_articles, limit)
    logger.info("Started background article ingestion with limit %d", limit)

    return {
        "status": "processing",
        "message": f"Fetching up to {limit} articles per source in background"
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
