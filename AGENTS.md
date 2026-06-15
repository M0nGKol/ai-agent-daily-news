# AGENTS.md

## Project

Daily AI Technology Digest Agent.

## Goal

Collect reliable AI technology news and research papers, summarize them, fact-check them with source links, and send a daily digest to Telegram.

## MVP Stack

- Python 3.11+
- requests / httpx
- feedparser
- SQLAlchemy
- PostgreSQL or SQLite for local MVP
- pytest
- Telegram Bot API
- GitHub Actions cron

## Rules

- Use API or RSS before scraping.
- Do not scrape websites that disallow crawling.
- Do not store secrets in code.
- Use .env and .env.example.
- Every digest item must include a source URL.
- Do not hallucinate claims in summaries.
- Tests must not call real external APIs unless marked as integration tests.
- Keep modules small and readable.

## Commands

Install:
pip install -r requirements.txt

Run daily job:
python -m app.jobs.daily_digest

Run tests:
pytest

## Coding Style

- Use type hints.
- Add docstrings for service-level functions.
- Prefer simple readable code over over-engineering.
- Handle API failures gracefully.
