import hashlib
from typing import Any, Dict, List, Optional

from llama_index.core.schema import Document

from src.config import settings
from src.ingestion.finnhub_calling import FinnhubNewsProvider
from src.ingestion.news_calling import MarketauxProvider, NewsApiProvider
from src.utils.logger import get_logger

logger = get_logger(__name__)


class LiveProviderManager:
    """Manager for enabling/disabling and querying live news providers."""

    PROVIDERS = {
        "newsapi": {
            "name": "newsapi",
            "display_name": "NewsAPI",
            "description": "Live search against NewsAPI.org",
            "configured_flag": lambda: bool(settings.the_news_api),
        },
        "finnhub": {
            "name": "finnhub",
            "display_name": "Finnhub",
            "description": "Live market news from Finnhub.io",
            "configured_flag": lambda: bool(settings.finnhub_api),
        },
        "marketaux": {
            "name": "marketaux",
            "display_name": "Marketaux",
            "description": "Live financial news from Marketaux",
            "configured_flag": lambda: bool(settings.marketaux_api),
        },
    }

    def __init__(self) -> None:
        self._enabled: Dict[str, bool] = {
            provider: False for provider in self.PROVIDERS
        }

    def get_available_provider_names(self) -> List[str]:
        return list(self.PROVIDERS.keys())

    def get_provider_status(self, name: str) -> Dict[str, Any]:
        provider = self.PROVIDERS.get(name)
        if not provider:
            raise ValueError(f"Unknown provider: {name}")

        return {
            "name": provider["name"],
            "enabled": self._enabled.get(name, False),
            "configured": provider["configured_flag"](),
            "description": provider["description"],
        }

    def get_providers_status(self) -> List[Dict[str, Any]]:
        return [self.get_provider_status(name) for name in self.PROVIDERS]

    def enable_provider(self, name: str) -> None:
        if name not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {name}")
        if not self.PROVIDERS[name]["configured_flag"]():
            raise ValueError(f"Provider '{name}' is not configured")

        self._enabled[name] = True

    def disable_provider(self, name: str) -> None:
        if name not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {name}")
        self._enabled[name] = False

    def is_provider_enabled(self, name: str) -> bool:
        if name not in self.PROVIDERS:
            raise ValueError(f"Unknown provider: {name}")
        return self._enabled.get(name, False)

    def get_enabled_providers(self) -> List[str]:
        return [name for name, enabled in self._enabled.items() if enabled]

    async def fetch_provider_articles(self, provider_name: str, query: str, limit: int) -> List[Dict[str, Any]]:
        if provider_name == "newsapi":
            provider = NewsApiProvider()
            payload = await provider.search_everything(
                q=query,
                search_in="title,description,content",
                language=settings.newsapi_default_language,
                sort_by="publishedAt",
                page_size=min(limit, settings.newsapi_default_page_size),
                page=1
            )
            return payload.get("articles", [])

        if provider_name == "marketaux":
            provider = MarketauxProvider()
            payload = await provider.get_financial_news(
                search=query,
                language=settings.marketaux_default_language,
                limit=min(limit, settings.marketaux_default_limit),
                page=1,
                group_similar=settings.marketaux_group_similar,
            )
            return payload.get("data", [])

        if provider_name == "finnhub":
            provider = FinnhubNewsProvider()
            payload = await provider.get_market_news(category=settings.finnhub_default_category)
            articles = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(articles, list):
                return []
            if query:
                query_lower = query.lower()
                articles = [
                    article for article in articles
                    if query_lower in str(article.get("headline", "")).lower()
                    or query_lower in str(article.get("summary", "")).lower()
                ]
            return articles[:limit]

        raise ValueError(f"Unsupported provider: {provider_name}")

    def _build_document(self, article: Dict[str, Any], provider_name: str) -> Document:
        provider_meta = self.PROVIDERS.get(provider_name, {})
        title = article.get("title") or article.get("headline") or article.get("summary") or "Untitled"
        content = article.get("content") or article.get("description") or article.get("summary") or ""
        url = article.get("url") or article.get("link") or article.get("web_url") or ""
        published_at = article.get("publishedAt") or article.get("published_at") or article.get("published_at_raw") or article.get("datetime") or ""

        doc_id_source = f"{provider_name}:{url or title}"
        doc_id = hashlib.sha256(doc_id_source.encode("utf-8")).hexdigest()

        metadata = {
            "provider": provider_name,
            "provider_name": provider_meta.get("display_name"),
            "url": url,
            "published_at": published_at,
            "source": article.get("source", {}).get("name") if isinstance(article.get("source"), dict) else article.get("source", None)
        }

        text = (
            f"Title: {title}\n"
            f"Provider: {provider_meta.get('display_name')}\n"
            f"Published At: {published_at}\n"
            f"URL: {url}\n\n"
            f"{content}"
        )

        return Document(
            text=text,
            extra_info=metadata,
            id_=doc_id
        )

    async def fetch_documents_for_sources(self, query: str, sources: List[str], limit: int) -> List[Document]:
        documents: List[Document] = []
        for source in sources:
            if source == "scraping":
                continue
            if not self.is_provider_enabled(source):
                raise ValueError(f"Provider not enabled: {source}")
            raw_articles = await self.fetch_provider_articles(source, query, limit)
            for article in raw_articles:
                try:
                    documents.append(self._build_document(article, source))
                except Exception as e:
                    logger.warning("Failed to convert article from %s to document: %s", source, e)
        return documents
