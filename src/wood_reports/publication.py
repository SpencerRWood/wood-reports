"""Native report lifecycle operations shared by Python callers and the CLI."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from wood_reports.compilation import (
    CompilationError,
    CompilationResult,
    WorkspaceCompiler,
)
from wood_reports.latex_workspace import LatexWorkspacePublisher
from wood_reports.markdown import MarkdownReportCompiler
from wood_reports.model import Report
from wood_reports.profiles import scaffold_markdown
from wood_reports.release import ReleasePublisher, ReleaseResult
from wood_reports.sources import DriveReader, compile_drive_report, read_drive_markdown
from wood_reports.theme import WOOD_ANALYTICS_THEME, PublicationTheme


@dataclass(frozen=True, slots=True)
class PreviewResult:
    compilation: CompilationResult
    warnings: tuple[str, ...]


class PublicationAPI:
    """Author and validate Markdown, then compile isolated preview artifacts.

    Preview PDFs are review artifacts. A successful preview never constitutes
    release validation or permission to deliver an artifact to a client.
    """

    def __init__(self, *, theme: PublicationTheme = WOOD_ANALYTICS_THEME) -> None:
        theme.validate()
        self.theme = theme

    def create(  # noqa: PLR0913
        self,
        destination: Path,
        *,
        doc_type: str | None = None,
        doc_name: str | None = None,
        drive_reference: str | None = None,
        reader: DriveReader | None = None,
        artifact_root: Path | None = None,
    ) -> Path:
        """Create a scaffold or import validated Drive Markdown without overwrites."""
        if destination.suffix.lower() != ".md":
            raise ValueError("create destination must be a Markdown (.md) file")
        if drive_reference is not None:
            if reader is None:
                raise ValueError("Drive source requires an authenticated reader")
            if doc_type is not None or doc_name is not None:
                raise ValueError("Drive create uses the source's profile and name")
            source, text = read_drive_markdown(drive_reference, reader)
            MarkdownReportCompiler().compile_text(
                text, source=source, artifact_root=artifact_root or destination.parent
            )
        else:
            if doc_type is None or doc_name is None:
                raise ValueError("local create requires doc_type and doc_name")
            text = scaffold_markdown(doc_type, doc_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as output:
            output.write(text)
        return destination

    def validate(
        self,
        source: str,
        *,
        artifact_root: Path | None = None,
        reader: DriveReader | None = None,
    ) -> Report:
        """Deterministically validate authoring semantics and local asset references."""
        if reader is not None:
            if artifact_root is None:
                raise ValueError("Drive validation requires artifact_root")
            report = compile_drive_report(source, reader, artifact_root=artifact_root)
        else:
            report = MarkdownReportCompiler().compile_file(
                Path(source), artifact_root=artifact_root
            )
        return replace(report, theme=self.theme)

    def preview(  # noqa: PLR0913
        self,
        source: str,
        destination: Path,
        *,
        compiler: WorkspaceCompiler,
        artifact_root: Path | None = None,
        reader: DriveReader | None = None,
        resource_urls: Mapping[str, str] | None = None,
    ) -> PreviewResult:
        """Compile to a new directory, preserving failed attempts for diagnosis."""
        report = self.validate(source, artifact_root=artifact_root, reader=reader)
        root = artifact_root or Path(source).parent
        destination.mkdir(parents=True, exist_ok=False)
        workspace = destination / "workspace"
        LatexWorkspacePublisher().publish(report, workspace, artifact_root=root)
        result = compiler.compile(
            workspace, destination / "compilation", resource_urls=resource_urls
        )
        if result.status != "success" or result.pdf is None:
            raise CompilationError(result)
        warnings = tuple(
            sorted(
                {
                    line.strip()
                    for log in result.logs
                    for line in log.read_text(
                        encoding="utf-8", errors="replace"
                    ).splitlines()
                    if "Warning" in line or "Overfull" in line or "Underfull" in line
                }
            )
        )
        return PreviewResult(result, warnings)

    def release(  # noqa: PLR0913
        self,
        source: str,
        destination: Path,
        *,
        compiler: WorkspaceCompiler,
        build_epoch: int,
        artifact_root: Path | None = None,
        reader: DriveReader | None = None,
        source_revision: str | None = None,
        resource_urls: Mapping[str, str] | None = None,
    ) -> ReleaseResult:
        """Validate and publish an immutable version; retain failed attempt evidence."""
        report = self.validate(source, artifact_root=artifact_root, reader=reader)
        return ReleasePublisher().publish(
            report,
            destination,
            compiler=compiler,
            artifact_root=artifact_root or Path(source).parent,
            source_identity=source if reader is not None else Path(source).name,
            source_revision=source_revision,
            build_epoch=build_epoch,
            resource_urls=resource_urls,
        )
