from typing import Awaitable, Callable

import pytest
from api.infra.tools import WebSearchRequest, WebSearchResponse, ddgs_web_search


class WebSearchContract:
    @pytest.mark.asyncio
    async def test_web_search(
        self, search: Callable[[WebSearchRequest], Awaitable[WebSearchResponse]]
    ):

        request = WebSearchRequest(query="Wikipedia")
        response = await search(request)

        assert len(response.results) > 0
        assert any("wikipedia.org" in r.url for r in response.results)


class TestDDGSWebSearch(WebSearchContract):
    @pytest.fixture
    def search(self) -> Callable[[WebSearchRequest], Awaitable[WebSearchResponse]]:
        return ddgs_web_search
