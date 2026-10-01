"""Typed, renderer-neutral report definitions and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from wood_reports.theme import WOOD_ANALYTICS_THEME, PublicationTheme

type Alignment = Literal["left", "center", "right"]
type RendererHints = dict[str, str]
type TableCell = str | int | float | bool | None


class ReportValidationError(ValueError):
    """A report validation error with the precise report location and artifact."""

    def __init__(
        self,
        element: str,
        message: str,
        *,
        artifact: Path | None = None,
    ) -> None:
        self.element = element
        self.artifact = artifact
        detail = f"{element}: {message}"
        if artifact is not None:
            detail = f"{detail} (artifact: {artifact})"
        super().__init__(detail)


def _require_text(value: str, element: str) -> None:
    if not value.strip():
        raise ReportValidationError(element, "must not be blank")


@dataclass(frozen=True, slots=True)
class ReportMetadata:
    """Identity and descriptive information for a report."""

    title: str
    subtitle: str | None = None
    author: str | None = None
    source: str | None = None
    renderer_hints: RendererHints = field(default_factory=dict)

    doc_type: str | None = None
    doc_name: str | None = None
    profile_version: str | None = None
    client: str | None = None
    project: str | None = None
    engagement: str | None = None
    version: str | None = None
    audience: str | None = None
    confidentiality: str | None = None
    period: str | None = None
    comparison_period: str | None = None

    def validate(self, element: str = "metadata") -> None:
        _require_text(self.title, f"{element}.title")


@dataclass(frozen=True, slots=True)
class Narrative:
    """A renderer-neutral narrative block."""

    text: str
    renderer_hints: RendererHints = field(default_factory=dict)
    kind: Literal["prose", "list", "callout", "heading", "code"] = "prose"
    semantic: str | None = None

    def validate(self, element: str) -> None:
        _require_text(self.text, f"{element}.text")


@dataclass(frozen=True, slots=True)
class ChartReference:
    """A logical chart or locally produced artifact to place in a report."""

    artifact: Path | None = None
    identity: str | None = None
    caption: str | None = None
    renderer_hints: RendererHints = field(default_factory=dict)

    def validate(self, element: str, artifact_root: Path) -> None:
        if self.artifact is None and self.identity is None:
            raise ReportValidationError(
                element, "must reference a chart identity or local artifact"
            )
        if self.artifact is None:
            return
        artifact = resolve_chart_artifact(self, artifact_root)
        if not artifact.is_file():
            raise ReportValidationError(
                element,
                "references a local artifact that does not exist",
                artifact=artifact,
            )


@dataclass(frozen=True, slots=True)
class TableColumn:
    """A publication-table column, independent of analytical computation."""

    identity: str
    label: str
    format: str | None = None
    alignment: Alignment = "left"
    renderer_hints: RendererHints = field(default_factory=dict)

    def validate(self, element: str) -> None:
        _require_text(self.identity, f"{element}.identity")
        _require_text(self.label, f"{element}.label")


@dataclass(frozen=True, slots=True)
class PublicationTable:
    """Presentation data for a table, with no embedded analytical logic."""

    columns: tuple[TableColumn, ...]
    rows: tuple[tuple[TableCell, ...], ...]
    caption: str | None = None
    notes: tuple[str, ...] = ()
    renderer_hints: RendererHints = field(default_factory=dict)

    def validate(self, element: str) -> None:
        if not self.columns:
            raise ReportValidationError(f"{element}.columns", "must contain a column")
        identities = [column.identity for column in self.columns]
        if len(set(identities)) != len(identities):
            raise ReportValidationError(
                f"{element}.columns", "column identities must be unique"
            )
        for index, column in enumerate(self.columns):
            column.validate(f"{element}.columns[{index}]")
        for index, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise ReportValidationError(
                    f"{element}.rows[{index}]",
                    f"contains {len(row)} cells; expected {len(self.columns)}",
                )


type ReportContent = Narrative | ChartReference | PublicationTable


@dataclass(frozen=True, slots=True)
class Finding:
    """A semantic conclusion surfaced by a report."""

    identity: str
    title: str
    narrative: Narrative
    severity: Literal["info", "warning", "critical"] = "info"
    renderer_hints: RendererHints = field(default_factory=dict)
    subtitle: str | None = None
    source: str | None = None
    visual: ChartReference | PublicationTable | None = None
    include_if: str | None = None

    def validate(self, element: str, artifact_root: Path) -> None:
        _require_text(self.identity, f"{element}.identity")
        _require_text(self.title, f"{element}.title")
        self.narrative.validate(f"{element}.narrative")
        if self.include_if is not None:
            _require_text(self.include_if, f"{element}.include_if")
        if self.visual is not None:
            if isinstance(self.visual, ChartReference):
                self.visual.validate(f"{element}.visual", artifact_root)
            else:
                self.visual.validate(f"{element}.visual")


@dataclass(frozen=True, slots=True)
class Section:
    """An ordered report section containing publication content."""

    title: str
    content: tuple[ReportContent, ...]
    renderer_hints: RendererHints = field(default_factory=dict)
    semantic: str | None = None

    def validate(self, element: str, artifact_root: Path) -> None:
        _require_text(self.title, f"{element}.title")
        if not self.content:
            raise ReportValidationError(f"{element}.content", "must not be empty")
        for index, item in enumerate(self.content):
            item_element = f"{element}.content[{index}]"
            if isinstance(item, ChartReference):
                item.validate(item_element, artifact_root)
            else:
                item.validate(item_element)


@dataclass(frozen=True, slots=True)
class Appendix:
    """Supplementary ordered content attached to a report."""

    title: str
    content: tuple[ReportContent, ...]
    renderer_hints: RendererHints = field(default_factory=dict)

    def validate(self, element: str, artifact_root: Path) -> None:
        Section(self.title, self.content, self.renderer_hints).validate(
            element, artifact_root
        )


@dataclass(frozen=True, slots=True)
class Report:
    """The complete renderer-neutral report definition."""

    metadata: ReportMetadata
    sections: tuple[Section, ...]
    findings: tuple[Finding, ...] = ()
    appendices: tuple[Appendix, ...] = ()
    renderer_hints: RendererHints = field(default_factory=dict)
    theme: PublicationTheme = WOOD_ANALYTICS_THEME

    def validate(self, artifact_root: Path) -> None:
        """Reject incomplete report structure or missing local artifacts."""
        self.metadata.validate()
        self.theme.validate()
        if not self.sections:
            raise ReportValidationError("sections", "must contain a section")
        for index, section in enumerate(self.sections):
            section.validate(f"sections[{index}]", artifact_root)
        for index, finding in enumerate(self.findings):
            finding.validate(f"findings[{index}]", artifact_root)
        for index, appendix in enumerate(self.appendices):
            appendix.validate(f"appendices[{index}]", artifact_root)


def resolve_chart_artifact(chart: ChartReference, artifact_root: Path) -> Path:
    """Return the physical chart file used for both validation and rendering."""
    if chart.artifact is None:
        raise ReportValidationError("chart", "requires a resolved local artifact")
    return (
        chart.artifact
        if chart.artifact.is_absolute()
        else artifact_root / chart.artifact
    )
