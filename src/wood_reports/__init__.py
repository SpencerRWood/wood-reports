"""Reusable publication primitives for analytical reports."""

from typing import TYPE_CHECKING, Any

from wood_reports.api import (
    ReportGenerationAPI,
    ReportGenerationError,
    ReportGenerationResult,
)
from wood_reports.compiler import ReportCompiler, SourceCompilationError
from wood_reports.latex import LatexRenderer, LatexRenderError
from wood_reports.latex_workspace import LatexWorkspaceError, LatexWorkspacePublisher
from wood_reports.manifest import OutputExistsError, RunOutputWriter, TargetStatus
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
from wood_reports.run import Comparison, ReportRun, ReportRunError, ReportRunFactory

if TYPE_CHECKING:
    from wood_reports.powerpoint import PowerPointRenderer, PowerPointRenderError

__all__ = [
    "Appendix",
    "ChartGenerationContext",
    "ChartReference",
    "ChartResolutionError",
    "Comparison",
    "Finding",
    "LatexRenderError",
    "LatexRenderer",
    "LatexWorkspaceError",
    "LatexWorkspacePublisher",
    "Narrative",
    "OutputExistsError",
    "PowerPointRenderError",
    "PowerPointRenderer",
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
    "ReportRunFactory",
    "ReportValidationError",
    "RunOutputWriter",
    "Section",
    "SourceCompilationError",
    "TableColumn",
    "TargetStatus",
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
