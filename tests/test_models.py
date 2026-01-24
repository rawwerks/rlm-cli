"""Tests for model validation and listing."""

import json
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from rlm_cli.models import (
    CACHE_TTL_SECONDS,
    ModelCache,
    ModelInfo,
    ValidationResult,
    _fuzzy_match_score,
    _load_cache,
    _save_cache,
    find_similar_models,
    format_model_list,
    validate_model,
)


class TestModelInfo:
    """Tests for ModelInfo dataclass."""

    def test_from_api(self) -> None:
        data = {
            "id": "openai/gpt-4",
            "name": "OpenAI: GPT-4",
            "context_length": 8192,
            "pricing": {"prompt": 0.00003, "completion": 0.00006},
        }
        model = ModelInfo.from_api(data)
        assert model.id == "openai/gpt-4"
        assert model.name == "OpenAI: GPT-4"
        assert model.context_length == 8192
        assert model.pricing_prompt == 30.0  # per 1M tokens
        assert model.pricing_completion == 60.0

    def test_from_api_missing_fields(self) -> None:
        data = {"id": "test/model"}
        model = ModelInfo.from_api(data)
        assert model.id == "test/model"
        assert model.name == "test/model"
        assert model.context_length == 0
        assert model.pricing_prompt == 0.0
        assert model.pricing_completion == 0.0


class TestModelCache:
    """Tests for model caching."""

    def test_is_valid_fresh_cache(self) -> None:
        cache = ModelCache(models=[], fetched_at=time.time())
        assert cache.is_valid()

    def test_is_valid_stale_cache(self) -> None:
        old_time = time.time() - CACHE_TTL_SECONDS - 1
        cache = ModelCache(models=[], fetched_at=old_time)
        assert not cache.is_valid()

    def test_to_dict_and_from_dict(self) -> None:
        models = [
            ModelInfo(
                id="test/model",
                name="Test Model",
                context_length=1000,
                pricing_prompt=1.0,
                pricing_completion=2.0,
            )
        ]
        original = ModelCache(models=models, fetched_at=12345.0)
        data = original.to_dict()
        restored = ModelCache.from_dict(data)
        assert len(restored.models) == 1
        assert restored.models[0].id == "test/model"
        assert restored.fetched_at == 12345.0

    def test_save_and_load_cache(self, tmp_path: Path) -> None:
        models = [
            ModelInfo(
                id="test/model",
                name="Test",
                context_length=1000,
                pricing_prompt=1.0,
                pricing_completion=2.0,
            )
        ]
        cache = ModelCache(models=models, fetched_at=time.time())

        cache_file = tmp_path / "models.json"
        with patch("rlm_cli.models.CACHE_FILE", cache_file):
            with patch("rlm_cli.models.CACHE_DIR", tmp_path):
                _save_cache(cache)
                loaded = _load_cache()
                assert loaded is not None
                assert len(loaded.models) == 1
                assert loaded.models[0].id == "test/model"

    def test_load_cache_returns_none_for_stale(self, tmp_path: Path) -> None:
        models = [
            ModelInfo(
                id="test/model",
                name="Test",
                context_length=1000,
                pricing_prompt=1.0,
                pricing_completion=2.0,
            )
        ]
        # Create stale cache
        stale_time = time.time() - CACHE_TTL_SECONDS - 100
        cache = ModelCache(models=models, fetched_at=stale_time)

        cache_file = tmp_path / "models.json"
        cache_file.write_text(json.dumps(cache.to_dict()))

        with patch("rlm_cli.models.CACHE_FILE", cache_file):
            loaded = _load_cache()
            assert loaded is None


class TestFuzzyMatching:
    """Tests for fuzzy matching."""

    def test_exact_match(self) -> None:
        assert _fuzzy_match_score("openai/gpt-4", "openai/gpt-4") == 1.0

    def test_case_insensitive_match(self) -> None:
        assert _fuzzy_match_score("OpenAI/GPT-4", "openai/gpt-4") == 1.0

    def test_substring_match(self) -> None:
        score = _fuzzy_match_score("gpt-4", "openai/gpt-4")
        assert score == 0.9

    def test_partial_match(self) -> None:
        score = _fuzzy_match_score("gpt-4", "openai/gpt-4o")
        assert 0.5 < score < 0.95

    def test_find_similar_models(self) -> None:
        valid_ids = {
            "openai/gpt-4",
            "openai/gpt-4o",
            "openai/gpt-3.5-turbo",
            "anthropic/claude-3-opus",
            "meta/llama-3",
        }
        suggestions = find_similar_models("openai/gpt-4o-mini", valid_ids, limit=3)
        assert "openai/gpt-4o" in suggestions
        assert "openai/gpt-4" in suggestions

    def test_find_similar_models_no_matches(self) -> None:
        valid_ids = {"anthropic/claude-3-opus"}
        suggestions = find_similar_models("xyz-random-model", valid_ids, limit=3, threshold=0.8)
        assert len(suggestions) == 0


class TestValidation:
    """Tests for model validation."""

    def test_validate_empty_model(self) -> None:
        result = validate_model("")
        assert result.valid
        assert result.suggestions == []

    def test_validate_model_with_error(self) -> None:
        # Mock fetch_models to raise error
        with patch("rlm_cli.models.get_model_ids") as mock_get:
            mock_get.side_effect = RuntimeError("API error")
            result = validate_model("any-model")
            # Should optimistically allow when API fails
            assert result.valid
            assert "API error" in (result.error or "")

    def test_validate_valid_model(self) -> None:
        with patch("rlm_cli.models.get_model_ids") as mock_get:
            mock_get.return_value = {"openai/gpt-4", "anthropic/claude-3"}
            result = validate_model("openai/gpt-4")
            assert result.valid
            assert result.suggestions == []

    def test_validate_invalid_model_with_suggestions(self) -> None:
        with patch("rlm_cli.models.get_model_ids") as mock_get:
            mock_get.return_value = {"openai/gpt-4", "openai/gpt-4o", "openai/gpt-3.5-turbo"}
            result = validate_model("openai/gpt-4-turbo")
            assert not result.valid
            assert "openai/gpt-4" in result.suggestions or "openai/gpt-4o" in result.suggestions


class TestFormatModelList:
    """Tests for model list formatting."""

    def test_format_empty_list(self) -> None:
        result = format_model_list([])
        assert result == "No models found."

    def test_format_with_filter_no_matches(self) -> None:
        models = [
            ModelInfo(id="openai/gpt-4", name="GPT-4", context_length=8192,
                     pricing_prompt=1.0, pricing_completion=2.0)
        ]
        result = format_model_list(models, filter_query="anthropic")
        assert result == "No models found."

    def test_format_basic(self) -> None:
        models = [
            ModelInfo(id="openai/gpt-4", name="GPT-4", context_length=8192,
                     pricing_prompt=1.0, pricing_completion=2.0)
        ]
        result = format_model_list(models)
        assert "Found 1 model(s)" in result
        assert "openai/gpt-4" in result
        assert "8K context" in result

    def test_format_with_pricing(self) -> None:
        models = [
            ModelInfo(id="openai/gpt-4", name="GPT-4", context_length=8192,
                     pricing_prompt=30.0, pricing_completion=60.0)
        ]
        result = format_model_list(models, show_pricing=True)
        assert "$30.00/$60.00" in result
        assert "per 1M tokens" in result
