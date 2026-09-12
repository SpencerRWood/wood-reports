import json
from pathlib import Path

import pytest

from wood_reports import (
    Narrative,
    OutputExistsError,
    Report,
    ReportGenerationAPI,
    ReportGenerationError,
    ReportMetadata,
    ReportRun,
    Section,
)


def report() -> Report:
    return Report(ReportMetadata("Report"), (Section("Results", (Narrative("Text"),)),))


def run() -> ReportRun:
    return ReportRun.create(report(), period="2026-09", values={"revenue": 120})


def test_renders_a_materialized_run(tmp_path: Path) -> None:
    result = ReportGenerationAPI().generate(
        run(), tmp_path / "output", artifact_root=tmp_path, targets=("latex",)
    )
    assert result.period == "2026-09"
    assert (tmp_path / "output" / "report.tex").is_file()


def test_preserves_successful_target_when_another_renderer_fails(
    tmp_path: Path,
) -> None:
    result = ReportGenerationAPI().generate(
        run(),
        tmp_path / "output",
        artifact_root=tmp_path,
        targets=("latex", "powerpoint"),
    )
    assert result.targets[0].status == "success"
    assert result.targets[1].target == "powerpoint"


def test_immutable_run_writes_manifest_and_protects_outputs(tmp_path: Path) -> None:
    api = ReportGenerationAPI()
    result = api.generate(
        run(),
        tmp_path,
        artifact_root=tmp_path,
        targets=("latex",),
        report_id="sales",
        definition_revision="v1",
        immutable=True,
    )
    assert result.manifest == tmp_path / "sales" / "2026-09" / "manifest.json"
    assert json.loads(result.manifest.read_text())["parameters"] == {"revenue": 120}
    with pytest.raises(OutputExistsError):
        api.generate(
            run(), tmp_path, artifact_root=tmp_path, report_id="sales", immutable=True
        )


def test_run_requires_an_artifact_root(tmp_path: Path) -> None:
    with pytest.raises(ReportGenerationError, match="artifact_root"):
        ReportGenerationAPI().generate(run(), tmp_path, targets=("latex",))
