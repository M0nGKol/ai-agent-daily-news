from __future__ import annotations

from datetime import UTC, datetime
from tempfile import NamedTemporaryFile

from app.config import Settings
from app.jobs import daily_topics
from app.services.telegram import TelegramDeliveryResult


def test_run_daily_topics_force_sends_only_one_topic(monkeypatch) -> None:
    sent_messages: list[str] = []

    def fake_send(messages, **kwargs):
        sent_messages.extend(messages)
        return [
            TelegramDeliveryResult(
                ok=True,
                message_index=1,
                total_messages=1,
                character_count=len(messages[0]),
                telegram_message_id=123,
            )
        ]

    monkeypatch.setattr(daily_topics, "send_telegram_messages", fake_send)

    with NamedTemporaryFile(suffix=".db") as tmp:
        settings = Settings(
            database_url=f"sqlite:///{tmp.name}",
            telegram_bot_token="token",
            telegram_chat_id="chat",
            max_digest_items=5,
            topic_timezone="Asia/Phnom_Penh",
            _env_file=None,
        )

        result = daily_topics.run_daily_topics(
            settings=settings,
            now=datetime(2026, 6, 13, 1, tzinfo=UTC),
            force=True,
        )

    assert result.succeeded is True
    assert result.delivery_attempted is True
    assert result.sent_count == 1
    assert len(sent_messages) == 1
    assert "<b>1/5." in sent_messages[0]
    assert "<b>Snippet</b>" in sent_messages[0]


def test_run_daily_topics_noops_when_nothing_is_due(monkeypatch) -> None:
    monkeypatch.setattr(
        daily_topics,
        "send_telegram_messages",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not send")),
    )

    with NamedTemporaryFile(suffix=".db") as tmp:
        settings = Settings(
            database_url=f"sqlite:///{tmp.name}",
            telegram_bot_token="token",
            telegram_chat_id="chat",
            max_digest_items=5,
            topic_timezone="Asia/Phnom_Penh",
            topic_send_start_hour=20,
            topic_send_end_hour=22,
            _env_file=None,
        )

        result = daily_topics.run_daily_topics(
            settings=settings,
            now=datetime(2026, 6, 13, 1, tzinfo=UTC),
            force=False,
        )

    assert result.succeeded is True
    assert result.delivery_attempted is False
    assert result.sent_count == 0
