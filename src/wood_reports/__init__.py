"""Reusable publication primitives for analytical reports."""

from typing import TYPE_CHECKING, Any

from wood_reports.api import (
    OutputExistsError,
    ReportGenerationAPI,
    ReportGenerationError,
    ReportGenerationResult,
    TargetStatus,
)
from wood_reports.branding import PublicationBranding
from wood_reports.citations import BibliographySource
from wood_reports.clsi import CLSICompiler
from wood_reports.compilation import (
    CLSIConfig,
    CLSICredentials,
    CompilationError,
    CompilationResult,
    WorkspaceCompiler,
)
from wood_reports.compiler import ReportCompiler, SourceCompilationError
from wood_reports.diagrams import ArchitectureDiagram
from wood_reports.latex import LatexRenderer, LatexRenderError
from wood_reports.latex_workspace import LatexWorkspaceError, LatexWorkspacePublisher
from wood_reports.markdown import MarkdownReportCompiler
from wood_reports.model import (
    Appendix,
    ChartReference,
    Finding,
    Narrative,
    PublicationTable,
    Report,
    ReportMetadata,
    ReportValidationError,
    Section,
    TableColumn,
)
from wood_reports.pdf_validation import (
    PDFValidationError,
    PDFValidationResult,
    ValidationIssue,
    validate_pdf,
    validate_release_report,
)
from wood_reports.pipeline import (
    ChartGenerationContext,
    ChartResolutionError,
    ReportGenerationPipeline,
)
from wood_reports.profiles import (
    DocumentProfile,
    ProfileSection,
    ProfileValidationError,
    get_profile,
    list_profiles,
    scaffold_markdown,
)
from wood_reports.publication import (
    PreviewResult,
    PublicationAPI,
)
from wood_reports.release import (
    ReleasePublisher,
    ReleaseResult,
    release_manifest,
    semantic_content_digest,
)
from wood_reports.run import Comparison, ReportRun, ReportRunError
from wood_reports.sources import (
    DriveFile,
    DriveReader,
    GoogleDriveReader,
    compile_drive_report,
)
from wood_reports.theme import (
    WOOD_ANALYTICS_THEME,
    PrimitiveStyle,
    PublicationColors,
    PublicationGeometry,
    PublicationSpacing,
    PublicationTableLayout,
    PublicationTheme,
    PublicationTypography,
)

if TYPE_CHECKING:
    from wood_reports.powerpoint import PowerPointRenderer, PowerPointRenderError

__all__ = [
    "WOOD_ANALYTICS_THEME",
    "Appendix",
    "ArchitectureDiagram",
    "BibliographySource",
    "CLSICompiler",
    "CLSIConfig",
    "CLSICredentials",
    "ChartGenerationContext",
    "ChartReference",
    "ChartResolutionError",
    "Comparison",
    "CompilationError",
    "CompilationResult",
    "DocumentProfile",
    "DriveFile",
    "DriveReader",
    "Finding",
    "GoogleDriveReader",
    "LatexRenderError",
    "LatexRenderer",
    "LatexWorkspaceError",
    "LatexWorkspacePublisher",
    "MarkdownReportCompiler",
    "Narrative",
    "OutputExistsError",
    "PDFValidationError",
    "PDFValidationResult",
    "PowerPointRenderError",
    "PowerPointRenderer",
    "PreviewResult",
    "PrimitiveStyle",
    "ProfileSection",
    "ProfileValidationError",
    "PublicationAPI",
    "PublicationBranding",
    "PublicationColors",
    "PublicationGeometry",
    "PublicationSpacing",
    "PublicationTable",
    "PublicationTableLayout",
    "PublicationTheme",
    "PublicationTypography",
    "ReleasePublisher",
    "ReleaseResult",
    "Report",
    "ReportCompiler",
    "ReportGenerationAPI",
    "ReportGenerationError",
    "ReportGenerationPipeline",
    "ReportGenerationResult",
    "ReportMetadata",
    "ReportRun",
    "ReportRunError",
    "ReportValidationError",
    "Section",
    "SourceCompilationError",
    "TableColumn",
    "TargetStatus",
    "ValidationIssue",
    "WorkspaceCompiler",
    "compile_drive_report",
    "get_profile",
    "list_profiles",
    "release_manifest",
    "scaffold_markdown",
    "semantic_content_digest",
    "validate_pdf",
    "validate_release_report",
]


def __getattr__(name: str) -> Any:
    """Lazily expose PowerPoint support without requiring it for other targets."""
    if name in {"PowerPointRenderer", "PowerPointRenderError"}:
        from wood_reports.powerpoint import (  # noqa: PLC0415
            PowerPointRenderer,
            PowerPointRenderError,
        )

        return {
            "PowerPointRenderer": PowerPointRenderer,
            "PowerPointRenderError": PowerPointRenderError,
        }[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
