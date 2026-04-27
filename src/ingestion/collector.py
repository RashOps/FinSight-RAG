"""Financial news collector with stealth HTTP and async pipeline.

Collects articles from RSS feeds using TLS-impersonated HTTP requests,
extracts full-text content via Trafilatura, and persists to MongoDB.
"""

import asyncio
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import feedparser
import pymongo
from pymongo import UpdateOne
from trafilatura import extract

from src.config import settings
from src.ingestion.source import RSS_FEEDS
from src.utils.date_parser import standardize_date
from src.utils.db_client import get_db
from src.utils.http_client import StealthHttpClient
from src.utils.logger import get_logger

# Logger
logger = get_logger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# RSS Fetching & Parsing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def fetch_link(
    client: StealthHttpClient, url: str
) -> str:
    """Fetch RSS feed content using stealth HTTP client.

    Args:
        client: Initialised StealthHttpClient instance.
        url: RSS feed URL to fetch.

    Returns:
        Raw RSS feed content as string.

    Raises:
        RuntimeError: If all HTTP strategies fail.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")

    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise ValueError(f"Invalid URL format: {url}")

    logger.debug("Fetching RSS feed from: %s", url)
    content = await client.get_text(url)

    if not content.strip():
        raise ValueError("Empty response content")

    logger.info("RSS feed fetched successfully from %s", url)
    return content


def parse_news(link: str) -> Tuple[List[Any], Dict[str, Any]]:
    """Parse RSS feed content and extract entries and feed metadata.

    Args:
        link: Raw RSS feed content.

    Returns:
        Tuple of (entries list, feed metadata dict).

    Raises:
        ValueError: If parsing fails or feed is empty.
    """
    if not link or not isinstance(link, str):
        raise ValueError("RSS content must be a non-empty string")

    logger.debug("Parsing RSS feed content")

    try:
        data = feedparser.parse(link)

        if data.bozo:  # feedparser detected an error
            logger.warning("Feedparser detected malformed feed: %s", data.bozo_exception)

        if not hasattr(data, 'entries') or not data.entries:
            raise ValueError("No entries found in RSS feed")

        if not hasattr(data, 'feed'):
            raise ValueError("No feed metadata found")

        entries = data.entries
        feed_info = dict(data.feed) if data.feed else {}

        logger.info("Successfully parsed %d entries from RSS feed", len(entries))
        return entries, feed_info

    except Exception as e:
        logger.error("Failed to parse RSS feed: %s", e)
        raise ValueError(f"RSS parsing failed: {e}") from e


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Article Content Extraction
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def fetch_article_text(
    client: StealthHttpClient, article_url: str
) -> Optional[str]:
    """Extract article text content using Trafilatura.

    Args:
        client: Initialised StealthHttpClient instance.
        article_url: URL of the article to extract.

    Returns:
        Extracted text content, or None if extraction fails.
    """
    if not article_url or not isinstance(article_url, str):
        logger.warning("Invalid article URL provided")
        return None

    logger.debug("Extracting content from article: %s", article_url)

    try:
        html = await client.get_text(article_url)

        if not html:
            logger.warning("No HTML content fetched from %s", article_url)
            return None

        # Extract text via Trafilatura (CPU-bound, run in thread pool)
        result = await asyncio.to_thread(
            extract,
            filecontent=html,
            output_format="txt",
            include_comments=False,
            include_tables=True,
            include_links=False,
            include_images=False,
            with_metadata=False,
        )

        if result and len(result.strip()) > 50:  # Minimum content length
            logger.debug(
                "Successfully extracted %d characters from %s",
                len(result), article_url,
            )
            return result.strip()

        logger.warning("Extracted content too short or empty from %s", article_url)
        return None

    except RuntimeError as e:
        logger.warning("HTTP strategies exhausted for %s: %s", article_url, e)
        return None
    except Exception as e:
        logger.warning("Failed to extract content from %s: %s", article_url, e)
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Hashing & Validation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def generate_content_hash(text: str) -> str:
    """Generate SHA256 hash for content deduplication.

    Args:
        text: Text content to hash.

    Returns:
        SHA256 hash of the normalised content.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Text must be a non-empty string")

    try:
        # Normalize text for consistent hashing
        normalized_text = text.lower().replace(" ", "").strip()
        byte_content = normalized_text.encode(encoding="utf-8")

        hash_obj = hashlib.sha256(byte_content)
        hash_str = hash_obj.hexdigest()

        logger.debug("Generated hash for content: %s...", hash_str[:16])
        return hash_str

    except Exception as e:
        logger.error("Failed to generate content hash: %s", e)
        raise RuntimeError(f"Hash generation failed: {e}") from e


