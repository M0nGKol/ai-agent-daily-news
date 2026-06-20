from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.pipelines.news_models import DailyDigestRunResult
from app.telegram.commands import poll_telegram_commands_once


class FakeTelegramResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeTelegramClient:
    def __init__(self, updates: list[dict[str, Any]]) -> None:
        self.updates = updates
        self.get_requests: list[dict[str, Any]] = []
        self.post_requests: list[dict[str, Any]] = []

    def get(self, url: str, *, params: dict[str, Any]) -> FakeTelegramResponse:
        self.get_requests.append({"url": url, "params": params})
        return FakeTelegramResponse(200, {"ok": True, "result": self.updates})

    def post(self, url: str, *, json: dict[str, Any]) -> FakeTelegramResponse:
        self.post_requests.append({"url": url, "json": json})
        return FakeTelegramResponse(200, {"ok": True, "result": {"message_id": 123}})


def test_digest_command_runs_for_allowed_chat() -> None:
    settings = _settings(allowed_ids="111")
    client = FakeTelegramClient([_message_update(chat_id=111, user_id=222, text="/digest")])
    calls: list[Any] = []

    def digest_runner(received_settings: Any) -> DailyDigestRunResult:
        calls.append(received_settings)
        return DailyDigestRunResult(
            collected_count=7,
            selected_count=5,
            summarized_count=5,
            persisted_source_count=7,
            digest_id=10,
            delivery_attempted=True,
            delivery_succeeded=True,
            collector_outcomes=(),
        )

    result = poll_telegram_commands_once(
        settings,
        client=client,
        digest_runner=digest_runner,
    )

    assert result.next_offset == 101
    assert result.handled_commands == 1
    assert result.denied_commands == 0
    assert calls == [settings]
    assert [request["json"]["chat_id"] for request in client.post_requests] == [
        "111",
        "111",
    ]
    assert "Starting" in client.post_requests[0]["json"]["text"]
    assert "Digest sent with 5 item" in client.post_requests[1]["json"]["text"]


def test_digest_command_rejects_unapproved_chat() -> None:
    settings = _settings(allowed_ids="999")
    client = FakeTelegramClient([_message_update(chat_id=111, user_id=222, text="/digest")])
    calls: list[Any] = []

    result = poll_telegram_commands_once(
        settings,
        client=client,
        digest_runner=lambda received_settings: calls.append(received_settings),
    )

    assert result.handled_commands == 0
    assert result.denied_commands == 1
    assert calls == []
    assert "not allowed" in client.post_requests[0]["json"]["text"]


def test_digest_command_defaults_to_target_chat_when_no_allowed_ids() -> None:
    settings = _settings(allowed_ids="", target_chat_id="-100123")
    client = FakeTelegramClient(
        [_message_update(chat_id=-100123, user_id=222, text="/digest@ai_news_bot")]
    )

    result = poll_telegram_commands_once(
        settings,
        client=client,
        digest_runner=lambda _settings: DailyDigestRunResult(
            collected_count=1,
            selected_count=1,
            summarized_count=0,
            persisted_source_count=1,
            digest_id=None,
            delivery_attempted=False,
            delivery_succeeded=False,
            collector_outcomes=(),
        ),
    )

    assert result.handled_commands == 1
    assert result.denied_commands == 0
    assert "no publishable" in client.post_requests[-1]["json"]["text"]


def _settings(
    *,
    allowed_ids: str,
    target_chat_id: str = "-100456",
) -> SimpleNamespace:
    return SimpleNamespace(
        telegram_bot_token="bot-token",
        telegram_chat_id=target_chat_id,
        telegram_command_allowed_ids=allowed_ids,
        telegram_digest_command="/digest",
        telegram_command_poll_timeout_seconds=1,
        http_timeout_seconds=2,
    )


def _message_update(*, chat_id: int, user_id: int, text: str) -> dict[str, Any]:
    return {
        "update_id": 100,
        "message": {
            "text": text,
            "chat": {"id": chat_id},
            "from": {"id": user_id},
        },
    }
