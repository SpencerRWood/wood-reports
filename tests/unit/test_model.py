from pathlib import Path

import pytest

from wood_reports import (
    Appendix,
    ChartReference,
    Finding,
    Narrative,
    PublicationTable,
    Report,
    ReportMetadata,
    ReportValidationError,
    Section,
    TableColumn,
)


def valid_report() -> Report:
    return Report(
        metadata=ReportMetadata(title="Monthly performance", author="Wood Analytics"),
        sections=(
            Section(
                title="Overview",
                content=(
                    Narrative("Revenue grew by 8%."),
                    ChartReference(Path("charts/revenue.png"), caption="Revenue trend"),
                    PublicationTable(
                        columns=(
                            TableColumn("month", "Month"),
                            TableColumn(
                                "revenue",
                                "Revenue",
                                format="currency",
                                alignment="right",
                            ),
                        ),
                        rows=(("January", 1000.0), ("February", 1080.0)),
                        caption="Monthly revenue",
                        notes=("Unaudited.",),
                    ),
                ),
            ),
        ),
        findings=(
            Finding(
                "revenue-growth",
                "Revenue increased",
                Narrative("Growth was broad based."),
            ),
        ),
        appendices=(Appendix("Definitions", (Narrative("Revenue excludes tax."),)),),
    )


def test_report_model_validates_all_supported_content(tmp_path: Path) -> None:
    chart = tmp_path / "charts" / "revenue.png"
    chart.parent.mkdir()
    chart.touch()

    valid_report().validate(tmp_path)


def test_validation_identifies_missing_chart_artifact(tmp_path: Path) -> None:
    with pytest.raises(ReportValidationError) as error:
        valid_report().validate(tmp_path)

    assert error.value.element == "sections[0].content[1]"
    assert error.value.artifact == tmp_path / "charts" / "revenue.png"
    assert "sections[0].content[1]" in str(error.value)


def test_validation_identifies_missing_required_structure(tmp_path: Path) -> None:
    report = Report(metadata=ReportMetadata(title=" "), sections=())

    with pytest.raises(ReportValidationError) as error:
        report.validate(tmp_path)

    assert error.value.element == "metadata.title"


def test_publication_table_rejects_invalid_row_shape(tmp_path: Path) -> None:
    report = Report(
        metadata=ReportMetadata(title="Table report"),
        sections=(
            Section(
                title="Table",
                content=(
                    PublicationTable(
                        columns=(
                            TableColumn("name", "Name"),
                            TableColumn("value", "Value"),
                        ),
                        rows=(("Only one cell",),),
                    ),
                ),
            ),
        ),
    )

    with pytest.raises(
        ReportValidationError,
        match=r"sections\[0\]\.content\[0\]\.rows\[0\]",
    ):
        report.validate(tmp_path)
