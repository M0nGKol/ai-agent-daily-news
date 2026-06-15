"""Validation helpers for source-grounded digest summaries."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlparse


_URL_RE = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
_NUMBER_RE = re.compile(r"\b\d+(?:[.,]\d+)*(?:%|x|X)?\b")


@dataclass(frozen=True)
class FactCheckIssue:
    """A validation issue that should block or warn on digest publication."""

    code: str
    message: str
    field: str | None = None
    severity: str = "error"


@dataclass(frozen=True)
class FactCheckResult:
    """The outcome of lightweight digest validation checks."""

    passed: bool
    issues: tuple[FactCheckIssue, ...] = ()


def validate_source_url(source_url: str | None) -> FactCheckResult:
    """Validate that a digest source URL is present and publishable."""

    issues: list[FactCheckIssue] = []
    if not source_url or not source_url.strip():
        issues.append(
            FactCheckIssue(
                code="missing_source_url",
                message="Digest items must include a source URL.",
                field="source_url",
            )
        )
        return FactCheckResult(passed=False, issues=tuple(issues))

    parsed = urlparse(source_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        issues.append(
            FactCheckIssue(
                code="unsupported_source_url",
                message="Source URL must be an absolute http(s) URL.",
                field="source_url",
            )
        )

    return FactCheckResult(passed=not issues, issues=tuple(issues))


def validate_source_item(item: Mapping[str, Any] | object) -> FactCheckResult:
    """Reject source items that cannot support a grounded digest summary."""

    issues = list(validate_source_url(_read_field(item, "source_url")).issues)
    title = _clean_text(_read_field(item, "title"))
    abstract = _clean_text(_read_field(item, "abstract"))

    if not title and not abstract:
        issues.append(
            FactCheckIssue(
                code="empty_source_content",
                message="Source item needs a title or abstract before summarization.",
                field="title",
            )
        )

    return FactCheckResult(passed=not issues, issues=tuple(issues))


def validate_digest_summary(
    summary: Mapping[str, Any] | object,
    source_item: Mapping[str, Any] | object | None = None,
) -> FactCheckResult:
    """Validate that a summary is source-linked and free of obvious grounding issues."""

    issues: list[FactCheckIssue] = []
    summary_url = _clean_text(_read_field(summary, "source_url"))
    issues.extend(validate_source_url(summary_url).issues)

    summary_text = _clean_text(_read_field(summary, "summary"))
    why_it_matters = _clean_text(_read_field(summary, "why_it_matters"))
    if not summary_text:
        issues.append(
            FactCheckIssue(
                code="empty_summary",
                message="Digest summary text cannot be empty.",
                field="summary",
            )
        )
    if not why_it_matters:
        issues.append(
            FactCheckIssue(
                code="empty_why_it_matters",
                message="Digest why_it_matters text cannot be empty.",
                field="why_it_matters",
            )
        )

    if source_item is not None:
        source_url = _clean_text(_read_field(source_item, "source_url"))
        if source_url and summary_url and source_url != summary_url:
            issues.append(
                FactCheckIssue(
                    code="source_url_mismatch",
                    message="Summary source URL does not match the source item URL.",
                    field="source_url",
                )
            )
        issues.extend(_validate_grounding(summary_text, why_it_matters, source_item))

    return FactCheckResult(passed=not issues, issues=tuple(issues))


def ensure_publishable_summary(
    summary: Mapping[str, Any] | object,
    source_item: Mapping[str, Any] | object | None = None,
) -> None:
    """Raise ValueError when a digest summary is not safe to publish."""

    result = validate_digest_summary(summary, source_item)
    if not result.passed:
        details = "; ".join(issue.message for issue in result.issues)
        raise ValueError(f"Digest summary failed validation: {details}")


def _validate_grounding(
    summary_text: str,
    why_it_matters: str,
    source_item: Mapping[str, Any] | object,
) -> list[FactCheckIssue]:
    issues: list[FactCheckIssue] = []
    source_url = _clean_text(_read_field(source_item, "source_url"))
    source_text = " ".join(
        text
        for text in (
            _clean_text(_read_field(source_item, "title")),
            _clean_text(_read_field(source_item, "abstract")),
        )
        if text
    )

    if not source_text:
        return [
            FactCheckIssue(
                code="empty_source_content",
                message="Summary cannot be grounded because the source item has no title or abstract.",
                field="summary",
            )
        ]

    combined = f"{summary_text} {why_it_matters}".strip()
    extra_urls = {url.rstrip(".,") for url in _URL_RE.findall(combined)}
    if source_url:
        extra_urls.discard(source_url)
    if extra_urls:
        issues.append(
            FactCheckIssue(
                code="unsupported_external_url",
                message="Summary contains URL(s) that were not present as the source URL.",
                field="summary",
            )
        )

    source_numbers = set(_NUMBER_RE.findall(source_text))
    unsupported_numbers = {
        number for number in _NUMBER_RE.findall(combined) if number not in source_numbers
    }
    if unsupported_numbers:
        issues.append(
            FactCheckIssue(
                code="unsupported_numeric_claim",
                message="Summary contains numeric claim(s) absent from the source fields.",
                field="summary",
            )
        )

    return issues


def _read_field(item: Mapping[str, Any] | object, field_name: str) -> Any:
    if isinstance(item, Mapping):
        return item.get(field_name)
    return getattr(item, field_name, None)


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()
