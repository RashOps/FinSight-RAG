from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from src.api.schemas import QueryRequest, QueryResponse, ArticleSchema
from src.config import settings
from src.utils.db_client import get_db
from src.utils.logger import get_logger
from src.rag.engine import get_query_engine
from src.ingestion.vectorizer import get_article, convert_to_doc, update_to_mongodb
from src.ingestion.source import RSS_FEEDS
from src.ingestion.collector import fecth_link, parse_news, create_payload, save_news_to_db

logger = get_logger(__name__)
settings.logs_dir.mkdir(parents=True, exist_ok=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Démarrage : Chargement du modèle en RAM
    logger.info("Chargement du Query Engine...")
    app.state.query_engine = get_query_engine()
    yield
    # Extinction : Nettoyage de la mémoire
    logger.info("Extinction de l'API...")

app = FastAPI(
    title="FinSight RAG API",
    description="MVP Financial RAG.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/app-status", tags=["Health"])
def get_status():
    """Check FinSight Status"""
    return {"status": "online", "message": "FinSight RAG is ready."}

@app.get("/mongodb_status", tags=["DB Connexion"])
def test_db_connexion():
    """Check MongoDB connexion"""
    try:
        db = get_db()
        logger.info("Connexion reussie, collection: %s", db["news-scraped"].name)
        return{
            "message": "Connexion à MongoDB réussi",
            "collection": db["news-scraped"].name
        }
    except Exception as e:
        logger.error("Erreur lors de la connexion à la DB: %s", e)
        raise Exception(f"Erreur de connexion DB: {e}")
    
@app.get("/articles-list", response_model=list[ArticleSchema], tags=["Articles"])
def get_list_articles(status: str = "all"):
    """Get articles lists"""
    try:
        db = get_db()
        collection = db["news-scraped"]
        logger.info("Connexion reussie")
    except Exception as e:
        logger.error("Erreur lors de la connexion à la DB: %s", e)
        raise Exception(f"Erreur de connexion DB: {e}")
    
    query_filter = {}
    if status == "vectorized":
        query_filter = {"vectorized": True}
    elif status == "non-vectorized":
        query_filter = {"vectorized": False}

    # MongoDB filtre
    cursor = collection.find(query_filter).limit(100) # Sécurité : on limite à 100
    
    return [
        {
            "_id": str(article["_id"]),
            "source": article.get("source"),
            "title": article.get("title"),
            "summary": article.get("summary", ""),
            "content": article.get("content", ""),
            "url": article.get("url"),
            "published_at": article["published_at"].isoformat() if article.get("published_at") else None,
            "language": article.get("language", "en"),
            "vectorized": article.get("vectorized", False),
            "vectorized_at": article["vectorized_at"].isoformat() if article.get("vectorized_at") else None,
            "qdrant_chunk_ids": article.get("qdrant_chunk_ids", [])
        }
        for article in cursor
    ]

@app.get("/articles-status", tags=["Articles"])
def get_articles_status():
    """Get all articles status"""
    try:
        db = get_db()
        collection = db["news-scraped"]
        logger.info("Connexion reussie")
    except Exception as e:
        logger.error("Erreur lors de la connexion à la DB: %s", e)
        raise Exception(f"Erreur de connexion DB: {e}")

    # Articles status
    return {
        "Total articles": collection.count_documents({}),
        "Total Non-vectorized articles": collection.count_documents({"vectorized": False}),
        "Total Vectorized articles": collection.count_documents({"vectorized": True})
    }

async def fetch_articles(num_aticles: int = 3):
    """Load new articles content"""
    try:
        for link in RSS_FEEDS:
            url = fecth_link(RSS_FEEDS[link])
            entries, feed_info = parse_news(url)
            news = create_payload(entries, feed_info, num_aticles)
            save_news_to_db(news)
        logger.info("Articles chargées avec succès")
    except Exception as e:
        logger.error("Failed to fetch new articles: %s", e)
        raise Exception(f"Failed to fetch new articles: {e}")
    
@app.post("/fetch-articles", tags=["Articles"])
async def run_fetch_articles(background_tasks: BackgroundTasks, limit: int = 3):
    """Lauching background fetch article"""
    background_tasks.add_task(fetch_articles, limit)
    return {
        "status": "processing", 
        "message": f"Fetch articles {limit} to mongoDB in background."
    }

async def article_vectorizer(limit: int = 10):
    """Run End-to-End Vectorizer pipeline"""
    try:
        db = get_db()
        collection = db["news-scraped"]
        logger.info("Connexion reussie")
    except Exception as e:
        logger.error("Erreur lors de la connexion à la DB: %s", e)
        raise Exception(f"Erreur de connexion DB: {e}")

    while collection.count_documents({"vectorized": False}) > 0:
        data = get_article(limit)
        if not data:
            break
        doc = convert_to_doc(data)
        update_to_mongodb(doc)

@app.post("/run-vectorizer", tags=["Vectorizer"])
async def run_article_vectorizer(background_tasks: BackgroundTasks, limit: int = 10):
    """Lauching background vectorizer and update status"""
    background_tasks.add_task(article_vectorizer, limit)
    return {
        "status": "processing", 
        "message": f"Get articles {limit} from mongoDB -> Convert to doc -> Vectorize and load into Qdrant -> Update MongoDB status."
    }

@app.post("/query", tags=["Query"])
def get_answer(request: QueryRequest):
    """Get RAG answer"""
    engine = app.state.query_engine
    response = engine.query(request.query)

    return QueryResponse(answer=str(response))
