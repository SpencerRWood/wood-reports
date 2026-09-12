import pytest

from wood_reports import (
    Comparison,
    Finding,
    Narrative,
    Report,
    ReportMetadata,
    ReportRun,
    ReportRunError,
    Section,
)


def definition() -> Report:
    return Report(
        ReportMetadata("Report"), (Section("Overview", (Narrative("Text"),)),)
    )


def test_creates_isolated_run_with_comparisons_and_flags() -> None:
    report = definition()
    run = ReportRun.create(
        report,
        period="2026-09",
        values={"revenue": 120},
        comparisons={"revenue": Comparison(120, 100, 110, 115)},
        flags={"include_growth": True},
    )
    assert run.definition is report
    assert run.comparisons["revenue"].comparison == 100
    assert run.flags["include_growth"]


def test_rejects_incomplete_parameters() -> None:
    with pytest.raises(ReportRunError, match="period"):
        ReportRun.create(definition(), period=" ")


def test_materializes_precomputed_finding_conditions() -> None:
    report = Report(
        ReportMetadata("Report"),
        (Section("Overview", (Narrative("Text"),)),),
        findings=(Finding("growth", "Growth", Narrative("Text"), include_if="show"),),
    )
    included = ReportRun.create(report, period="2026-09", flags={"show": True})
    excluded = ReportRun.create(report, period="2026-09", flags={"show": False})

    assert included.materialize().findings[0].include_if is None
    assert excluded.materialize().findings == ()


def test_missing_finding_condition_flag_is_explicit() -> None:
    report = Report(
        ReportMetadata("Report"),
        (Section("Overview", (Narrative("Text"),)),),
        findings=(Finding("growth", "Growth", Narrative("Text"), include_if="show"),),
    )
    with pytest.raises(ReportRunError, match=r"flags\.show"):
        ReportRun.create(report, period="2026-09").materialize()
