import json
from typing import Awaitable, Callable

import pytest
from api.infra.tools import (
    WebScrapeRequest,
    WebSearchRequest,
    ddgs_web_search,
    html2text_web_scrape,
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

        assert "# Example Domain" in response


class TestDDGSWebSearch(WebSearchContract):
    @pytest.fixture
    def search(self) -> Callable[[WebSearchRequest], Awaitable[str]]:
        return ddgs_web_search


class TestHtml2TextWebScrape(WebScrapeContract):
    @pytest.fixture
    def scrape(self) -> Callable[[WebScrapeRequest], Awaitable[str]]:
        return html2text_web_scrape
