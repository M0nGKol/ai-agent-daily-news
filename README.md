# Daily AI Learning Brief Agent

Daily AI Learning Brief Agent is a Python batch-job MVP for sending short, source-linked AI learning topics to Telegram.

The default mode sends 5 AI topic cards per day, one topic at a time, at randomized local times. Topics cover Machine Learning, Deep Learning, GenAI techniques, AI engineering, and evaluation/safety. Each card includes a short snippet, why it matters, a small practical action, and a source URL.

The earlier news digest job is still available at `python -m app.jobs.daily_digest`, but the scheduled workflow now runs the topic dispatcher.

## Requirements

- Python 3.11+
- A Telegram bot token and chat ID for delivery
- Optional API keys for LLM and research providers

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` with local values. Do not commit `.env`.

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./daily_digest.db` | SQLite is the local MVP default. PostgreSQL URLs can be used later with SQLAlchemy. |
| `TELEGRAM_BOT_TOKEN` | empty | Required before sending Telegram topic cards. |
| `TELEGRAM_CHAT_ID` | empty | Required before sending Telegram topic cards. |
| `LLM_PROVIDER` | empty | Provider name used by the summarization slice. |
| `LLM_API_KEY` | empty | API key for the configured LLM provider. |
| `LLM_MODEL` | empty | Model name for the configured LLM provider. |
| `LLM_BASE_URL` | empty | Optional OpenAI-compatible API base URL. |
| `SEMANTIC_SCHOLAR_API_KEY` | empty | Optional key for higher Semantic Scholar limits. |
| `RSS_FEEDS` | curated AI news feeds | Optional comma-separated RSS feed URLs. Blank values use curated defaults. |
| `DIGEST_MODE` | `topics` | Default product mode. |
| `MAX_DIGEST_ITEMS` | `5` | Number of topic cards planned per day. Values above 5 are capped. |
| `TOPIC_TIMEZONE` | `Asia/Phnom_Penh` | Local timezone used for daily topic dates and random send slots. |
| `TOPIC_SEND_START_HOUR` | `8` | Earliest local hour for randomized sends. |
| `TOPIC_SEND_END_HOUR` | `22` | Latest local hour for randomized sends. |
| `TOPIC_DUE_WINDOW_MINUTES` | `75` | How long after a randomized slot an hourly run may send that topic. |
| `HTTP_TIMEOUT_SECONDS` | `20` | Default timeout for HTTP calls. |

## Run

Run the hourly topic dispatcher:

```bash
python -m app.jobs.daily_topics
```

The dispatcher creates today's 5-card plan, checks whether one randomized send slot is due, and sends at most one unsent topic. If no card is due yet, it exits successfully without sending.

For local testing, force the next unsent topic immediately:

```bash
python -m app.jobs.daily_topics --send-now
```

The old news digest entrypoint is still available:

```bash
python -m app.jobs.daily_digest
```

There is no FastAPI service to start.

GitHub Actions runs `.github/workflows/daily_digest.yml` hourly. The app decides whether a topic is due, which gives randomized delivery while still using a simple cron.

For reliable once-only scheduled sends in GitHub Actions, use a persistent `DATABASE_URL` such as PostgreSQL. SQLite is fine locally. The hourly job also uses a due window so temporary CI runs do not keep sending the earliest topic all day, but persistent storage is still the safer production setup.

## Test

```bash
pytest
```

Tests should mock external API calls by default. Real network calls should only appear in tests explicitly marked as integration tests.

## Project Rules

- Prefer APIs and RSS feeds before scraping.
- Do not scrape sites that disallow crawling.
- Do not store secrets in code or logs.
- Every digest item must include a source URL.
- Keep modules small, typed, and readable.
- Handle provider and network failures gracefully.
