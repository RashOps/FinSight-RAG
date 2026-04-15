from src.ingestion.source import RSS_FEEDS
from src.utils.date_parser import standardize_date
import feedparser
from trafilatura import fetch_url, extract
import time
import random
import hashlib
import httpx

test_feed = {
    "yahoo": RSS_FEEDS["yahoo_top_stories"],
    "investing": RSS_FEEDS["investing_com"]
}

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/xml, text/xml, */*",
}

payload = {
      "_id": "sha256(url)",             
      "source": "reuters",
      "title": "Fed raises rates...",
      "title_hash": "fedraisesrates...", 
      "summary": "...",
      "content": "Full text...",         
      "url": "https://...",
      "published_at": "ISODate(...)",   
      "language": "en",              
      "vectorized": False,               
      "vectorized_at": None,
      "qdrant_chunk_ids": []             
  }

def fecth_link(url: str) -> str:
    """Get Primary market news"""
    client = httpx.Client(timeout=10, headers=DEFAULT_HEADERS)
    text = client.get(url).text
    time.sleep(random.uniform(1.5, 2.5))
    return text

def parse_news(link: str):
    """Get news and the channel info"""
    data = feedparser.parse(link)
    return data.entries, data.feed

def fetch_text(article_link: str):
    """Get article text via Trafilatura"""
    html = fetch_url(article_link)
    result = extract(
        filecontent=html, 
        output_format="txt", 
        include_comments=False, 
        include_tables=True, 
        with_metadata=False
    )
    time.sleep(random.uniform(1.5, 3.0))
    return result

def generate_hash(text: str) -> str:
    """Generate SHA256 hash for absolute deduplication"""
    formatted_text = text.lower().replace(" ", "").strip()
    byte = formatted_text.encode(encoding="utf-8")
    return hashlib.sha256(byte).hexdigest()

def create_payload(entries, feed, numb_articles=5):
    """
    Create article payload for BD
    """

    def get_date(info_dict):
        """
        Get the published date
        """
        if info_dict.get("updated"):
            return info_dict.get("updated")
        elif info_dict.get("published"):
            return info_dict.get("published")
        return None

    def get_description(info_dict):
        """
        Get the article description
        """
        if info_dict.get("summary"):
            return info_dict.get("summary")
        elif info_dict.get("description"):
            return info_dict.get("description")
        return ""

    list_article = []

    for info in entries[:numb_articles]:

        list_article.append(
            {
            "_id": generate_hash(info.link),            
            "source": feed.title,
            "title": info.title,
            "title_hash": generate_hash(info.title), 
            "summary": get_description(info),             
            "content": fetch_text(info.link),        
            "url": info.link,
            "published_at": standardize_date(get_date(info)), 
            "language": feed.get("language", "en"),       
            "vectorized": False,               
            "vectorized_at": None,
            "qdrant_chunk_ids": []             
            } 
        )

    return list_article

if __name__ == "__main__":
    for test_url in test_feed:
        url = fecth_link(test_feed[test_url])
        entries, feed_info = parse_news(url)
        print(create_payload(entries, feed_info, numb_articles=1))
