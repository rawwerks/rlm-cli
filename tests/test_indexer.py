"""Unit tests for the indexer module."""

from pathlib import Path
from unittest.mock import patch

import pytest


def _tantivy_available() -> bool:
    """Check if tantivy is available."""
    try:
        import tantivy  # noqa: F401

        return True
    except ImportError:
        return False


def test_tantivy_not_available_error() -> None:
    """Test error when tantivy is not installed."""
    import importlib

    from rlm_cli import indexer

    # Store original value
    original_value = indexer.TANTIVY_AVAILABLE

    try:
        with patch.dict("sys.modules", {"tantivy": None}):
            # Force reload to pick up the patch
            importlib.reload(indexer)

            # Should show tantivy as unavailable
            assert indexer.TANTIVY_AVAILABLE is False
    finally:
        # Restore the module to its original state
        importlib.reload(indexer)
        # Verify restoration
        assert indexer.TANTIVY_AVAILABLE == original_value


def test_index_config_defaults() -> None:
    """Test IndexConfig default values."""
    from rlm_cli.indexer import IndexConfig

    config = IndexConfig()
    assert config.heap_size_mb == 50
    assert config.boosts["path_stem"] == 3.0
    assert config.boosts["path"] == 2.0
    assert config.boosts["content"] == 1.0


def test_index_config_custom() -> None:
    """Test IndexConfig with custom values."""
    from rlm_cli.indexer import IndexConfig

    config = IndexConfig(
        index_dir=Path("/tmp/test-index"),
        heap_size_mb=100,
        boosts={"content": 2.0},
    )
    assert config.index_dir == Path("/tmp/test-index")
    assert config.heap_size_mb == 100
    assert config.boosts["content"] == 2.0


def test_search_result_dataclass() -> None:
    """Test SearchResult dataclass."""
    from rlm_cli.indexer import SearchResult

    result = SearchResult(
        path="src/main.py",
        score=1.5,
        language="python",
        doc_id="doc-0001",
        sha256="abc123",
        bytes_size=1024,
    )
    assert result.path == "src/main.py"
    assert result.score == 1.5
    assert result.language == "python"
    assert result.snippet is None


def test_index_result_dataclass() -> None:
    """Test IndexResult dataclass."""
    from rlm_cli.indexer import IndexResult

    result = IndexResult(
        indexed_count=10,
        skipped_count=5,
        total_bytes=1024,
    )
    assert result.indexed_count == 10
    assert result.skipped_count == 5
    assert result.total_bytes == 1024
    assert result.warnings == []
    assert result.index_path is None


def test_language_from_path() -> None:
    """Test language detection from file path."""
    from rlm_cli.indexer import _language_from_path

    assert _language_from_path(Path("main.py")) == "python"
    assert _language_from_path(Path("app.ts")) == "typescript"
    assert _language_from_path(Path("index.js")) == "javascript"
    assert _language_from_path(Path("main.go")) == "go"
    assert _language_from_path(Path("lib.rs")) == "rust"
    assert _language_from_path(Path("README.md")) == "markdown"
    assert _language_from_path(Path("config.yaml")) == "yaml"
    assert _language_from_path(Path("config.yml")) == "yaml"
    assert _language_from_path(Path("settings.json")) == "json"
    assert _language_from_path(Path("Makefile")) == "text"


def test_filter_files_fallback_without_tantivy() -> None:
    """Test filter_files_by_search falls back to substring matching without tantivy."""
    from rlm_cli.context import FileEntry
    from rlm_cli.indexer import TANTIVY_AVAILABLE

    if TANTIVY_AVAILABLE:
        pytest.skip("Tantivy is available, fallback not tested")

    from rlm_cli.indexer import filter_files_by_search

    files = [
        FileEntry(path=Path("foo.py"), size=10, content="def foo(): pass"),
        FileEntry(path=Path("bar.py"), size=10, content="def bar(): pass"),
        FileEntry(path=Path("baz.py"), size=10, content="def baz(): pass"),
    ]

    # Should match foo by content
    result = filter_files_by_search(files, "foo", Path.cwd())
    assert len(result) == 1
    assert result[0].path == Path("foo.py")


