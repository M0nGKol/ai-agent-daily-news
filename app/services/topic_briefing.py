"""Topic selection, scheduling, and formatting for daily AI learning cards."""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, time
from importlib import resources
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from html import escape

DEFAULT_TOPIC_CATEGORIES: tuple[str, ...] = (
    "Machine Learning",
    "Deep Learning",
    "GenAI Technique",
    "AI Engineering",
    "Evaluation & Safety",
)


@dataclass(frozen=True)
class Topic:
    """A reusable AI learning topic from the local catalog."""

    key: str
    title: str
    category: str
    difficulty: str
    snippet: str
    why_it_matters: str
    try_this: str
    source_url: str


@dataclass(frozen=True)
class TopicCard:
    """A concrete topic card selected for one delivery date."""

    item_order: int
    topic_key: str
    title: str
    category: str
    difficulty: str
    snippet: str
    why_it_matters: str
    try_this: str
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        """Return a serializable dictionary."""
        return asdict(self)


@dataclass(frozen=True)
class PlannedTopicCard:
    """A topic card plus the randomized send time for the day."""

    card: TopicCard
    scheduled_for: datetime

    def to_repository_dict(self) -> dict[str, Any]:
        """Return the repository payload for creating a delivery plan."""
        payload = self.card.to_dict()
        payload["scheduled_for"] = self.scheduled_for
        return payload


def load_topic_catalog() -> list[Topic]:
    """Load the static topic catalog bundled with the application."""
    catalog_path = resources.files("app.content").joinpath("topics.json")
    raw_topics = json.loads(catalog_path.read_text(encoding="utf-8"))
    return [_topic_from_mapping(raw_topic) for raw_topic in raw_topics]


def choose_daily_topic_cards(
    delivery_date: date,
    *,
    count: int = 5,
    catalog: Sequence[Topic] | None = None,
    categories: Sequence[str] = DEFAULT_TOPIC_CATEGORIES,
) -> list[TopicCard]:
    """Choose deterministic daily topic cards with category balance."""
    if count <= 0:
        return []

    topics = list(catalog or load_topic_catalog())
    rng = random.Random(f"topics:{delivery_date.isoformat()}")
    selected: list[Topic] = []

    for category in categories:
        if len(selected) >= count:
            break
        category_topics = [
            topic for topic in topics if topic.category.casefold() == category.casefold()
        ]
        if category_topics:
            selected.append(rng.choice(category_topics))

    if len(selected) < count:
        remaining = [topic for topic in topics if topic.key not in {item.key for item in selected}]
        rng.shuffle(remaining)
        selected.extend(remaining[: count - len(selected)])

    return [
        TopicCard(
            item_order=index,
            topic_key=topic.key,
            title=topic.title,
            category=topic.category,
            difficulty=topic.difficulty,
            snippet=topic.snippet,
            why_it_matters=topic.why_it_matters,
            try_this=topic.try_this,
            source_url=topic.source_url,
        )
        for index, topic in enumerate(selected[:count], start=1)
    ]


def build_daily_topic_plan(
    delivery_date: date,
    *,
    count: int = 5,
    timezone_name: str,
    start_hour: int,
    end_hour: int,
    catalog: Sequence[Topic] | None = None,
) -> list[PlannedTopicCard]:
    """Build daily topic cards with deterministic randomized send times."""
    cards = choose_daily_topic_cards(
        delivery_date,
        count=count,
        catalog=catalog,
    )
    slots = random_daily_send_slots(
        delivery_date,
        count=len(cards),
        timezone_name=timezone_name,
        start_hour=start_hour,
        end_hour=end_hour,
    )
    return [
        PlannedTopicCard(card=card, scheduled_for=scheduled_for)
        for card, scheduled_for in zip(cards, slots, strict=True)
    ]


def random_daily_send_slots(
    delivery_date: date,
    *,
    count: int,
    timezone_name: str,
    start_hour: int,
    end_hour: int,
) -> list[datetime]:
    """Return deterministic random UTC datetimes for a local delivery date."""
    if count <= 0:
        return []
    if not 0 <= start_hour <= 23 or not 0 <= end_hour <= 23 or start_hour >= end_hour:
        raise ValueError("start_hour must be less than end_hour and both must be 0-23")

    rng = random.Random(f"slots:{delivery_date.isoformat()}:{timezone_name}")
    start_minute = start_hour * 60
    end_minute = end_hour * 60
    candidates = _spread_random_minutes(
        rng=rng,
        count=count,
        start_minute=start_minute,
        end_minute=end_minute,
    )

    timezone = ZoneInfo(timezone_name)
    return [
        datetime.combine(
            delivery_date,
            time(hour=minute // 60, minute=minute % 60, tzinfo=timezone),
        ).astimezone(UTC)
        for minute in candidates
    ]


def format_topic_card_message(
    topic: Mapping[str, Any] | object,
    *,
    total: int = 5,
) -> str:
    """Format one topic card as Telegram-compatible HTML."""
    title = _read_field(topic, "title")
    category = _read_field(topic, "category")
    difficulty = _read_field(topic, "difficulty")
    snippet = _read_field(topic, "snippet")
    why_it_matters = _read_field(topic, "why_it_matters")
    try_this = _read_field(topic, "try_this")
    source_url = _read_field(topic, "source_url")
    item_order = _read_field(topic, "item_order")

    return "\n".join(
        [
            f"<b>{escape(str(item_order))}/{total}. {escape(str(title))}</b>",
            f"<i>{escape(str(category))} - {escape(str(difficulty).title())}</i>",
            "",
            f"<b>Snippet</b>\n{escape(str(snippet))}",
            "",
            f"<b>Why it matters</b>\n{escape(str(why_it_matters))}",
            "",
            f"<b>Try this</b>\n{escape(str(try_this))}",
            "",
            f"<a href=\"{escape(str(source_url), quote=True)}\">Source</a>",
        ]
    )


def _topic_from_mapping(raw_topic: Mapping[str, Any]) -> Topic:
    return Topic(
        key=_required(raw_topic, "key"),
        title=_required(raw_topic, "title"),
        category=_required(raw_topic, "category"),
        difficulty=_required(raw_topic, "difficulty"),
        snippet=_required(raw_topic, "snippet"),
        why_it_matters=_required(raw_topic, "why_it_matters"),
        try_this=_required(raw_topic, "try_this"),
        source_url=_required(raw_topic, "source_url"),
    )


def _spread_random_minutes(
    *,
    rng: random.Random,
    count: int,
    start_minute: int,
    end_minute: int,
) -> list[int]:
    minimum_gap = 60 if end_minute - start_minute >= count * 60 else 1
    possible_minutes = list(range(start_minute, end_minute + 1))
    for _ in range(500):
        minutes = sorted(rng.sample(possible_minutes, count))
        if all(right - left >= minimum_gap for left, right in zip(minutes, minutes[1:])):
            return minutes

    step = max((end_minute - start_minute) // count, 1)
    return [
        min(start_minute + (index * step) + rng.randint(0, max(step - 1, 0)), end_minute)
        for index in range(count)
    ]


def _read_field(item: Mapping[str, Any] | object, field_name: str) -> Any:
    if isinstance(item, Mapping):
        return item[field_name]
    return getattr(item, field_name)


def _required(raw_topic: Mapping[str, Any], field_name: str) -> str:
    value = str(raw_topic.get(field_name, "")).strip()
    if not value:
        raise ValueError(f"Topic is missing required field: {field_name}")
    return value
