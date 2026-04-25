"""
Integration tests for FinSight RAG API.
"""
import pytest
from httpx import AsyncClient
from fastapi.testclient import TestClient
import sys
import os
from unittest.mock import patch, MagicMock

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from src.api.main import app
from src.config import settings

class TestAPIIntegration:
    """Integration tests for the FastAPI application"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    def test_health_endpoint(self):
        """Test health check endpoint"""
        response = self.client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "healthy"
        assert "message" in data
        assert "timestamp" in data

    def test_legacy_status_endpoint(self):
        """Test legacy status endpoint"""
        response = self.client.get("/status")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] == "online"

    @patch('src.api.main.get_db')
    def test_database_status_success(self, mock_get_db):
        """Test successful database status check"""
        # Mock successful database connection
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.name = "news-scraped"
        mock_db.__getitem__.return_value = mock_collection
        mock_get_db.return_value = mock_db

        response = self.client.get("/db/status")
        assert response.status_code == 200

        data = response.json()
        assert data["message"] == "MongoDB connection successful"
        assert data["collection"] == "news-scraped"

    @patch('src.api.main.get_db')
    def test_database_status_failure(self, mock_get_db):
        """Test database connection failure"""
        mock_get_db.side_effect = Exception("Connection failed")

        response = self.client.get("/db/status")
        assert response.status_code == 500

        data = response.json()
        assert "Database connection failed" in data["detail"]

    @patch('src.api.main.get_db')
    def test_get_articles_empty(self, mock_get_db):
        """Test getting articles when none exist"""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find.return_value = []
        mock_db.__getitem__.return_value = mock_collection
        mock_get_db.return_value = mock_db

        response = self.client.get("/articles")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    @patch('src.api.main.get_db')
    def test_get_articles_with_data(self, mock_get_db):
        """Test getting articles with mock data"""
        from datetime import datetime, timezone

        mock_articles = [
            {
                "_id": "test_id_1",
                "source": "Test Source",
                "title": "Test Article 1",
                "summary": "Test summary",
                "content": "Test content",
                "url": "https://example.com/1",
                "published_at": datetime.now(timezone.utc),
                "language": "en",
                "vectorized": False,
                "vectorized_at": None,
                "qdrant_chunk_ids": []
            }
        ]

        mock_cursor = MagicMock()
        mock_cursor.__iter__.return_value = mock_articles
        mock_collection = MagicMock()
        mock_collection.find.return_value = mock_cursor
        mock_db = {"news-scraped": mock_collection}
        mock_get_db.return_value = mock_db

        response = self.client.get("/articles")
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == "test_id_1"
        assert data[0]["title"] == "Test Article 1"

    def test_get_articles_invalid_limit(self):
        """Test articles endpoint with invalid limit"""
        response = self.client.get("/articles?limit=150")
        assert response.status_code == 400
        assert "Limit must be between 1 and 100" in response.json()["detail"]

    def test_get_articles_negative_skip(self):
        """Test articles endpoint with negative skip"""
        response = self.client.get("/articles?skip=-1")
        assert response.status_code == 400
        assert "Skip must be non-negative" in response.json()["detail"]

    @patch('src.api.main.get_db')
    def test_get_articles_status(self, mock_get_db):
        """Test articles status endpoint"""
        mock_collection = MagicMock()
        mock_collection.count_documents.side_effect = [100, 75, 25]  # total, vectorized, non-vectorized

        mock_last_doc = {
            "_id": "last_id",
            "published_at": "2024-01-01T00:00:00Z"
        }
        mock_collection.find_one.return_value = mock_last_doc

        mock_db = {"news-scraped": mock_collection}
        mock_get_db.return_value = mock_db

        response = self.client.get("/articles/status")
        assert response.status_code == 200

        data = response.json()
        assert data["total_articles"] == 100
        assert data["vectorized_articles"] == 75
        assert data["non_vectorized_articles"] == 25

    @patch('src.api.main.app.state')
    def test_query_endpoint_success(self, mock_app_state):
        """Test successful query processing"""
        # Mock query engine
        mock_engine = MagicMock()
        mock_response = MagicMock()
        mock_response.__str__ = MagicMock(return_value="Test response")
        mock_engine.query.return_value = mock_response

        mock_app_state.query_engine = mock_engine

        request_data = {"query": "What is the latest financial news?"}
        response = self.client.post("/query", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "processing_time" in data
        assert data["answer"] == "Test response"

    @patch('src.api.main.app.state')
    def test_query_endpoint_no_engine(self, mock_app_state):
        """Test query when engine is not available"""
        mock_app_state.query_engine = None

        request_data = {"query": "Test query"}
        response = self.client.post("/query", json=request_data)

        assert response.status_code == 503
        assert "Query engine not available" in response.json()["detail"]

    def test_query_endpoint_invalid_request(self):
        """Test query with invalid request data"""
        # Empty query
        response = self.client.post("/query", json={"query": ""})
        assert response.status_code == 422

        # Query too short
        response = self.client.post("/query", json={"query": "Hi"})
        assert response.status_code == 422

    def test_query_endpoint_dangerous_query(self):
        """Test query with potentially dangerous content"""
        dangerous_queries = [
            "SELECT * FROM users",
            "DROP TABLE articles",
            "script injection; --"
        ]

        for query in dangerous_queries:
            response = self.client.post("/query", json={"query": query})
            assert response.status_code == 422

    def test_cors_headers(self):
        """Test CORS headers are present"""
        response = self.client.options("/health")
        assert response.status_code == 200

        # Check CORS headers
        assert "access-control-allow-origin" in response.headers
        assert "access-control-allow-methods" in response.headers
        assert "access-control-allow-headers" in response.headers

    def test_openapi_docs_available(self):
        """Test that OpenAPI documentation is available"""
        response = self.client.get("/docs")
        assert response.status_code == 200

        response = self.client.get("/redoc")
        assert response.status_code == 200

        response = self.client.get("/openapi.json")
        assert response.status_code == 200

class TestAPIErrorHandling:
    """Test error handling in the API"""

    def setup_method(self):
        """Setup test client"""
        self.client = TestClient(app)

    def test_404_not_found(self):
        """Test 404 response for unknown endpoints"""
        response = self.client.get("/nonexistent")
        assert response.status_code == 404

    def test_method_not_allowed(self):
        """Test method not allowed"""
        response = self.client.post("/health")
        assert response.status_code == 405

    @patch('src.api.main.logger')
    def test_unexpected_error_handling(self, mock_logger):
        """Test handling of unexpected errors"""
        # This would require mocking internal functions to raise unexpected errors
        # For now, just ensure the error handler is in place
        pass

if __name__ == "__main__":
    pytest.main([__file__, "-v"])