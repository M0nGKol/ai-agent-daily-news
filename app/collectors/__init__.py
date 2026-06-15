__all__ = [
    "collect_arxiv_papers",
    "collect_rss_items",
    "collect_semantic_scholar_papers",
]


def __getattr__(name: str):
    """Import collectors lazily so one optional dependency cannot break all collectors."""
    if name == "collect_arxiv_papers":
        from app.collectors.arxiv import collect_arxiv_papers

        return collect_arxiv_papers
    if name == "collect_rss_items":
        from app.collectors.rss import collect_rss_items

        return collect_rss_items
    if name == "collect_semantic_scholar_papers":
        from app.collectors.semantic_scholar import collect_semantic_scholar_papers

        return collect_semantic_scholar_papers
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
