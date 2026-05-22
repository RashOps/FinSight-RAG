import httpx
from typing import Optional, Any, Dict

from src.config import settings
from src.utils.logger import get_logger

# Logger
logger = get_logger(__name__)


class BaseNewsProvider:
    """
    Base class for news API providers with common functionality.
    """
    
    def __init__(self, api_key: str, base_url: str, timeout: int = None):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout or settings.request_timeout
        self.headers = self._get_headers()
    
    def _get_headers(self) -> Dict[str, str]:
        """Get stealth headers to avoid blocking."""
        # Note: Do NOT set Accept-Encoding manually — httpx handles gzip decompression
        # automatically only when it negotiates the encoding itself.
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json, text/html, */*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Connection": "keep-alive",
        }


class NewsApiProvider(BaseNewsProvider):
    """
    NewsAPI.org provider for fetching news articles.
    Supports both /everything and /top-headlines endpoints.
    """
    
    BASE_URL = "https://newsapi.org/v2"
    
    def __init__(self):
        super().__init__(api_key=settings.the_news_api, base_url=self.BASE_URL)
    
    async def search_everything(
        self,
        q: str,
        search_in: Optional[str] = None,
        sources: Optional[str] = None,
        domains: Optional[str] = None,
        exclude_domains: Optional[str] = None,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        language: Optional[str] = None,
        sort_by: str = "publishedAt",
        page_size: int = 100,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Search through millions of articles from over 150,000 sources.
        
        Args:
            q: Keywords or phrases to search for (max 500 chars)
            search_in: Fields to search (title, description, content)
            sources: Comma-separated news source IDs (max 20)
            domains: Comma-separated domains to include
            exclude_domains: Comma-separated domains to exclude
            from_date: Oldest article date (ISO 8601 format)
            to_date: Newest article date (ISO 8601 format)
            language: 2-letter ISO 639-1 language code
            sort_by: Sorting method (relevancy, popularity, publishedAt)
            page_size: Results per page (default 100, max 100)
            page: Page number for pagination
            
        Returns:
            News articles data
        """
        if not q or len(q) > 500:
            raise ValueError("Query must be between 1 and 500 characters")
        
        params = {
            "apiKey": self.api_key,
            "q": q,
            "sortBy": sort_by,
            "pageSize": min(page_size, 100),
            "page": page
        }
        
        # Add optional parameters
        if search_in:
            params["searchIn"] = search_in
        if sources:
            params["sources"] = sources
        if domains:
            params["domains"] = domains
        if exclude_domains:
            params["excludeDomains"] = exclude_domains
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date
        if language:
            params["language"] = language
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/everything",
                    params=params,
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()  # httpx: .json() is synchronous, no await
                logger.info(f"NewsAPI /everything: Found {data.get('totalResults', 0)} articles for '{q}'")
                return data
        except httpx.HTTPError as e:
            logger.error(f"HTTP error in NewsAPI /everything: {e}")
            raise
        except Exception as e:
            logger.error(f"Error in NewsAPI /everything: {e}")
            raise
    
    async def get_top_headlines(
        self,
        country: Optional[str] = None,
        category: Optional[str] = None,
        sources: Optional[str] = None,
        q: Optional[str] = None,
        page_size: int = 20,
        page: int = 1
    ) -> Dict[str, Any]:
        """
        Get live top and breaking headlines.
        
        Args:
            country: 2-letter ISO 3166-1 country code (e.g., 'us')
            category: News category (business, entertainment, general, health, science, sports, technology)
            sources: Comma-separated source IDs (can't mix with country or category)
            q: Keywords or phrase to search for
            page_size: Results per page (default 20, max 100)
            page: Page number for pagination
            
        Returns:
            Top headlines data
        """
        if country and sources:
            raise ValueError("Cannot mix 'country' parameter with 'sources' parameter")
        if category and sources:
            raise ValueError("Cannot mix 'category' parameter with 'sources' parameter")
        
        params = {
            "apiKey": self.api_key,
            "pageSize": min(page_size, 100),
            "page": page
        }
        
        if country:
            params["country"] = country
        if category:
            params["category"] = category
        if sources:
            params["sources"] = sources
        if q:
            params["q"] = q
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/top-headlines",
                    params=params,
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()  # httpx: .json() is synchronous, no await
                logger.info(f"NewsAPI /top-headlines: Found {len(data.get('articles', []))} headlines")
                return data
        except httpx.HTTPError as e:
            logger.error(f"HTTP error in NewsAPI /top-headlines: {e}")
            raise
        except Exception as e:
            logger.error(f"Error in NewsAPI /top-headlines: {e}")
            raise


class MarketauxProvider(BaseNewsProvider):
    """
    Marketaux API provider for financial news and market data.
    Supports filtering by symbols, entities, industries, countries, and sentiment.
    """
    
    BASE_URL = "https://api.marketaux.com/v1/news/all"
    
    def __init__(self):
        super().__init__(api_key=settings.marketaux_api, base_url=self.BASE_URL)
    
    async def get_financial_news(
        self,
        symbols: Optional[str] = None,
        entity_types: Optional[str] = None,
        industries: Optional[str] = None,
        countries: Optional[str] = None,
        sentiment_gte: Optional[float] = None,
        sentiment_lte: Optional[float] = None,
        search: Optional[str] = None,
        domains: Optional[str] = None,
        exclude_domains: Optional[str] = None,
        language: Optional[str] = None,
        published_before: Optional[str] = None,
        published_after: Optional[str] = None,
        sort: str = "published_at",
        limit: int = 50,
        page: int = 1,
        must_have_entities: bool = False,
        filter_entities: bool = False,
        group_similar: bool = True
    ) -> Dict[str, Any]:
        """
        Get global financial news with advanced filtering.
        
        Args:
            symbols: Entity symbols to filter by (comma-separated, max 20)
            entity_types: Entity types to filter (index, equity, etc.)
            industries: Industries to filter by
            countries: Countries of exchange entities to filter by
            sentiment_gte: Minimum sentiment score (-1 to 1)
            sentiment_lte: Maximum sentiment score (-1 to 1)
            search: Advanced search query with +, -, | operators
            domains: Comma-separated domains to include
            exclude_domains: Comma-separated domains to exclude
            language: Comma-separated language codes
            published_before: Filter articles published before date
            published_after: Filter articles published after date
            sort: Sort by (published_at, entity_match_score, entity_sentiment_score, relevance_score)
            limit: Number of articles to return (1-200 depending on plan)
            page: Page number for pagination
            must_have_entities: Only return articles with identified entities
            filter_entities: Only return relevant entities for your query
            group_similar: Group similar articles to avoid duplicates
            
        Returns:
            Financial news data
        """
        params = {
            "api_token": self.api_key,
            "limit": min(limit, 200),
            "page": page,
            "sort": sort,
            "must_have_entities": "true" if must_have_entities else "false",
            "filter_entities": "true" if filter_entities else "false",
            "group_similar": "true" if group_similar else "false"
        }
        
        # Add optional parameters
        if symbols:
            params["symbols"] = symbols
        if entity_types:
            params["entity_types"] = entity_types
        if industries:
            params["industries"] = industries
        if countries:
            params["countries"] = countries
        if sentiment_gte is not None:
            params["sentiment_gte"] = str(sentiment_gte)
        if sentiment_lte is not None:
            params["sentiment_lte"] = str(sentiment_lte)
        if search:
            params["search"] = search
        if domains:
            params["domains"] = domains
        if exclude_domains:
            params["exclude_domains"] = exclude_domains
        if language:
            params["language"] = language
        if published_before:
            params["published_before"] = published_before
        if published_after:
            params["published_after"] = published_after
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    self.base_url,
                    params=params,
                    headers=self.headers
                )
                response.raise_for_status()
                data = response.json()  # httpx: .json() is synchronous, no await
                logger.info(f"Marketaux: Found {len(data.get('data', []))} financial news articles")
                return data
        except httpx.HTTPError as e:
            logger.error(f"HTTP error in Marketaux API: {e}")
            raise
        except Exception as e:
            logger.error(f"Error in Marketaux API: {e}")
            raise


# Convenience functions for easy access
async def search_newsapi_everything(q: str, **kwargs) -> Dict[str, Any]:
    """Search NewsAPI /everything endpoint"""
    provider = NewsApiProvider()
    return await provider.search_everything(q=q, **kwargs)


async def get_newsapi_top_headlines(**kwargs) -> Dict[str, Any]:
    """Get NewsAPI /top-headlines"""
    provider = NewsApiProvider()
    return await provider.get_top_headlines(**kwargs)


async def get_marketaux_news(**kwargs) -> Dict[str, Any]:
    """Get Marketaux financial news"""
    provider = MarketauxProvider()
    return await provider.get_financial_news(**kwargs)
