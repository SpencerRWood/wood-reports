"""Typed programmatic entry point for compiling and rendering reports."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from wood_reports.compiler import ReportCompiler, TemplateValues
from wood_reports.manifest import TargetStatus
from wood_reports.model import Report

type RenderTarget = Literal["latex", "powerpoint"]


class ReportGenerationError(ValueError):
    """Raised when a caller requests an unsupported rendering target."""


@dataclass(frozen=True, slots=True)
class ReportGenerationResult:
    """The compiled report and status of each independently requested target."""

    report: Report
    targets: tuple[TargetStatus, ...]
    period: str | None = None


class ReportGenerationAPI:
    """Compile, validate, and render a report through one typed entry point.

    Renderer modules are imported only for selected targets. This keeps LaTeX-only
    callers independent from the optional PowerPoint installation, and vice versa.
    ``period`` is deliberately metadata rather than a renderer concern, so one-off
    and recurring callers use precisely the same invocation.
    """

    def generate(  # noqa: PLR0913
        self,
        source: Path | Report,
        destination: Path,
        *,
        artifact_root: Path | None = None,
        targets: Iterable[RenderTarget] = ("latex", "powerpoint"),
        values: TemplateValues | None = None,
        period: str | None = None,
    ) -> ReportGenerationResult:
        """Compile or validate ``source`` and render each selected target."""
        report, artifacts = self._report_and_artifacts(source, artifact_root, values)
        selected = tuple(dict.fromkeys(targets))
        unknown = set(selected) - {"latex", "powerpoint"}
        if unknown:
            raise ReportGenerationError(
                f"unsupported render targets: {sorted(unknown)}"
            )
        destination.mkdir(parents=True, exist_ok=True)
        statuses = tuple(
            self._render(target, report, destination, artifacts) for target in selected
        )
        return ReportGenerationResult(report, statuses, period)

    @staticmethod
    def _report_and_artifacts(
        source: Path | Report,
        artifact_root: Path | None,
        values: TemplateValues | None,
    ) -> tuple[Report, Path]:
        if isinstance(source, Path):
            artifacts = artifact_root or source.parent
            return ReportCompiler(values).compile_file(
                source, artifact_root=artifacts
            ), artifacts
        if artifact_root is None:
            raise ReportGenerationError("artifact_root is required for a Report source")
        source.validate(artifact_root)
        return source, artifact_root

    @staticmethod
    def _render(
        target: RenderTarget,
        report: Report,
        destination: Path,
        artifact_root: Path,
    ) -> TargetStatus:
        try:
            if target == "latex":
                from wood_reports.latex import LatexRenderer  # noqa: PLC0415

                output = LatexRenderer().render(
                    report, destination / "report.tex", artifact_root=artifact_root
                )
            else:
                from wood_reports.powerpoint import PowerPointRenderer  # noqa: PLC0415

                output = PowerPointRenderer().render(
                    report, destination / "report.pptx", artifact_root=artifact_root
                )
        except Exception as error:
            return TargetStatus(target, "failed", error=str(error))
        return TargetStatus(target, "success", str(output))
