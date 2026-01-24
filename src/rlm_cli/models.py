"""Model validation and listing for OpenRouter backend."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# Cache settings
CACHE_DIR = Path.home() / ".cache" / "rlm-cli"
CACHE_FILE = CACHE_DIR / "models.json"
CACHE_TTL_SECONDS = 3600  # 1 hour

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/models"


@dataclass(frozen=True)
class ModelInfo:
    """Information about an OpenRouter model."""

    id: str
    name: str
    context_length: int
    pricing_prompt: float  # per 1M tokens
    pricing_completion: float  # per 1M tokens

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> ModelInfo:
        """Create ModelInfo from OpenRouter API response."""
        pricing = data.get("pricing", {})
        # API returns price per token, convert to per 1M tokens
        prompt_price = float(pricing.get("prompt", 0)) * 1_000_000
        completion_price = float(pricing.get("completion", 0)) * 1_000_000
        return cls(
            id=data.get("id", ""),
            name=data.get("name", data.get("id", "")),
            context_length=int(data.get("context_length", 0)),
            pricing_prompt=prompt_price,
            pricing_completion=completion_price,
        )


@dataclass(frozen=True)
class ModelCache:
    """Cached model list with timestamp."""

    models: list[ModelInfo]
    fetched_at: float

    def is_valid(self) -> bool:
        """Check if cache is still valid (within TTL)."""
        return (time.time() - self.fetched_at) < CACHE_TTL_SECONDS

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-serializable dict."""
        return {
            "fetched_at": self.fetched_at,
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "context_length": m.context_length,
                    "pricing_prompt": m.pricing_prompt,
                    "pricing_completion": m.pricing_completion,
                }
                for m in self.models
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelCache:
        """Create from dict."""
        models = [
            ModelInfo(
                id=m["id"],
                name=m["name"],
                context_length=m["context_length"],
                pricing_prompt=m["pricing_prompt"],
                pricing_completion=m["pricing_completion"],
            )
            for m in data.get("models", [])
        ]
        return cls(models=models, fetched_at=data.get("fetched_at", 0))


@dataclass
class ValidationResult:
    """Result of model validation."""

    valid: bool
    model_id: str
    suggestions: list[str]
    error: str | None = None


def _load_cache() -> ModelCache | None:
    """Load model cache from disk."""
    if not CACHE_FILE.exists():
        return None
    try:
        data = json.loads(CACHE_FILE.read_text())
        cache = ModelCache.from_dict(data)
        if cache.is_valid():
            return cache
        return None
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


