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


async def web_search(request: WebSearchRequest) -> WebSearchResponse:
    # Mock implementation for testing
    return WebSearchResponse(
        results=[
            WebSearchResult(
                title="Example Result",
                url="https://www.example.com",
                snippet=f"Mock search result for query: {request.query}",
            )
        ]
    )
