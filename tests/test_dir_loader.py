from pathlib import Path

from rlm_cli.context import WalkOptions, collect_directory


def test_collect_directory_defaults() -> None:
    root = Path(__file__).parent / "fixtures" / "tiny_repo"
    result = collect_directory(root, options=WalkOptions(extensions=[".py", ".md", ".js"]))
    paths = [entry.path.as_posix() for entry in result.files]
    assert paths == ["a.py", "b.md", "sub/c.js"]


def test_collect_directory_limits() -> None:
    root = Path(__file__).parent / "fixtures" / "tiny_repo"
    result = collect_directory(
        root,
        options=WalkOptions(
            extensions=[".py", ".md", ".js"],
            max_total_bytes=1,
        ),
    )
    assert result.truncated is True
    assert result.warnings
