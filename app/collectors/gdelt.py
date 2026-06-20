from __future__ import annotations

import logging
from typing import Any

import httpx

from app.schemas import CollectedItem, clean_text, normalize_datetime


logger = logging.getLogger(__name__)

GDELT_DOC_API_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def collect_gdelt_articles(
    *,
    query: str,
    timespan: str = "3d",
    max_records: int = 50,
    timeout: float = 20.0,
    client: httpx.Client | None = None,
) -> list[CollectedItem]:
    """Collect global news articles from the GDELT DOC API."""

    clean_query = clean_text(query)
    if not clean_query or max_records <= 0:
        return []

    params = {
        "query": clean_query,
        "mode": "artlist",
        "format": "json",
        "maxrecords": str(max_records),
        "timespan": clean_text(timespan) or "3d",
        "sort": "datedesc",
    }
    close_client = client is None
    http_client = client or httpx.Client(timeout=timeout)
    try:
        response = http_client.get(GDELT_DOC_API_URL, params=params)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("GDELT collection failed: %s", exc)
        return []
    finally:
        if close_client:
            http_client.close()

    articles = payload.get("articles") if isinstance(payload, dict) else None
    if not isinstance(articles, list):
        return []

    items: list[CollectedItem] = []
    seen_urls: set[str] = set()
    for article in articles:
        if not isinstance(article, dict):
            continue
        item = _article_to_item(article)
        if item is None or item.source_url in seen_urls:
            continue
        seen_urls.add(item.source_url)
        items.append(item)

    return items


def _article_to_item(article: dict[str, Any]) -> CollectedItem | None:
    source_url = clean_text(article.get("url"))
    title = clean_text(article.get("title"))
    if not source_url or not title:
        return None

    domain = clean_text(article.get("domain")) or _domain_from_url(source_url)
    source_name = domain or "GDELT"
    seen_date = (
        clean_text(article.get("seendate"))
        or clean_text(article.get("seendatetime"))
        or clean_text(article.get("date"))
    )

    return CollectedItem(
        source_type="news_search",
        source_name=source_name,
        external_id=source_url,
        title=title,
        abstract=title,
        authors=[],
        published_at=normalize_datetime(seen_date),
        source_url=source_url,
        image_url=clean_text(article.get("socialimage")) or None,
        raw_payload=article,
    )


def _domain_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse

        host = urlparse(url).netloc
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host
