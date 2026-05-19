import json
from typing import Awaitable, Callable

import pytest
from api.infra.tools import (
    WebScrapeRequest,
    WebSearchRequest,
    crawl4ai_web_scrape,
    ddgs_web_search,
)


class WebSearchContract:
    @pytest.mark.asyncio
    async def test_web_search(
        self, search: Callable[[WebSearchRequest], Awaitable[str]]
    ):

        request = WebSearchRequest(query="Wikipedia")
        response = await search(request)

        results = json.loads(response)
        assert isinstance(results, list)
        assert len(results) > 0
        assert any("wikipedia.org" in r["url"] for r in results)


class WebScrapeContract:
    @pytest.mark.asyncio
    async def test_web_scrape(
        self, scrape: Callable[[WebScrapeRequest], Awaitable[str]]
    ):
        request = WebScrapeRequest(url="https://example.com")
        response = await scrape(request)

        assert "Example Domain" in response


class TestDDGSWebSearch(WebSearchContract):
    @pytest.fixture
    def search(self) -> Callable[[WebSearchRequest], Awaitable[str]]:
        return ddgs_web_search


class TestCrawl4AIWebScrape(WebScrapeContract):
    @pytest.fixture
    def scrape(self) -> Callable[[WebScrapeRequest], Awaitable[str]]:
        return crawl4ai_web_scrape
