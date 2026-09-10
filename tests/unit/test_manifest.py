import json
from pathlib import Path

from wood_reports import RunOutputWriter


def test_preserves_success_when_target_fails(tmp_path: Path) -> None:
    def good(path: Path) -> Path:
        output = path / "a.txt"
        output.write_text("ok")
        return output

    def bad(_: Path) -> Path:
        raise RuntimeError("bad")

    manifest = RunOutputWriter().write(
        tmp_path, "sales", "2026-09", {"x": 1}, {"good": good, "bad": bad}
    )
    data = json.loads(manifest.read_text())
    assert (tmp_path / "sales" / "2026-09" / "a.txt").is_file()
    assert [x["status"] for x in data["targets"]] == ["failed", "success"]
