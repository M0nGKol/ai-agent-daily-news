"""CLI entrypoint for the daily AI news digest pipeline.

Run with:
    python -m app.jobs.daily_digest
"""

from __future__ import annotations

import logging
import sys

from app.config import get_settings
from app.pipelines.news_digest import _log_run_result, run_daily_digest
from app.utils.logging import configure_logging


logger = logging.getLogger(__name__)

def main() -> int:
    """Run the daily digest job and return a process exit code."""

    settings = get_settings()
    configure_logging(
        extra_secret_values=(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            settings.llm_api_key,
            settings.semantic_scholar_api_key,
        )
    )

    try:
        result = run_daily_digest(settings)
    except Exception:
        logger.exception("Daily digest job failed unexpectedly")
        return 1

    _log_run_result(result)
    return 0 if result.succeeded else 1


if __name__ == "__main__":
    sys.exit(main())
