from pathlib import Path

import pytest

from wood_reports import (
    ChartGenerationContext,
    ChartReference,
    ChartResolutionError,
    Report,
    ReportGenerationPipeline,
    ReportMetadata,
    Section,
)


def logical_chart_report() -> Report:
    return Report(
        metadata=ReportMetadata(
            title="Monthly performance",
            subtitle="August 2026",
            source="Finance ledger",
        ),
        sections=(
            Section(
                "Overview",
                (ChartReference(identity="revenue-trend", caption="Revenue"),),
            ),
        ),
    )


def test_pipeline_resolves_logical_chart_with_consistent_context(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "exports" / "revenue.png"
    artifact.parent.mkdir()
    artifact.touch()
    contexts: list[ChartGenerationContext] = []

    def build_revenue(context: ChartGenerationContext) -> Path:
        contexts.append(context)
        return artifact

    visual = tmp_path / "brand" / "logo.png"
    result = ReportGenerationPipeline(
        {"revenue-trend": build_revenue},
        run_context={"period": "2026-08"},
        visual_references={"logo": visual},
    ).generate(logical_chart_report(), artifact_root=tmp_path)

    chart = result.sections[0].content[0]
    assert isinstance(chart, ChartReference)
    assert chart.artifact == artifact
    assert chart.identity == "revenue-trend"
    assert contexts == [
        ChartGenerationContext(
            title="Monthly performance",
            subtitle="August 2026",
            source="Finance ledger",
            run_context={"period": "2026-08"},
            visual_references={"logo": visual},
        )
    ]


def test_pipeline_preserves_externally_produced_chart_artifact(tmp_path: Path) -> None:
    artifact = tmp_path / "wood-charts" / "revenue.png"
    artifact.parent.mkdir()
    artifact.touch()
    report = Report(
        metadata=ReportMetadata("External chart"),
        sections=(Section("Overview", (ChartReference(artifact=artifact),)),),
    )

    result = ReportGenerationPipeline({}).generate(report, artifact_root=tmp_path)

    assert result == report


def test_pipeline_identifies_missing_logical_chart_builder(tmp_path: Path) -> None:
    with pytest.raises(ChartResolutionError) as error:
        ReportGenerationPipeline({}).generate(
            logical_chart_report(), artifact_root=tmp_path
        )

    assert error.value.element == "sections[0].content[0]"
    assert error.value.identity == "revenue-trend"
