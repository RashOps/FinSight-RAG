import qdrant_client
from llama_index.llms.groq import Groq
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.llms import LLM
from llama_index.core.embeddings import BaseEmbedding
from typing import Optional
from src.utils.logger import get_logger
from src.rag.prompts import QA_PROMPT
from src.config import settings

logger = get_logger(__name__)

def _setup_embedding_model() -> BaseEmbedding:
    """
    Setup the embedding model based on configuration.

    Returns:
        BaseEmbedding: Configured embedding model

    Raises:
        ValueError: If embedding configuration is invalid
        Exception: If model initialization fails
    """
    try:
        if settings.is_cloud_embedding_enabled():
            logger.info("Using Cohere cloud embeddings: %s", settings.cohere_embedding_model)
            return CohereEmbedding(
                api_key=settings.cohere_api_key,
                model_name=settings.cohere_embedding_model,
            )
        else:
            logger.info("Using HuggingFace local embeddings: %s", settings.embedding_model)
            return HuggingFaceEmbedding(
                model_name=settings.embedding_model,
                trust_remote_code=False  # Security: disable remote code execution
            )
    except Exception as e:
        logger.error("Failed to initialize embedding model: %s", e)
        raise

def _setup_llm() -> LLM:
    """
    Setup the Groq LLM.

    Returns:
        LLM: Configured Groq LLM instance

    Raises:
        Exception: If LLM initialization fails
    """
    try:
        logger.info("Initializing Groq LLM")
        return Groq(
            api_key=settings.groq_api_key,
            model="llama-3.3-70b-versatile",
            temperature=0.1,  # Low temperature for consistent financial analysis
            max_tokens=1024,  # Reasonable limit for responses
            timeout=settings.request_timeout
        )
    except Exception as e:
        logger.error("Failed to initialize Groq LLM: %s", e)
        raise

def _setup_qdrant_client() -> qdrant_client.QdrantClient:
    """
    Setup Qdrant client connection.

    Returns:
        QdrantClient: Configured Qdrant client

    Raises:
        Exception: If connection fails
    """
    try:
        logger.info("Connecting to Qdrant at: %s", settings.qdrant_url)
        client = qdrant_client.QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key,
            timeout=settings.request_timeout
        )

        # Test connection
        client.get_collections()
        logger.info("Qdrant connection successful")
        return client

    except Exception as e:
        logger.error("Failed to connect to Qdrant: %s", e)
        raise

def brain_setup():
    """
    Configure the LLM and embedding model globally.

    This function sets up the global Settings for LlamaIndex.
    """
    logger.debug("Setting up brain configuration")

    try:
        # Setup embedding model
        embed_model = _setup_embedding_model()

        # Setup LLM
        llm = _setup_llm()

        # Apply to global settings
        Settings.embed_model = embed_model
        Settings.llm = llm

        logger.info("Brain configuration completed successfully")

    except Exception as e:
        logger.error("Brain setup failed: %s", e)
        raise

def get_query_engine():
    """
    Setup Qdrant connection and create query engine.

    Returns:
        QueryEngine: Configured LlamaIndex query engine

    Raises:
        Exception: If setup fails
    """
    logger.debug("Initializing query engine")

    try:
        # Setup brain (LLM and embeddings)
        brain_setup()

        # Setup Qdrant client
        client = _setup_qdrant_client()

        # Setup vector store
        vector_store = QdrantVectorStore(
            client=client,
            collection_name="finsight_news"
        )

        # Create index from vector store
        index = VectorStoreIndex.from_vector_store(
            vector_store=vector_store
        )

        # Create query engine with optimized settings
        engine = index.as_query_engine(
            similarity_top_k=5,  # Retrieve top 5 similar chunks
            text_qa_template=QA_PROMPT,
            streaming=False,  # Disable streaming for now
            node_postprocessors=[],  # Can add reranking here later
        )

        logger.info("Query engine initialized successfully")
        return engine

    except Exception as e:
        logger.error("Failed to initialize query engine: %s", e)
        raise

def test_query_engine(engine) -> bool:
    """
    Test the query engine with a simple query.

    Args:
        engine: The query engine to test

    Returns:
        bool: True if test successful, False otherwise
    """
    try:
        logger.info("Testing query engine...")
        test_query = "What is the latest financial news?"
        response = engine.query(test_query)

        if response and len(str(response).strip()) > 0:
            logger.info("Query engine test successful")
            return True
        else:
            logger.warning("Query engine test returned empty response")
            return False

    except Exception as e:
        logger.error("Query engine test failed: %s", e)
        return False

if __name__ == "__main__":
    try:
        rag_engine = get_query_engine()

        # Test the engine
        if test_query_engine(rag_engine):
            print("✅ Query engine is working correctly")
        else:
            print("❌ Query engine test failed")

        # Demo queries
        queries = [
            "What is the latest news?",
            "Quelles sont les dernières nouvelles concernant la finance?"
        ]

        for query in queries:
            print(f"\n🔍 Query: {query}")
            print("=" * 50)
            response = rag_engine.query(query)
            print(response)
            print("=" * 50)

    except Exception as e:
        print(f"❌ Failed to initialize RAG engine: {e}")
        exit(1)