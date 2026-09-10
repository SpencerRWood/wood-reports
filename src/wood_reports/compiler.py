"""Compile bounded YAML and Markdown authoring sources into report models."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import yaml
from jinja2 import StrictUndefined, nodes
from jinja2.sandbox import SandboxedEnvironment
from yaml.error import MarkedYAMLError, YAMLError

from wood_reports.model import (
    Appendix,
    ChartReference,
    Finding,
    Narrative,
    PublicationTable,
    RendererHints,
    Report,
    ReportMetadata,
    ReportValidationError,
    Section,
    TableCell,
    TableColumn,
)


class SourceCompilationError(ValueError):
    """An authoring error identified by its source file and field path."""

    def __init__(self, source: Path, field: str, message: str) -> None:
        self.source = source
        self.field = field
        super().__init__(f"{source}:{field}: {message}")


type SourceMapping = Mapping[str, object]
type TemplateValues = Mapping[str, str | int | float | bool | None]


class ReportCompiler:
    """Compile declarative report files without analytical or structural templating."""

    def __init__(self, values: TemplateValues | None = None) -> None:
        self._values = values or {}
        self._templates = SandboxedEnvironment(
            undefined=StrictUndefined,
            autoescape=False,
        )
        self._templates.filters = {"presentation": self._presentation}

    @staticmethod
    def _presentation(value: object, format_spec: str = "") -> str:
        return format(value, format_spec)

    def compile_file(
        self,
        source: Path,
        *,
        artifact_root: Path | None = None,
    ) -> Report:
        """Compile one YAML report definition and validate its referenced artifacts."""
        document = self._load_yaml(source)
        report = self._compile_report(document, source)
        try:
            report.validate(artifact_root or source.parent)
        except ReportValidationError as error:
            raise SourceCompilationError(source, error.element, str(error)) from error
        return report

    def _load_yaml(self, source: Path) -> SourceMapping:
        try:
            raw = yaml.safe_load(source.read_text(encoding="utf-8"))
        except OSError as error:
            raise SourceCompilationError(source, "source", str(error)) from error
        except (MarkedYAMLError, YAMLError) as error:
            raise SourceCompilationError(source, "yaml", str(error)) from error
        return self._mapping(raw, source, "root")

    def _compile_report(self, document: SourceMapping, source: Path) -> Report:
        metadata = self._mapping(document.get("metadata"), source, "metadata")
        sections = tuple(
            self._compile_section(value, source, f"sections[{index}]")
            for index, value in enumerate(
                self._sequence(document.get("sections"), source, "sections")
            )
        )
        findings = tuple(
            self._compile_finding_reference(value, source, f"findings[{index}]")
            for index, value in enumerate(
                self._sequence(document.get("findings", []), source, "findings")
            )
        )
        appendices = tuple(
            self._compile_appendix(value, source, f"appendices[{index}]")
            for index, value in enumerate(
                self._sequence(document.get("appendices", []), source, "appendices")
            )
        )
        return Report(
            metadata=ReportMetadata(
                title=self._text(metadata.get("title"), source, "metadata.title"),
                subtitle=self._optional_text(
                    metadata.get("subtitle"), source, "metadata.subtitle"
                ),
                author=self._optional_text(
                    metadata.get("author"), source, "metadata.author"
                ),
                renderer_hints=self._hints(
                    metadata.get("renderer_hints", {}),
                    source,
                    "metadata.renderer_hints",
                ),
            ),
            sections=sections,
            findings=findings,
            appendices=appendices,
            renderer_hints=self._hints(
                document.get("renderer_hints", {}), source, "renderer_hints"
            ),
        )

    def _compile_section(self, value: object, source: Path, field: str) -> Section:
        data = self._mapping(value, source, field)
        return Section(
            title=self._text(data.get("title"), source, f"{field}.title"),
            content=self._compile_content(
                data.get("content"), source, f"{field}.content"
            ),
            renderer_hints=self._hints(
                data.get("renderer_hints", {}), source, f"{field}.renderer_hints"
            ),
        )

    def _compile_appendix(self, value: object, source: Path, field: str) -> Appendix:
        data = self._mapping(value, source, field)
        return Appendix(
            title=self._text(data.get("title"), source, f"{field}.title"),
            content=self._compile_content(
                data.get("content"), source, f"{field}.content"
            ),
            renderer_hints=self._hints(
                data.get("renderer_hints", {}), source, f"{field}.renderer_hints"
            ),
        )

    def _compile_content(
        self, value: object, source: Path, field: str
    ) -> tuple[Narrative | ChartReference | PublicationTable, ...]:
        return tuple(
            self._compile_content_item(item, source, f"{field}[{index}]")
            for index, item in enumerate(self._sequence(value, source, field))
        )

    def _compile_content_item(
        self, value: object, source: Path, field: str
    ) -> Narrative | ChartReference | PublicationTable:
        data = self._mapping(value, source, field)
        declared = [name for name in ("narrative", "chart", "table") if name in data]
        if len(declared) != 1:
            raise SourceCompilationError(
                source, field, "must declare exactly one content type"
            )
        kind = declared[0]
        payload = data[kind]
        if kind == "narrative":
            return Narrative(self._render_text(payload, source, f"{field}.narrative"))
        payload_data = self._mapping(payload, source, f"{field}.{kind}")
        if kind == "chart":
            return ChartReference(
                artifact=Path(
                    self._text(
                        payload_data.get("artifact"), source, f"{field}.chart.artifact"
                    )
                ),
                caption=self._optional_rendered_text(
                    payload_data.get("caption"), source, f"{field}.chart.caption"
                ),
                renderer_hints=self._hints(
                    payload_data.get("renderer_hints", {}),
                    source,
                    f"{field}.chart.renderer_hints",
                ),
            )
        columns = tuple(
            self._compile_column(column, source, f"{field}.table.columns[{index}]")
            for index, column in enumerate(
                self._sequence(
                    payload_data.get("columns"), source, f"{field}.table.columns"
                )
            )
        )
        rows = tuple(
            tuple(
                cast(TableCell, cell)
                for cell in self._sequence(row, source, f"{field}.table.rows[{index}]")
            )
            for index, row in enumerate(
                self._sequence(
                    payload_data.get("rows", []), source, f"{field}.table.rows"
                )
            )
        )
        return PublicationTable(
            columns=columns,
            rows=rows,
            caption=self._optional_rendered_text(
                payload_data.get("caption"), source, f"{field}.table.caption"
            ),
            notes=tuple(
                self._render_text(note, source, f"{field}.table.notes[{index}]")
                for index, note in enumerate(
                    self._sequence(
                        payload_data.get("notes", []), source, f"{field}.table.notes"
                    )
                )
            ),
            renderer_hints=self._hints(
                payload_data.get("renderer_hints", {}),
                source,
                f"{field}.table.renderer_hints",
            ),
        )

    def _compile_column(self, value: object, source: Path, field: str) -> TableColumn:
        data = self._mapping(value, source, field)
        alignment = self._text(
            data.get("alignment", "left"), source, f"{field}.alignment"
        )
        if alignment not in {"left", "center", "right"}:
            raise SourceCompilationError(
                source,
                f"{field}.alignment",
                "must be left, center, or right",
            )
        return TableColumn(
            identity=self._text(data.get("identity"), source, f"{field}.identity"),
            label=self._render_text(data.get("label"), source, f"{field}.label"),
            format=self._optional_text(data.get("format"), source, f"{field}.format"),
            alignment=cast(Any, alignment),
            renderer_hints=self._hints(
                data.get("renderer_hints", {}), source, f"{field}.renderer_hints"
            ),
        )

    def _compile_finding_reference(
        self, value: object, source: Path, field: str
    ) -> Finding:
        data = self._mapping(value, source, field)
        relative_source = self._text(data.get("source"), source, f"{field}.source")
        finding_source = source.parent / relative_source
        frontmatter, body = self._load_markdown(finding_source)
        severity = self._text(
            frontmatter.get("severity", "info"), finding_source, "severity"
        )
        if severity not in {"info", "warning", "critical"}:
            raise SourceCompilationError(
                finding_source,
                "severity",
                "must be info, warning, or critical",
            )
        return Finding(
            identity=self._text(
                frontmatter.get("identity"), finding_source, "identity"
            ),
            title=self._render_text(frontmatter.get("title"), finding_source, "title"),
            narrative=Narrative(self._render_text(body, finding_source, "body")),
            severity=cast(Any, severity),
            renderer_hints=self._hints(
                frontmatter.get("renderer_hints", {}),
                finding_source,
                "renderer_hints",
            ),
        )

    def _load_markdown(self, source: Path) -> tuple[SourceMapping, str]:
        try:
            text = source.read_text(encoding="utf-8")
        except OSError as error:
            raise SourceCompilationError(source, "source", str(error)) from error
        if not text.startswith("---\n"):
            raise SourceCompilationError(source, "frontmatter", "must begin with ---")
        try:
            _, raw_frontmatter, body = text.split("---\n", 2)
        except ValueError as error:
            raise SourceCompilationError(
                source, "frontmatter", "must be closed with ---"
            ) from error
        try:
            frontmatter = yaml.safe_load(raw_frontmatter)
        except YAMLError as error:
            raise SourceCompilationError(source, "frontmatter", str(error)) from error
        return self._mapping(frontmatter, source, "frontmatter"), body.strip()

    def _render_text(self, value: object, source: Path, field: str) -> str:
        text = self._text(value, source, field)
        try:
            parsed = self._templates.parse(text)
        except Exception as error:
            raise SourceCompilationError(
                source, field, f"invalid template: {error}"
            ) from error
        if not self._is_bounded_template(parsed):
            raise SourceCompilationError(
                source,
                field,
                "templates permit only named values and the presentation filter",
            )
        try:
            return self._templates.from_string(text).render(**self._values)
        except Exception as error:
            raise SourceCompilationError(
                source, field, f"template rendering failed: {error}"
            ) from error

    def _optional_rendered_text(
        self, value: object, source: Path, field: str
    ) -> str | None:
        return None if value is None else self._render_text(value, source, field)

    def _is_bounded_template(self, parsed: nodes.Template) -> bool:
        return all(
            isinstance(node, (nodes.Output, nodes.TemplateData))
            and (
                not isinstance(node, nodes.Output)
                or all(self._is_value(item) for item in node.nodes)
            )
            for node in parsed.body
        )

    def _is_value(self, node: nodes.Expr | nodes.TemplateData) -> bool:
        if isinstance(node, (nodes.Name, nodes.Const, nodes.TemplateData)):
            return True
        return (
            isinstance(node, nodes.Filter)
            and node.name == "presentation"
            and node.node is not None
            and self._is_value(node.node)
            and all(isinstance(argument, nodes.Const) for argument in node.args)
            and not node.kwargs
        )

    @staticmethod
    def _mapping(value: object, source: Path, field: str) -> SourceMapping:
        if not isinstance(value, Mapping):
            raise SourceCompilationError(source, field, "must be a mapping")
        if not all(isinstance(key, str) for key in value):
            raise SourceCompilationError(source, field, "keys must be strings")
        return cast(SourceMapping, value)

    @staticmethod
    def _sequence(value: object, source: Path, field: str) -> list[object]:
        if not isinstance(value, list):
            raise SourceCompilationError(source, field, "must be a list")
        return value

    @staticmethod
    def _text(value: object, source: Path, field: str) -> str:
        if not isinstance(value, str):
            raise SourceCompilationError(source, field, "must be a string")
        return value

    def _optional_text(self, value: object, source: Path, field: str) -> str | None:
        return None if value is None else self._text(value, source, field)

    @staticmethod
    def _hints(value: object, source: Path, field: str) -> RendererHints:
        hints = ReportCompiler._mapping(value, source, field)
        if not all(isinstance(item, str) for item in hints.values()):
            raise SourceCompilationError(source, field, "values must be strings")
        return dict(cast(Mapping[str, str], hints))
