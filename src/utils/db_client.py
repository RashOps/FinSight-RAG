from pymongo import MongoClient
from pymongo.database import Database

from src.utils.logger import get_logger
from src.config import settings

logger = get_logger(__name__)

_client: MongoClient | None = None

def get_db() -> Database:
    """
    Returns the MongoDB Database object via lazy initialization.

    Returns:
        Database: PyMongo database instance.

    Raises:
        Exception: If connection to MongoDB fails.
    """
    global _client

    if _client is None:
        try:
            logger.debug("Initializing MongoDB connection...")
            _client = MongoClient(settings.mongo_uri)
            _client.admin.command('ping')
            logger.info("Successfully connected to MongoDB.")
        except Exception as e:
            logger.critical("Critical failure connecting to MongoDB: %s", e)
            raise e

    return _client[settings.mongo_db_name]