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
        for result in response.results:
            assert "wikipedia.org" in result.url


class TestDDGSWebSearch(WebSearchContract):
    @pytest.fixture
    def search(self) -> Callable[[WebSearchRequest], Awaitable[WebSearchResponse]]:
        return ddgs_web_search
