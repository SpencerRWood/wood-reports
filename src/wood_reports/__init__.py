"""Reusable publication primitives for analytical reports."""

from wood_reports.compiler import ReportCompiler, SourceCompilationError
from wood_reports.latex import LatexRenderer, LatexRenderError
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
from wood_reports.powerpoint import PowerPointRenderer, PowerPointRenderError
from wood_reports.run import Comparison, ReportRun, ReportRunError, ReportRunFactory

__all__ = [
    "Appendix",
    "ChartGenerationContext",
    "ChartReference",
    "ChartResolutionError",
    "Comparison",
    "Finding",
    "LatexRenderError",
    "LatexRenderer",
    "Narrative",
    "PowerPointRenderError",
    "PowerPointRenderer",
    "PublicationTable",
    "Report",
    "ReportCompiler",
    "ReportGenerationPipeline",
    "ReportMetadata",
    "ReportRun",
    "ReportRunError",
    "ReportRunFactory",
    "ReportValidationError",
    "Section",
    "SourceCompilationError",
    "TableColumn",
]
