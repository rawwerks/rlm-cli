from pathlib import Path

import rlm_cli.context as context
from rlm_cli.context import WalkOptions, build_context_from_sources
from rlm_cli.inputs import InputKind, InputSource


def test_url_markitdown(monkeypatch) -> None:
    def fake_convert(source: str) -> str | None:
        assert source == "https://example.com"
        return "# Example"

    monkeypatch.setattr(context, "_convert_with_markitdown", fake_convert)
    sources = [InputSource(InputKind.URL, "https://example.com")]
    payload, result = build_context_from_sources(
        sources,
        options=WalkOptions(use_markitdown=True),
    )
    assert payload["documents"][0]["content"] == "# Example"
    assert result.total_bytes == len("# Example".encode("utf-8"))


def test_binary_markitdown(monkeypatch, tmp_path: Path) -> None:
    file_path = tmp_path / "sample.bin"
    file_path.write_bytes(b"\x00\x01\x02\x03")

    def fake_convert(source: str) -> str | None:
        assert source == str(file_path)
        return "converted"

    monkeypatch.setattr(context, "_convert_with_markitdown", fake_convert)
    sources = [InputSource(InputKind.FILE, file_path)]
    payload, result = build_context_from_sources(
        sources,
        options=WalkOptions(use_markitdown=True),
    )
    assert payload["documents"][0]["content"] == "converted"
    assert result.total_bytes == len("converted".encode("utf-8"))

    payload_skip, result_skip = build_context_from_sources(
        sources,
        options=WalkOptions(use_markitdown=False),
    )
    assert payload_skip["documents"] == []
    assert result_skip.total_bytes == 0
