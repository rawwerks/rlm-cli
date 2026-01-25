"""Tests for the rlm config command group."""

from __future__ import annotations

from pathlib import Path

from rlm_cli.config import (
    coerce_value,
    get_nested_value,
    get_user_config_path,
    load_or_create_config,
    set_nested_value,
    write_config_file,
)


class TestCoerceValue:
    """Tests for value coercion."""

    def test_coerce_true(self) -> None:
        assert coerce_value("true") is True
        assert coerce_value("True") is True
        assert coerce_value("TRUE") is True

    def test_coerce_false(self) -> None:
        assert coerce_value("false") is False
        assert coerce_value("False") is False

    def test_coerce_null(self) -> None:
        assert coerce_value("null") is None
        assert coerce_value("none") is None

    def test_coerce_int(self) -> None:
        assert coerce_value("42") == 42
        assert coerce_value("-10") == -10
        assert coerce_value("+5") == 5

    def test_coerce_float(self) -> None:
        assert coerce_value("3.14") == 3.14
        assert coerce_value("-2.5") == -2.5
        assert coerce_value("1.0e10") == 1.0e10

    def test_coerce_json_object(self) -> None:
        result = coerce_value('{"key": "value"}')
        assert result == {"key": "value"}

    def test_coerce_json_array(self) -> None:
        result = coerce_value('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_coerce_string(self) -> None:
        assert coerce_value("hello") == "hello"
        assert coerce_value("hello world") == "hello world"

    def test_coerce_invalid_json(self) -> None:
        # Invalid JSON should be returned as string
        assert coerce_value("{invalid}") == "{invalid}"


class TestNestedAccess:
    """Tests for dot-notation config access."""

    def test_get_nested_value_simple(self) -> None:
        data = {"backend": "openai"}
        assert get_nested_value(data, "backend") == "openai"

    def test_get_nested_value_nested(self) -> None:
        data = {"backend_kwargs": {"temperature": 0.7}}
        assert get_nested_value(data, "backend_kwargs.temperature") == 0.7

    def test_get_nested_value_deep(self) -> None:
        data = {"a": {"b": {"c": "deep"}}}
        assert get_nested_value(data, "a.b.c") == "deep"

    def test_get_nested_value_missing(self) -> None:
        data = {"backend": "openai"}
        assert get_nested_value(data, "missing") is None
        assert get_nested_value(data, "missing.nested") is None

    def test_set_nested_value_simple(self) -> None:
        data: dict = {}
        set_nested_value(data, "backend", "openrouter")
        assert data == {"backend": "openrouter"}

    def test_set_nested_value_nested(self) -> None:
        data: dict = {}
        set_nested_value(data, "backend_kwargs.temperature", 0.7)
        assert data == {"backend_kwargs": {"temperature": 0.7}}

    def test_set_nested_value_existing(self) -> None:
        data = {"backend_kwargs": {"temperature": 0.5}}
        set_nested_value(data, "backend_kwargs.temperature", 0.9)
        assert data == {"backend_kwargs": {"temperature": 0.9}}

    def test_set_nested_value_add_to_existing(self) -> None:
        data = {"backend_kwargs": {"temperature": 0.5}}
        set_nested_value(data, "backend_kwargs.max_tokens", 100)
        assert data == {"backend_kwargs": {"temperature": 0.5, "max_tokens": 100}}


class TestConfigFile:
    """Tests for config file operations."""

    def test_write_config_file(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        data = {"backend": "openai", "model": "gpt-4"}
        write_config_file(config_path, data)
        assert config_path.exists()
        content = config_path.read_text()
        assert "backend: openai" in content
        assert "model: gpt-4" in content

    def test_write_config_creates_dirs(self, tmp_path: Path) -> None:
        config_path = tmp_path / "subdir" / "nested" / "config.yaml"
        data = {"backend": "openai"}
        write_config_file(config_path, data)
        assert config_path.exists()

    def test_load_or_create_empty(self, tmp_path: Path) -> None:
        config_path = tmp_path / "nonexistent.yaml"
        data = load_or_create_config(config_path)
        assert data == {}

    def test_load_or_create_existing(self, tmp_path: Path) -> None:
        config_path = tmp_path / "config.yaml"
        config_path.write_text("backend: openrouter\n")
        data = load_or_create_config(config_path)
        assert data == {"backend": "openrouter"}


class TestUserConfigPath:
    """Tests for config path resolution."""

    def test_get_user_config_path(self) -> None:
        path = get_user_config_path()
        assert str(path).endswith(".config/rlm/config.yaml")
        assert "~" not in str(path)  # Should be expanded
