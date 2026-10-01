"""Reusable publication primitives for analytical reports."""

from typing import TYPE_CHECKING, Any

from wood_reports.api import (
    OutputExistsError,
    ReportGenerationAPI,
    ReportGenerationError,
    ReportGenerationResult,
    TargetStatus,
)
from wood_reports.compiler import ReportCompiler, SourceCompilationError
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
from wood_reports.run import Comparison, ReportRun, ReportRunError
from wood_reports.sources import (
    DriveFile,
    DriveReader,
    GoogleDriveReader,
    compile_drive_report,
)

if TYPE_CHECKING:
    from wood_reports.powerpoint import PowerPointRenderer, PowerPointRenderError

__all__ = [
    "Appendix",
    "ChartGenerationContext",
    "ChartReference",
    "ChartResolutionError",
    "Comparison",
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
    "PowerPointRenderError",
    "PowerPointRenderer",
    "ProfileSection",
    "ProfileValidationError",
    "PublicationTable",
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
    "compile_drive_report",
    "get_profile",
    "list_profiles",
    "scaffold_markdown",
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
