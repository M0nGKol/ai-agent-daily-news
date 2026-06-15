from __future__ import annotations

import logging
from typing import Any

import httpx

from app.schemas import CollectedItem, clean_text, normalize_datetime


logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_SEARCH_URL = "https://api.semanticscholar.org/graph/v1/paper/search"
DEFAULT_SEARCH_QUERY = "artificial intelligence machine learning large language models"
SEARCH_FIELDS = "paperId,title,abstract,authors,year,publicationDate,url,externalIds"


def collect_semantic_scholar_papers(
    query: str = DEFAULT_SEARCH_QUERY,
    limit: int = 25,
    *,
    client: httpx.Client | None = None,
    api_key: str | None = None,
    timeout: float = 10.0,
) -> list[CollectedItem]:
    """Search Semantic Scholar papers and normalize results into collected items."""
    normalized_query = clean_text(query)
    if not normalized_query or limit <= 0:
        return []

    params = {
        "query": normalized_query,
        "limit": min(limit, 100),
        "fields": SEARCH_FIELDS,
    }
    headers = {"x-api-key": api_key} if api_key else None
    should_close = client is None
    http_client = client or httpx.Client(follow_redirects=True)

    try:
        response = http_client.get(
            SEMANTIC_SCHOLAR_SEARCH_URL,
            params=params,
            headers=headers,
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Semantic Scholar collection failed: %s", exc)
        return []
    finally:
        if should_close:
            http_client.close()

    papers = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(papers, list):
        logger.warning("Semantic Scholar response did not include a paper list")
        return []

    items: list[CollectedItem] = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue
        try:
            item = _paper_to_item(paper)
        except ValueError as exc:
            logger.debug("Skipping Semantic Scholar paper without required fields: %s", exc)
            continue
        if item is not None:
            items.append(item)
    return items


def _paper_to_item(paper: dict[str, Any]) -> CollectedItem | None:
    paper_id = clean_text(paper.get("paperId"))
    source_url = _source_url_for_paper(paper)
    if not source_url:
        return None

    authors = [
        clean_text(author.get("name"))
        for author in paper.get("authors", [])
        if isinstance(author, dict) and clean_text(author.get("name"))
    ]
    published_value = paper.get("publicationDate") or paper.get("year")

    return CollectedItem(
        source_type="paper",
        source_name="Semantic Scholar",
        external_id=paper_id or source_url,
        title=clean_text(paper.get("title")),
        abstract=clean_text(paper.get("abstract")),
        authors=authors,
        published_at=normalize_datetime(published_value),
        source_url=source_url,
        raw_payload=dict(paper),
    )


def _source_url_for_paper(paper: dict[str, Any]) -> str:
    url = clean_text(paper.get("url"))
    if url:
        return url

    external_ids = paper.get("externalIds")
    if isinstance(external_ids, dict):
        doi = clean_text(external_ids.get("DOI"))
        if doi:
            return f"https://doi.org/{doi}"

        arxiv_id = clean_text(external_ids.get("ArXiv"))
        if arxiv_id:
            return f"https://arxiv.org/abs/{arxiv_id}"

        pubmed_id = clean_text(external_ids.get("PubMed"))
        if pubmed_id:
            return f"https://pubmed.ncbi.nlm.nih.gov/{pubmed_id}/"

    paper_id = clean_text(paper.get("paperId"))
    if paper_id:
        return f"https://www.semanticscholar.org/paper/{paper_id}"

    return ""
