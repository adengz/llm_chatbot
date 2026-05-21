import asyncio
import json

import httpx
from ddgs import DDGS
from pydantic import BaseModel, Field
from trafilatura import extract

from api.infra.exceptions import ToolExecutionError, reraise_as


class WebSearchRequest(BaseModel):
    """Use this tool to find up-to-date information, news, or specific facts from the web to answer user queries."""

    query: str = Field(
        ...,
        description="The exact word, phrase, or question to find information on the web",
    )
    num_results: int = Field(
        3,
        description="The number of search results to return. Default is 3.",
        ge=1,
        le=10,
    )
    page: int = Field(
        1,
        description="Page number of search results. Default is 1.",
        ge=1,
        le=3,
    )


class WebSearchResult(BaseModel):
    title: str
    url: str
    snippet: str


class WebScrapeRequest(BaseModel):
    """Use this tool to fetch and scrape the content of a web page. It can be used to extract specific information from a web page or to retrieve the main content of the page. The web page might be blocked by anti-scraping measures, in which case the tool will return a 'blocked' status."""

    url: str = Field(..., description="The URL of the web page to fetch and scrape")


def ddgs_search(query: str, num_results: int, page: int) -> list[dict]:
    with DDGS() as ddgs:
        return ddgs.text(query, max_results=num_results, page=page)


@reraise_as(ToolExecutionError)
async def ddgs_web_search(request: WebSearchRequest) -> str:
    loop = asyncio.get_running_loop()
    results = await loop.run_in_executor(
        None, ddgs_search, request.query, request.num_results, request.page
    )
    return json.dumps(
        [{"title": r["title"], "url": r["href"], "snippet": r["body"]} for r in results]
    )


@reraise_as(ToolExecutionError)
async def trafilatura_web_scrape(request: WebScrapeRequest) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    ret = {"status": "success"}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(request.url, headers=headers, follow_redirects=True)
        if response.status_code == 403:
            ret["status"] = "blocked"
            return json.dumps(ret)
        response.raise_for_status()

    content = extract(response.text)
    if content:
        ret["content"] = content
    else:
        ret["status"] = "no_content"
    return json.dumps(ret)
