"""Validated websearch input, CLI output and public response."""

from datetime import date, datetime
from typing import Annotated, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MODEL = "gpt-6-luna"
REASONING_EFFORT = "low"
Query = Annotated[str, Field(min_length=1, max_length=2000, strict=True)]
ResultLimit = Annotated[int, Field(ge=1, le=10, strict=True)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SearchRequest(StrictModel):
    query: Query
    max_results: ResultLimit = 5

    @field_validator("query")
    @classmethod
    def clean_query(cls, value: str) -> str:
        value = value.strip()
        if not value or any(ord(char) < 32 and char not in "\n\t\r" for char in value):
            raise ValueError("query must contain text and no control characters")
        return value


class RawResult(StrictModel):
    title: Annotated[str, Field(min_length=1, max_length=1000)]
    url: Annotated[str, Field(min_length=1, max_length=8192)]
    snippet: Annotated[str, Field(min_length=1, max_length=4000)]
    published_at: str | None

    @field_validator("title", "snippet")
    @classmethod
    def clean_text(cls, value: str) -> str:
        value = " ".join(value.split())
        if not value:
            raise ValueError("text must not be blank")
        return value

    @field_validator("url")
    @classmethod
    def clean_url(cls, value: str) -> str:
        value = value.strip()
        parts = urlsplit(value)
        if (
            parts.scheme.lower() not in {"http", "https"}
            or not parts.hostname
            or parts.username is not None
            or parts.password is not None
            or any(char.isspace() or ord(char) < 32 for char in value)
        ):
            raise ValueError("url must be an absolute HTTP(S) URL without credentials")
        host = parts.hostname.encode("idna").decode("ascii").lower()
        if ":" in host:
            host = f"[{host}]"
        port = parts.port
        scheme = parts.scheme.lower()
        if port is not None and (scheme, port) not in {("http", 80), ("https", 443)}:
            host += f":{port}"
        return urlunsplit((scheme, host, parts.path or "/", parts.query, ""))

    @field_validator("published_at")
    @classmethod
    def clean_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError("published_at must be YYYY-MM-DD or null")
        return value


class RawResponse(StrictModel):
    results: Annotated[list[RawResult], Field(max_length=10)]


class SearchResult(RawResult):
    rank: Annotated[int, Field(ge=1, le=10)]


ErrorCode = Literal[
    "INVALID_ARGUMENT", "CODEX_NOT_FOUND", "CODEX_START_FAILED", "CODEX_FAILED",
    "TIMEOUT", "OUTPUT_TOO_LARGE", "INCOMPLETE_RESPONSE", "SEARCH_NOT_PERFORMED",
    "INVALID_RESPONSE", "INTERNAL_ERROR",
]


class SearchFailure(StrictModel):
    code: ErrorCode
    message: str


class SearchResponse(StrictModel):
    schema_version: Literal["1.0"]
    status: Literal["ok", "error"]
    query: str | None
    provider: Literal["codex-cli"]
    model: Literal["gpt-6-luna"]
    reasoning_effort: Literal["low"]
    searched_at: datetime | None
    search_queries: list[str]
    results: Annotated[list[SearchResult], Field(max_length=10)]
    count: Annotated[int, Field(ge=0, le=10)]
    error: SearchFailure | None

    @model_validator(mode="after")
    def check_consistency(self) -> "SearchResponse":
        if self.count != len(self.results):
            raise ValueError("count must equal result length")
        if [item.rank for item in self.results] != list(range(1, self.count + 1)):
            raise ValueError("ranks must be contiguous and start at 1")
        if len({item.url for item in self.results}) != self.count:
            raise ValueError("result URLs must be unique")
        if self.status == "ok":
            if self.error is not None or self.searched_at is None or not self.query:
                raise ValueError("successful response needs a query, timestamp and no error")
        elif self.error is None or self.results or self.search_queries or self.searched_at is not None:
            raise ValueError("failed response needs an error and no search data")
        return self
