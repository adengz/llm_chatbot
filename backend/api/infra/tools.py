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


class WebScrapeRequest(BaseModel):
    """Use this tool to fetch and scrape the content of a web page. It can be used to extract specific information from a web page or to retrieve the main content of the page."""

    url: str = Field(..., description="The URL of the web page to fetch and scrape")


def ddgs_search(query: str) -> list[dict]:
    with DDGS() as ddgs:
        return ddgs.text(query, max_results=3)


async def ddgs_web_search(request: WebSearchRequest) -> list[WebSearchResult]:
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, ddgs_search, request.query)
    return [
        WebSearchResult(
            title=result["title"],
            url=result["href"],
            snippet=result["body"],
        )
        for result in results
    ]
