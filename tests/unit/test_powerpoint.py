import base64
from pathlib import Path
from typing import Any

from pptx import Presentation

from wood_reports import (
    ChartReference,
    Finding,
    Narrative,
    PowerPointRenderer,
    PublicationTable,
    Report,
    ReportMetadata,
    Section,
    TableColumn,
)


def write_png(path: Path) -> None:
    path.write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/"
            "OcE1owAAAABJRU5ErkJggg=="
        )
    )


def report_with_layouts(chart: Path) -> Report:
    return Report(
        metadata=ReportMetadata(
            title="Monthly performance",
            subtitle="August 2026",
            source="Finance ledger",
        ),
        sections=(
            Section(
                "Overview",
                (
                    Narrative("Revenue increased during the month."),
                    ChartReference(artifact=chart, caption="Revenue trend"),
                    PublicationTable(
                        columns=(
                            TableColumn("month", "Month"),
                            TableColumn("revenue", "Revenue"),
                        ),
                        rows=(("August", 1200),),
                        caption="Monthly revenue",
                    ),
                ),
            ),
        ),
        findings=(
            Finding(
                "growth", "Revenue increased", Narrative("Growth was broad based.")
            ),
        ),
    )


def slide_text(slide: Any) -> str:
    return "\n".join(shape.text for shape in slide.shapes if shape.has_text_frame)


def test_renderer_writes_valid_editable_presentation_with_all_layouts(
    tmp_path: Path,
) -> None:
    chart = tmp_path / "charts" / "revenue.png"
    chart.parent.mkdir()
    write_png(chart)
    destination = tmp_path / "reports" / "monthly.pptx"

    output = PowerPointRenderer().render(
        report_with_layouts(chart), destination, artifact_root=tmp_path
    )
    presentation = Presentation(str(output))

    assert output == destination
    assert destination.is_file()
    assert len(presentation.slides) == 6
    assert "Monthly performance" in slide_text(presentation.slides[3])
    assert "August 2026" in slide_text(presentation.slides[3])
    assert "Finance ledger" in slide_text(presentation.slides[3])
    assert "4" in slide_text(presentation.slides[3])
    assert any(shape.shape_type == 13 for shape in presentation.slides[3].shapes)
    assert any(shape.has_table for shape in presentation.slides[4].shapes)
    assert "Revenue increased" in slide_text(presentation.slides[5])


def test_full_frame_chart_layout_uses_the_entire_slide_without_report_chrome(
    tmp_path: Path,
) -> None:
    chart = tmp_path / "chart.png"
    write_png(chart)
    report = Report(
        metadata=ReportMetadata(title="Monthly performance"),
        sections=(
            Section(
                "Overview",
                (
                    ChartReference(
                        artifact=chart,
                        renderer_hints={"powerpoint.layout": "full-frame-chart"},
                    ),
                ),
            ),
        ),
    )
    destination = tmp_path / "full-frame.pptx"

    PowerPointRenderer().render(report, destination, artifact_root=tmp_path)
    presentation = Presentation(str(destination))

    assert len(presentation.slides) == 3
    assert slide_text(presentation.slides[2]) == ""
    assert len(presentation.slides[2].shapes) == 1
