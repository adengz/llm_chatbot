import asyncio
import json

import httpx
from ddgs import DDGS
from html2text import HTML2Text
from pydantic import BaseModel, Field

# from api.infra.exceptions import ToolExecutionError, reraise_as


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


# @reraise_as(ToolExecutionError)
async def ddgs_web_search(request: WebSearchRequest) -> str:
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(None, ddgs_search, request.query)
    return json.dumps(
        [{"title": r["title"], "url": r["href"], "snippet": r["body"]} for r in results]
    )


# @reraise_as(ToolExecutionError)
async def html2text_web_scrape(request: WebScrapeRequest) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(request.url, headers=headers, follow_redirects=True)
        response.raise_for_status()

    markdown_content = HTML2Text().handle(response.text)
    return markdown_content
