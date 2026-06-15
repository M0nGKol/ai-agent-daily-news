from __future__ import annotations

import json
from typing import Any

import pytest

from app.services.summarization import SourceGroundedSummarizer, summarize_item


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.response


def test_summarize_item_uses_deterministic_fallback_without_configured_llm() -> None:
    item = {
        "title": "LLM Evaluation Benchmark",
        "abstract": (
            "This LLM evaluation benchmark compares agent behavior. "
            "It reports dataset design. "
            "A third sentence should be omitted."
        ),
        "source_url": "https://example.com/papers/llm-eval",
        "source_name": "arXiv",
        "source_type": "paper",
    }

    summary = summarize_item(item, config={})

    assert summary.used_fallback is True
    assert summary.title == "LLM Evaluation Benchmark"
    assert summary.summary == (
        "This LLM evaluation benchmark compares agent behavior. "
        "It reports dataset design."
    )
    assert "Worth watching" in summary.why_it_matters
    assert "benchmark" in summary.why_it_matters
    assert summary.source_url == item["source_url"]
    assert summary.confidence_category == "medium"


def test_source_grounded_summarizer_uses_fake_llm_response() -> None:
    source_url = "https://example.com/research/agents"
    fake_llm = FakeLLM(
        "prefix "
        + json.dumps(
            {
                "title": "Agent Evaluation Study",
                "summary": "The source describes an AI agent evaluation benchmark.",
                "why_it_matters": "It may help readers track agent evaluation work.",
                "source_url": "https://wrong.example/ignored",
                "confidence_score": 0.82,
            }
        )
        + " suffix"
    )
    summarizer = SourceGroundedSummarizer(
        llm_client=fake_llm,
        model_used="fake-model",
    )

    summary = summarizer.summarize(
        {
            "title": "Agent Evaluation Study",
            "abstract": "A source about AI agent evaluation benchmark methods.",
            "source_url": source_url,
            "source_name": "Semantic Scholar",
            "source_type": "paper",
        }
    )

    assert len(fake_llm.prompts) == 1
    assert source_url in fake_llm.prompts[0]
    assert "A source about AI agent evaluation benchmark methods." in fake_llm.prompts[0]
    assert summary.used_fallback is False
    assert summary.model_used == "fake-model"
    assert summary.source_url == source_url
    assert summary.confidence_score == 0.82
    assert summary.confidence_category == "high"


def test_source_grounded_summarizer_falls_back_when_fake_llm_is_not_publishable() -> None:
    fake_llm = FakeLLM(
        json.dumps(
            {
                "title": "Agent Evaluation Study",
                "summary": "The source reports a 99% improvement.",
                "why_it_matters": "The unsupported 99% claim should force fallback.",
                "confidence_score": 0.9,
            }
        )
    )
    summarizer = SourceGroundedSummarizer(llm_client=fake_llm)

    summary = summarizer.summarize(
        {
            "title": "Agent Evaluation Study",
            "abstract": "A source about AI agent evaluation benchmark methods.",
            "source_url": "https://example.com/research/agents",
        }
    )

    assert len(fake_llm.prompts) == 1
    assert summary.used_fallback is True
    assert "99%" not in summary.summary


def test_summarizer_rejects_items_without_source_url() -> None:
    with pytest.raises(ValueError, match="Source item failed validation"):
        summarize_item({"title": "Missing source", "abstract": "Has content."}, config={})
