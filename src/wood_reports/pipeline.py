"""Resolve logical charts into reusable report artifacts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from wood_reports.model import Appendix, ChartReference, Finding, Report, Section


@dataclass(frozen=True, slots=True)
class ChartGenerationContext:
    """Stable publication context supplied to a consumer-owned chart builder."""

    title: str
    subtitle: str | None
    source: str | None
    run_context: Mapping[str, object]
    visual_references: Mapping[str, Path]


type ChartBuilder = Callable[[ChartGenerationContext], Path]


class ChartResolutionError(ValueError):
    """A chart generation error with its report location and logical identity."""

    def __init__(self, element: str, identity: str, message: str) -> None:
        self.element = element
        self.identity = identity
        super().__init__(f"{element}: chart identity {identity!r} {message}")


class ReportGenerationPipeline:
    """Resolve logical charts while leaving chart construction to consumers."""

    def __init__(
        self,
        chart_builders: Mapping[str, ChartBuilder],
        *,
        run_context: Mapping[str, object] | None = None,
        visual_references: Mapping[str, Path] | None = None,
    ) -> None:
        self._chart_builders = chart_builders
        self._run_context = run_context or {}
        self._visual_references = visual_references or {}

    def generate(self, report: Report, *, artifact_root: Path) -> Report:
        """Build logical charts and return a report ready for document renderers."""
        context = ChartGenerationContext(
            title=report.metadata.title,
            subtitle=report.metadata.subtitle,
            source=report.metadata.source,
            run_context=self._run_context,
            visual_references=self._visual_references,
        )
        resolved = replace(
            report,
            sections=tuple(
                self._resolve_section(section, f"sections[{index}]", context)
                for index, section in enumerate(report.sections)
            ),
            appendices=tuple(
                self._resolve_appendix(appendix, f"appendices[{index}]", context)
                for index, appendix in enumerate(report.appendices)
            ),
            findings=tuple(
                self._resolve_finding(finding, f"findings[{index}]", context)
                for index, finding in enumerate(report.findings)
            ),
        )
        resolved.validate(artifact_root)
        return resolved

    def _resolve_section(
        self, section: Section, element: str, context: ChartGenerationContext
    ) -> Section:
        return replace(
            section,
            content=tuple(
                self._resolve_chart(item, f"{element}.content[{index}]", context)
                if isinstance(item, ChartReference)
                else item
                for index, item in enumerate(section.content)
            ),
        )

    def _resolve_appendix(
        self, appendix: Appendix, element: str, context: ChartGenerationContext
    ) -> Appendix:
        return replace(
            appendix,
            content=tuple(
                self._resolve_chart(item, f"{element}.content[{index}]", context)
                if isinstance(item, ChartReference)
                else item
                for index, item in enumerate(appendix.content)
            ),
        )

    def _resolve_finding(
        self, finding: Finding, element: str, context: ChartGenerationContext
    ) -> Finding:
        return replace(
            finding,
            visual=self._resolve_chart(finding.visual, f"{element}.visual", context)
            if isinstance(finding.visual, ChartReference)
            else finding.visual,
        )

    def _resolve_chart(
        self, chart: ChartReference, element: str, context: ChartGenerationContext
    ) -> ChartReference:
        if chart.artifact is not None:
            return chart
        identity = chart.identity
        if identity is None:
            return chart
        builder = self._chart_builders.get(identity)
        if builder is None:
            raise ChartResolutionError(element, identity, "has no configured builder")
        try:
            artifact = builder(context)
        except Exception as error:
            raise ChartResolutionError(
                element, identity, f"failed to build: {error}"
            ) from error
        return replace(chart, artifact=artifact)
