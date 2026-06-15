from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo

from app.services.topic_briefing import (
    DEFAULT_TOPIC_CATEGORIES,
    choose_daily_topic_cards,
    format_topic_card_message,
    load_topic_catalog,
    random_daily_send_slots,
)


def test_load_topic_catalog_has_required_category_coverage() -> None:
    topics = load_topic_catalog()
    categories = {topic.category for topic in topics}

    assert len(topics) >= 20
    assert set(DEFAULT_TOPIC_CATEGORIES).issubset(categories)
    assert all(topic.source_url.startswith("https://") for topic in topics)


def test_choose_daily_topic_cards_is_deterministic_and_balanced() -> None:
    delivery_date = date(2026, 6, 13)

    first = choose_daily_topic_cards(delivery_date, count=5)
    second = choose_daily_topic_cards(delivery_date, count=5)

    assert first == second
    assert [card.item_order for card in first] == [1, 2, 3, 4, 5]
    assert {card.category for card in first} == set(DEFAULT_TOPIC_CATEGORIES)


def test_random_daily_send_slots_are_sorted_and_local_windowed() -> None:
    slots = random_daily_send_slots(
        date(2026, 6, 13),
        count=5,
        timezone_name="Asia/Phnom_Penh",
        start_hour=8,
        end_hour=22,
    )

    assert len(slots) == 5
    assert slots == sorted(slots)
    local_hours = [slot.astimezone(ZoneInfo("Asia/Phnom_Penh")).hour for slot in slots]
    assert all(8 <= hour <= 22 for hour in local_hours)


def test_format_topic_card_message_is_short_and_source_linked() -> None:
    card = choose_daily_topic_cards(date(2026, 6, 13), count=1)[0]
    message = format_topic_card_message(card, total=5)

    assert f"<b>1/5. {card.title}</b>" in message
    assert "<b>Snippet</b>" in message
    assert "<b>Try this</b>" in message
    assert "Source" in message
    assert card.source_url in message
