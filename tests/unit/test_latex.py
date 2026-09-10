from pathlib import Path

from wood_reports import (
    ChartReference,
    LatexRenderer,
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
