from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services import telegram


class FakeTelegramResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> Any:
        return self._payload


class FakeTelegramClient:
    def __init__(self, responses: list[FakeTelegramResponse] | None = None) -> None:
        self.responses = responses or []
        self.requests: list[dict[str, Any]] = []

    def post(self, url: str, *, json: dict[str, Any]) -> FakeTelegramResponse:
        self.requests.append({"url": url, "json": json})
        return self.responses.pop(0)


@pytest.fixture
def stub_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        telegram,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_bot_token=None,
            telegram_chat_id=None,
            http_timeout_seconds=20,
        ),
    )


def test_format_digest_message_escapes_html_and_requires_source_url() -> None:
    message = telegram.format_digest_message(
        [
            {
                "title": "<Model> & news",
                "summary": "Uses <tags> & symbols.",
                "why_it_matters": "Useful for R&D teams.",
                "category": "Research & releases",
                "source_url": "https://example.com/news?a=1&b=2",
            }
        ],
        title="AI <Digest>",
    )

    assert "<b>AI &lt;Digest&gt;</b>" in message
    assert "1 curated AI update(s)." in message
    assert "<b>1/1. &lt;Model&gt; &amp; news</b>" in message
    assert "<i>Research &amp; releases</i>" in message
    assert "<b>Summary</b>" in message
    assert "Uses &lt;tags&gt; &amp; symbols." in message
    assert '<a href="https://example.com/news?a=1&amp;b=2">Read source</a>' in message

    with pytest.raises(ValueError, match="source_url"):
        telegram.format_digest_message([{"title": "No source"}])


def test_send_digest_to_telegram_posts_formatted_message(stub_settings: None) -> None:
    client = FakeTelegramClient(
        [
            FakeTelegramResponse(200, {"ok": True, "result": {"message_id": 777}}),
            FakeTelegramResponse(200, {"ok": True, "result": {"message_id": 778}}),
        ]
    )

    results = telegram.send_digest_to_telegram(
        [
            {
                "title": "Agent benchmark",
                "summary": "A source-grounded summary.",
                "why_it_matters": "It may help readers track evaluation.",
                "source_url": "https://example.com/agent-benchmark",
            }
        ],
        title="Daily Test Digest",
        bot_token="bot-token",
        chat_id=12345,
        timeout_seconds=2.0,
        client=client,
    )

    assert len(results) == 2
    assert results[0].ok is True
    assert results[0].telegram_message_id == 777
    assert results[0].status_code == 200
    assert results[1].telegram_message_id == 778
    assert len(client.requests) == 2
    request = client.requests[0]
    assert request["url"] == f"{telegram.TELEGRAM_API_BASE_URL}/botbot-token/sendMessage"
    assert request["json"]["chat_id"] == "12345"
    assert request["json"]["parse_mode"] == "HTML"
    assert request["json"]["disable_web_page_preview"] is True
    assert "<b>Daily Test Digest</b>" in request["json"]["text"]
    item_request = client.requests[1]
    assert item_request["url"] == f"{telegram.TELEGRAM_API_BASE_URL}/botbot-token/sendMessage"
    assert item_request["json"]["disable_web_page_preview"] is False
    assert "<b>1/1. Agent benchmark</b>" in item_request["json"]["text"]
    assert "Read source" in item_request["json"]["text"]


def test_send_digest_to_telegram_uses_photo_when_image_url_exists(stub_settings: None) -> None:
    client = FakeTelegramClient(
        [
            FakeTelegramResponse(200, {"ok": True, "result": {"message_id": 1}}),
            FakeTelegramResponse(200, {"ok": True, "result": {"message_id": 2}}),
        ]
    )

    results = telegram.send_digest_to_telegram(
        [
            {
                "title": "AI product launch",
                "summary": "A concise launch summary.",
                "why_it_matters": "It affects AI builders.",
                "source_url": "https://example.com/launch",
                "image_url": "https://example.com/launch.jpg",
            }
        ],
        bot_token="bot-token",
        chat_id=12345,
        client=client,
    )

    assert len(results) == 2
    assert all(result.ok for result in results)
    photo_request = client.requests[1]
    assert photo_request["url"] == f"{telegram.TELEGRAM_API_BASE_URL}/botbot-token/sendPhoto"
    assert photo_request["json"]["photo"] == "https://example.com/launch.jpg"
    assert "<b>1/1. AI product launch</b>" in photo_request["json"]["caption"]


def test_send_telegram_messages_returns_api_error(stub_settings: None) -> None:
    client = FakeTelegramClient(
        [
            FakeTelegramResponse(
                400,
                {"ok": False, "description": "Bad Request: chat not found"},
            )
        ]
    )

    results = telegram.send_telegram_messages(
        ["<b>Hello</b>"],
        bot_token="bot-token",
        chat_id="chat-id",
        timeout_seconds=2.0,
        client=client,
    )

    assert len(results) == 1
    assert results[0].ok is False
    assert results[0].status_code == 400
    assert results[0].error == "Bad Request: chat not found"


def test_send_telegram_messages_dry_run_does_not_use_http() -> None:
    results = telegram.send_telegram_messages(["<b>Hello</b>"], dry_run=True)

    assert len(results) == 1
    assert results[0].dry_run is True
    assert results[0].ok is False
    assert "Dry run" in str(results[0].error)
