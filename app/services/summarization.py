"""Source-grounded summarization services for daily AI digest items."""

from __future__ import annotations

import html
import json
import os
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime
from typing import Any, Callable, Mapping, Protocol, Sequence
from urllib import request
from urllib.error import HTTPError, URLError

from app.services.fact_checking import ensure_publishable_summary, validate_source_item


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL = "gpt-4o-mini"
UNAVAILABLE = "Not available in source."


class LLMClient(Protocol):
    """Minimal LLM interface so tests can inject a fake completion client."""

    def complete(self, prompt: str) -> str:
        """Return model text for a prepared prompt."""


@dataclass(frozen=True)
class SourceItem:
    """Normalized source data used by summarization and fact checking."""

    title: str
    source_url: str
    abstract: str = ""
    authors: tuple[str, ...] = ()
    published_at: str | None = None
    source_name: str | None = None
    source_type: str | None = None


@dataclass(frozen=True)
class DigestSummary:
    """A publishable, source-linked summary for the daily digest."""

    title: str
    summary: str
    why_it_matters: str
    source_url: str
    confidence_score: float
    confidence_category: str
    source_name: str | None = None
    source_type: str | None = None
    model_used: str | None = None
    used_fallback: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dictionary representation for rendering or persistence."""

        return asdict(self)


class Summarizer(Protocol):
    """Minimal summarization interface for mocking service-level behavior."""

    def summarize(self, item: Mapping[str, Any] | object) -> DigestSummary:
        """Create a digest summary for one source item."""


class OpenAICompatibleClient:
    """Small OpenAI-compatible chat completions client.

    No HTTP request is made until ``complete`` is called. Pass a fake ``urlopen``
    in tests to avoid real network access.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        timeout_seconds: float = 20.0,
        urlopen: Callable[..., Any] | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._urlopen = urlopen or request.urlopen

    def complete(self, prompt: str) -> str:
        """Call an OpenAI-compatible chat completions endpoint."""

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You summarize AI technology sources using only the "
                        "provided source fields. Return strict JSON only."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        req = request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with self._urlopen(req, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise RuntimeError("LLM summarization request failed") from exc

        try:
            return str(data["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM summarization response was missing content") from exc


class SourceGroundedSummarizer:
    """Summarize source items with an optional LLM and deterministic fallback."""

    def __init__(
        self,
        llm_client: LLMClient | None = None,
        model_used: str | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.model_used = model_used

    def summarize(self, item: Mapping[str, Any] | object) -> DigestSummary:
        """Create a validated digest summary for a single source item."""

        source = normalize_source_item(item)
        source_validation = validate_source_item(source)
        if not source_validation.passed:
            details = "; ".join(issue.message for issue in source_validation.issues)
            raise ValueError(f"Source item failed validation: {details}")

        if self.llm_client is not None:
            try:
                prompt = build_source_grounded_prompt(source)
                summary = self._summary_from_llm_text(source, self.llm_client.complete(prompt))
                ensure_publishable_summary(summary, source)
                return summary
            except (RuntimeError, ValueError, json.JSONDecodeError, TypeError):
                pass

        summary = build_extractive_fallback_summary(source, model_used=self.model_used)
        ensure_publishable_summary(summary, source)
        return summary

    def _summary_from_llm_text(self, source: SourceItem, raw_text: str) -> DigestSummary:
        data = json.loads(_extract_json_object(raw_text))
        summary = _clean_text(data.get("summary")) or UNAVAILABLE
        why_it_matters = _clean_text(data.get("why_it_matters")) or UNAVAILABLE
        score = _coerce_score(data.get("confidence_score"), default=0.75)
        category = _confidence_category(score)

        return DigestSummary(
            title=_clean_text(data.get("title")) or source.title,
            summary=summary,
            why_it_matters=why_it_matters,
            source_url=source.source_url,
            confidence_score=score,
            confidence_category=category,
            source_name=source.source_name,
            source_type=source.source_type,
            model_used=self.model_used,
            used_fallback=False,
        )


def summarize_item(
    item: Mapping[str, Any] | object,
    *,
    llm_client: LLMClient | None = None,
    config: Mapping[str, Any] | object | None = None,
) -> DigestSummary:
    """Summarize one source item, using a configured LLM only when available."""

    summarizer = create_summarizer(llm_client=llm_client, config=config)
    return summarizer.summarize(item)


def create_summarizer(
    *,
    llm_client: LLMClient | None = None,
    config: Mapping[str, Any] | object | None = None,
) -> SourceGroundedSummarizer:
    """Build a summarizer with an injected client or configured HTTP client."""

    if llm_client is not None:
        model_used = _read_config_value(config, "LLM_MODEL") if config is not None else None
        return SourceGroundedSummarizer(llm_client=llm_client, model_used=model_used)

    configured_client = build_configured_llm_client(config)
    return SourceGroundedSummarizer(
        llm_client=configured_client,
        model_used=configured_client.model if configured_client is not None else None,
    )


def build_configured_llm_client(
    config: Mapping[str, Any] | object | None = None,
) -> OpenAICompatibleClient | None:
    """Create an OpenAI-compatible client only when provider and API key exist."""

    if config is None:
        provider = os.getenv("LLM_PROVIDER")
        api_key = os.getenv("LLM_API_KEY")
        model = os.getenv("LLM_MODEL") or DEFAULT_LLM_MODEL
        base_url = os.getenv("LLM_BASE_URL") or os.getenv("LLM_API_BASE_URL")
    else:
        provider = _read_config_value(config, "LLM_PROVIDER")
        api_key = _read_config_value(config, "LLM_API_KEY")
        model = _read_config_value(config, "LLM_MODEL") or DEFAULT_LLM_MODEL
        base_url = _read_config_value(config, "LLM_BASE_URL") or _read_config_value(
            config, "LLM_API_BASE_URL"
        )

    provider = _clean_text(provider).lower()
    api_key = _clean_text(api_key)
    model = _clean_text(model)
    if not provider or not api_key or not model:
        return None

    resolved_base_url = _resolve_base_url(provider, base_url)
    if resolved_base_url is None:
        return None

    return OpenAICompatibleClient(
        api_key=api_key,
        model=model,
        base_url=resolved_base_url,
    )


def normalize_source_item(item: Mapping[str, Any] | object) -> SourceItem:
    """Normalize mapping or object source records into the service input model."""

    authors = _normalize_authors(_read_field(item, "authors"))
    published_at = _normalize_published_at(_read_field(item, "published_at"))
    source_name = _read_field(item, "source_name") or _read_field(item, "source")

    return SourceItem(
        title=_clean_text(_read_field(item, "title")),
        abstract=_clean_text(_read_field(item, "abstract")),
        authors=authors,
        published_at=published_at,
        source_url=_clean_text(_read_field(item, "source_url")),
        source_name=_clean_text(source_name) or None,
        source_type=_clean_text(_read_field(item, "source_type")) or None,
    )


def build_source_grounded_prompt(source: SourceItem) -> str:
    """Build a safe prompt that constrains the model to provided source fields."""

    authors = ", ".join(source.authors) if source.authors else UNAVAILABLE
    return (
        "Summarize this single source for a daily AI technology digest.\n"
        "Rules:\n"
        "- Use only the source fields below; do not add outside facts.\n"
        f"- Include this exact source_url in the JSON: {source.source_url}\n"
        f"- If a detail is unavailable, say \"{UNAVAILABLE}\"\n"
        "- Keep summary to 1-2 concise sentences.\n"
        "- Keep why_it_matters to 1 concise sentence grounded in the source.\n"
        "- Return JSON with keys: title, summary, why_it_matters, source_url, "
        "confidence_score.\n\n"
        f"title: {source.title or UNAVAILABLE}\n"
        f"abstract: {source.abstract or UNAVAILABLE}\n"
        f"authors: {authors}\n"
        f"published_at: {source.published_at or UNAVAILABLE}\n"
        f"source_name: {source.source_name or UNAVAILABLE}\n"
        f"source_type: {source.source_type or UNAVAILABLE}\n"
        f"source_url: {source.source_url}\n"
    )


def build_extractive_fallback_summary(
    source: SourceItem,
    *,
    model_used: str | None = None,
) -> DigestSummary:
    """Build a deterministic summary directly from the source title and abstract."""

    title = source.title or UNAVAILABLE
    if source.abstract:
        extracted = _first_sentences(source.abstract, max_sentences=2)
        summary = extracted or source.abstract
    else:
        summary = f"Source did not provide an abstract; available title: {title}."

    why_it_matters = _fallback_why_it_matters(source)
    score = _fallback_confidence(source)

    return DigestSummary(
        title=title,
        summary=summary,
        why_it_matters=why_it_matters,
        source_url=source.source_url,
        confidence_score=score,
        confidence_category=_confidence_category(score),
        source_name=source.source_name,
        source_type=source.source_type,
        model_used=model_used,
        used_fallback=True,
    )


def _fallback_why_it_matters(source: SourceItem) -> str:
    source_text = f"{source.title} {source.abstract}".strip()
    matched_terms = _extract_known_terms(source_text)
    if matched_terms:
        return (
            "Worth watching for teams tracking "
            f"{', '.join(matched_terms[:3])}."
        )
    return "Worth scanning as part of today's AI technology watchlist."


def _fallback_confidence(source: SourceItem) -> float:
    if len(source.abstract) >= 500:
        return 0.78
    if len(source.abstract) >= 160:
        return 0.68
    if source.abstract:
        return 0.55
    return 0.35


def _extract_known_terms(text: str) -> list[str]:
    candidates = (
        "AI",
        "agent",
        "benchmark",
        "dataset",
        "evaluation",
        "GPU",
        "LLM",
        "model",
        "open source",
        "research",
        "robotics",
        "safety",
    )
    lowered = text.lower()
    matched_terms: list[str] = []
    for term in candidates:
        pattern = r"\b" + re.escape(term.lower()).replace(r"\ ", r"\s+") + r"\b"
        if re.search(pattern, lowered):
            matched_terms.append(term)
    return matched_terms


def _first_sentences(text: str, *, max_sentences: int) -> str:
    sentences = [
        part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()
    ]
    if not sentences:
        return ""
    return " ".join(sentences[:max_sentences])


def _extract_json_object(raw_text: str) -> str:
    stripped = raw_text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", raw_text, 0)
    return stripped[start : end + 1]


def _resolve_base_url(provider: str, configured_base_url: Any) -> str | None:
    base_url = _clean_text(configured_base_url)
    if base_url:
        return base_url.rstrip("/")
    if provider in {"openai", "openai-compatible"}:
        return DEFAULT_OPENAI_BASE_URL
    if provider.startswith("http://") or provider.startswith("https://"):
        return provider.rstrip("/")
    return None


def _coerce_score(value: Any, *, default: float) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    return max(0.0, min(1.0, score))


def _confidence_category(score: float) -> str:
    if score >= 0.75:
        return "high"
    if score >= 0.5:
        return "medium"
    return "low"


def _normalize_authors(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = re.split(r",| and ", value)
        return tuple(_clean_text(part) for part in parts if _clean_text(part))
    if isinstance(value, Sequence):
        return tuple(_clean_text(author) for author in value if _clean_text(author))
    return (_clean_text(value),) if _clean_text(value) else ()


def _normalize_published_at(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return _clean_text(value) or None


def _read_config_value(config: Mapping[str, Any] | object | None, field_name: str) -> Any:
    if config is None:
        return None
    return _read_field(config, field_name) or _read_field(config, field_name.lower())


def _read_field(item: Mapping[str, Any] | object, field_name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(field_name)
    return getattr(item, field_name, None)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()
