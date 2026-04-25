import time
import random
import hashlib
import httpx
import feedparser
import pymongo
from pymongo import UpdateOne
from datetime import datetime, timezone
from typing import List, Dict, Optional, Tuple, Any
from urllib.parse import urlparse
from src.ingestion.source import RSS_FEEDS
from src.utils.date_parser import standardize_date
from trafilatura import extract
from src.utils.logger import get_logger
from src.utils.db_client import get_db
from src.config import settings

# Test RSS Link
test_feed = {
    # "yahoo": RSS_FEEDS["yahoo_top_stories"],
    "investing": RSS_FEEDS["investing_com"]
}

# Header for scraping with enhanced browser simulation
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# Logger
logger = get_logger(__name__)

def fetch_link(url: str, max_retries: int = 3) -> str:
    """
    Fetch RSS feed content with retry logic and enhanced error handling.

    Args:
        url: RSS feed URL to fetch
        max_retries: Maximum number of retry attempts

    Returns:
        str: Raw RSS feed content

    Raises:
        Exception: If all retry attempts fail
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string")

    try:
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise ValueError(f"Invalid URL format: {url}")
    except Exception as e:
        raise ValueError(f"URL validation failed: {e}")

    logger.debug("Fetching RSS feed from: %s", url)

    for attempt in range(max_retries):
        try:
            with httpx.Client(
                timeout=settings.request_timeout,
                headers=DEFAULT_HEADERS,
                follow_redirects=True
            ) as client:
                response = client.get(url)
                response.raise_for_status()

                content = response.text
                if not content.strip():
                    raise ValueError("Empty response content")

                logger.info("RSS feed fetched successfully from %s", url)
                time.sleep(random.uniform(0.5, 2.5))  # Rate limiting
                return content

        except httpx.TimeoutException as e:
            logger.warning("Timeout fetching %s (attempt %d/%d): %s", url, attempt + 1, max_retries, e)
        except httpx.HTTPStatusError as e:
            logger.warning("HTTP error fetching %s (attempt %d/%d): %s", url, attempt + 1, max_retries, e)
        except Exception as e:
            logger.warning("Error fetching %s (attempt %d/%d): %s", url, attempt + 1, max_retries, e)

        if attempt < max_retries - 1:
            wait_time = (2 ** attempt) + random.uniform(0, 1)  # Exponential backoff
            logger.info("Waiting %.2f seconds before retry...", wait_time)
            time.sleep(wait_time)

    raise Exception(f"Failed to fetch RSS feed after {max_retries} attempts: {url}")

def parse_news(link: str) -> Tuple[List[Any], Dict[str, Any]]:
    """
    Parse RSS feed content and extract entries and feed metadata.

    Args:
        link: Raw RSS feed content

    Returns:
        Tuple of (entries list, feed metadata dict)

    Raises:
        Exception: If parsing fails
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
        raise Exception(f"RSS parsing failed: {e}")

def fetch_article_text(article_url: str, max_retries: int = 2) -> Optional[str]:
    """
    Extract article text content using Trafilatura with retry logic.

    Args:
        article_url: URL of the article to extract
        max_retries: Maximum number of retry attempts

    Returns:
        Optional[str]: Extracted text content, or None if extraction fails
    """
    if not article_url or not isinstance(article_url, str):
        logger.warning("Invalid article URL provided")
        return None

    logger.debug("Extracting content from article: %s", article_url)

    for attempt in range(max_retries):
        try:
            # Fetch HTML content using httpx with proper headers
            with httpx.Client(
                timeout=settings.request_timeout,
                headers=DEFAULT_HEADERS,
                follow_redirects=True
            ) as client:
                response = client.get(article_url)
                response.raise_for_status()
                html = response.text

            if not html:
                logger.warning("No HTML content fetched from %s", article_url)
                return None

            # Extract text
            result = extract(
                filecontent=html,
                output_format="txt",
                include_comments=False,
                include_tables=True,
                include_links=False,  # Exclude links for cleaner text
                include_images=False,
                with_metadata=False
            )

            if result and len(result.strip()) > 50:  # Minimum content length
                logger.debug("Successfully extracted %d characters from %s", len(result), article_url)
                time.sleep(random.uniform(0.5, 2.0))  # Rate limiting
                return result.strip()
            else:
                logger.warning("Extracted content too short or empty from %s", article_url)
                return None

        except Exception as e:
            logger.warning("Failed to extract content from %s (attempt %d/%d): %s",
                         article_url, attempt + 1, max_retries, e)

        if attempt < max_retries - 1:
            time.sleep(random.uniform(1, 3))  # Wait before retry

    logger.error("Failed to extract content from %s after %d attempts", article_url, max_retries)
    return None

