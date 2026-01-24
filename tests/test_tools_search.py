"""Tests for the unified tools_search module."""

from pathlib import Path

import pytest

from rlm_cli.tools_search import (
    EXA_AVAILABLE,
    RIPGREP_AVAILABLE,
    TANTIVY_AVAILABLE,
    ExaHit,
    RGHit,
    TVHit,
    exa,
    recall,
    rg,
    scan,
    tv,
    web,
)


class TestRipgrepSearch:
    """Tests for rg.* ripgrep search."""

    @pytest.mark.skipif(not RIPGREP_AVAILABLE, reason="python-ripgrep not installed")
    def test_rg_available(self):
        """Test that ripgrep availability check works."""
        assert rg.available() is True

    @pytest.mark.skipif(not RIPGREP_AVAILABLE, reason="python-ripgrep not installed")
    def test_rg_search_basic(self, tmp_path: Path):
        """Test basic ripgrep search."""
        # Create test files
        test_file = tmp_path / "test.py"
        test_file.write_text("def hello():\n    print('Hello')\n\ndef world():\n    pass\n")

        hits = rg.search(pattern="def ", paths=[str(tmp_path)], globs=["*.py"])

        assert len(hits) == 2
        assert all(h["path"].endswith("test.py") for h in hits)
        assert hits[0]["line"] == 1
        assert "def hello" in hits[0]["text"]
        assert hits[1]["line"] == 4
        assert "def world" in hits[1]["text"]

    @pytest.mark.skipif(not RIPGREP_AVAILABLE, reason="python-ripgrep not installed")
    def test_rg_search_with_globs(self, tmp_path: Path):
        """Test ripgrep search with glob filtering."""
        # Create test files
        (tmp_path / "test.py").write_text("TODO: fix this\n")
        (tmp_path / "test.txt").write_text("TODO: fix that\n")
        (tmp_path / "test.md").write_text("TODO: fix markdown\n")

        # Search only Python files
        hits = rg.search(pattern="TODO", paths=[str(tmp_path)], globs=["*.py"])

        assert len(hits) == 1
        assert hits[0]["path"].endswith("test.py")

    @pytest.mark.skipif(not RIPGREP_AVAILABLE, reason="python-ripgrep not installed")
    def test_rg_search_regex(self, tmp_path: Path):
        """Test ripgrep search with regex enabled."""
        test_file = tmp_path / "test.py"
        test_file.write_text("def foo():\n    pass\ndef bar():\n    pass\n")

        # Regex pattern for function definitions
        hits = rg.search(pattern=r"def \w+\(", paths=[str(tmp_path)], regex=True)

        assert len(hits) == 2

    @pytest.mark.skipif(not RIPGREP_AVAILABLE, reason="python-ripgrep not installed")
    def test_rg_search_max_hits(self, tmp_path: Path):
        """Test ripgrep search respects max_hits."""
        test_file = tmp_path / "test.py"
        # Create file with many matches
        lines = [f"line{i} = {i}" for i in range(100)]
        test_file.write_text("\n".join(lines))

        hits = rg.search(pattern="line", paths=[str(tmp_path)], max_hits=5)

        assert len(hits) <= 5

    @pytest.mark.skipif(not RIPGREP_AVAILABLE, reason="python-ripgrep not installed")
    def test_scan_alias(self, tmp_path: Path):
        """Test that scan() is an alias for rg.search()."""
        test_file = tmp_path / "test.py"
        test_file.write_text("class Foo:\n    pass\n")

        hits = scan(pattern="class", paths=[str(tmp_path)])

        assert len(hits) == 1
        assert "class Foo" in hits[0]["text"]


class TestTantivySearch:
    """Tests for tv.* Tantivy search."""

    @pytest.mark.skipif(not TANTIVY_AVAILABLE, reason="tantivy not installed")
    def test_tv_available(self):
        """Test that Tantivy availability check works."""
        assert tv.available() is True

    @pytest.mark.skipif(not TANTIVY_AVAILABLE, reason="tantivy not installed")
    def test_tv_ensure_index(self, tmp_path: Path):
        """Test building Tantivy index."""
        # Create test files
        (tmp_path / "test.py").write_text("def hello():\n    print('Hello')\n")
        (tmp_path / "test2.py").write_text("class World:\n    pass\n")

        result = tv.ensure_index(root=str(tmp_path), force=True)

        assert result["indexed_count"] == 2
        assert result["total_bytes"] > 0
        assert result["index_path"] is not None

    @pytest.mark.skipif(not TANTIVY_AVAILABLE, reason="tantivy not installed")
    def test_tv_search_basic(self, tmp_path: Path):
        """Test basic Tantivy search."""
        # Create test files with distinct content
        (tmp_path / "errors.py").write_text(
            "class CustomError(Exception):\n"
            "    '''Handle custom errors'''\n"
            "    pass\n"
        )
        (tmp_path / "utils.py").write_text(
            "def helper():\n"
            "    '''Utility function'''\n"
            "    return 42\n"
        )

        # Build index
        tv.ensure_index(root=str(tmp_path), force=True)

        # Search for error-related content
        results = tv.search(query="error exception", limit=5, root=str(tmp_path))

        assert len(results) >= 1
        # The errors.py file should rank higher due to error/exception content
        assert any("errors.py" in r["path"] for r in results)

    @pytest.mark.skipif(not TANTIVY_AVAILABLE, reason="tantivy not installed")
    def test_recall_alias(self, tmp_path: Path):
        """Test that recall() is an alias for tv.search()."""
        (tmp_path / "test.py").write_text("def authenticate():\n    pass\n")

        tv.ensure_index(root=str(tmp_path), force=True)

        results = recall(query="authenticate", limit=5, root=str(tmp_path))

        assert len(results) >= 1


