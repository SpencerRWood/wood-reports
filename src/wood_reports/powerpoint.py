"""Render report models into native, editable PowerPoint presentations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

from wood_reports.model import (
    ChartReference,
    Finding,
    PublicationTable,
    Report,
    Section,
)

_SLIDE_WIDTH = Inches(13.333)
_SLIDE_HEIGHT = Inches(7.5)
_MARGIN = Inches(0.65)
_CONTENT_TOP = Inches(1.45)
_CONTENT_HEIGHT = Inches(5.25)
_NAVY = RGBColor(23, 43, 77)  # type: ignore[no-untyped-call]
_GRAY = RGBColor(89, 89, 89)  # type: ignore[no-untyped-call]


class PowerPointRenderError(ValueError):
    """A rendering failure with the report element responsible for it."""

    def __init__(self, element: str, message: str) -> None:
        self.element = element
        super().__init__(f"{element}: {message}")


class PowerPointRenderer:
    """Render a report independently once its logical charts are resolved."""

    def render(self, report: Report, destination: Path, *, artifact_root: Path) -> Path:
        """Write a valid PowerPoint file and return its destination."""
        report.validate(artifact_root)
        presentation = Presentation()
        presentation.slide_width = _SLIDE_WIDTH
        presentation.slide_height = _SLIDE_HEIGHT

        self._add_title_slide(presentation, report)
        for section_index, section in enumerate(report.sections):
            self._add_section_slide(presentation, report, section, section_index)
            self._add_section_content(presentation, report, section, section_index)
        if report.findings:
            self._add_summary_slide(presentation, report)

        destination.parent.mkdir(parents=True, exist_ok=True)
        presentation.save(str(destination))
        return destination

    def _add_title_slide(self, presentation: Any, report: Report) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        self._add_text(
            slide, report.metadata.title, _MARGIN, Inches(2.1), Inches(12), 1, 32
        )
        if report.metadata.subtitle:
            self._add_text(
                slide,
                report.metadata.subtitle,
                _MARGIN,
                Inches(3.25),
                Inches(12),
                0.55,
                18,
            )
        if report.metadata.source:
            self._add_text(
                slide,
                report.metadata.source,
                _MARGIN,
                Inches(6.65),
                Inches(12),
                0.3,
                10,
                color=_GRAY,
            )

    def _add_section_slide(
        self,
        presentation: Any,
        report: Report,
        section: Section,
        _section_index: int,
    ) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        self._add_text(
            slide,
            report.metadata.title,
            _MARGIN,
            Inches(0.55),
            Inches(10),
            0.3,
            10,
            color=_GRAY,
        )
        self._add_text(slide, section.title, _MARGIN, Inches(3.05), Inches(12), 0.8, 28)
        self._add_page_number(slide, len(presentation.slides))

    def _add_section_content(
        self,
        presentation: Any,
        report: Report,
        section: Section,
        section_index: int,
    ) -> None:
        for content_index, content in enumerate(section.content):
            element = f"sections[{section_index}].content[{content_index}]"
            if isinstance(content, ChartReference):
                self._add_chart_slide(presentation, report, section, content, element)
            elif isinstance(content, PublicationTable):
                self._add_table_slide(presentation, report, section, content)
            else:
                self._add_narrative_slide(presentation, report, section, content.text)

    def _add_chart_slide(
        self,
        presentation: Any,
        report: Report,
        section: Section,
        chart: ChartReference,
        element: str,
    ) -> None:
        if chart.artifact is None:
            raise PowerPointRenderError(element, "requires a resolved chart artifact")
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        full_frame = chart.renderer_hints.get("powerpoint.layout") == "full-frame-chart"
        artifact = chart.artifact
        if full_frame:
            slide.shapes.add_picture(str(artifact), 0, 0, _SLIDE_WIDTH, _SLIDE_HEIGHT)
            return
        self._add_chrome(
            slide,
            report,
            chart.caption or section.title,
            len(presentation.slides),
        )
        slide.shapes.add_picture(
            str(artifact), _MARGIN, _CONTENT_TOP, Inches(8.15), _CONTENT_HEIGHT
        )

    def _add_table_slide(
        self,
        presentation: Any,
        report: Report,
        section: Section,
        table: PublicationTable,
    ) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        self._add_chrome(
            slide,
            report,
            table.caption or section.title,
            len(presentation.slides),
        )
        rows = len(table.rows) + 1
        shape = slide.shapes.add_table(
            rows, len(table.columns), _MARGIN, _CONTENT_TOP, Inches(12), Inches(4.5)
        )
        ppt_table = shape.table
        for column_index, column in enumerate(table.columns):
            ppt_table.cell(0, column_index).text = column.label
        for row_index, row in enumerate(table.rows, start=1):
            for column_index, cell in enumerate(row):
                ppt_table.cell(row_index, column_index).text = (
                    "" if cell is None else str(cell)
                )
        if table.caption:
            self._add_text(
                slide,
                table.caption,
                _MARGIN,
                Inches(6.15),
                Inches(12),
                0.35,
                11,
                color=_GRAY,
            )

    def _add_narrative_slide(
        self, presentation: Any, report: Report, section: Section, text: str
    ) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        self._add_chrome(slide, report, section.title, len(presentation.slides))
        self._add_text(slide, text, _MARGIN, _CONTENT_TOP, Inches(12), Inches(4.8), 18)

    def _add_summary_slide(self, presentation: Any, report: Report) -> None:
        slide = presentation.slides.add_slide(presentation.slide_layouts[6])
        self._add_chrome(slide, report, "Summary", len(presentation.slides))
        for index, finding in enumerate(report.findings):
            self._add_finding(slide, finding, index)

    def _add_finding(self, slide: Any, finding: Finding, index: int) -> None:
        top = _CONTENT_TOP + Inches(index * 1.25)
        self._add_text(slide, finding.title, _MARGIN, top, Inches(12), 0.3, 16)
        self._add_text(
            slide,
            finding.narrative.text,
            _MARGIN,
            top + Inches(0.35),
            Inches(12),
            0.65,
            12,
        )

    def _add_chrome(self, slide: Any, report: Report, heading: str, page: int) -> None:
        self._add_text(
            slide,
            report.metadata.title,
            _MARGIN,
            Inches(0.35),
            Inches(10),
            0.3,
            10,
            color=_GRAY,
        )
        self._add_text(slide, heading, _MARGIN, Inches(0.75), Inches(10), 0.55, 22)
        if report.metadata.subtitle:
            self._add_text(
                slide,
                report.metadata.subtitle,
                _MARGIN,
                Inches(1.18),
                Inches(10),
                0.25,
                9,
                color=_GRAY,
            )
        if report.metadata.source:
            self._add_text(
                slide,
                report.metadata.source,
                _MARGIN,
                Inches(7.1),
                Inches(8),
                0.2,
                8,
                color=_GRAY,
            )
        self._add_page_number(slide, page)

    def _add_page_number(self, slide: Any, page: int) -> None:
        self._add_text(
            slide,
            str(page),
            Inches(12.1),
            Inches(7.0),
            Inches(0.5),
            0.2,
            8,
            color=_GRAY,
            alignment=PP_ALIGN.RIGHT,
        )

    def _add_text(  # noqa: PLR0913, PLR0917
        self,
        slide: Any,
        text: str,
        left: Any,
        top: Any,
        width: Any,
        height: Any,
        size: Any,
        *,
        color: Any = _NAVY,
        alignment: PP_ALIGN = PP_ALIGN.LEFT,
    ) -> None:
        shape = slide.shapes.add_textbox(left, top, width, height)
        frame = shape.text_frame
        frame.clear()
        paragraph = frame.paragraphs[0]
        paragraph.text = text
        paragraph.alignment = alignment
        paragraph.font.size = Pt(size)
        paragraph.font.color.rgb = color