@pytest.mark.skipif(
    not _tantivy_available(),
    reason="Tantivy not installed",
)
def test_indexer_create_and_search(tmp_path: Path) -> None:
    """Test creating an index and searching it."""
    from rlm_cli.context import WalkOptions
    from rlm_cli.indexer import IndexConfig, RlmIndexer

    # Create test files
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()
    (test_dir / "hello.py").write_text("def hello(): print('hello world')")
    (test_dir / "goodbye.py").write_text("def goodbye(): print('goodbye world')")
    (test_dir / "readme.md").write_text("# Test README\nThis is a test file.")

    # Create index
    config = IndexConfig(index_dir=tmp_path / "index")
    indexer = RlmIndexer(test_dir, config)

    walk_opts = WalkOptions(extensions=[".py", ".md"])
    result = indexer.index_directory(walk_opts)

    assert result.indexed_count == 3
    assert result.skipped_count == 0
    assert result.index_path is not None

    # Search
    results = indexer.search("hello", limit=10)
    assert len(results) >= 1
    paths = [r.path for r in results]
    assert "hello.py" in paths


@pytest.mark.skipif(
    not _tantivy_available(),
    reason="Tantivy not installed",
)
def test_indexer_incremental(tmp_path: Path) -> None:
    """Test incremental indexing skips unchanged files."""
    from rlm_cli.context import WalkOptions
    from rlm_cli.indexer import IndexConfig, RlmIndexer

    # Create test file
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()
    (test_dir / "test.py").write_text("def test(): pass")

    config = IndexConfig(index_dir=tmp_path / "index")
    indexer = RlmIndexer(test_dir, config)
    walk_opts = WalkOptions(extensions=[".py"])

    # First index
    result1 = indexer.index_directory(walk_opts)
    assert result1.indexed_count == 1
    assert result1.skipped_count == 0

    # Second index (same content)
    result2 = indexer.index_directory(walk_opts)
    assert result2.indexed_count == 0
    assert result2.skipped_count == 1

    # Modify file
    (test_dir / "test.py").write_text("def test(): return True")

    # Third index (changed content)
    result3 = indexer.index_directory(walk_opts)
    assert result3.indexed_count == 1


@pytest.mark.skipif(
    not _tantivy_available(),
    reason="Tantivy not installed",
)
def test_indexer_force_reindex(tmp_path: Path) -> None:
    """Test force reindex rebuilds entire index."""
    from rlm_cli.context import WalkOptions
    from rlm_cli.indexer import IndexConfig, RlmIndexer

    # Create test file
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()
    (test_dir / "test.py").write_text("def test(): pass")

    config = IndexConfig(index_dir=tmp_path / "index")
    indexer = RlmIndexer(test_dir, config)
    walk_opts = WalkOptions(extensions=[".py"])

    # First index
    result1 = indexer.index_directory(walk_opts)
    assert result1.indexed_count == 1

    # Force reindex (same content)
    result2 = indexer.index_directory(walk_opts, force=True)
    assert result2.indexed_count == 1
    assert result2.skipped_count == 0


@pytest.mark.skipif(
    not _tantivy_available(),
    reason="Tantivy not installed",
)
def test_indexer_clear(tmp_path: Path) -> None:
    """Test clearing the index."""
    from rlm_cli.context import WalkOptions
    from rlm_cli.indexer import IndexConfig, RlmIndexer

    # Create test file
    test_dir = tmp_path / "test_repo"
    test_dir.mkdir()
    (test_dir / "test.py").write_text("def test(): pass")

    config = IndexConfig(index_dir=tmp_path / "index")
    indexer = RlmIndexer(test_dir, config)
    walk_opts = WalkOptions(extensions=[".py"])

    # Index and then clear
    indexer.index_directory(walk_opts)
    assert (tmp_path / "index").exists()

    indexer.clear()
    # The parent dir still exists but the hash-based subdir is gone
    assert len(list((tmp_path / "index").glob("*"))) == 0 or not (tmp_path / "index").exists()
