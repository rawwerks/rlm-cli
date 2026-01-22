import shutil
from pathlib import Path

from rlm_cli.context import WalkOptions, collect_directory


def test_gitignore_respected() -> None:
    root = Path(__file__).parent / "fixtures" / "gitignore_repo"
    result = collect_directory(root, options=WalkOptions(extensions=[".py", ".log"]))
    paths = [entry.path.as_posix() for entry in result.files]
    assert "keep.py" in paths
    assert "drop.log" not in paths
    assert "ignored/drop.py" not in paths


def test_gitignore_disabled(tmp_path: Path) -> None:
    fixture_root = Path(__file__).parent / "fixtures" / "gitignore_repo"
    root = tmp_path / "gitignore_repo"
    shutil.copytree(fixture_root, root)
    (root / "drop.log").write_text("nope\n", encoding="utf-8")
    result = collect_directory(
        root,
        options=WalkOptions(extensions=[".py", ".log"], respect_gitignore=False),
    )
    paths = [entry.path.as_posix() for entry in result.files]
    assert "drop.log" in paths
