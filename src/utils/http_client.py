"""Stealth HTTP client with TLS impersonation and anti-bot evasion.

Uses curl_cffi for realistic browser TLS fingerprints, fake-useragent
for User-Agent rotation, and httpx as a last-resort fallback.

Architecture:
    curl_cffi (chrome) → curl_cffi (safari) → httpx (enriched headers) → raise
"""

import asyncio
import random
from typing import Optional
from urllib.parse import urlparse, quote_plus
from dataclasses import dataclass, field

from curl_cffi.requests import AsyncSession, Response
from fake_useragent import UserAgent

from src.utils.logger import get_logger
from src.config import settings

logger = get_logger(__name__)

# Browser impersonation targets for fallback rotation
_IMPERSONATE_TARGETS: list[str] = ["chrome", "safari", "chrome110", "edge101"]

# Singleton UserAgent instance (caches UA list on first call)
_ua = UserAgent(browsers=["Chrome", "Edge", "Safari"], os=["Windows", "Mac OS X"])


@dataclass(frozen=True)
class StealthResponse:
    """Normalised response object returned by StealthHttpClient."""

    status_code: int
    text: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)


class StealthHttpClient:
    """Async HTTP client with multi-strategy anti-bot evasion.

    Usage::

        async with StealthHttpClient() as client:
            text = await client.get_text("https://example.com/feed.rss")
    """

    def __init__(
        self,
        max_retries: int = settings.http_max_retries,
        timeout: int = settings.request_timeout,
        impersonate: str = settings.http_impersonate,
        min_delay: float = settings.http_min_delay,
        max_delay: float = settings.http_max_delay,
    ) -> None:
        self._max_retries = max_retries
        self._timeout = timeout
        self._primary_impersonate = impersonate
        self._min_delay = min_delay
        self._max_delay = max_delay
        self._session: Optional[AsyncSession] = None

    # ------------------------------------------------------------------ #
    # Context manager
    # ------------------------------------------------------------------ #

    async def __aenter__(self) -> "StealthHttpClient":
        self._session = AsyncSession()
        return self

    async def __aexit__(self, *exc) -> None:  # type: ignore[override]
        if self._session:
            try:
                await self._session.close()
            except Exception:
                pass
            self._session = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    async def get(self, url: str) -> StealthResponse:
        """Perform a GET request with full anti-bot strategy chain.

        Raises:
            RuntimeError: If all strategies are exhausted.
        """
        self._validate_url(url)

        errors: list[str] = []

        # Strategy 1 — curl_cffi with primary impersonation
        for attempt in range(self._max_retries):
            try:
                resp = await self._curl_request(url, self._primary_impersonate)
                if resp:
                    return resp
            except Exception as exc:
                msg = f"curl_cffi/{self._primary_impersonate} attempt {attempt + 1}: {exc}"
                logger.warning(msg)
                errors.append(msg)
            await self._backoff(attempt)

        # Strategy 2 — Scrape.do API (Premium Fallback)
        if settings.scrape_do_api_key:
            try:
                resp = await self._scrape_do_request(url)
                if resp:
                    logger.info("Scrape.do fallback succeeded for %s", url)
                    return resp
            except Exception as exc:
                msg = f"Scrape.do API fallback: {exc}"
                logger.warning(msg)
                errors.append(msg)
            await self._rate_limit()

        # Strategy 3 — curl_cffi with fallback impersonation targets
        for target in _IMPERSONATE_TARGETS:
            if target == self._primary_impersonate:
                continue
            try:
                resp = await self._curl_request(url, target)
                if resp:
                    logger.info("Fallback impersonate=%s succeeded for %s", target, url)
                    return resp
            except Exception as exc:
                msg = f"curl_cffi/{target} fallback: {exc}"
                logger.warning(msg)
                errors.append(msg)
            await self._rate_limit()

        # Strategy 3 — httpx fallback (last resort)
        try:
            resp = await self._httpx_fallback(url)
            if resp:
                logger.info("httpx fallback succeeded for %s", url)
                return resp
        except Exception as exc:
            msg = f"httpx fallback: {exc}"
            logger.warning(msg)
            errors.append(msg)

        raise RuntimeError(
            f"All strategies exhausted for {url}. "
            f"Errors: {'; '.join(errors[-5:])}"
        )

    async def get_text(self, url: str) -> str:
        """Convenience wrapper returning response body text."""
        response = await self.get(url)
        return response.text

    # ------------------------------------------------------------------ #
    # Private strategies
    # ------------------------------------------------------------------ #

    async def _curl_request(
        self, url: str, impersonate: str, proxy: Optional[str] = None
    ) -> Optional[StealthResponse]:
        """Single curl_cffi request with dynamic headers."""
        headers = self._build_headers(url)

        async with AsyncSession() as session:
            response: Response = await session.get(
                url,
                headers=headers,
                impersonate=impersonate,
                proxy=proxy,
                timeout=self._timeout,
                allow_redirects=True,
            )

        if response.status_code == 403:
            logger.warning(
                "403 Forbidden from %s (impersonate=%s)", url, impersonate
            )
            return None

        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", "10"))
            logger.warning(
                "429 Rate Limited from %s — waiting %ds", url, retry_after
            )
            await asyncio.sleep(retry_after)
            return None

        response.raise_for_status()

        text = response.text
        if not text or not text.strip():
            logger.warning("Empty response body from %s", url)
            return None

        return StealthResponse(
            status_code=response.status_code,
            text=text,
            url=str(response.url),
            headers=dict(response.headers),
        )

    async def _scrape_do_request(self, url: str) -> Optional[StealthResponse]:
        """Scrape.do Proxy fallback to bypass severe IP bans."""
        proxy_url = f"http://{settings.scrape_do_api_key}:customHeaders=false@proxy.scrape.do:8080"
        
        logger.debug("Attempting Scrape.do Proxy Mode for %s", url)
        
        # Call the original target URL using the Scrape.do proxy
        resp = await self._curl_request(url, self._primary_impersonate, proxy=proxy_url)
        
        # 407 means Proxy Authentication Required
        if resp and resp.status_code in (401, 407):
            logger.error("Scrape.do Proxy authentication failed. Check your API key.")
            return None
            
        return resp

    async def _httpx_fallback(self, url: str) -> Optional[StealthResponse]:
        """Last-resort httpx request with enriched headers."""
        import httpx

        headers = self._build_headers(url)

        async with httpx.AsyncClient(
            timeout=self._timeout,
            follow_redirects=True,
            headers=headers,
        ) as client:
            response = await client.get(url)

        if response.status_code in (403, 429):
            logger.warning(
                "httpx fallback got %d from %s", response.status_code, url
            )
            return None

        response.raise_for_status()
        text = response.text

        if not text or not text.strip():
            return None

        return StealthResponse(
            status_code=response.status_code,
            text=text,
            url=str(response.url),
            headers=dict(response.headers),
        )

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _build_headers(self, url: str) -> dict[str, str]:
        """Generate realistic, rotating request headers."""
        parsed = urlparse(url)
        referer_domain = f"{parsed.scheme}://{parsed.netloc}/"

        return {
            "User-Agent": _ua.random,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;"
                "q=0.9,image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-US,en;q=0.9,fr;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": referer_domain,
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "cross-site",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "max-age=0",
        }

    async def _backoff(self, attempt: int) -> None:
        """Exponential backoff with jitter."""
        base = min(2**attempt, 30)
        jitter = random.uniform(0, base * 0.5)
        wait = base + jitter
        logger.debug("Backoff: waiting %.2fs (attempt %d)", wait, attempt + 1)
        await asyncio.sleep(wait)

    async def _rate_limit(self) -> None:
        """Random delay between requests to avoid detection."""
        delay = random.uniform(self._min_delay, self._max_delay)
        await asyncio.sleep(delay)

    @staticmethod
    def _validate_url(url: str) -> None:
        """Validate URL format."""
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string")
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"Invalid URL format: {url}")
