from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlparse
from xml.etree import ElementTree

import httpx

from app.schemas import CollectedItem, clean_text, normalize_datetime


logger = logging.getLogger(__name__)

ARXIV_API_URL = "https://export.arxiv.org/api/query"
DEFAULT_QUERY_TERMS: tuple[str, ...] = (
    "cat:cs.AI",
    "cat:cs.LG",
    "cat:cs.CL",
    "cat:cs.CV",
    "cat:stat.ML",
    "large language models",
    "generative AI",
)
ATOM_NAMESPACE = {"atom": "http://www.w3.org/2005/Atom"}
ARXIV_SEARCH_PREFIXES = ("ti:", "au:", "abs:", "co:", "jr:", "cat:", "rn:", "id:", "all:")


def collect_arxiv_papers(
    query_terms: Sequence[str] = DEFAULT_QUERY_TERMS,
    max_results: int = 25,
    *,
    client: httpx.Client | None = None,
    timeout: float = 10.0,
) -> list[CollectedItem]:
    """Collect recent AI-related papers from the arXiv Atom API."""
    terms = [clean_text(term) for term in query_terms if clean_text(term)]
    if not terms or max_results <= 0:
        return []

    params = {
        "search_query": _build_search_query(terms),
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }

    should_close = client is None
    http_client = client or httpx.Client(follow_redirects=True)

    try:
        response = http_client.get(ARXIV_API_URL, params=params, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("arXiv collection failed: %s", exc)
        return []
    finally:
        if should_close:
            http_client.close()

    try:
        return _parse_arxiv_feed(response.text, max_results=max_results)
    except ElementTree.ParseError as exc:
        logger.warning("arXiv response was not valid Atom XML: %s", exc)
        return []


def _build_search_query(query_terms: Sequence[str]) -> str:
    return " OR ".join(_format_query_term(term) for term in query_terms)


def _format_query_term(term: str) -> str:
    if term.startswith(ARXIV_SEARCH_PREFIXES):
        return term
    return f'all:"{term.replace(chr(34), "")}"'


def _parse_arxiv_feed(xml_text: str, *, max_results: int) -> list[CollectedItem]:
    root = ElementTree.fromstring(xml_text)
    items: list[CollectedItem] = []

    for entry in root.findall("atom:entry", ATOM_NAMESPACE):
        try:
            item = _entry_to_item(entry)
        except ValueError as exc:
            logger.debug("Skipping arXiv entry without required fields: %s", exc)
            continue

        if item is not None:
            items.append(item)

        if len(items) >= max_results:
            break

    return items


def _entry_to_item(entry: ElementTree.Element) -> CollectedItem | None:
    entry_id = clean_text(_text(entry, "atom:id"))
    links = [dict(link.attrib) for link in entry.findall("atom:link", ATOM_NAMESPACE)]
    source_url = _alternate_link(links) or entry_id

    if not source_url:
        return None

    title = clean_text(_text(entry, "atom:title"))
    abstract = clean_text(_text(entry, "atom:summary"))
    authors = [
        clean_text(author.findtext("atom:name", default="", namespaces=ATOM_NAMESPACE))
        for author in entry.findall("atom:author", ATOM_NAMESPACE)
    ]
    categories = [
        clean_text(category.attrib.get("term"))
        for category in entry.findall("atom:category", ATOM_NAMESPACE)
        if clean_text(category.attrib.get("term"))
    ]
    published = clean_text(_text(entry, "atom:published")) or clean_text(_text(entry, "atom:updated"))

    return CollectedItem(
        source_type="paper",
        source_name="arXiv",
        external_id=_arxiv_id(entry_id or source_url),
        title=title,
        abstract=abstract,
        authors=authors,
        published_at=normalize_datetime(published),
        source_url=source_url,
        raw_payload={
            "id": entry_id,
            "title": title,
            "summary": abstract,
            "published": clean_text(_text(entry, "atom:published")),
            "updated": clean_text(_text(entry, "atom:updated")),
            "authors": authors,
            "links": links,
            "categories": categories,
        },
    )


def _text(entry: ElementTree.Element, path: str) -> str:
    return entry.findtext(path, default="", namespaces=ATOM_NAMESPACE)


def _alternate_link(links: Sequence[dict[str, str]]) -> str:
    for link in links:
        if link.get("rel") == "alternate" and link.get("href"):
            return clean_text(link["href"])
    for link in links:
        if link.get("href"):
            return clean_text(link["href"])
    return ""


def _arxiv_id(value: str) -> str:
    parsed = urlparse(value)
    path = parsed.path.rstrip("/")
    if path:
        return clean_text(path.rsplit("/", 1)[-1])
    return clean_text(value)
