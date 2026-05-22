"""
Tests for News API providers (Finnhub, NewsAPI, Marketaux).
Tests use mocks to avoid external API calls.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import httpx
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.ingestion.finnhub_calling import FinnhubNewsProvider, get_finnhub_news
from src.ingestion.news_calling import (
    NewsApiProvider, 
    MarketauxProvider,
    search_newsapi_everything,
    get_newsapi_top_headlines,
    get_marketaux_news
)
from src.config import settings


class TestFinnhubNewsProvider:
    """Tests for Finnhub News Provider with OpenAPI integration"""
    
    @pytest.fixture
    def finnhub_provider(self):
        """Create a Finnhub provider instance"""
        return FinnhubNewsProvider()
    
    def test_initialization(self, finnhub_provider):
        """Test Finnhub provider initialization"""
        assert finnhub_provider.api_key == settings.finnhub_api
        assert finnhub_provider.BASE_URL == "https://finnhub.io/api/v1"
        assert finnhub_provider.SWAGGER_URL == "https://finnhub.io/static/swagger.json"
    
    @pytest.mark.asyncio
    async def test_get_market_news_success(self, finnhub_provider):
        """Test successful market news retrieval"""
        mock_response = {
            "data": [
                {
                    "id": 123,
                    "headline": "Test News",
                    "summary": "Test summary",
                    "source": "Reuters",
                    "url": "https://example.com",
                    "image": "https://example.com/image.jpg",
                    "category": "general",
                    "datetime": 1234567890,
                    "related": "AAPL"
                }
            ]
        }
        
        with patch('src.ingestion.finnhub_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await finnhub_provider.get_market_news(category="general")
            
            assert "data" in result
            assert len(result["data"]) == 1
            assert result["data"][0]["headline"] == "Test News"
    
    @pytest.mark.asyncio
    async def test_get_market_news_with_pagination(self, finnhub_provider):
        """Test market news retrieval with pagination"""
        mock_response = {"data": []}
        
        with patch('src.ingestion.finnhub_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await finnhub_provider.get_market_news(category="forex", min_id=10)
            
            assert isinstance(result, dict)
    
    @pytest.mark.asyncio
    async def test_get_market_news_http_error(self, finnhub_provider):
        """Test handling of HTTP errors"""
        with patch('src.ingestion.finnhub_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPError("Connection failed")
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            with pytest.raises(httpx.HTTPError):
                await finnhub_provider.get_market_news()
    
    def test_get_available_tools(self, finnhub_provider):
        """Test retrieving available tools"""
        tools = finnhub_provider.get_available_tools()
        assert isinstance(tools, list)
        # Check that endpoint metadata is available
        if tools:
            assert "name" in tools[0]
            assert "endpoint" in tools[0]


@pytest.mark.asyncio
async def test_get_finnhub_news_convenience_function():
    """Test convenience function for Finnhub news"""
    mock_response = {"data": []}
    
    with patch.object(FinnhubNewsProvider, 'get_market_news', new_callable=AsyncMock) as mock_method:
        mock_method.return_value = mock_response
        result = await get_finnhub_news(category="crypto")
        
        assert isinstance(result, dict)


class TestNewsApiProvider:
    """Tests for NewsAPI.org Provider"""
    
    @pytest.fixture
    def newsapi_provider(self):
        """Create a NewsAPI provider instance"""
        return NewsApiProvider()
    
    def test_initialization(self, newsapi_provider):
        """Test NewsAPI provider initialization"""
        assert newsapi_provider.api_key == settings.the_news_api
        assert newsapi_provider.BASE_URL == "https://newsapi.org/v2"
        assert hasattr(newsapi_provider, 'headers')
    
    @pytest.mark.asyncio
    async def test_search_everything_success(self, newsapi_provider):
        """Test successful /everything endpoint search"""
        mock_response = {
            "status": "ok",
            "totalResults": 1,
            "articles": [
                {
                    "source": {"id": "bbc-news", "name": "BBC News"},
                    "author": "John Doe",
                    "title": "Test Article",
                    "description": "Test Description",
                    "url": "https://example.com/article",
                    "urlToImage": "https://example.com/image.jpg",
                    "publishedAt": "2026-05-22T10:00:00Z",
                    "content": "Test content"
                }
            ]
        }
        
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await newsapi_provider.search_everything(q="Bitcoin")
            
            assert result["status"] == "ok"
            assert result["totalResults"] == 1
            assert len(result["articles"]) == 1
            assert result["articles"][0]["title"] == "Test Article"
    
    @pytest.mark.asyncio
    async def test_search_everything_with_filters(self, newsapi_provider):
        """Test /everything search with advanced filters"""
        mock_response = {"status": "ok", "totalResults": 0, "articles": []}
        
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await newsapi_provider.search_everything(
                q="Tesla",
                search_in="title,description",
                language="en",
                sort_by="popularity",
                page_size=50,
                page=2
            )
            
            assert result["status"] == "ok"
    
    @pytest.mark.asyncio
    async def test_search_everything_invalid_query(self, newsapi_provider):
        """Test search with invalid query"""
        with pytest.raises(ValueError, match="Query must be between"):
            await newsapi_provider.search_everything(q="")
        
        with pytest.raises(ValueError, match="Query must be between"):
            await newsapi_provider.search_everything(q="a" * 501)
    
    @pytest.mark.asyncio
    async def test_get_top_headlines_success(self, newsapi_provider):
        """Test successful /top-headlines endpoint"""
        mock_response = {
            "status": "ok",
            "totalResults": 1,
            "articles": [
                {
                    "source": {"id": "bbc-news", "name": "BBC News"},
                    "author": "Jane Doe",
                    "title": "Breaking News",
                    "description": "Breaking Description",
                    "url": "https://example.com/breaking",
                    "urlToImage": "https://example.com/img.jpg",
                    "publishedAt": "2026-05-22T12:00:00Z",
                    "content": "Breaking content"
                }
            ]
        }
        
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await newsapi_provider.get_top_headlines(country="us", category="business")
            
            assert result["status"] == "ok"
            assert result["articles"][0]["title"] == "Breaking News"
    
    @pytest.mark.asyncio
    async def test_get_top_headlines_conflicting_params(self, newsapi_provider):
        """Test /top-headlines with conflicting parameters"""
        with pytest.raises(ValueError, match="Cannot mix"):
            await newsapi_provider.get_top_headlines(country="us", sources="bbc-news")
        
        with pytest.raises(ValueError, match="Cannot mix"):
            await newsapi_provider.get_top_headlines(category="business", sources="bbc-news")
    
    @pytest.mark.asyncio
    async def test_search_everything_http_error(self, newsapi_provider):
        """Test handling of HTTP errors"""
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPError("API error")
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            with pytest.raises(httpx.HTTPError):
                await newsapi_provider.search_everything(q="test")


class TestMarketauxProvider:
    """Tests for Marketaux Financial News Provider"""
    
    @pytest.fixture
    def marketaux_provider(self):
        """Create a Marketaux provider instance"""
        return MarketauxProvider()
    
    def test_initialization(self, marketaux_provider):
        """Test Marketaux provider initialization"""
        assert marketaux_provider.api_key == settings.marketaux_api
        assert marketaux_provider.BASE_URL == "https://api.marketaux.com/v1/news/all"
    
    @pytest.mark.asyncio
    async def test_get_financial_news_success(self, marketaux_provider):
        """Test successful financial news retrieval"""
        mock_response = {
            "status": "success",
            "data": [
                {
                    "id": 1,
                    "title": "Stock Market Rally",
                    "description": "Markets surge",
                    "content": "Content here",
                    "url": "https://example.com/article",
                    "image_url": "https://example.com/img.jpg",
                    "published_at": "2026-05-22T14:00:00Z",
                    "updated_at": "2026-05-22T14:30:00Z",
                    "entities": [
                        {
                            "symbol": "AAPL",
                            "name": "Apple Inc",
                            "type": "equity",
                            "sentiment_score": 0.8,
                            "match_score": 0.95
                        }
                    ]
                }
            ],
            "pagination": {"page": 1, "page_size": 50, "total": 100}
        }
        
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await marketaux_provider.get_financial_news()
            
            assert result["status"] == "success"
            assert len(result["data"]) == 1
            assert result["data"][0]["title"] == "Stock Market Rally"
    
    @pytest.mark.asyncio
    async def test_get_financial_news_with_symbol_filter(self, marketaux_provider):
        """Test financial news with symbol filtering"""
        mock_response = {"status": "success", "data": []}
        
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await marketaux_provider.get_financial_news(symbols="TSLA,AMZN")
            
            assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_get_financial_news_with_sentiment_filter(self, marketaux_provider):
        """Test financial news with sentiment filtering"""
        mock_response = {"status": "success", "data": []}
        
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await marketaux_provider.get_financial_news(
                sentiment_gte=0.5,
                sentiment_lte=1.0,
                industries="Technology"
            )
            
            assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_get_financial_news_with_date_filters(self, marketaux_provider):
        """Test financial news with date filtering"""
        mock_response = {"status": "success", "data": []}
        
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await marketaux_provider.get_financial_news(
                published_after="2026-05-20",
                published_before="2026-05-22"
            )
            
            assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_get_financial_news_advanced_search(self, marketaux_provider):
        """Test financial news with advanced search query"""
        mock_response = {"status": "success", "data": []}
        
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = AsyncMock()
            mock_response_obj.json = AsyncMock(return_value=mock_response)
            mock_response_obj.raise_for_status = MagicMock(return_value=None)
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            result = await marketaux_provider.get_financial_news(
                search="ipo -nyse",
                must_have_entities=True,
                filter_entities=True
            )
            
            assert result["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_get_financial_news_http_error(self, marketaux_provider):
        """Test handling of HTTP errors"""
        with patch('src.ingestion.news_calling.httpx.AsyncClient') as mock_client_class:
            mock_response_obj = MagicMock()
            mock_response_obj.raise_for_status.side_effect = httpx.HTTPError("API error")
            
            mock_client_instance = AsyncMock()
            mock_client_instance.get = AsyncMock(return_value=mock_response_obj)
            mock_client_instance.__aenter__ = AsyncMock(return_value=mock_client_instance)
            mock_client_instance.__aexit__ = AsyncMock(return_value=None)
            
            mock_client_class.return_value = mock_client_instance
            
            with pytest.raises(httpx.HTTPError):
                await marketaux_provider.get_financial_news()


# Tests for convenience functions
@pytest.mark.asyncio
async def test_search_newsapi_everything_convenience():
    """Test convenience function for NewsAPI /everything"""
    mock_response = {"status": "ok", "articles": []}
    
    with patch.object(NewsApiProvider, 'search_everything', new_callable=AsyncMock) as mock_method:
        mock_method.return_value = mock_response
        result = await search_newsapi_everything(q="crypto")
        
        assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_get_newsapi_top_headlines_convenience():
    """Test convenience function for NewsAPI /top-headlines"""
    mock_response = {"status": "ok", "articles": []}
    
    with patch.object(NewsApiProvider, 'get_top_headlines', new_callable=AsyncMock) as mock_method:
        mock_method.return_value = mock_response
        result = await get_newsapi_top_headlines(country="us")
        
        assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_get_marketaux_news_convenience():
    """Test convenience function for Marketaux"""
    mock_response = {"status": "success", "data": []}
    
    with patch.object(MarketauxProvider, 'get_financial_news', new_callable=AsyncMock) as mock_method:
        mock_method.return_value = mock_response
        result = await get_marketaux_news(symbols="AAPL")
        
        assert result["status"] == "success"


class TestHeadersStealth:
    """Tests for HTTP stealth headers"""
    
    def test_newsapi_headers(self):
        """Test NewsAPI provider headers"""
        provider = NewsApiProvider()
        headers = provider._get_headers()
        
        assert "User-Agent" in headers
        assert "Mozilla" in headers["User-Agent"]
        assert "Sec-Ch-Ua" in headers
        assert "Sec-Fetch-Mode" in headers
    
    def test_marketaux_headers(self):
        """Test Marketaux provider headers"""
        provider = MarketauxProvider()
        headers = provider._get_headers()
        
        assert "User-Agent" in headers
        assert len(headers) > 0
