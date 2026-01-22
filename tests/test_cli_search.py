"""Integration tests for search CLI commands."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rlm_cli.cli import app

runner = CliRunner()


def _tantivy_available() -> bool:
    """Check if tantivy is available."""
    try:
        import tantivy  # noqa: F401

        return True
    except ImportError:
        return False


def test_index_command_no_tantivy() -> None:
    """Test index command without tantivy shows error."""
    if _tantivy_available():
        pytest.skip("Tantivy is installed")

    result = runner.invoke(app, ["index", "."])
    assert result.exit_code == 40
    assert "tantivy" in result.output.lower() or "Tantivy" in result.output


def test_search_command_no_tantivy() -> None:
    """Test search command without tantivy shows error."""
    if _tantivy_available():
        pytest.skip("Tantivy is installed")

    result = runner.invoke(app, ["search", "test"])
    assert result.exit_code == 40
    assert "tantivy" in result.output.lower() or "Tantivy" in result.output


@pytest.mark.skipif(not _tantivy_available(), reason="Tantivy not installed")
def test_index_command_success(tmp_path: Path) -> None:
    """Test successful indexing."""
    # Create test files
    test_dir = tmp_path / "repo"
    test_dir.mkdir()
    (test_dir / "main.py").write_text("def main(): pass")
    (test_dir / "utils.py").write_text("def helper(): pass")

    result = runner.invoke(app, ["index", str(test_dir)])
    assert result.exit_code == 0
    assert "Indexed" in result.output


@pytest.mark.skipif(not _tantivy_available(), reason="Tantivy not installed")
def test_index_command_json_output(tmp_path: Path) -> None:
    """Test index command JSON output."""
    test_dir = tmp_path / "repo"
    test_dir.mkdir()
    (test_dir / "main.py").write_text("def main(): pass")

    result = runner.invoke(app, ["index", str(test_dir), "--json"])
    assert result.exit_code == 0

    output = json.loads(result.output)
    assert output["ok"] is True
    assert "indexed" in output["result"]


@pytest.mark.skipif(not _tantivy_available(), reason="Tantivy not installed")
def test_index_command_force(tmp_path: Path) -> None:
    """Test force reindex."""
    test_dir = tmp_path / "repo"
    test_dir.mkdir()
    (test_dir / "main.py").write_text("def main(): pass")

    # First index
    result1 = runner.invoke(app, ["index", str(test_dir)])
    assert result1.exit_code == 0

    # Force reindex
    result2 = runner.invoke(app, ["index", str(test_dir), "--force"])
    assert result2.exit_code == 0
    assert "Indexed" in result2.output


@pytest.mark.skipif(not _tantivy_available(), reason="Tantivy not installed")
def test_search_command_success(tmp_path: Path) -> None:
    """Test successful search."""
    test_dir = tmp_path / "repo"
    test_dir.mkdir()
    (test_dir / "main.py").write_text("def main(): print('hello world')")
    (test_dir / "utils.py").write_text("def helper(): pass")

    # Index first
    runner.invoke(app, ["index", str(test_dir)])

    # Search
    result = runner.invoke(app, ["search", "hello", "--path", str(test_dir)])
    assert result.exit_code == 0


@pytest.mark.skipif(not _tantivy_available(), reason="Tantivy not installed")
def test_search_command_json_output(tmp_path: Path) -> None:
    """Test search command JSON output."""
    test_dir = tmp_path / "repo"
    test_dir.mkdir()
    (test_dir / "main.py").write_text("def main(): pass")

    # Index first
    runner.invoke(app, ["index", str(test_dir)])

    # Search with JSON
    result = runner.invoke(app, ["search", "main", "--path", str(test_dir), "--json"])
    assert result.exit_code == 0

    output = json.loads(result.output)
    assert output["ok"] is True
    assert "results" in output["result"]


@pytest.mark.skipif(not _tantivy_available(), reason="Tantivy not installed")
def test_search_command_paths_only(tmp_path: Path) -> None:
    """Test search command with --paths-only."""
    test_dir = tmp_path / "repo"
    test_dir.mkdir()
    (test_dir / "main.py").write_text("def main(): pass")

    # Index first
    runner.invoke(app, ["index", str(test_dir)])

    # Search with paths only
    result = runner.invoke(app, ["search", "main", "--path", str(test_dir), "--paths-only"])
    assert result.exit_code == 0


@pytest.mark.skipif(not _tantivy_available(), reason="Tantivy not installed")
def test_search_command_limit(tmp_path: Path) -> None:
    """Test search command with limit."""
    test_dir = tmp_path / "repo"
    test_dir.mkdir()
    for i in range(10):
        (test_dir / f"file{i}.py").write_text(f"def func{i}(): pass")

    # Index first
    runner.invoke(app, ["index", str(test_dir)])

    # Search with limit
    result = runner.invoke(app, ["search", "func", "--path", str(test_dir), "--limit", "3", "--json"])
    assert result.exit_code == 0

    output = json.loads(result.output)
    assert len(output["result"]["results"]) <= 3


def test_index_command_nonexistent_path() -> None:
    """Test index command with nonexistent path."""
    result = runner.invoke(app, ["index", "/nonexistent/path"])
    assert result.exit_code != 0


def test_index_command_file_not_directory(tmp_path: Path) -> None:
    """Test index command with file instead of directory."""
    test_file = tmp_path / "file.txt"
    test_file.write_text("test")

    if not _tantivy_available():
        pytest.skip("Tantivy not installed")

    result = runner.invoke(app, ["index", str(test_file)])
    assert result.exit_code != 0
