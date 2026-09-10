"""Reusable publication primitives for analytical reports."""

from wood_reports.compiler import ReportCompiler, SourceCompilationError
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

__all__ = [
    "Appendix",
    "ChartGenerationContext",
    "ChartReference",
    "ChartResolutionError",
    "Finding",
    "Narrative",
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
