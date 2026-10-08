from pathlib import Path

import pytest

from wood_reports import (
    ChartReference,
    Finding,
    LatexRenderer,
    LatexRenderError,
    Narrative,
    PublicationTable,
    Report,
    ReportMetadata,
    Section,
    TableColumn,
)


@pytest.mark.parametrize(
    "text",
    [
        r"\input{/etc/passwd}",
        r"\def\x{y}",
        r"\write18{command}",
        r"\textbf{unclosed",
        "unmatched}",
        "% comment",
        "x" * 4097,
    ],
)
def test_rejects_unbounded_raw_latex(tmp_path: Path, text: str) -> None:
    report = Report(
        ReportMetadata("Test"),
        (Section("Results", (Narrative(text, {"latex.raw": "inline"}),)),),
    )
    with pytest.raises(LatexRenderError, match="raw inline"):
        LatexRenderer().render(report, tmp_path / "report.tex", artifact_root=tmp_path)


@pytest.mark.parametrize(
    "hint",
    [
        {"latex.ref": "missing"},
        {"latex.ref": "bad}\\input{x}"},
        {"latex.raw": "document"},
    ],
)
def test_rejects_invalid_reference_or_raw_mode(
    tmp_path: Path, hint: dict[str, str]
) -> None:
    report = Report(
        ReportMetadata("Test"), (Section("Results", (Narrative("Text", hint),)),)
    )
    with pytest.raises(LatexRenderError):
        LatexRenderer().render(report, tmp_path / "report.tex", artifact_root=tmp_path)


@pytest.mark.parametrize("label", ["same", "unsafe}\\input{x}"])
def test_rejects_duplicate_or_unsafe_labels(tmp_path: Path, label: str) -> None:
    report = Report(
        ReportMetadata("Test"),
        (
            Section("First", (Narrative("Text"),), {"latex.label": label}),
            Section("Second", (Narrative("Text"),), {"latex.label": label}),
        ),
    )
    with pytest.raises(LatexRenderError):
        LatexRenderer().render(report, tmp_path / "report.tex", artifact_root=tmp_path)


def test_labeled_longtable_without_caption_and_source_notes(tmp_path: Path) -> None:
    report = Report(
        ReportMetadata("Test"),
        (
            Section(
                "Results",
                (
                    PublicationTable(
                        (TableColumn("x", "X"),),
                        ((1,),),
                        renderer_hints={
                            "latex.layout": "longtable",
                            "latex.label": "tab:values",
                            "latex.source": "Data & evidence",
                        },
                    ),
                    Narrative("See values", {"latex.ref": "tab:values"}),
                ),
            ),
        ),
    )
    output = LatexRenderer().render(
        report, tmp_path / "report.tex", artifact_root=tmp_path
    )
    assert r"\caption{}\label{tab:values}" in output.read_text()
    assert r"\WoodSource{Data \& evidence}" in output.read_text()


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
    assert "\\author{Spencer Wood}" in text
    assert "\\label{fig:trend}" in text
    assert "\\begin{table}" in text


def test_latex_uses_the_report_author_when_provided(tmp_path: Path) -> None:
    report = Report(
        ReportMetadata("Report", author="Wood Analytics"),
        (Section("Results", (Narrative("Text"),)),),
    )

    output = LatexRenderer().render(
        report, tmp_path / "report.tex", artifact_root=tmp_path
    )

    assert "\\author{Wood Analytics}" in output.read_text()


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


def test_width_hint_preserves_existing_table_rendering(tmp_path: Path) -> None:
    table = PublicationTable(
        (TableColumn("month", "Month"),),
        tuple((f"Month {index}",) for index in range(8)),
        renderer_hints={"latex.width": "wide"},
    )
    report = Report(ReportMetadata("Report"), (Section("Results", (table,)),))
    text = (
        LatexRenderer()
        .render(report, tmp_path / "report.tex", artifact_root=tmp_path)
        .read_text()
    )
    assert r"\begin{table}[htbp]" in text
    assert r"\begin{longtable}" not in text
    assert all(f"Month {index}" in text for index in range(8))


def test_finding_figure_keeps_semantic_chrome_and_local_asset(tmp_path: Path) -> None:
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"x")
    report = Report(
        ReportMetadata("Report"),
        (Section("Results", (Narrative("Text"),)),),
        findings=(
            Finding(
                "weekday-sessions",
                "Weekend falls",
                Narrative("See figure."),
                subtitle="Below baseline",
                source="Synthetic",
                visual=ChartReference(Path("chart.png"), caption="Sessions"),
            ),
        ),
    )
    output = LatexRenderer().render(
        report, tmp_path / "out" / "report.tex", artifact_root=tmp_path
    )
    text = output.read_text()
    assert "Weekend falls" in text
    assert "Below baseline" in text
    assert r"\WoodSource{Synthetic}" in text
    assert "\\label{fig:weekday-sessions}" in text
    assert "assets/1-chart.png" in text
    assert (output.parent / "assets" / "1-chart.png").is_file()


def test_latex_table_applies_formats_and_labels(tmp_path: Path) -> None:
    table = PublicationTable(
        (TableColumn("value", "Value", format=",.1f", alignment="right"),),
        ((1200.25,),),
        caption="Values",
        notes=("Note.",),
        renderer_hints={"latex.label": "tab:values"},
    )
    report = Report(ReportMetadata("Report"), (Section("Results", (table,)),))
    text = (
        LatexRenderer()
        .render(report, tmp_path / "report.tex", artifact_root=tmp_path)
        .read_text()
    )
    assert "1,200.2" in text
    assert "\\label{tab:values}" in text
    assert "Note." in text


def test_latex_escapes_percentages_in_formatted_table_cells(tmp_path: Path) -> None:
    table = PublicationTable(
        (TableColumn("growth", "Growth", format=".1%", alignment="right"),),
        ((0.083,),),
    )
    report = Report(ReportMetadata("Report"), (Section("Results", (table,)),))

    text = (
        LatexRenderer()
        .render(report, tmp_path / "report.tex", artifact_root=tmp_path)
        .read_text()
    )

    assert "8.3\\%" in text


def test_latex_rejects_an_invalid_table_format(tmp_path: Path) -> None:
    table = PublicationTable((TableColumn("value", "Value", format="bad"),), ((1,),))
    report = Report(ReportMetadata("Report"), (Section("Results", (table,)),))
    with pytest.raises(LatexRenderError, match="invalid table format"):
        LatexRenderer().render(report, tmp_path / "report.tex", artifact_root=tmp_path)
