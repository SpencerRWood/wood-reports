"""Typed, renderer-neutral report definitions and validation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

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
    renderer_hints: RendererHints = field(default_factory=dict)

    def validate(self, element: str = "metadata") -> None:
        _require_text(self.title, f"{element}.title")


@dataclass(frozen=True, slots=True)
class Narrative:
    """A renderer-neutral narrative block."""

    text: str
    renderer_hints: RendererHints = field(default_factory=dict)

    def validate(self, element: str) -> None:
        _require_text(self.text, f"{element}.text")


@dataclass(frozen=True, slots=True)
class ChartReference:
    """A locally rendered chart artifact to place in a report."""

    artifact: Path
    caption: str | None = None
    renderer_hints: RendererHints = field(default_factory=dict)

    def validate(self, element: str, artifact_root: Path) -> None:
        artifact = artifact_root / self.artifact
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

    def validate(self, element: str) -> None:
        _require_text(self.identity, f"{element}.identity")
        _require_text(self.title, f"{element}.title")
        self.narrative.validate(f"{element}.narrative")


@dataclass(frozen=True, slots=True)
class Section:
    """An ordered report section containing publication content."""

    title: str
    content: tuple[ReportContent, ...]
    renderer_hints: RendererHints = field(default_factory=dict)

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

    def validate(self, artifact_root: Path) -> None:
        """Reject incomplete report structure or missing local artifacts."""
        self.metadata.validate()
        if not self.sections:
            raise ReportValidationError("sections", "must contain a section")
        for index, section in enumerate(self.sections):
            section.validate(f"sections[{index}]", artifact_root)
        for index, finding in enumerate(self.findings):
            finding.validate(f"findings[{index}]")
        for index, appendix in enumerate(self.appendices):
            appendix.validate(f"appendices[{index}]", artifact_root)