def validate_article_data(article: Dict[str, Any]) -> bool:
    """Validate article data before database insertion.

    Args:
        article: Article data dictionary.

    Returns:
        True if valid, False otherwise.
    """
    required_fields = ['_id', 'title', 'url', 'source', 'published_at']

    for field_name in required_fields:
        if not article.get(field_name):
            logger.warning("Article missing required field: %s", field_name)
            return False

    # Validate URL format
    try:
        parsed = urlparse(article['url'])
        if not parsed.scheme or not parsed.netloc:
            logger.warning("Invalid URL format: %s", article['url'])
            return False
    except Exception:
        logger.warning("URL validation failed for: %s", article['url'])
        return False

    # Check content quality
    content = article.get('content', '')
    summary = article.get('summary', '')

    if len(content.strip()) < 10 and len(summary.strip()) < 10:
        logger.warning("Article has insufficient content: %s", article.get('title', 'Unknown'))
        return False

    return True


def save_to_dlq(article_url: str, title: str, source: str, error_reason: str) -> None:
    """Save a failed article to the Dead Letter Queue for later retry."""
    try:
        db = get_db()
        dlq_collection = db["news-dlq"]
        article_id = generate_content_hash(article_url)
        
        now = datetime.now(timezone.utc)
        
        dlq_collection.update_one(
            {"_id": article_id},
            {
                "$set": {
                    "url": article_url,
                    "title": title,
                    "source": source,
                    "error_reason": error_reason,
                    "last_attempt_at": now,
                },
                "$setOnInsert": {
                    "first_failed_at": now,
                    "status": "pending",
                },
                "$inc": {"retry_count": 1}
            },
            upsert=True
        )
        logger.debug("Saved to DLQ: %s", title)
    except Exception as e:
        logger.error("Failed to save article to DLQ: %s", e)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Payload Creation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def create_payload(
    client: StealthHttpClient,
    entries: List[Any],
    feed: Dict[str, Any],
    numb_articles: int = 5,
) -> List[Dict[str, Any]]:
    """Create article payloads for database with async content fetching.

    Args:
        client: Initialised StealthHttpClient instance.
        entries: RSS feed entries.
        feed: Feed metadata dictionary.
        numb_articles: Maximum number of articles to process.

    Returns:
        List of validated article payload dicts.
    """
    if not entries:
        logger.warning("No entries provided to create_payload")
        return []

    if numb_articles <= 0:
        raise ValueError("numb_articles must be positive")

    logger.debug("Creating payloads for %d articles", min(len(entries), numb_articles))

    articles_payload: List[Dict[str, Any]] = []
    processed_count = 0
    error_count = 0

    for entry in entries[:numb_articles]:
        try:
            # Extract article URL
            article_url = getattr(entry, 'link', None) or getattr(entry, 'url', None)
            if not article_url:
                logger.warning("Article missing URL, skipping")
                error_count += 1
                continue

            # Extract title
            title = getattr(entry, 'title', '').strip()
            if not title:
                logger.warning("Article missing title, skipping")
                error_count += 1
                continue

            # Extract content (async)
            content = await fetch_article_text(client, article_url)
            if not content:
                logger.warning("Failed to extract content for article: %s", title)
                source_name = feed.get('title', 'Unknown Source')
                save_to_dlq(article_url, title, source_name, "Extraction returned empty content or failed")
                error_count += 1
                continue

            # Extract summary/description
            summary = ""
            if hasattr(entry, 'summary'):
                summary = getattr(entry, 'summary', '')
            elif hasattr(entry, 'description'):
                summary = getattr(entry, 'description', '')
            summary = summary.strip()

            # Extract publication date
            published_date = None
            if hasattr(entry, 'updated'):
                published_date = standardize_date(getattr(entry, 'updated', ''))
            elif hasattr(entry, 'published'):
                published_date = standardize_date(getattr(entry, 'published', ''))

            if not published_date:
                logger.warning("Could not parse publication date for article: %s", title)
                # Use current time as fallback
                published_date = datetime.now(timezone.utc)

            # Generate unique ID from URL
            article_id = generate_content_hash(article_url)

            # Extract language
            language = feed.get('language', 'en') or 'en'

            # Extract source name
            source_name = feed.get('title', 'Unknown Source')

            # Create article payload
            article_payload: Dict[str, Any] = {
                "_id": article_id,
                "source": source_name,
                "title": title,
                "title_hash": generate_content_hash(title),
                "summary": summary,
                "content": content,
                "url": article_url,
                "published_at": published_date,
                "language": language,
                "vectorized": False,
                "vectorized_at": None,
                "qdrant_chunk_ids": [],
                "content_length": len(content),
                "summary_length": len(summary),
            }

            # Validate article data
            if validate_article_data(article_payload):
                articles_payload.append(article_payload)
                processed_count += 1
                logger.debug("Successfully created payload for article: %s", title)
            else:
                error_count += 1
                logger.warning("Article validation failed: %s", title)

        except Exception as e:
            error_count += 1
            logger.error("Failed to process article entry: %s", e)
            continue

    logger.info(
        "Payload creation completed: %d successful, %d errors",
        processed_count, error_count,
    )
    return articles_payload


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Database Operations
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


