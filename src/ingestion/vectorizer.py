from datetime import datetime, timezone
from pymongo import UpdateOne
import qdrant_client
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.cohere import CohereEmbedding
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from src.utils.db_client import get_db
from src.utils.logger import get_logger
from src.config import settings

logger = get_logger(__name__)

def get_article(numb_articles: int = 5) -> list:
    """
    Load non-vectorized articles from MongoDB

    Args:
        numb_articles: Maximum number of articles to retrieve

    Returns:
        List of article documents
    """
    if numb_articles <= 0:
        raise ValueError("numb_articles must be positive")

    logger.debug("Loading non-vectorized articles from MongoDB")

    try:
        db = get_db()
        collection = db["news-scraped"]

        # Find non-vectorized articles, sorted by publication date (newest first)
        result = collection.find(
            {"vectorized": False}
        ).sort("published_at", -1).limit(numb_articles)

        articles = list(result)

        logger.info("Loaded %d articles for vectorization", len(articles))
        return articles

    except Exception as e:
        logger.error("Failed to load articles from MongoDB: %s", e)
        raise Exception(f"Article loading failed: {e}")

def convert_to_doc(data: list):
    """
    Convert articles to LlamaIndex Document objects with metadata

    Args:
        data: List of article dictionaries from MongoDB

    Returns:
        List of LlamaIndex Document objects
    """
    if not data:
        logger.warning("No data provided for document conversion")
        return []

    logger.debug("Converting %d articles to LlamaIndex documents", len(data))

    documents = []

    try:
        for article in data:
            if not isinstance(article, dict):
                logger.warning("Invalid article format, skipping")
                continue

            # Extract text to embed (prefer content over summary)
            summary = (article.get("summary") or "").strip()
            content = (article.get("content") or "").strip()

            if summary and content:
                if summary.lower() in content.lower()[:len(summary)+50]:
                    text_to_embed = content
                else:
                    text_to_embed = f"SUMMARY: {summary}\n\nMAIN CONTENT: {content}"
            else:
                # Fallback classique si l'un des deux manque
                text_to_embed = content or summary or ""

            if not text_to_embed or len(text_to_embed.strip()) < 10:
                logger.warning("Article %s has insufficient content, skipping",
                             article.get("_id", "unknown"))
                continue

            # Create document with metadata
            doc = Document(
                text=text_to_embed.strip(),
                metadata={
                    "_id": article.get("_id"),
                    "published": article.get("published_at"),
                    "source": article.get("source", "Unknown"),
                    "url": article.get("url", ""),
                    "title": article.get("title", "")
                }
            )
            documents.append(doc)

        logger.info("Successfully converted %d articles to %d documents",
                   len(data), len(documents))
        return documents

    except Exception as e:
        logger.error("Failed to convert articles to documents: %s", e)
        raise Exception(f"Document conversion failed: {e}")
    

def brain_config(documents, embedding_model: str = None):
    """
    Text splitter and model embedding configuration
    """
    if not documents:
        raise ValueError("No documents provided for configuration")

    # Use settings to determine embedding model if not specified
    if embedding_model is None:
        embedding_model = "cloud" if settings.is_cloud_embedding_enabled() else "local"

    # Text splitter configuration
    text_splitter = SentenceSplitter(
        chunk_size=settings.chunks,
        chunk_overlap=50
    )

    nodes = text_splitter.get_nodes_from_documents(
        documents,
        show_progress=True
    )

    # Embedding model selection
    model_embedding = None

    if embedding_model == "cloud":
        if not settings.cohere_api_key:
            raise ValueError("Cohere API key required for cloud embedding")
        model_embedding = CohereEmbedding(
            api_key=settings.cohere_api_key,
            model_name=settings.cohere_embedding_model,
        )
        logger.info("Using Cohere cloud embedding model: %s", settings.cohere_embedding_model)

    elif embedding_model == "local":
        model_embedding = HuggingFaceEmbedding(
            model_name=settings.embedding_model
        )
        logger.info("Using local HuggingFace embedding model")

    else:
        raise ValueError(f"Unsupported embedding model: {embedding_model}")

    return text_splitter, model_embedding, nodes


def load_to_qdrant(documents, embedding_model: str = None):
    """
    Transform documents into vectors and load to Qdrant

    Args:
        documents: List of LlamaIndex Document objects
        embedding_model: "cloud" or "local", auto-detected if None

    Returns:
        List of nodes created from the documents
    """
    if not documents:
        logger.warning("No documents provided for vectorization")
        return []

    logger.debug("Starting vectorization and loading vectors to Qdrant")

    try:
        # Configure text splitter and embedding model
        Settings.text_splitter, Settings.embed_model, nodes = brain_config(documents, embedding_model)

        if not nodes:
            logger.warning("No nodes generated from documents")
            return []

        # Initialize Qdrant client
        client = qdrant_client.QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key
        )

        # Create vector store
        vector_store = QdrantVectorStore(
            client=client,
            collection_name="finsight_news"
        )

        # Create index from existing vector store
        index = VectorStoreIndex.from_vector_store(vector_store=vector_store)

        # Insert nodes
        index.insert_nodes(nodes)
        logger.info("Successfully loaded %d nodes to Qdrant", len(nodes))

        return nodes

    except Exception as e:
        logger.error("Error during Qdrant vectorization: %s", e)
        raise Exception(f"Qdrant vectorization failed: {e}")

