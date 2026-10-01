"""Typed public entry point for one-off and recurring report generation."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from wood_reports.model import Report
from wood_reports.run import ReportRun

type RenderTarget = Literal["latex", "powerpoint"]


class ReportGenerationError(ValueError):
    """Raised for invalid generation requests."""


class OutputExistsError(FileExistsError):
    """Raised when generation would replace a caller-owned output."""


@dataclass(frozen=True, slots=True)
class TargetStatus:
    target: str
    status: str
    output: str | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class ReportGenerationResult:
    report: Report
    targets: tuple[TargetStatus, ...]
    period: str | None = None
    manifest: Path | None = None


class ReportGenerationAPI:
    """Compile/materialize once, then independently render selected targets.

    Schedulers call this same API with ``period`` and ``immutable=True``; they are
    not a library dependency.  Target failures are represented in the manifest so
    a successful sibling output remains available.
    """

    def generate(  # noqa: PLR0913
        self,
        run: ReportRun,
        destination: Path,
        *,
        artifact_root: Path | None = None,
        targets: Iterable[RenderTarget] = ("latex", "powerpoint"),
        report_id: str | None = None,
        definition_revision: str | None = None,
        input_artifacts: Iterable[Path] = (),
        replace: bool = False,
        immutable: bool = False,
    ) -> ReportGenerationResult:
        if artifact_root is None:
            raise ReportGenerationError("artifact_root is required")
        report = run.materialize()
        report.validate(artifact_root)
        artifacts = artifact_root
        selected = tuple(dict.fromkeys(targets))
        unknown = set(selected) - {"latex", "powerpoint"}
        if unknown:
            raise ReportGenerationError(
                f"unsupported render targets: {sorted(unknown)}"
            )
        output = destination
        if immutable:
            output = (
                output
                / (report_id or report.metadata.title.replace(" ", "-").lower())
                / run.period
            )
        if (
            output.exists()
            and not replace
            and any(
                (output / name).exists()
                for name in ("report.tex", "report.pptx", "manifest.json")
            )
        ):
            raise OutputExistsError(
                f"output already exists: {output}; pass replace=True to replace it"
            )
        output.mkdir(parents=True, exist_ok=True)
        statuses = tuple(
            self._render(target, report, output, artifacts, replace)
            for target in selected
        )
        manifest = output / "manifest.json"
        payload = {
            "theme": {
                "identity": report.theme.identity,
                "revision": report.theme.revision,
                "brand_revision": report.theme.brand_revision,
            },
            "comparison_period": run.comparison_period,
            "comparisons": {
                key: asdict(value) for key, value in sorted(run.comparisons.items())
            },
            "definition_revision": definition_revision,
            "generated_artifacts": [
                status.output for status in statuses if status.output
            ],
            "input_artifacts": [str(path) for path in sorted(input_artifacts)],
            "overall_status": "success"
            if all(status.status == "success" for status in statuses)
            else "partial_failure",
            "parameters": dict(sorted(run.values.items())),
            "period": run.period,
            "report_id": report_id or report.metadata.title,
            "targets": [asdict(status) for status in statuses],
        }
        manifest.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return ReportGenerationResult(report, statuses, run.period, manifest)

    @staticmethod
    def _render(
        target: RenderTarget,
        report: Report,
        destination: Path,
        artifact_root: Path,
        replace: bool,
    ) -> TargetStatus:
        output_path = destination / (
            "report.tex" if target == "latex" else "report.pptx"
        )
        if output_path.exists() and not replace:
            return TargetStatus(
                target,
                "failed",
                error=f"output exists: {output_path}; pass replace=True",
            )
        try:
            if target == "latex":
                from wood_reports.latex import LatexRenderer  # noqa: PLC0415

                output = LatexRenderer().render(
                    report, output_path, artifact_root=artifact_root
                )
            else:
                from wood_reports.powerpoint import PowerPointRenderer  # noqa: PLC0415

                output = PowerPointRenderer().render(
                    report, output_path, artifact_root=artifact_root
                )
        except Exception as error:
            return TargetStatus(target, "failed", error=str(error))
        return TargetStatus(target, "success", str(output))
