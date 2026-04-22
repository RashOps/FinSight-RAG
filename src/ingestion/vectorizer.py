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

def get_article(numb_articles:int = 5) -> list:
    """
    Load article from MongoDB
    """
    logger.debug("Début du chargement des articles...")

    try:
        db = get_db()
        collection = db["news-scraped"]
        result = collection.find({"vectorized" : False}).limit(numb_articles)
        
        all_articles = []
        for article in result:
            all_articles.append(article)

        logger.info("Chargement des articles effectué: %s", len(all_articles))
        return all_articles
    
    except Exception as e:
        logger.error("Un problème est survenue lors du chargement des articles: %s", e)
        raise Exception(f"Une erreur est survenue: {e}")

def convert_to_doc(data: list):
    """
    Convert all article to Llama Document with metadata
    """
    logger.debug("Lancement de la convertion des articles en document")

    all_doc = []
    try:
        for article in data:
            doc = Document(
                text = article["content"],
                metadata={
                    "_id": article["_id"],
                    "published": article["published_at"],
                    "source": article["source"]
                    }           
                )
            all_doc.append(doc)

        logger.info("Tous les articles ont été convertis: %s", len(all_doc))
        return all_doc
    
    except Exception as e:
        logger.error("Une erreur est survenue lors de la convertion des articles en document: %s", e)
        raise Exception(f"Une erreur est survenue lors de la convertion des articles: {e}")
    

def brain_config(documents, model: str = "local"):
    """
    Text splitter and model embedding configuration
    """
    # Embedding configuration
    text_splitter = SentenceSplitter(
        chunk_size=settings.chunks, 
        chunk_overlap=50
    )

    nodes = text_splitter.get_nodes_from_documents(
        documents,
        show_progress=True
        )

    model_embedding = None

    # Switch to match case statement after //
    if model == "cloud":
        embed_model_cohere = CohereEmbedding(
            api_key=settings.cohere_api_key,
            model_name="embed-multilingual-v3.0",
        )
        model_embedding = embed_model_cohere

    if model == "local":
        embed_model_huggingface = HuggingFaceEmbedding(
            model_name=settings.embedding_model
        )
        model_embedding = embed_model_huggingface

    return text_splitter, model_embedding, nodes


def load_to_qdrant(documents):
    """
    Transform into vectors and load to Qdrant
    """
    logger.debug("Debut de la vectorisarion et du chargement des vecteurs")
    Settings.text_splitter, Settings.embed_model, nodes = brain_config(documents, "local")

    client = qdrant_client.QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key
    )

    vector_store = QdrantVectorStore(
        client=client,
        collection_name="finsight_news"
    )

    index = VectorStoreIndex.from_vector_store(
        vector_store=vector_store
    )

    try:
        index.insert_nodes(nodes)
        logger.info("Les nodes ont été correctement chargés")
        return nodes
    except Exception as e:
        logger.error("Erreur lors de l'insertion des nodes: %s", e)
        raise Exception(f"Erreur lors de l'insertion des nodes: {e}")

def update_to_mongodb(documents):
    """
    Update data in mongoDB after vectorization
    """
    logger.debug("Mise a jour des payloads en DB")
    try:
        db = get_db()
        collection = db["news-scraped"]
        logger.info("Connexion reussie")
    except Exception as e:
        logger.error("Erreur lors de la connexion à la DB %s: ", e)
        raise Exception(f"Erreur de connexion DB: {e}")

    nodes = load_to_qdrant(documents)

    article_to_chunks = {}
    operations = []
    vectorized_at = datetime.now(timezone.utc)

    logger.debug("Recupération des IDs depuis les nodes")
    try: 
        for node in nodes:
            mongo_id = node.metadata["_id"]
            chunk_id = node.node_id

            # If ID doesn't exist, it's create a new list to store chunk
            if mongo_id not in article_to_chunks:
                article_to_chunks[mongo_id] = []

            # Store chunk into a list
            article_to_chunks[mongo_id].append(chunk_id)
        logger.info("Récupération des ID effectué avec succès")

    except Exception as e:
        logger.error("Fail to retrieve mongodb _id and chunk_id: %s", e)
        raise Exception(f"Erreur lors de la récuparation des ID: {e}")

    logger.debug("Mise a jour des articles en MongoDB")
    try:
        for mongo_id, chunk_ids_list in article_to_chunks.items():
            news = UpdateOne(
                filter={"_id": mongo_id},
                update={"$set": 
                        {
                        "vectorized": True, 
                        "vectorized_at": vectorized_at, 
                        "qdrant_chunk_ids": chunk_ids_list
                        }
                    }
                )
            operations.append(news)
        logger.info("Mise a jour effectuée avec succès")

    except Exception as e:
        logger.error("Erreur lors de la mise a jour des ID en mongoDB: %s", e)
        raise Exception(f"Erreur lors de la mise a jour des ID en mongoDB: {e}")

    logger.info("Nombre d'opérations détecté: %s", len(operations))
    if operations:
        collection.bulk_write(operations)
        logger.info("Insertion dans la DB réussie: %s", len(operations))
    else:
        logger.error("Aucune operation détecté")

if __name__ == "__main__":
    data = get_article()
    if data:
        doc = convert_to_doc(data)
        update_to_mongodb(doc)
    else:
        logger.info("Aucun nouvel article à vectoriser.")
