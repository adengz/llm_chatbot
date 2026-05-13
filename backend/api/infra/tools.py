import asyncio

from ddgs import DDGS
from pydantic import BaseModel, Field


class WebSearchRequest(BaseModel):
    """Use this tool to find up-to-date information, news, or specific facts from the web to answer user queries."""

    query: str = Field(
        ...,
        description="The exact word, phrase, or question to find information on the web",
    )


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class WebSearchResponse(BaseModel):
    results: list[WebSearchResult]


def ddgs_search(query: str) -> list[dict]:
    with DDGS() as ddgs:
        return ddgs.text(query, max_results=3)


async def ddgs_web_search(request: WebSearchRequest) -> WebSearchResponse:
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, ddgs_search, request.query)
    return WebSearchResponse(
        results=[
            WebSearchResult(
                title=result["title"],
                url=result["href"],
                snippet=result["body"],
            )
            for result in results
        ]
    )