def setup_database_indexes() -> None:
    """Create optimised database indexes for the news collection."""
    logger.debug("Setting up database indexes")

    try:
        db = get_db()
        collection = db["news-scraped"]

        # Unique index on _id (should already exist, but ensure it)
        collection.create_index(
            [("_id", pymongo.ASCENDING)],
            name="unique_id",
            unique=True
        )

        # Index for vectorization status queries
        collection.create_index(
            [("vectorized", pymongo.ASCENDING)],
            name="vectorized_status"
        )

        # Index for publication date queries
        collection.create_index(
            [("published_at", pymongo.DESCENDING)],
            name="publication_date"
        )

        # Compound index for source and date queries
        collection.create_index(
            [("source", pymongo.ASCENDING), ("published_at", pymongo.DESCENDING)],
            name="source_date"
        )

        # TTL index for automatic cleanup (30 days)
        collection.create_index(
            [("ingested_at", pymongo.DESCENDING)],
            expireAfterSeconds=30 * 24 * 60 * 60,  # 30 days
            name="ttl_ingested_at"
        )

        # Text index for content search (optional, for future use)
        try:
            collection.create_index(
                [("title", "text"), ("content", "text"), ("summary", "text")],
                name="text_search",
                weights={"title": 10, "content": 5, "summary": 3}
            )
        except pymongo.errors.OperationFailure:
            logger.warning("Text index creation failed (may already exist or not supported)")

        # Indexes for DLQ collection
        dlq_collection = db["news-dlq"]
        dlq_collection.create_index([("status", pymongo.ASCENDING)])
        dlq_collection.create_index([("retry_count", pymongo.ASCENDING)])
        dlq_collection.create_index(
            [("last_attempt_at", pymongo.DESCENDING)],
            expireAfterSeconds=7 * 24 * 60 * 60,  # 7 days TTL for DLQ
            name="ttl_dlq_last_attempt"
        )

        logger.info("Database indexes setup completed")

    except Exception as e:
        logger.error("Failed to setup database indexes: %s", e)
        raise


