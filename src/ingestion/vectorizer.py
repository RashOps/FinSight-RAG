import pymongo
from pymongo import UpdateOne
import llama_index.core
import qdrant_client
from llama_index.core import VectorStoreIndex, Settings, Document
from llama_index.vector_stores.qdrant import QdrantVectorStore
from llama_index.core.node_parser import SentenceSplitter
from llama_index.embeddings.cohere import CohereEmbedding
from src.utils.db_client import get_db
from src.utils.logger import get_logger
from src.config import settings

logger = get_logger(__name__)

def get_article(numb_articles:int = 5) -> list:
    db = get_db()
    collection = db["news-scraped"]
    result = collection.find({"vectorized" : False}).limit(numb_articles)
    
    all_articles = []
    for article in result:
        all_articles.append(article)

    return all_articles

def convert_to_doc(data: list):
    all_doc = []

    for article in data:
        doc = Document(
            content = article["content"],
            metadata={
                "_id": article["_id"],
                "published": article["published_at"],
                "source": article["source"]
                }           
            )
        all_doc.append(doc)
    
    return all_doc

def brain_config():
    # Embedding configuration
    text_splitter = SentenceSplitter(
        chunk_size=settings.chunks, 
        chunk_overlap=50
    )

    embed_model = CohereEmbedding(
        api_key=settings.cohere_api_key,
        model_name="embed-multilingual-v3.0",
    )

    return text_splitter, embed_model


def load_to_qdrant():

    Settings.text_splitter, Settings.embed_model = brain_config()
    client = qdrant_client.QdrantClient(
        url=settings.qdrant_url,
        api_key=settings.qdrant_api_key
    )


if __name__ == "__main__":
    data = get_article()
    print(convert_to_doc(data))
