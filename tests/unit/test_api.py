from pathlib import Path

from wood_reports import (
    Narrative,
    Report,
    ReportGenerationAPI,
    ReportMetadata,
    Section,
)


def report() -> Report:
    return Report(ReportMetadata("Report"), (Section("Results", (Narrative("Text"),)),))


def test_renders_selected_target_with_explicit_recurring_period(tmp_path: Path) -> None:
    result = ReportGenerationAPI().generate(
        report(),
        tmp_path / "output",
        artifact_root=tmp_path,
        targets=("latex",),
        period="2026-09",
    )

    assert result.period == "2026-09"
    assert result.targets[0].status == "success"
    assert (tmp_path / "output" / "report.tex").is_file()


def test_preserves_successful_target_when_another_renderer_fails(
    tmp_path: Path,
) -> None:
    result = ReportGenerationAPI().generate(
        report(),
        tmp_path / "output",
        artifact_root=tmp_path,
        targets=("latex", "powerpoint"),
    )

    assert result.targets[0].status == "success"
    assert (tmp_path / "output" / "report.tex").is_file()
    assert result.targets[1].target == "powerpoint"
