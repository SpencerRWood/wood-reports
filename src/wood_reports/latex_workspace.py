"""Publish generated LaTeX sources without taking ownership of extensions."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from wood_reports.latex import LatexRenderer
from wood_reports.model import Appendix, ChartReference, Report, Section


class LatexWorkspaceError(ValueError):
    """Raised when a workspace layout would blur its ownership boundary."""


class LatexWorkspacePublisher:
    """Publish a self-contained, mutable LaTeX source workspace.

    ``generated`` is owned exclusively by Wood Reports and is replaced on each
    publication.  ``extensions`` is reserved for human-maintained files and is
    never created, removed, or modified by this publisher.  A synchronization
    service can consequently copy the whole workspace without needing a Wood
    Reports-specific integration.
    """

    def __init__(
        self,
        renderer: LatexRenderer | None = None,
        *,
        generated_directory: str = "generated",
        extensions_directory: str = "extensions",
    ) -> None:
        self._renderer = renderer or LatexRenderer()
        self._generated_directory = self._directory_name(generated_directory)
        self._extensions_directory = self._directory_name(extensions_directory)
        if self._generated_directory == self._extensions_directory:
            raise LatexWorkspaceError(
                "generated and human-maintained directories must differ"
            )

    def publish(self, report: Report, workspace: Path, *, artifact_root: Path) -> Path:
        """Render ``report`` and its chart assets into the generated source tree.

        The returned path is the generated ``report.tex``.  Existing extension
        files remain untouched, including when the generated tree is replaced.
        """
        report.validate(artifact_root)
        workspace = workspace.resolve()
        generated = workspace / self._generated_directory
        if generated.exists() and not generated.is_dir():
            raise LatexWorkspaceError(f"generated path is not a directory: {generated}")

        workspace.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=workspace, prefix=".wood-reports-") as temporary:
            staging = Path(temporary) / self._generated_directory
            staging.mkdir()
            rendered = self._copy_assets(report, artifact_root, staging)
            self._renderer.render(
                rendered,
                staging / "report.tex",
                artifact_root=staging,
            )
            if generated.exists():
                shutil.rmtree(generated)
            staging.replace(generated)
        return generated / "report.tex"

    @staticmethod
    def _directory_name(name: str) -> str:
        path = Path(name)
        if (
            not name
            or path.is_absolute()
            or len(path.parts) != 1
            or name in {".", ".."}
        ):
            raise LatexWorkspaceError(
                "workspace directory names must be single relative paths"
            )
        return name

    @staticmethod
    def _copy_assets(report: Report, artifact_root: Path, staging: Path) -> Report:
        """Copy referenced artifacts and point the rendered report at local copies."""
        counter = 0

        def copy_chart(chart: ChartReference) -> ChartReference:
            nonlocal counter
            if chart.artifact is None:
                return chart
            source = artifact_root / chart.artifact
            counter += 1
            relative = Path("assets") / f"{counter}-{source.name}"
            destination = staging / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            return replace(chart, artifact=relative)

        def copy_section(section: Section) -> Section:
            return replace(
                section,
                content=tuple(
                    copy_chart(item) if isinstance(item, ChartReference) else item
                    for item in section.content
                ),
            )

        def copy_appendix(appendix: Appendix) -> Appendix:
            return replace(
                appendix,
                content=tuple(
                    copy_chart(item) if isinstance(item, ChartReference) else item
                    for item in appendix.content
                ),
            )

        return replace(
            report,
            sections=tuple(copy_section(section) for section in report.sections),
            appendices=tuple(copy_appendix(appendix) for appendix in report.appendices),
        )