def generate_content_hash(text: str) -> str:
    """
    Generate SHA256 hash for content deduplication.

    Args:
        text: Text content to hash

    Returns:
        str: SHA256 hash of the normalized content
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
        raise Exception(f"Hash generation failed: {e}")

def validate_article_data(article: Dict[str, Any]) -> bool:
    """
    Validate article data before database insertion.

    Args:
        article: Article data dictionary

    Returns:
        bool: True if valid, False otherwise
    """
    required_fields = ['_id', 'title', 'url', 'source', 'published_at']

    for field in required_fields:
        if not article.get(field):
            logger.warning("Article missing required field: %s", field)
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

def create_payload(entries, feed, numb_articles=5):
    """
    Create article payload for database with enhanced validation and error handling.
    """
    if not entries:
        logger.warning("No entries provided to create_payload")
        return []

    if numb_articles <= 0:
        raise ValueError("numb_articles must be positive")

    logger.debug("Creating payloads for %d articles", min(len(entries), numb_articles))

    articles_payload = []
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

            # Extract content
            content = fetch_article_text(article_url)
            if not content:
                logger.warning("Failed to extract content for article: %s", title)
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
            language = getattr(feed, 'language', 'en') or 'en'

            # Extract source name
            source_name = getattr(feed, 'title', 'Unknown Source')

            # Create article payload
            article_payload = {
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
                "summary_length": len(summary)
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

    logger.info("Payload creation completed: %d successful, %d errors", processed_count, error_count)
    return articles_payload

def setup_database_indexes() -> None:
    """
    Create optimized database indexes for the news collection.
    """
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

        logger.info("Database indexes setup completed")

    except Exception as e:
        logger.error("Failed to setup database indexes: %s", e)
        raise

def save_news_to_db(news_list: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Save news articles to database with bulk operations and error handling.

    Args:
        news_list: List of article payloads to save

    Returns:
        Dict with operation statistics
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
        raise Exception(f"Database connection error: {e}")

    operations = []
    stats = {"inserted": 0, "updated": 0, "errors": 0}
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
        raise Exception(f"Database bulk write failed: {e}")

def collect_articles_from_feed(feed_url: str, max_articles: int = 5) -> Dict[str, Any]:
    """
    Complete pipeline to collect articles from a single RSS feed.

    Args:
        feed_url: RSS feed URL
        max_articles: Maximum articles to collect

    Returns:
        Dict with collection statistics
    """
    logger.info("Starting article collection from feed: %s", feed_url)

    try:
        # Fetch RSS feed
        rss_content = fetch_link(feed_url)

        # Parse feed
        entries, feed_info = parse_news(rss_content)

        # Create payloads
        articles = create_payload(entries, feed_info, max_articles)

        # Save to database
        if articles:
            save_stats = save_news_to_db(articles)
            logger.info("Collection completed for %s: %s", feed_url, save_stats)
            return {
                "success": True,
                "feed_url": feed_url,
                "articles_collected": len(articles),
                "database_stats": save_stats,
                "feed_title": feed_info.get('title', 'Unknown')
            }
        else:
            logger.warning("No articles collected from %s", feed_url)
            return {
                "success": False,
                "feed_url": feed_url,
                "articles_collected": 0,
                "error": "No articles could be processed"
            }

    except Exception as e:
        logger.error("Article collection failed for %s: %s", feed_url, e)
        return {
            "success": False,
            "feed_url": feed_url,
            "articles_collected": 0,
            "error": str(e)
        }

if __name__ == "__main__":
    for test_url in test_feed:
        url = fetch_link(test_feed[test_url])
        entries, feed_info = parse_news(url)
        news = create_payload(entries, feed_info, numb_articles=3)
        save_news_to_db(news)
