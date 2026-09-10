import pytest

from wood_reports import (
    Comparison,
    Narrative,
    Report,
    ReportMetadata,
    ReportRunError,
    ReportRunFactory,
    Section,
)


def definition() -> Report:
    return Report(
        ReportMetadata("Report"), (Section("Overview", (Narrative("Text"),)),)
    )


def test_creates_isolated_run_with_comparisons_and_flags() -> None:
    report = definition()
    run = ReportRunFactory().create(
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
        ReportRunFactory().create(definition(), period=" ")
