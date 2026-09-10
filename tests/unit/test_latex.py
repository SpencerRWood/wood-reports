from pathlib import Path

import pytest

from wood_reports import (
    ChartReference,
    LatexRenderer,
    LatexRenderError,
    Narrative,
    PublicationTable,
    Report,
    ReportMetadata,
    Section,
    TableColumn,
)


def test_renders_native_latex_structures(tmp_path: Path) -> None:
    chart = tmp_path / "trend.png"
    chart.touch()
    report = Report(
        ReportMetadata("Report", subtitle="Period", source="Ledger"),
        (
            Section(
                "Results",
                (
                    Narrative("Text"),
                    ChartReference(
                        chart,
                        caption="Trend",
                        renderer_hints={"latex.label": "fig:trend"},
                    ),
                    PublicationTable((TableColumn("x", "X"),), ((1,),), caption="Data"),
                ),
            ),
        ),
    )
    output = LatexRenderer().render(
        report, tmp_path / "report.tex", artifact_root=tmp_path
    )
    text = output.read_text()
    assert "\\section{Results}" in text
    assert "\\label{fig:trend}" in text
    assert "\\begin{table}" in text


def test_longtable_repeats_headers_and_preserves_notes(tmp_path: Path) -> None:
    table = PublicationTable(
        (
            TableColumn("month", "Month"),
            TableColumn("value", "Value", alignment="right"),
        ),
        (("August", 1200), ("September", 1300)),
        caption="Revenue",
        notes=("Unaudited.",),
        renderer_hints={"latex.layout": "longtable"},
    )
    report = Report(ReportMetadata("Report"), (Section("Results", (table,)),))
    output = LatexRenderer().render(
        report, tmp_path / "report.tex", artifact_root=tmp_path
    )
    text = output.read_text()
    assert "\\begin{longtable}{lr}" in text
    assert "\\endhead" in text
    assert "Unaudited." in text


def test_longtable_width_hint_fails_explicitly(tmp_path: Path) -> None:
    table = PublicationTable(
        (TableColumn("month", "Month"),),
        (("August",),),
        renderer_hints={"latex.layout": "longtable", "latex.width": "wide"},
    )
    report = Report(ReportMetadata("Report"), (Section("Results", (table,)),))
    with pytest.raises(LatexRenderError, match="longtable cannot use"):
        LatexRenderer().render(report, tmp_path / "report.tex", artifact_root=tmp_path)
