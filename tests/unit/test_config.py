"""
Unit tests for FinSight RAG components.
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from datetime import datetime, timezone
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.config import Settings
from src.api.schemas import QueryRequest, QueryResponse, ArticleSchema
from src.ingestion.collector import (
    generate_content_hash,
    validate_article_data,
    fetch_link
)
from src.utils.date_parser import standardize_date

class TestSettings:
    """Test configuration validation"""

    def test_valid_settings_creation(self):
        """Test that valid settings can be created"""
        with patch.dict(os.environ, {
            'QDRANT_URL': 'https://test.qdrant.tech',
            'QDRANT_API_KEY': 'test_key_123456789012',
            'GROQ_API_KEY': 'test_groq_key_123456789012'
        }):
            settings = Settings()
            assert settings.qdrant_url == 'https://test.qdrant.tech'
            assert settings.qdrant_api_key == 'test_key_123456789012'
            assert settings.groq_api_key == 'test_groq_key_123456789012'

    def test_invalid_mongo_uri(self):
        """Test MongoDB URI validation"""
        with patch.dict(os.environ, {
            'QDRANT_URL': 'https://test.qdrant.tech',
            'QDRANT_API_KEY': 'test_key_123456789012',
            'GROQ_API_KEY': 'test_groq_key_123456789012'
        }):
            with pytest.raises(ValueError, match="MongoDB URI must start with"):
                Settings(mongo_uri="invalid_uri")

    def test_invalid_qdrant_url(self):
        """Test Qdrant URL validation"""
        with patch.dict(os.environ, {
            'QDRANT_API_KEY': 'test_key_123456789012',
            'GROQ_API_KEY': 'test_groq_key_123456789012'
        }):
            from pydantic import ValidationError
            with pytest.raises(ValidationError):
                Settings(qdrant_url="ftp://invalid.url")

    def test_embedding_provider_detection(self):
        """Test embedding provider detection"""
        with patch.dict(os.environ, {
            'QDRANT_URL': 'https://test.qdrant.tech',
            'QDRANT_API_KEY': 'test_key_123456789012',
            'GROQ_API_KEY': 'test_groq_key_123456789012',
            'COHERE_API_KEY': 'test_cohere_key_123456789012'
        }):
            settings = Settings()
            assert settings.is_cloud_embedding_enabled() == True
            assert settings.get_embedding_provider() == "cohere"

class TestSchemas:
    """Test Pydantic schemas"""

    def test_valid_query_request(self):
        """Test valid query request creation"""
        request = QueryRequest(query="What is the latest financial news?")
        assert request.query == "What is the latest financial news?"

    def test_query_request_validation(self):
        """Test query request validation"""
        # Too short
        with pytest.raises(ValueError):
            QueryRequest(query="Hi")

        # Dangerous characters
        with pytest.raises(ValueError):
            QueryRequest(query="SELECT * FROM users")

    def test_valid_article_schema(self):
        """Test valid article schema creation"""
        article = ArticleSchema(
            _id="test_id_123",
            source="Test Source",
            title="Test Article",
            content="This is test content with sufficient length.",
            url="https://example.com/article",
            published_at="2024-01-01T00:00:00Z"
        )
        assert article.id == "test_id_123"
        assert article.title == "Test Article"
        assert article.vectorized == False

    def test_invalid_url_in_article(self):
        """Test URL validation in article schema"""
        with pytest.raises(ValueError):
            ArticleSchema(
                _id="test_id",
                source="Test",
                title="Test",
                content="Content",
                url="not-a-valid-url",
                published_at="2024-01-01T00:00:00Z"
            )

class TestCollector:
    """Test data collection functions"""

    def test_generate_content_hash(self):
        """Test content hash generation"""
        text = "Test content for hashing"
        hash1 = generate_content_hash(text)
        hash2 = generate_content_hash(text)

        # Same text should produce same hash
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex length

        # Different text should produce different hash
        different_hash = generate_content_hash("Different content")
        assert hash1 != different_hash

    def test_generate_content_hash_empty(self):
        """Test hash generation with empty string"""
        with pytest.raises(ValueError):
            generate_content_hash("")

    def test_validate_article_data_valid(self):
        """Test article data validation with valid data"""
        valid_article = {
            "_id": "test_id",
            "title": "Test Title",
            "url": "https://example.com",
            "source": "Test Source",
            "published_at": datetime.now(timezone.utc),
            "content": "This is sufficient content for validation."
        }
        assert validate_article_data(valid_article) == True

    def test_validate_article_data_missing_field(self):
        """Test article validation with missing required field"""
        invalid_article = {
            "title": "Test Title",
            "url": "https://example.com",
            "source": "Test Source",
            # Missing _id
            "published_at": datetime.now(timezone.utc),
            "content": "Content"
        }
        assert validate_article_data(invalid_article) == False

    def test_validate_article_data_invalid_url(self):
        """Test article validation with invalid URL"""
        invalid_article = {
            "_id": "test_id",
            "title": "Test Title",
            "url": "not-a-valid-url",
            "source": "Test Source",
            "published_at": datetime.now(timezone.utc),
            "content": "Content"
        }
        assert validate_article_data(invalid_article) == False

    @pytest.mark.asyncio
    async def test_fetch_link_success(self):
        """Test successful RSS feed fetching via StealthHttpClient"""
        mock_client = AsyncMock()
        mock_client.get_text.return_value = "<rss><channel><title>Test Feed</title></channel></rss>"

        result = await fetch_link(mock_client, "https://example.com/rss")
        assert result == "<rss><channel><title>Test Feed</title></channel></rss>"
        mock_client.get_text.assert_awaited_once_with("https://example.com/rss")

    @pytest.mark.asyncio
    async def test_fetch_link_invalid_url(self):
        """Test fetch_link rejects invalid URL"""
        mock_client = AsyncMock()
        with pytest.raises(ValueError):
            await fetch_link(mock_client, "not-a-url")

class TestDateParser:
    """Test date parsing functionality"""

    def test_standardize_date_valid_iso(self):
        """Test parsing valid ISO date string"""
        result = standardize_date("2024-01-01T12:00:00Z")
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_standardize_date_human_readable(self):
        """Test parsing human-readable date"""
        result = standardize_date("January 1, 2024")
        assert result is not None
        assert result.year == 2024

    def test_standardize_date_invalid(self):
        """Test parsing invalid date string"""
        result = standardize_date("not-a-date")
        assert result is None

class TestIntegration:
    """Integration tests for component interaction"""

    @patch('src.ingestion.collector.get_db')
    def test_save_news_to_db_empty_list(self, mock_get_db):
        """Test saving empty news list"""
        from src.ingestion.collector import save_news_to_db

        result = save_news_to_db([])
        assert result == {"inserted": 0, "updated": 0, "errors": 0}

    @patch('src.ingestion.collector.get_db')
    @patch('src.ingestion.collector.logger')
    def test_save_news_to_db_with_data(self, mock_logger, mock_get_db):
        """Test saving news with valid data"""
        from src.ingestion.collector import save_news_to_db

        mock_collection = Mock()
        mock_db = {"news-scraped": mock_collection}
        mock_get_db.return_value = mock_db

        mock_result = Mock()
        mock_result.upserted_count = 2
        mock_result.modified_count = 1
        mock_collection.bulk_write.return_value = mock_result

        test_articles = [
            {
                "_id": "test1",
                "title": "Test Article 1",
                "content": "Content 1",
                "url": "https://example.com/1",
                "source": "Test",
                "published_at": datetime.now(timezone.utc)
            },
            {
                "_id": "test2",
                "title": "Test Article 2",
                "content": "Content 2",
                "url": "https://example.com/2",
                "source": "Test",
                "published_at": datetime.now(timezone.utc)
            }
        ]

        result = save_news_to_db(test_articles)

        assert result["inserted"] == 2
        assert result["updated"] == 1
        assert result["errors"] == 0
        mock_collection.bulk_write.assert_called_once()

if __name__ == "__main__":
    pytest.main([__file__])