def update_mongodb_after_vectorization(nodes):
    """
    Update MongoDB articles after successful vectorization

    Args:
        nodes: List of nodes returned from vectorization
    """
    if not nodes:
        logger.warning("No nodes provided for MongoDB update")
        return

    logger.debug("Updating MongoDB after vectorization")

    try:
        db = get_db()
        collection = db["news-scraped"]
        logger.debug("MongoDB connection established")
    except Exception as e:
        logger.error("MongoDB connection failed: %s", e)
        raise Exception(f"MongoDB connection error: {e}")

    # Group chunk IDs by article ID
    article_to_chunks = {}
    vectorized_at = datetime.now(timezone.utc)

    logger.debug("Grouping chunk IDs by article ID")
    try:
        for node in nodes:
            mongo_id = node.metadata.get("_id")
            chunk_id = node.node_id

            if not mongo_id:
                logger.warning("Node missing _id in metadata, skipping")
                continue

            if mongo_id not in article_to_chunks:
                article_to_chunks[mongo_id] = []

            article_to_chunks[mongo_id].append(chunk_id)

        logger.info("Successfully grouped %d articles with chunks", len(article_to_chunks))

    except Exception as e:
        logger.error("Failed to group chunk IDs: %s", e)
        raise Exception(f"Chunk ID grouping failed: {e}")

    # Prepare bulk update operations
    operations = []
    logger.debug("Preparing MongoDB update operations")

    try:
        for mongo_id, chunk_ids_list in article_to_chunks.items():
            operation = UpdateOne(
                filter={"_id": mongo_id},
                update={"$set": {
                    "vectorized": True,
                    "vectorized_at": vectorized_at,
                    "qdrant_chunk_ids": chunk_ids_list
                }}
            )
            operations.append(operation)

        logger.info("Prepared %d update operations", len(operations))

    except Exception as e:
        logger.error("Failed to prepare update operations: %s", e)
        raise Exception(f"Update operation preparation failed: {e}")

    # Execute bulk write
    if operations:
        try:
            result = collection.bulk_write(operations, ordered=False)
            logger.info("MongoDB update completed: %d modified, %d matched",
                       result.modified_count, result.matched_count)
        except Exception as e:
            logger.error("Bulk write operation failed: %s", e)
            raise Exception(f"MongoDB bulk update failed: {e}")
    else:
        logger.warning("No update operations to execute")

def vectorize_articles(num_articles: int = 5, embedding_model: str = None):
    """
    Complete pipeline to vectorize non-vectorized articles

    Args:
        num_articles: Maximum number of articles to vectorize
        embedding_model: "cloud" or "local", auto-detected if None

    Returns:
        Dict with vectorization statistics
    """
    logger.info("Starting article vectorization pipeline")

    try:
        # 1. Get non-vectorized articles
        articles = get_article(num_articles)
        if not articles:
            logger.info("No articles to vectorize")
            return {"vectorized": 0, "message": "No articles to vectorize"}

        logger.info("Found %d articles to vectorize", len(articles))

        # 2. Convert to LlamaIndex documents
        documents = convert_to_doc(articles)
        if not documents:
            logger.warning("No valid documents created from articles")
            return {"vectorized": 0, "message": "No valid documents created"}

        logger.info("Created %d documents for vectorization", len(documents))

        # 3. Vectorize and load to Qdrant
        nodes = load_to_qdrant(documents, embedding_model)
        if not nodes:
            logger.error("Vectorization failed - no nodes created")
            return {"vectorized": 0, "message": "Vectorization failed"}

        # 4. Update MongoDB with vectorization status
        update_mongodb_after_vectorization(nodes)

        logger.info("Successfully vectorized %d articles", len(articles))
        return {
            "vectorized": len(articles),
            "documents_created": len(documents),
            "nodes_created": len(nodes),
            "message": "Vectorization completed successfully"
        }

    except Exception as e:
        logger.error("Vectorization pipeline failed: %s", e)
        raise Exception(f"Vectorization pipeline failed: {e}")

if __name__ == "__main__":
    try:
        result = vectorize_articles()
        print(f"Vectorization result: {result}")
    except Exception as e:
        print(f"Vectorization failed: {e}")
        exit(1)
