from pathlib import Path

import pytest

from wood_reports import (
    ChartReference,
    LatexWorkspaceError,
    LatexWorkspacePublisher,
    Narrative,
    Report,
    ReportMetadata,
    Section,
)


def report_with_chart(chart: Path) -> Report:
    return Report(
        ReportMetadata("Monthly report"),
        (Section("Results", (Narrative("Summary"), ChartReference(chart))),),
    )


def test_publishes_self_contained_source_tree(tmp_path: Path) -> None:
    artifact = tmp_path / "charts" / "trend.png"
    artifact.parent.mkdir()
    artifact.write_bytes(b"chart")

    output = LatexWorkspacePublisher().publish(
        report_with_chart(Path("charts/trend.png")),
        tmp_path / "workspace",
        artifact_root=tmp_path,
    )

    assert output == tmp_path / "workspace" / "generated" / "report.tex"
    assert "assets/1-trend.png" in output.read_text()
    assert (output.parent / "assets" / "1-trend.png").read_bytes() == b"chart"


def test_regeneration_preserves_human_extensions(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    extension = workspace / "extensions" / "appendix.tex"
    extension.parent.mkdir(parents=True)
    extension.write_text("Human maintained", encoding="utf-8")
    artifact = tmp_path / "trend.png"
    artifact.write_bytes(b"first")
    publisher = LatexWorkspacePublisher()

    publisher.publish(
        report_with_chart(Path("trend.png")), workspace, artifact_root=tmp_path
    )
    artifact.write_bytes(b"second")
    publisher.publish(
        report_with_chart(Path("trend.png")), workspace, artifact_root=tmp_path
    )

    assert extension.read_text(encoding="utf-8") == "Human maintained"
    assert (
        workspace / "generated" / "assets" / "1-trend.png"
    ).read_bytes() == b"second"


def test_rejects_an_ambiguous_ownership_boundary() -> None:
    with pytest.raises(LatexWorkspaceError, match="must differ"):
        LatexWorkspacePublisher(
            generated_directory="sources", extensions_directory="sources"
        )
