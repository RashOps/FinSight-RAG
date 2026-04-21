import qdrant_client
from llama_index.llms.groq import Groq
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import VectorStoreIndex, Settings
from llama_index.vector_stores.qdrant import QdrantVectorStore
from src.utils.logger import get_logger
from src.config import settings

logger = get_logger(__name__)

def brain_setup():
    """
    Vectorizer model and llm configuration
    """
    logger.debug("Lancement de la configuration du LLM et du Vectorizer")

    try:
        embed_model_huggingface = HuggingFaceEmbedding(
                model_name=settings.embedding_model
            )
        
        llm = Groq(
            api_key=settings.groq_api_key,
            model="llama-3.3-70b-versatile"
            )

        Settings.embed_model = embed_model_huggingface
        Settings.llm = llm

        logger.info("Configuration complète")

    except Exception as e:
        logger.error("Erreur lors de la configuration du LLM et du Vectorizer: %s", e)
        raise Exception(f"Message: {e}")


def get_query_engine():
    """
    Setup Qdrant connexion and Query engine
    """
    logger.debug("Lancement de la configuration de la query engine")
    brain_setup()

    try:
        logger.debug("Debut de la connexion à Qdrant...")
        client = qdrant_client.QdrantClient(
            url=settings.qdrant_url,
            api_key=settings.qdrant_api_key
        )

        vector_store = QdrantVectorStore(
            client=client,
            collection_name="finsight_news"
        )
        logger.info("Connexion à Qdrand réussi")

    except Exception as e:
        logger.error("Erreur lors de la connexion à Qdrant: %s", e)
        raise Exception(f"Message: {e}")

    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store
    )

    engine = index.as_query_engine(
        similarity_top_k=5)

    return engine

if __name__ == "__main__":
    rag_engine = get_query_engine()
    response = rag_engine.query("What is the latest news ?")
    print(response)