def save_news_to_db(news_list: List[Dict[str, Any]]) -> Dict[str, int]:
    """Save news articles to database with bulk operations and error handling.

    Args:
        news_list: List of article payloads to save.

    Returns:
        Dict with operation statistics.
    """
    if not news_list:
        logger.warning("No articles provided to save")
        return {"inserted": 0, "updated": 0, "errors": 0}

    logger.debug("Saving %d articles to database", len(news_list))

    try:
        db = get_db()
        collection = db["news-scraped"]
        logger.debug("Database connection established")

    except Exception as e:
        logger.error("Database connection failed: %s", e)
        raise RuntimeError(f"Database connection error: {e}") from e

    operations: list[UpdateOne] = []
    stats: Dict[str, int] = {"inserted": 0, "updated": 0, "errors": 0}
    ingested_at = datetime.now(timezone.utc)

    for article in news_list:
        try:
            if not article:
                stats["errors"] += 1
                continue

            # Add ingestion timestamp
            article_copy = article.copy()
            article_copy["ingested_at"] = ingested_at

            # Create upsert operation
            operation = UpdateOne(
                filter={"_id": article["_id"]},
                update={"$set": article_copy, "$setOnInsert": {"first_ingested_at": ingested_at}},
                upsert=True
            )
            operations.append(operation)

        except Exception as e:
            stats["errors"] += 1
            logger.error("Failed to prepare operation for article %s: %s", article.get("_id", "unknown"), e)
            continue

    if not operations:
        logger.warning("No valid operations to execute")
        return stats

    try:
        # Execute bulk write
        logger.info("Executing bulk write with %d operations", len(operations))
        result = collection.bulk_write(operations, ordered=False)

        stats["inserted"] = result.upserted_count
        stats["updated"] = result.modified_count

        logger.info("Bulk write completed: %d inserted, %d updated, %d errors",
                   stats["inserted"], stats["updated"], stats["errors"])

        return stats

    except Exception as e:
        logger.error("Bulk write operation failed: %s", e)
        stats["errors"] += len(operations)
        raise RuntimeError(f"Database bulk write failed: {e}") from e

async def process_dlq(client: StealthHttpClient) -> Dict[str, int]:
    """Process pending articles in the Dead Letter Queue.

    Args:
        client: Initialised StealthHttpClient instance.

    Returns:
        Dict with DLQ processing statistics.
    """
    logger.info("Starting DLQ processing")
    stats = {"processed": 0, "recovered": 0, "failed_permanently": 0, "errors": 0}
    
    try:
        db = get_db()
        dlq_collection = db["news-dlq"]
        
        # Find pending articles under max retries
        pending_items = list(dlq_collection.find({
            "status": "pending",
            "retry_count": {"$lt": settings.dlq_max_retries}
        }).limit(20)) # Process in small batches
        
        if not pending_items:
            logger.info("DLQ is empty or has no items eligible for retry")
            return stats
            
        logger.info("Found %d items in DLQ eligible for retry", len(pending_items))
        
        for item in pending_items:
            stats["processed"] += 1
            article_id = item["_id"]
            url = item["url"]
            title = item["title"]
            source = item.get("source", "Unknown Source")
            
            logger.debug("DLQ Retrying: %s", url)
            
            # Attempt to extract text again
            content = await fetch_article_text(client, url)
            
            now = datetime.now(timezone.utc)
            
            if content:
                # Success! Recover the article
                logger.info("DLQ Recovery successful for: %s", url)
                
                # We don't have the original RSS entry, so we create a minimal valid payload
                article_payload = {
                    "_id": article_id,
                    "source": source,
                    "title": title,
                    "title_hash": generate_content_hash(title),
                    "summary": "Recovered from DLQ",
                    "content": content,
                    "url": url,
                    "published_at": now,
                    "language": "en",
                    "vectorized": False,
                    "vectorized_at": None,
                    "qdrant_chunk_ids": [],
                    "content_length": len(content),
                    "summary_length": len("Recovered from DLQ"),
                }
                
                if validate_article_data(article_payload):
                    save_news_to_db([article_payload])
                    # Mark as resolved in DLQ
                    dlq_collection.update_one(
                        {"_id": article_id},
                        {"$set": {"status": "resolved", "resolved_at": now}}
                    )
                    stats["recovered"] += 1
                else:
                    stats["errors"] += 1
            else:
                # Still failing
                new_retry_count = item.get("retry_count", 0) + 1
                update_doc = {
                    "last_attempt_at": now,
                    "retry_count": new_retry_count,
                    "error_reason": "Extraction still failing after DLQ retry"
                }
                
                if new_retry_count >= settings.dlq_max_retries:
                    update_doc["status"] = "failed_permanently"
                    stats["failed_permanently"] += 1
                    logger.warning("DLQ item %s reached max retries and permanently failed", article_id)
                
                dlq_collection.update_one(
                    {"_id": article_id},
                    {"$set": update_doc}
                )

    except Exception as e:
        logger.error("DLQ processing failed: %s", e)
        stats["errors"] += 1

    logger.info("DLQ processing completed: %s", stats)
    return stats


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Pipeline Orchestration
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


