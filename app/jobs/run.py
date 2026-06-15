"""Unified job entrypoint that honors DIGEST_MODE.

Run with:
    python -m app.jobs.run

DIGEST_MODE controls which job executes:
    * "digest" / "news" -> live AI engineering news digest (app.jobs.daily_digest)
    * anything else      -> scheduled learning-topic cards (app.jobs.daily_topics)
"""

from __future__ import annotations

import sys

from app.config import get_settings

DIGEST_MODES = {"digest", "news", "daily_digest"}


def main() -> int:
    """Dispatch to the configured job and return its process exit code."""

    settings = get_settings()
    mode = (settings.digest_mode or "topics").strip().lower()

    if mode in DIGEST_MODES:
        from app.jobs.daily_digest import main as digest_main

        return digest_main()

    from app.jobs.daily_topics import main as topics_main

    return topics_main()


if __name__ == "__main__":
    sys.exit(main())
