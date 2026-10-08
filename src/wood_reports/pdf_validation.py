"""Deterministic release gates for semantic reports, compiler evidence, and PDFs."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from pypdf import PdfReader

from wood_reports.compilation import CompilationResult
from wood_reports.model import Report
from wood_reports.profiles import get_profile
from wood_reports.tex_diagnostics import (
    CompilerDiagnostic,
    DiagnosticContext,
    parse_tex_diagnostics,
)

_PLACEHOLDER = re.compile(r"\b(?:TODO|TBD|FIXME|PLACEHOLDER)\b|\{\{.+?\}\}", re.I)
_LOCAL_PATH = re.compile(r"/(?:Users|home|private|tmp)/|(?<![A-Za-z])[A-Za-z]:[\\/]")
_LOG_FAILURE = re.compile(
    r"undefined references|undefined citations|(?:Reference|Citation).+undefined"
    r"|File .+not found|file .+not found|not found:|Missing character:"
    r"|^! |Fatal error occurred|Latexmk: Errors, so",
    re.I | re.M,
)
_OVERFULL = re.compile(r"Overfull \\[hv]box \(([\d.]+)pt too (?:wide|high)\)")


@dataclass(frozen=True, slots=True, order=True)
class ValidationIssue:
    code: str
    location: str
    message: str


@dataclass(frozen=True, slots=True)
class PDFValidationResult:
    issues: tuple[ValidationIssue, ...]
    pdf_sha256: str | None = None
    pages: int = 0
    compiler_diagnostics: tuple[CompilerDiagnostic, ...] = ()
    compilation_succeeded: bool | None = None
    visual_acceptance: str = "not-assessed"

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def structural_validation_passed(self) -> bool:
        return self.passed

    def require_passed(self) -> None:
        if not self.passed:
            raise PDFValidationError(self)


class PDFValidationError(ValueError):
    def __init__(self, result: PDFValidationResult) -> None:
        self.result = result
        super().__init__(
            "; ".join(f"{issue.code}: {issue.message}" for issue in result.issues)
        )


def _strings(value: object, location: str = "report") -> list[tuple[str, str]]:
    if isinstance(value, str):
        return [(location, value)]
    if isinstance(value, dict):
        return [
            item
            for key, child in value.items()
            for item in _strings(child, f"{location}.{key}")
        ]
    if isinstance(value, (tuple, list)):
        return [
            item
            for index, child in enumerate(value)
            for item in _strings(child, f"{location}[{index}]")
        ]
    return []


def validate_release_report(
    report: Report, *, artifact_root: Path
) -> PDFValidationResult:
    """Apply profile, asset, placeholder, and portability gates before compilation."""
    issues: list[ValidationIssue] = []
    try:
        report.validate(artifact_root)
        metadata = report.metadata
        profile = get_profile(metadata.doc_type or "")
        fields = {
            key: value
            for key, value in asdict(metadata).items()
            if isinstance(value, str) and key != "profile_version"
        }
        profile.validate_instance(
            fields,
            tuple(
                profile.section(section.title).identity for section in report.sections
            ),
        )
        for appendix in report.appendices:
            profile.section(appendix.title)
        if metadata.profile_version != profile.version:
            raise ValueError("report profile_version must match the installed profile")
        if not metadata.version:
            raise ValueError("report version is required for release")
    except ValueError as error:
        issues.append(ValidationIssue("report-invalid", "report", str(error)))
    for location, text in _strings(asdict(report)):
        if _PLACEHOLDER.search(text):
            issues.append(
                ValidationIssue(
                    "placeholder", location, "unresolved authoring placeholder"
                )
            )
        if _LOCAL_PATH.search(text):
            issues.append(
                ValidationIssue(
                    "local-path", location, "machine-local path in publication content"
                )
            )
    return PDFValidationResult(tuple(sorted(set(issues))))


def validate_pdf(  # noqa: PLR0912, PLR0915
    compilation: CompilationResult,
    *,
    overfull_limit_pt: float = 5.0,
    underfull_badness: int = 1000,
) -> PDFValidationResult:
    """Check compile evidence, TeX diagnostics, and the complete PDF structure.

    Cosmetic underfull boxes and overfull boxes up to five points are allowed.
    This validates structural readability, not visual design or PDF/A compliance.
    """
    if not 0 <= overfull_limit_pt <= 100:
        raise ValueError("overfull_limit_pt must be between 0 and 100")
    issues: list[ValidationIssue] = []
    diagnostics: list[CompilerDiagnostic] = []
    # stdout usually repeats the TeX log; classify the .log authority once.
    parse_tex_diagnostics("", underfull_badness=underfull_badness)
    if compilation.status != "success" or compilation.compiler_status != "success":
        diagnostics.append(
            CompilerDiagnostic(
                "compilation-failure",
                "error",
                1,
                "compilation",
                (DiagnosticContext(0, "compiler did not succeed"),),
            )
        )
        issues.append(
            ValidationIssue("compile-failed", "compilation", "compiler did not succeed")
        )
    if compilation.diagnostics:
        issues.append(
            ValidationIssue(
                "compile-diagnostics",
                "compilation",
                "compiler returned failure diagnostics",
            )
        )
    if not any(log.suffix == ".log" for log in compilation.logs):
        issues.append(
            ValidationIssue("log-missing", "compilation", "TeX log is required")
        )
    for index, log in enumerate(compilation.logs):
        location = f"logs[{index}]"
        try:
            if log.is_symlink():
                raise ValueError("compiler log cannot be a symlink")
            text = log.read_text(encoding="utf-8", errors="replace")
        except OSError, ValueError:
            issues.append(
                ValidationIssue("log-missing", location, "compiler log cannot be read")
            )
            continue
        if log.suffix == ".log":
            extracted = parse_tex_diagnostics(
                text, log=location, underfull_badness=underfull_badness
            )
            diagnostics.extend(extracted)
            for diagnostic in extracted:
                if diagnostic.severity == "error":
                    issues.append(
                        ValidationIssue(
                            diagnostic.category,
                            location,
                            diagnostic.contexts[0].message,
                        )
                    )
        if _LOG_FAILURE.search(text):
            issues.append(
                ValidationIssue(
                    "tex-unresolved",
                    location,
                    "TeX reports errors or unresolved files, references, citations, "
                    "glyphs",
                )
            )
        if any(
            float(match[1]) > overfull_limit_pt for match in _OVERFULL.finditer(text)
        ):
            issues.append(
                ValidationIssue("tex-overfull", location, "materially overfull TeX box")
            )
    digest = None
    pages = 0
    try:
        pdf = compilation.pdf
        if pdf is None or pdf.is_symlink():
            raise ValueError("PDF is missing or a symlink")
        content = pdf.read_bytes()
        if not content.startswith(b"%PDF-") or not content.rstrip().endswith(b"%%EOF"):
            raise ValueError("PDF is empty, truncated, or lacks its header/trailer")
        digest = hashlib.sha256(content).hexdigest()
        reader = PdfReader(pdf, strict=True)
        if reader.is_encrypted:
            raise ValueError("encrypted PDF cannot be validated for release")
        pages = len(reader.pages)
        contents = [page.get_contents() for page in reader.pages]
        if not pages or not any(
            stream is not None and stream.get_data().strip() for stream in contents
        ):
            raise ValueError("PDF contains no publication content")
        # Decode every stream, including later pages, before accepting the PDF.
        for stream in contents:
            if stream is not None:
                stream.get_data()
        for index, page in enumerate(reader.pages):
            text = page.extract_text()
            if _PLACEHOLDER.search(text):
                issues.append(
                    ValidationIssue(
                        "placeholder",
                        f"pdf.pages[{index}]",
                        "unresolved placeholder in PDF text",
                    )
                )
            if _LOCAL_PATH.search(text):
                issues.append(
                    ValidationIssue(
                        "local-path",
                        f"pdf.pages[{index}]",
                        "machine-local path in PDF text",
                    )
                )
    except Exception:
        issues.append(
            ValidationIssue(
                "pdf-invalid",
                "pdf",
                "PDF is missing, malformed, encrypted, truncated, or empty",
            )
        )
    return PDFValidationResult(
        tuple(sorted(set(issues))),
        digest,
        pages,
        tuple(diagnostics),
        compilation.status == "success" and compilation.compiler_status == "success",
    )
