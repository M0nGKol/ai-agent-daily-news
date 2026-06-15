from __future__ import annotations

from datetime import datetime, timezone
import time
from typing import Any

from app.collectors.arxiv import ARXIV_API_URL, collect_arxiv_papers
from app.collectors.rss import collect_rss_items
from app.collectors.semantic_scholar import (
    SEMANTIC_SCHOLAR_SEARCH_URL,
    collect_semantic_scholar_papers,
)


class FakeResponse:
    def __init__(self, *, text: str = "", payload: Any = None) -> None:
        self.text = text
        self._payload = payload
        self.status_code = 200

    def raise_for_status(self) -> None:
        return None

    def json(self) -> Any:
        return self._payload


class FakeHttpClient:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response
        self.get_calls: list[dict[str, Any]] = []
        self.closed = False

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.get_calls.append({"url": url, **kwargs})
        return self.response

    def close(self) -> None:
        self.closed = True


def test_collect_arxiv_papers_normalizes_atom_entries() -> None:
    atom_xml = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2401.00001v2</id>
        <updated>2024-01-03T00:00:00Z</updated>
        <published>2024-01-02T12:30:00Z</published>
        <title>  Large   Language Models  for Agents </title>
        <summary> First line.

        Second line. </summary>
        <author><name> Ada Lovelace </name></author>
        <author><name>Alan Turing</name></author>
        <link href="https://arxiv.org/pdf/2401.00001v2" title="pdf"/>
        <link rel="alternate" href="https://arxiv.org/abs/2401.00001v2"/>
        <category term="cs.AI"/>
      </entry>
      <entry>
        <id>https://arxiv.org/abs/2401.00002</id>
        <updated>2024-01-01T00:00:00Z</updated>
        <title>Second AI Paper</title>
        <summary>Short summary.</summary>
      </entry>
    </feed>
    """
    client = FakeHttpClient(FakeResponse(text=atom_xml))

    items = collect_arxiv_papers(
        query_terms=["cat:cs.AI", 'large "quoted" models'],
        max_results=2,
        client=client,
        timeout=3.0,
    )

    assert len(items) == 2
    assert client.get_calls[0]["url"] == ARXIV_API_URL
    assert client.get_calls[0]["params"]["search_query"] == (
        'cat:cs.AI OR all:"large quoted models"'
    )
    assert client.get_calls[0]["params"]["max_results"] == 2
    assert client.get_calls[0]["timeout"] == 3.0
    assert client.closed is False

    first = items[0]
    assert first.source_type == "paper"
    assert first.source_name == "arXiv"
    assert first.external_id == "2401.00001v2"
    assert first.title == "Large Language Models for Agents"
    assert first.abstract == "First line. Second line."
    assert first.authors == ["Ada Lovelace", "Alan Turing"]
    assert first.published_at == datetime(2024, 1, 2, 12, 30, tzinfo=timezone.utc)
    assert first.source_url == "https://arxiv.org/abs/2401.00001v2"
    assert first.raw_payload["categories"] == ["cs.AI"]

    assert items[1].source_url == "https://arxiv.org/abs/2401.00002"
    assert items[1].external_id == "2401.00002"


def test_collect_semantic_scholar_papers_normalizes_json_results() -> None:
    payload = {
        "data": [
            {
                "paperId": "S2-1",
                "title": "  Agent   Benchmark  ",
                "abstract": "  Measures agent behavior. ",
                "authors": [{"name": " Grace Hopper "}, {"name": ""}, {"bad": "value"}],
                "publicationDate": "2024-02-10",
                "url": "https://www.semanticscholar.org/paper/S2-1",
                "externalIds": {"DOI": "10.0000/unused"},
            },
            {
                "paperId": "S2-2",
                "title": "A DOI-only paper",
                "abstract": "",
                "authors": [],
                "year": 2023,
                "externalIds": {"DOI": "10.1234/example"},
            },
            {"paperId": "", "title": "No usable URL", "externalIds": {}},
        ]
    }
    client = FakeHttpClient(FakeResponse(payload=payload))

    items = collect_semantic_scholar_papers(
        query="  AI agents  ",
        limit=101,
        client=client,
        api_key="test-api-key",
        timeout=4.0,
    )

    assert len(items) == 2
    assert client.get_calls[0]["url"] == SEMANTIC_SCHOLAR_SEARCH_URL
    assert client.get_calls[0]["params"]["query"] == "AI agents"
    assert client.get_calls[0]["params"]["limit"] == 100
    assert client.get_calls[0]["headers"] == {"x-api-key": "test-api-key"}
    assert client.get_calls[0]["timeout"] == 4.0

    first = items[0]
    assert first.source_name == "Semantic Scholar"
    assert first.external_id == "S2-1"
    assert first.title == "Agent Benchmark"
    assert first.abstract == "Measures agent behavior."
    assert first.authors == ["Grace Hopper"]
    assert first.published_at == datetime(2024, 2, 10, tzinfo=timezone.utc)
    assert first.source_url == "https://www.semanticscholar.org/paper/S2-1"

    assert items[1].source_url == "https://doi.org/10.1234/example"
    assert items[1].published_at == datetime(2023, 1, 1, tzinfo=timezone.utc)


def test_collect_rss_items_uses_fake_parser_and_normalizes_entries() -> None:
    parsed_at = time.strptime("2024-03-01", "%Y-%m-%d")
    parser_calls: list[str] = []

    def fake_parser(feed_url: str) -> dict[str, Any]:
        parser_calls.append(feed_url)
        return {
            "bozo": False,
            "feed": {"title": " Example AI Feed "},
            "entries": [
                {
                    "id": "entry-1",
                    "title": "  New   LLM   Release ",
                    "summary": "  Summary with\nextra whitespace. ",
                    "authors": [{"name": " Alice "}, {"author": "Bob"}],
                    "author": "Alice",
                    "published_parsed": parsed_at,
                    "link": "https://example.com/news/1",
                    "media_thumbnail": [
                        {"url": "https://example.com/news/1.jpg", "type": "image/jpeg"}
                    ],
                },
                {
                    "id": "entry-2",
                    "title": "Skipped by limit",
                    "link": "https://example.com/news/2",
                },
            ],
        }

    items = collect_rss_items(
        [" ", "https://feeds.example/rss"],
        limit_per_feed=1,
        parser=fake_parser,
    )

    assert parser_calls == ["https://feeds.example/rss"]
    assert len(items) == 1
    item = items[0]
    assert item.source_type == "rss"
    assert item.source_name == "Example AI Feed"
    assert item.external_id == "entry-1"
    assert item.title == "New LLM Release"
    assert item.abstract == "Summary with extra whitespace."
    assert item.authors == ["Alice", "Bob"]
    assert item.published_at == datetime(2024, 3, 1, tzinfo=timezone.utc)
    assert item.source_url == "https://example.com/news/1"
    assert item.image_url == "https://example.com/news/1.jpg"
    assert item.raw_payload["published_parsed"][:3] == (2024, 3, 1)


def test_collect_rss_items_continues_when_parser_fails() -> None:
    def fake_parser(feed_url: str) -> dict[str, Any]:
        if "bad" in feed_url:
            raise RuntimeError("parser failed")
        return {
            "feed": {"title": "Working Feed"},
            "entries": [{"title": "Working item", "link": "https://example.com/ok"}],
        }

    items = collect_rss_items(
        ["https://feeds.example/bad", "https://feeds.example/ok"],
        parser=fake_parser,
    )

    assert [item.title for item in items] == ["Working item"]
