from typing import Optional, Any, Dict, List
from src.config import settings
from src.utils.logger import get_logger
import httpx

# Logger
logger = get_logger(__name__)


class FinnhubNewsProvider:
    """
    Finnhub News API provider with Swagger/OpenAPI support.
    Can leverage llama-index-tools-openapi for automatic tool generation.
    """
    
    SWAGGER_URL = "https://finnhub.io/static/swagger.json"
    BASE_URL = "https://finnhub.io/api/v1"
    
    def __init__(self):
        self.api_key = settings.finnhub_api
        self.tools = None
        self._initialize_tools()
    
    def _initialize_tools(self) -> None:
        """
        Initialize OpenAPI tools from Finnhub Swagger specification.
        Note: Automatic tool generation from OpenAPI spec requires llama-index-tools-openapi v0.1.0+
        For now, we support direct API calls with tool metadata for LLM agent usage.
        """
        try:
            logger.info("Finnhub OpenAPI specification available at: %s", self.SWAGGER_URL)
            # Tools can be auto-generated using: 
            # from llama_index.tools.openapi import OpenAPIToolFactory
            # factory = OpenAPIToolFactory.from_url(self.SWAGGER_URL)
            # self.tools = factory.create_tools()
            self.tools = self._get_available_endpoints()
            logger.info(f"Initialized {len(self.tools)} Finnhub API endpoints")
        except Exception as e:
            logger.warning(f"Note: Full OpenAPI tool generation requires llama-index-tools-openapi. {e}")
            self.tools = self._get_available_endpoints()
    
    def _get_available_endpoints(self) -> List[Dict[str, str]]:
        """Get available Finnhub API endpoints metadata"""
        return [
            {"name": "market_news", "endpoint": "/news", "method": "GET", "description": "Get market news"},
            {"name": "company_news", "endpoint": "/company-news", "method": "GET", "description": "Get company news"},
        ]
    
    async def get_market_news(
        self,
        category: str = "general",
        min_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Fetch market news from Finnhub API.
        
        Args:
            category: News category (general, forex, crypto, merger)
            min_id: Get only news after this ID for pagination
            
        Returns:
            News data from Finnhub
        """
        try:
            params = {
                "token": self.api_key,
                "category": category
            }
            if min_id is not None:
                params["minId"] = min_id
            
            async with httpx.AsyncClient(timeout=settings.request_timeout) as client:
                response = await client.get(
                    f"{self.BASE_URL}/news",
                    params=params
                )
                response.raise_for_status()
                data = response.json()  # httpx returns the object directly, no await
                # Finnhub returns a plain list, not {"data": [...]}
                if isinstance(data, list):
                    data = {"data": data}
                logger.info(f"Successfully fetched {len(data.get('data', []))} articles from Finnhub")
                return data
        except httpx.HTTPError as e:
            logger.error(f"HTTP error in Finnhub news fetching: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in Finnhub news fetching: {e}")
            raise
    
    def get_available_tools(self) -> List[Dict[str, str]]:
        """
        Get list of available Finnhub API tools with metadata.
        """
        return self.tools if self.tools else []


async def get_finnhub_news(category: str = "general", min_id: Optional[int] = None):
    """
    Convenience function to fetch Finnhub news.
    """
    provider = FinnhubNewsProvider()
    return await provider.get_market_news(category=category, min_id=min_id)