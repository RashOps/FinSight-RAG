from datetime import datetime, timezone
from dateutil import parser
from typing import Optional
from src.utils.logger import get_logger

logger = get_logger(__name__)


def standardize_date(date_str: str) -> Optional[datetime]:
    """
    Parses an arbitrary date string into a native UTC datetime object.
    Args:
        date_str (str): The raw date string to parse.
    Returns:
        Optional[datetime]: Native UTC datetime object, or None if parsing fails.
    """
    if not date_str:
        return None
        
    try:
        # Intelligent parsing of the date string
        parsed_date = parser.parse(date_str)
        
        # Ensure timezone awareness
        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(tzinfo=timezone.utc)
            
        # Absolute conversion to UTC for unified storage
        utc_date = parsed_date.astimezone(timezone.utc)
        return utc_date
        
    except Exception as e:
        logger.warning("Temporal normalization failed for string: '%s' - %s", date_str, e)
        return None