"""Source-grounded summarization package."""

from app.summarization.fallback import build_extractive_fallback_summary
from app.summarization.llm_client import (
    DEFAULT_LLM_MODEL,
    DEFAULT_OPENAI_BASE_URL,
    OpenAICompatibleClient,
    build_configured_llm_client,
)
from app.summarization.models import (
    DigestSummary,
    LLMClient,
    SourceItem,
    Summarizer,
)
from app.summarization.prompts import UNAVAILABLE, build_source_grounded_prompt
from app.summarization.service import (
    SourceGroundedSummarizer,
    create_summarizer,
    normalize_source_item,
    summarize_item,
)

__all__ = [
    "DEFAULT_LLM_MODEL",
    "DEFAULT_OPENAI_BASE_URL",
    "UNAVAILABLE",
    "DigestSummary",
    "LLMClient",
    "OpenAICompatibleClient",
    "SourceGroundedSummarizer",
    "SourceItem",
    "Summarizer",
    "build_configured_llm_client",
    "build_extractive_fallback_summary",
    "build_source_grounded_prompt",
    "create_summarizer",
    "normalize_source_item",
    "summarize_item",
]
