from pathlib import Path

from rlm_cli.context import WalkOptions, build_context_from_sources
from rlm_cli.inputs import InputKind, InputSource


def test_file_input_updates_total_bytes() -> None:
    root = Path(__file__).parent / "fixtures" / "tiny_repo"
    file_path = root / "a.py"
    content = file_path.read_text(encoding="utf-8")

    sources = [InputSource(InputKind.FILE, file_path)]
    payload, result = build_context_from_sources(
        sources,
        options=WalkOptions(extensions=[".py"]),
    )

    assert payload["documents"]
    assert result.total_bytes == len(content.encode("utf-8"))