def _save_cache(cache: ModelCache) -> None:
    """Save model cache to disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(json.dumps(cache.to_dict(), indent=2))


def fetch_models(api_key: str | None = None, force_refresh: bool = False) -> list[ModelInfo]:
    """Fetch available models from OpenRouter API.

    Args:
        api_key: OpenRouter API key. If None, uses OPENROUTER_API_KEY env var.
        force_refresh: If True, bypass cache and fetch fresh data.

    Returns:
        List of ModelInfo objects.

    Raises:
        RuntimeError: If API request fails.
    """
    # Check cache first
    if not force_refresh:
        cache = _load_cache()
        if cache is not None:
            return cache.models

    # Get API key
    key = api_key or os.getenv("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError(
            "OpenRouter API key required. Set OPENROUTER_API_KEY or pass api_key."
        )

    # Fetch from API
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    request = Request(OPENROUTER_API_URL, headers=headers)

    try:
        with urlopen(request, timeout=30) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as e:
        raise RuntimeError(f"OpenRouter API error: {e.code} {e.reason}") from e
    except URLError as e:
        raise RuntimeError(f"Network error fetching models: {e.reason}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid JSON response from OpenRouter: {e}") from e

    # Parse models
    models_data = data.get("data", [])
    models = [ModelInfo.from_api(m) for m in models_data]

    # Cache results
    cache = ModelCache(models=models, fetched_at=time.time())
    try:
        _save_cache(cache)
    except OSError:
        pass  # Cache save failure is not critical

    return models


def get_model_ids(api_key: str | None = None, force_refresh: bool = False) -> set[str]:
    """Get set of valid model IDs.

    Args:
        api_key: OpenRouter API key.
        force_refresh: If True, bypass cache.

    Returns:
        Set of valid model ID strings.
    """
    models = fetch_models(api_key=api_key, force_refresh=force_refresh)
    return {m.id for m in models}


def _fuzzy_match_score(query: str, candidate: str) -> float:
    """Calculate fuzzy match score between query and candidate."""
    # Normalize for comparison
    query_lower = query.lower()
    candidate_lower = candidate.lower()

    # Exact match
    if query_lower == candidate_lower:
        return 1.0

    # Check if query is substring
    if query_lower in candidate_lower:
        return 0.9

    # Use SequenceMatcher for fuzzy matching
    return SequenceMatcher(None, query_lower, candidate_lower).ratio()


def find_similar_models(
    model_id: str,
    valid_ids: set[str],
    limit: int = 5,
    threshold: float = 0.3,
) -> list[str]:
    """Find similar model IDs using fuzzy matching.

    Args:
        model_id: The invalid model ID to find matches for.
        valid_ids: Set of valid model IDs.
        limit: Maximum number of suggestions to return.
        threshold: Minimum similarity score (0-1) to include.

    Returns:
        List of similar model IDs, sorted by similarity.
    """
    # Score all models
    scored = []
    for valid_id in valid_ids:
        score = _fuzzy_match_score(model_id, valid_id)
        if score >= threshold:
            scored.append((score, valid_id))

    # Sort by score descending
    scored.sort(key=lambda x: (-x[0], x[1]))

    # Return top matches
    return [model_id for _, model_id in scored[:limit]]


def validate_model(
    model_id: str,
    api_key: str | None = None,
    force_refresh: bool = False,
) -> ValidationResult:
    """Validate a model ID against OpenRouter's available models.

    Args:
        model_id: The model ID to validate.
        api_key: OpenRouter API key.
        force_refresh: If True, bypass cache.

    Returns:
        ValidationResult with validity status and suggestions if invalid.
    """
    if not model_id:
        return ValidationResult(
            valid=True,  # Empty model uses backend default
            model_id=model_id,
            suggestions=[],
        )

    try:
        valid_ids = get_model_ids(api_key=api_key, force_refresh=force_refresh)
    except RuntimeError as e:
        # If we can't fetch models, don't block the request
        return ValidationResult(
            valid=True,  # Optimistically allow
            model_id=model_id,
            suggestions=[],
            error=str(e),
        )

    if model_id in valid_ids:
        return ValidationResult(
            valid=True,
            model_id=model_id,
            suggestions=[],
        )

    # Model not found, find suggestions
    suggestions = find_similar_models(model_id, valid_ids)
    return ValidationResult(
        valid=False,
        model_id=model_id,
        suggestions=suggestions,
    )


def format_model_list(
    models: list[ModelInfo],
    *,
    filter_query: str | None = None,
    sort_by: str = "id",
    show_pricing: bool = False,
) -> str:
    """Format model list for display.

    Args:
        models: List of ModelInfo objects.
        filter_query: Optional filter string.
        sort_by: Sort field ("id", "name", "context", "price").
        show_pricing: Whether to show pricing info.

    Returns:
        Formatted string for display.
    """
    # Filter if requested
    if filter_query:
        query_lower = filter_query.lower()
        models = [
            m for m in models
            if query_lower in m.id.lower() or query_lower in m.name.lower()
        ]

    if not models:
        return "No models found."

    # Sort
    if sort_by == "name":
        models = sorted(models, key=lambda m: m.name.lower())
    elif sort_by == "context":
        models = sorted(models, key=lambda m: -m.context_length)
    elif sort_by == "price":
        models = sorted(models, key=lambda m: m.pricing_prompt)
    else:  # Default to id
        models = sorted(models, key=lambda m: m.id.lower())

    # Format output
    lines = [f"Found {len(models)} model(s):", ""]

    for m in models:
        context_k = m.context_length // 1000 if m.context_length else 0
        if show_pricing:
            lines.append(
                f"  {m.id}"
                f"\n    {m.name} | {context_k}K context"
                f"\n    ${m.pricing_prompt:.2f}/${m.pricing_completion:.2f} per 1M tokens (in/out)"
            )
        else:
            lines.append(f"  {m.id} ({context_k}K context)")

    return "\n".join(lines)
