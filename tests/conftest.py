from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import socket
import sys
from types import SimpleNamespace
from typing import Any

import pytest

from app.schemas.items import CollectedItem


if importlib.util.find_spec("feedparser") is None:
    sys.modules["feedparser"] = SimpleNamespace(parse=lambda _url: {"entries": []})


@pytest.fixture(autouse=True)
def block_network_for_unit_tests(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    """Fail fast if an unmarked unit test tries to open a real socket."""

    if request.node.get_closest_marker("integration"):
        return

    def guarded_connect(self: socket.socket, address: Any) -> None:
        raise AssertionError(f"Network call blocked in unit test: {address!r}")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def make_item() -> Any:
    def _make_item(**overrides: Any) -> CollectedItem:
        values: dict[str, Any] = {
            "source_type": "paper",
            "source_name": "arXiv",
            "external_id": "item-1",
            "title": "AI agent benchmark",
            "abstract": "A source abstract about AI agent evaluation and benchmark design.",
            "authors": ["Ada Lovelace"],
            "published_at": datetime(2024, 1, 1, tzinfo=timezone.utc),
            "source_url": "https://example.com/item-1",
            "raw_payload": {},
        }
        values.update(overrides)
        return CollectedItem(**values)

    return _make_item
