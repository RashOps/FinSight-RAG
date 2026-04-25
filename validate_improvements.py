#!/usr/bin/env python3
"""
Quick validation script for FinSight RAG robustness improvements.
Run this to verify that all components are working correctly.
"""
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

def test_imports():
    """Test that all modules can be imported"""
    print("🔍 Testing imports...")

    try:
        from src.config import Settings
        print("✅ Config module imported successfully")
    except Exception as e:
        print(f"❌ Config import failed: {e}")
        return False

    try:
        from src.api.schemas import QueryRequest, QueryResponse, ArticleSchema
        print("✅ API schemas imported successfully")
    except Exception as e:
        print(f"❌ API schemas import failed: {e}")
        return False

    try:
        from src.api.main import app
        print("✅ FastAPI app imported successfully")
    except Exception as e:
        print(f"❌ FastAPI app import failed: {e}")
        return False

    try:
        from src.rag.engine import get_query_engine
        print("✅ RAG engine imported successfully")
    except Exception as e:
        print(f"❌ RAG engine import failed: {e}")
        return False

    try:
        from src.ingestion.collector import validate_article_data, generate_content_hash
        print("✅ Collector functions imported successfully")
    except Exception as e:
        print(f"❌ Collector import failed: {e}")
        return False

    return True

def test_config_validation():
    """Test configuration validation"""
    print("\n🔧 Testing configuration validation...")

    try:
        from src.config import Settings

        # Test with invalid data
        try:
            Settings(mongo_uri="invalid")
            print("❌ Config validation failed - should reject invalid MongoDB URI")
            return False
        except ValueError:
            print("✅ Config correctly rejects invalid MongoDB URI")

        try:
            Settings(qdrant_url="ftp://invalid")
            print("❌ Config validation failed - should reject invalid Qdrant URL")
            return False
        except ValueError:
            print("✅ Config correctly rejects invalid Qdrant URL")

        print("✅ Configuration validation working correctly")
        return True

    except Exception as e:
        print(f"❌ Config validation test failed: {e}")
        return False

def test_schema_validation():
    """Test Pydantic schema validation"""
    print("\n📋 Testing schema validation...")

    try:
        from src.api.schemas import QueryRequest, ArticleSchema

        # Test valid query
        query = QueryRequest(query="What is the latest financial news?")
        print("✅ Valid query accepted")

        # Test invalid query (too short)
        try:
            QueryRequest(query="Hi")
            print("❌ Schema validation failed - should reject short queries")
            return False
        except ValueError:
            print("✅ Schema correctly rejects short queries")

        # Test dangerous query
        try:
            QueryRequest(query="SELECT * FROM users")
            print("❌ Schema validation failed - should reject dangerous queries")
            return False
        except ValueError:
            print("✅ Schema correctly rejects dangerous queries")

        # Test valid article
        article = ArticleSchema(
            _id="test_id",
            source="Test Source",
            title="Test Article",
            content="This is sufficient content for validation purposes.",
            url="https://example.com/article",
            published_at="2024-01-01T00:00:00Z"
        )
        print("✅ Valid article schema accepted")

        # Test invalid URL
        try:
            ArticleSchema(
                _id="test_id",
                source="Test",
                title="Test",
                content="Content",
                url="not-a-valid-url",
                published_at="2024-01-01T00:00:00Z"
            )
            print("❌ Schema validation failed - should reject invalid URLs")
            return False
        except ValueError:
            print("✅ Schema correctly rejects invalid URLs")

        print("✅ Schema validation working correctly")
        return True

    except Exception as e:
        print(f"❌ Schema validation test failed: {e}")
        return False

def test_collector_functions():
    """Test collector utility functions"""
    print("\n📥 Testing collector functions...")

    try:
        from src.ingestion.collector import generate_content_hash, validate_article_data
        from datetime import datetime, timezone

        # Test hash generation
        hash1 = generate_content_hash("test content")
        hash2 = generate_content_hash("test content")
        if hash1 == hash2 and len(hash1) == 64:
            print("✅ Content hash generation working")
        else:
            print("❌ Content hash generation failed")
            return False

        # Test article validation
        valid_article = {
            "_id": "test_id",
            "title": "Test Title",
            "content": "This is sufficient content for validation.",
            "url": "https://example.com",
            "source": "Test Source",
            "published_at": datetime.now(timezone.utc)
        }

        if validate_article_data(valid_article):
            print("✅ Article validation accepts valid data")
        else:
            print("❌ Article validation rejects valid data")
            return False

        # Test invalid article
        invalid_article = {
            "title": "Test Title",
            "content": "Content",
            "url": "https://example.com",
            "source": "Test Source",
            # Missing _id
            "published_at": datetime.now(timezone.utc)
        }

        if not validate_article_data(invalid_article):
            print("✅ Article validation rejects invalid data")
        else:
            print("❌ Article validation accepts invalid data")
            return False

        print("✅ Collector functions working correctly")
        return True

    except Exception as e:
        print(f"❌ Collector functions test failed: {e}")
        return False

def test_api_endpoints():
    """Test basic API endpoint availability"""
    print("\n🌐 Testing API endpoints...")

    try:
        from fastapi.testclient import TestClient
        from src.api.main import app

        client = TestClient(app)

        # Test health endpoint - accept both 200 and 503 (service not fully initialized)
        response = client.get("/health")
        if response.status_code in [200, 503]:
            if response.status_code == 200:
                print("✅ Health endpoint working (service healthy)")
            else:
                print("✅ Health endpoint working (service initializing - expected in test environment)")
        else:
            print(f"❌ Health endpoint failed: {response.status_code}")
            return False

        # Test status endpoint
        response = client.get("/status")
        if response.status_code in [200, 503]:
            print("✅ Status endpoint working")
        else:
            print(f"❌ Status endpoint failed: {response.status_code}")
            return False

        # Test OpenAPI docs
        response = client.get("/docs")
        if response.status_code == 200:
            print("✅ API documentation available")
        else:
            print(f"❌ API documentation failed: {response.status_code}")
            return False

        print("✅ API endpoints working correctly")
        return True

    except Exception as e:
        print(f"❌ API endpoints test failed: {e}")
        return False

def main():
    """Run all validation tests"""
    print("🚀 FinSight RAG - Robustness Validation")
    print("=" * 50)

    tests = [
        test_imports,
        test_config_validation,
        test_schema_validation,
        test_collector_functions,
        test_api_endpoints
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1
        print()

    print("=" * 50)
    print(f"📊 Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All robustness improvements validated successfully!")
        print("\nNext steps:")
        print("1. Run 'pytest' to execute the full test suite")
        print("2. Start the application with 'uvicorn src.api.main:app --reload'")
        print("3. Check the API documentation at http://localhost:8000/docs")
        return 0
    else:
        print("⚠️  Some tests failed. Please check the errors above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())