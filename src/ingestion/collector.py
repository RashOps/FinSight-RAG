import time
import random
import hashlib
import httpx
import feedparser
import pymongo
from pymongo import UpdateOne
from datetime import datetime, timezone
from src.ingestion.source import RSS_FEEDS
from src.utils.date_parser import standardize_date
from trafilatura import fetch_url, extract
from src.utils.logger import get_logger
from src.utils.db_client import get_db

# Test RSS Link
test_feed = {
    "yahoo": RSS_FEEDS["yahoo_top_stories"],
    "investing": RSS_FEEDS["investing_com"]
}

# Header for scraping
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

# Logger
logger = get_logger(__name__)

def fecth_link(url: str) -> str:
    """Get Primary market news"""
    logger.debug("Lancement de la fonction de chargement du contenu du flux RSS")
    try:
        client = httpx.Client(timeout=10, headers=DEFAULT_HEADERS)
        text = client.get(url).text
        logger.info("Flux RSS chargé avec succès")
        time.sleep(random.uniform(0.5, 2.5))
        return text
    except Exception as e:
        logger.error("Echec lors du chargement du flux: %s", e)
        raise Exception(f"Impossible de charger le flux RSS: {e}")

def parse_news(link: str):
    """Get news and the channel info"""
    logger.debug("Debut du parsing des articles...")
    try:
        data = feedparser.parse(link)
        logger.info("Articles chargés et parsés avec succès")
        return data.entries, data.feed
    except Exception as e:
        logger.error("Echec lors du parsage du flux: %s", e)
        raise Exception(f"Impossible de parser, vérifier le contenu de la page: {e}")

def fetch_text(article_link: str):
    """Get article text via Trafilatura"""
    logger.debug("Chargement du contenu de chaque article")
    try:
        html = fetch_url(article_link)
        result = extract(
            filecontent=html, 
            output_format="txt", 
            include_comments=False, 
            include_tables=True, 
            with_metadata=False
        )
        time.sleep(random.uniform(0.5, 2.0))
        return result
    except Exception as e:
        logger.error("Echec lors de l'extraction du contenu de l'article %s :", e)
        raise Exception(f"Echec lors de l'extraction du contenu de l'article: {e}")

def generate_hash(text: str) -> str:
    """Generate SHA256 hash for absolute deduplication"""
    logger.debug("Lancement des hashages...")
    try:
        formatted_text = text.lower().replace(" ", "").strip()
        byte = formatted_text.encode(encoding="utf-8")
        logger.info("Hashage du contenu correctement effectué")
        return hashlib.sha256(byte).hexdigest()
    except Exception as e:
        logger.error("Une erreur est survenue lors du hashage %s :", e)
        raise Exception(f"Erreur lors du hashage du contenue: {e}")

def create_payload(entries, feed, numb_articles=5):
    """
    Create article payload for BD
    """
    logger.debug("Lancement de la creation des payloads")

    def get_date(info_dict):
        """
        Get the published date
        """
        logger.debug("Chargement de la date de publication")
        if info_dict.get("updated"):
            return info_dict.get("updated")
        elif info_dict.get("published"):
            return info_dict.get("published")
        return None

    def get_description(info_dict):
        """
        Get the article description
        """
        logger.debug("Chargment du résumé de l'article si existant")
        if info_dict.get("summary"):
            return info_dict.get("summary")
        elif info_dict.get("description"):
            return info_dict.get("description")
        return ""

    list_article = []

    try: 
        for info in entries[:numb_articles]:
            content = fetch_text(info.link)
            summary = get_description(info)

            if not content and not summary:
                logger.warning(f"Article ignoré (vide) : {info.title}")
                continue
           
            list_article.append(
                {
                "_id": generate_hash(info.link),            
                "source": feed.title,
                "title": info.title,
                "title_hash": generate_hash(info.title), 
                "summary": summary,             
                "content": content,        
                "url": info.link,
                "published_at": standardize_date(get_date(info)), 
                "language": feed.get("language", "en"),       
                "vectorized": False,               
                "vectorized_at": None,
                "qdrant_chunk_ids": []             
                } 
            )
        logger.info("Liste de payload créée avec succès: %s", len(list_article))
        return list_article 
    except Exception as e:
        logger.error("Erreur lors de la création du payload: %s: ", e)
        raise Exception(f"Echec de la création du payload: {e}")

def setup_database_indexes():
    """
    Index creation for payload in MongoDB
    """
    logger.debug("Creation des index pour mongo DB")

    db = get_db()
    collection = db["news-scraped"]

    collection.create_index(
        [("_id", pymongo.ASCENDING)],
        name="_id",
    )

    collection.create_index(
        [("ingested_at", pymongo.DESCENDING)],
        expireAfterSeconds=2592000,  
        name="ingested_at"
    )

def save_news_to_db(news_list: list) -> None:
    """Saves news to database. Applies a 30-day TTL on `ingested_at`."""
    logger.debug("Chargement des payloads en DB")

    try:
        db = get_db()
        collection = db["news-scraped"]
        logger.info("Connexion reussie")
    except Exception as e:
        logger.error("Erreur lors de la connexion à la DB: %s", e)
        raise Exception(f"Erreur de connexion DB: {e}")

    operations = []
    ingested_at = datetime.now(timezone.utc)

    for article in news_list:
        if article:
            article["ingested_at"] = ingested_at
            news = UpdateOne(filter={"_id": article["_id"]}, update={"$set": article}, upsert=True)
            operations.append(news)

    logger.info("Nombre d'opérations détecté: %s", len(operations))

    if operations:
        collection.bulk_write(operations)
        logger.info("Insertion dans la DB réussie: %s", len(operations))
    else:
        logger.error("Aucune operation détecté")

if __name__ == "__main__":
    for test_url in test_feed:
        url = fecth_link(test_feed[test_url])
        entries, feed_info = parse_news(url)
        news = create_payload(entries, feed_info, numb_articles=3)
        save_news_to_db(news)
