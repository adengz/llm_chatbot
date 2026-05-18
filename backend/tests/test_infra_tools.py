import json
from typing import Awaitable, Callable

import pytest
from api.infra.tools import WebSearchRequest, ddgs_web_search


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


class TestDDGSWebSearch(WebSearchContract):
    @pytest.fixture
    def search(self) -> Callable[[WebSearchRequest], Awaitable[str]]:
        return ddgs_web_search