class TestDataClasses:
    """Tests for RGHit and TVHit data classes."""

    def test_rg_hit_to_dict(self):
        """Test RGHit.to_dict()."""
        hit = RGHit(path="test.py", line=10, col=5, text="def foo():")
        d = hit.to_dict()

        assert d == {"path": "test.py", "line": 10, "col": 5, "text": "def foo():"}

    def test_tv_hit_to_dict(self):
        """Test TVHit.to_dict()."""
        hit = TVHit(
            doc_id="doc-0001",
            score=15.5,
            path="test.py",
            language="python",
            bytes_size=1024,
        )
        d = hit.to_dict()

        assert d == {
            "doc_id": "doc-0001",
            "score": 15.5,
            "path": "test.py",
            "language": "python",
            "bytes_size": 1024,
        }

    def test_exa_hit_to_dict(self):
        """Test ExaHit.to_dict()."""
        hit = ExaHit(
            url="https://example.com",
            title="Example Page",
            score=0.95,
            published_date="2024-01-15",
            author="John Doe",
            text=None,
            highlights=["relevant text excerpt"],
        )
        d = hit.to_dict()

        assert d == {
            "url": "https://example.com",
            "title": "Example Page",
            "score": 0.95,
            "published_date": "2024-01-15",
            "author": "John Doe",
            "highlights": ["relevant text excerpt"],
        }

    def test_exa_hit_to_dict_minimal(self):
        """Test ExaHit.to_dict() with minimal fields."""
        hit = ExaHit(
            url="https://example.com",
            title="Example",
            score=None,
            published_date=None,
            author=None,
            text=None,
            highlights=None,
        )
        d = hit.to_dict()

        assert d == {
            "url": "https://example.com",
            "title": "Example",
        }


class TestExaSearch:
    """Tests for exa.* Exa web search."""

    def test_exa_available_check(self):
        """Test that EXA_AVAILABLE reflects package installation."""
        # This should be True if exa-py is installed, False otherwise
        # The actual value depends on the test environment
        assert isinstance(EXA_AVAILABLE, bool)

    @pytest.mark.skipif(not EXA_AVAILABLE, reason="exa-py not installed")
    def test_exa_available_method(self):
        """Test exa.available() returns bool based on package and API key."""
        result = exa.available()
        assert isinstance(result, bool)
        # If EXA_API_KEY is not set, this should be False
        # If it is set, this should be True

    @pytest.mark.skipif(not EXA_AVAILABLE, reason="exa-py not installed")
    def test_exa_requires_api_key(self):
        """Test that exa.search() raises error without API key."""
        import os

        # Save and clear the API key
        saved_key = os.environ.pop("EXA_API_KEY", None)
        try:
            # Reset the cached client
            import rlm_cli.tools_search as ts
            ts._exa_client = None

            with pytest.raises(ValueError, match="EXA_API_KEY"):
                exa.search(query="test", limit=1)
        finally:
            # Restore the API key
            if saved_key:
                os.environ["EXA_API_KEY"] = saved_key

    @pytest.mark.skipif(
        not EXA_AVAILABLE or not exa.available(),
        reason="exa-py not installed or EXA_API_KEY not set"
    )
    @pytest.mark.integration
    def test_exa_search_basic(self):
        """Test basic Exa search (requires API key)."""
        results = exa.search(query="Python programming", limit=3)

        assert len(results) > 0
        assert all("url" in r for r in results)
        assert all("title" in r for r in results)

    @pytest.mark.skipif(
        not EXA_AVAILABLE or not exa.available(),
        reason="exa-py not installed or EXA_API_KEY not set"
    )
    @pytest.mark.integration
    def test_exa_search_with_highlights(self):
        """Test Exa search with highlights enabled."""
        results = exa.search(
            query="machine learning tutorial",
            limit=2,
            include_highlights=True,
        )

        assert len(results) > 0
        # Results should have highlights
        assert any(r.get("highlights") for r in results)

    @pytest.mark.skipif(
        not EXA_AVAILABLE or not exa.available(),
        reason="exa-py not installed or EXA_API_KEY not set"
    )
    @pytest.mark.integration
    def test_web_alias(self):
        """Test that web() is an alias for exa.search()."""
        results = web(query="Python asyncio", limit=2)

        assert len(results) > 0
        assert all("url" in r for r in results)
