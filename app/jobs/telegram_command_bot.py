"""CLI entrypoint for the Telegram /digest command bot.

Run with:
    python -m app.jobs.telegram_command_bot
"""

from __future__ import annotations

import argparse
import logging
import sys

from app.config import get_settings
from app.telegram.commands import run_telegram_command_bot
from app.telegram.models import TelegramConfigurationError
from app.utils.logging import configure_logging


logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> int:
    """Run the Telegram command bot."""

    parser = argparse.ArgumentParser(description="Listen for Telegram digest commands.")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Poll Telegram once and exit instead of listening forever.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=1.0,
        help="Seconds to sleep between long-polling requests.",
    )
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging(
        extra_secret_values=(
            settings.telegram_bot_token,
            settings.telegram_chat_id,
            settings.telegram_command_allowed_ids,
            settings.llm_api_key,
            settings.semantic_scholar_api_key,
        )
    )

    try:
        result = run_telegram_command_bot(
            settings,
            listen=not args.once,
            poll_interval_seconds=args.poll_interval,
        )
    except KeyboardInterrupt:
        logger.info("Telegram command bot stopped")
        return 0
    except TelegramConfigurationError as exc:
        logger.error("Telegram command bot is not configured: %s", exc)
        return 1
    except Exception:
        logger.exception("Telegram command bot failed unexpectedly")
        return 1

    logger.info("Telegram command bot result: %s", result)
    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(main())