async def collect_articles_from_feed(
    client: StealthHttpClient, feed_url: str, max_articles: int = 5
) -> Dict[str, Any]:
    """Complete pipeline to collect articles from a single RSS feed.

    Args:
        client: Initialised StealthHttpClient instance.
        feed_url: RSS feed URL.
        max_articles: Maximum articles to collect.

    Returns:
        Dict with collection statistics.
    """
    logger.info("Starting article collection from feed: %s", feed_url)

    try:
        # Fetch RSS feed
        rss_content = await fetch_link(client, feed_url)

        # Parse feed
        entries, feed_info = parse_news(rss_content)

        # Create payloads
        articles = await create_payload(client, entries, feed_info, max_articles)

        # Save to database
        if articles:
            save_stats = save_news_to_db(articles)
            logger.info("Collection completed for %s: %s", feed_url, save_stats)
            return {
                "success": True,
                "feed_url": feed_url,
                "articles_collected": len(articles),
                "database_stats": save_stats,
                "feed_title": feed_info.get('title', 'Unknown'),
            }

        logger.warning("No articles collected from %s", feed_url)
        return {
            "success": False,
            "feed_url": feed_url,
            "articles_collected": 0,
            "error": "No articles could be processed",
        }

    except Exception as e:
        logger.error("Article collection failed for %s: %s", feed_url, e)
        return {
            "success": False,
            "feed_url": feed_url,
            "articles_collected": 0,
            "error": str(e),
        }


async def run_ingestion_pipeline() -> Dict[str, Any]:
    """Run the full ingestion pipeline across all configured RSS feeds.

    Returns:
        Aggregated statistics for the entire pipeline run.
    """
    logger.info("═" * 60)
    logger.info("Starting FinSight ingestion pipeline — %d feeds", len(RSS_FEEDS))
    logger.info("═" * 60)

    pipeline_stats: Dict[str, Any] = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "feeds_total": len(RSS_FEEDS),
        "feeds_success": 0,
        "feeds_failed": 0,
        "articles_total": 0,
        "results": [],
    }

    async with StealthHttpClient() as client:
        for feed_name, feed_url in RSS_FEEDS.items():
            logger.info("━━ Processing feed: %s", feed_name)
            try:
                result = await collect_articles_from_feed(
                    client, feed_url, max_articles=settings.max_articles_per_batch
                )
                pipeline_stats["results"].append({
                    "feed_name": feed_name,
                    **result,
                })

                if result["success"]:
                    pipeline_stats["feeds_success"] += 1
                    pipeline_stats["articles_total"] += result["articles_collected"]
                else:
                    pipeline_stats["feeds_failed"] += 1

            except Exception as e:
                pipeline_stats["feeds_failed"] += 1
                logger.error("Pipeline error for feed %s: %s", feed_name, e)
                pipeline_stats["results"].append({
                    "feed_name": feed_name,
                    "success": False,
                    "error": str(e),
                })

    pipeline_stats["finished_at"] = datetime.now(timezone.utc).isoformat()

    logger.info("═" * 60)
    logger.info(
        "Pipeline complete: %d/%d feeds OK, %d articles collected",
        pipeline_stats["feeds_success"],
        pipeline_stats["feeds_total"],
        pipeline_stats["articles_total"],
    )
    logger.info("═" * 60)
    
    # Process DLQ after the main pipeline
    try:
        async with StealthHttpClient() as dlq_client:
            dlq_stats = await process_dlq(dlq_client)
            pipeline_stats["dlq_stats"] = dlq_stats
    except Exception as e:
        logger.error("Failed to run process_dlq during pipeline: %s", e)

    return pipeline_stats


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Entrypoint
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import sys
    
    if "--dlq-only" in sys.argv:
        # Run only the DLQ processor
        async def run_dlq_only():
            logger.info("═" * 60)
            logger.info("Starting isolated DLQ retry run")
            logger.info("═" * 60)
            async with StealthHttpClient() as client:
                await process_dlq(client)
        
        asyncio.run(run_dlq_only())
    else:
        # Run the full pipeline
        asyncio.run(run_ingestion_pipeline())
