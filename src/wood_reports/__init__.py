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

__all__ = [
    "Appendix",
    "ChartGenerationContext",
    "ChartReference",
    "ChartResolutionError",
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
    "ReportValidationError",
    "Section",
    "SourceCompilationError",
    "TableColumn",
]
