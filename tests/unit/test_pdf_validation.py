from dataclasses import replace
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from wood_reports import (
    CompilationResult,
    MarkdownReportCompiler,
    PDFValidationError,
    Report,
    scaffold_markdown,
    validate_pdf,
    validate_release_report,
)


def write_pdf(path: Path, *, blank: bool = False, encrypted: bool = False) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=100, height=100)
    if not blank:
        stream = DecodedStreamObject()
        stream.set_data(b"0 0 m 10 10 l S")
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("fixture-password")
    writer.write(path)


@pytest.fixture
def compilation(tmp_path: Path) -> CompilationResult:
    pdf = tmp_path / "report.pdf"
    write_pdf(pdf)
    log = tmp_path / "compiler.log"
    log.write_text("Compilation complete.\n")
    return CompilationResult(
        "success",
        "success",
        "project",
        "lualatex",
        pdf,
        (log,),
        tmp_path / "compilation.json",
        (),
    )


@pytest.fixture
def release_report() -> Report:
    text = scaffold_markdown("decision-memo", "release-example").replace(
        "title: Release Example", 'title: Release Example\nversion: "1.0.0"'
    )
    text = "\n".join(
        line + "\n\nCompleted internal content." if line.startswith("## ") else line
        for line in text.splitlines()
    )
    return MarkdownReportCompiler().compile_text(text)


def test_pdf_validation_is_deterministic(compilation: CompilationResult) -> None:
    first = validate_pdf(compilation)
    assert first == validate_pdf(compilation)
    assert first.passed
    assert first.pages == 1
    assert first.pdf_sha256 is not None
    assert first.compilation_succeeded is True
    assert first.structural_validation_passed is True
    assert first.visual_acceptance == "not-assessed"


def test_ignored_glue_error_fails_gate(compilation: CompilationResult) -> None:
    compilation.logs[0].write_text(
        "ignored error Infinite glue shrinkage found in box being split\n" * 5
    )
    result = validate_pdf(compilation)
    assert result.compilation_succeeded
    assert not result.structural_validation_passed
    assert result.compiler_diagnostics[0].occurrence_count == 5


def test_typographic_warnings_remain_visible(compilation: CompilationResult) -> None:
    compilation.logs[0].write_text(
        "Underfull \\hbox (badness 6641) in paragraph at lines 13--14\n"
        "Overfull \\hbox (2pt too wide)\n"
    )
    result = validate_pdf(compilation)
    assert result.passed
    assert {d.category for d in result.compiler_diagnostics} == {
        "underfull-box",
        "overfull-box",
    }


@pytest.mark.parametrize(
    "diagnostic",
    [
        "LaTeX Warning: Reference `x' undefined.",
        "LaTeX Warning: Citation `x' undefined.",
        "There were undefined references.",
        "There were undefined citations.",
        "! LaTeX Error: File `x' not found.",
        "Missing character: There is no X in font.",
        "Overfull \\hbox (5.01pt too wide)",
        "Overfull \\vbox (8pt too high)",
        "Fatal error occurred",
    ],
)
def test_strict_log_gates(compilation: CompilationResult, diagnostic: str) -> None:
    compilation.logs[0].write_text(diagnostic)
    result = validate_pdf(compilation)
    assert not result.passed
    with pytest.raises(PDFValidationError) as error:
        result.require_passed()
    assert error.value.result == result


def test_cosmetic_warnings_and_urls_are_allowed(
    compilation: CompilationResult, release_report: Report, tmp_path: Path
) -> None:
    compilation.logs[0].write_text(
        "Underfull \\hbox\nOverfull \\hbox (5.0pt too wide)\n"
    )
    assert validate_pdf(compilation).passed
    report = replace(
        release_report,
        metadata=replace(
            release_report.metadata, source="https://example.com/evidence"
        ),
    )
    assert validate_release_report(report, artifact_root=tmp_path).passed


@pytest.mark.parametrize(
    "pdf_bytes", [b"", b"%PDF-1.5", b"%PDF-1.5\ninvalid\n%%EOF", b"not a PDF"]
)
def test_malformed_pdfs_are_rejected(
    compilation: CompilationResult, pdf_bytes: bytes
) -> None:
    assert compilation.pdf is not None
    compilation.pdf.write_bytes(pdf_bytes)
    assert "pdf-invalid" in {issue.code for issue in validate_pdf(compilation).issues}


@pytest.mark.parametrize("encrypted", [False, True])
def test_empty_or_encrypted_pdf_rejected(
    compilation: CompilationResult, encrypted: bool
) -> None:
    assert compilation.pdf is not None
    write_pdf(compilation.pdf, blank=not encrypted, encrypted=encrypted)
    assert not validate_pdf(compilation).passed


def test_missing_logs_and_failed_compilation(compilation: CompilationResult) -> None:
    failed = replace(
        compilation,
        status="failed",
        compiler_status="error",
        pdf=None,
        logs=(),
        diagnostics=("failed",),
    )
    assert {issue.code for issue in validate_pdf(failed).issues} == {
        "compile-failed",
        "compile-diagnostics",
        "log-missing",
        "pdf-invalid",
    }
    compilation.logs[0].unlink()
    assert not validate_pdf(compilation).passed
    with pytest.raises(ValueError, match="overfull_limit"):
        validate_pdf(compilation, overfull_limit_pt=-1)


def test_symlink_evidence_rejected(
    compilation: CompilationResult, tmp_path: Path
) -> None:
    link = tmp_path / "linked.log"
    link.symlink_to(compilation.logs[0])
    assert not validate_pdf(replace(compilation, logs=(link,))).passed
    assert compilation.pdf is not None
    pdf_link = tmp_path / "linked.pdf"
    pdf_link.symlink_to(compilation.pdf)
    assert not validate_pdf(replace(compilation, pdf=pdf_link)).passed


@pytest.mark.parametrize(
    "text",
    [
        "TODO: finish this",
        "TBD",
        "{{ unresolved }}",
        "/Users/example/private.md",
        "/home/example/data",
        r"C:\Users\example\report",
    ],
)
def test_placeholders_and_machine_local_paths_rejected(
    release_report: Report, tmp_path: Path, text: str
) -> None:
    report = replace(
        release_report, metadata=replace(release_report.metadata, subtitle=text)
    )
    first = validate_release_report(report, artifact_root=tmp_path)
    assert not first.passed
    assert first == validate_release_report(report, artifact_root=tmp_path)


def test_release_requires_profile_version_sections_and_report_version(
    release_report: Report, tmp_path: Path
) -> None:
    for report in (
        replace(release_report, sections=release_report.sections[:1]),
        replace(
            release_report, metadata=replace(release_report.metadata, version=None)
        ),
        replace(
            release_report,
            metadata=replace(release_report.metadata, profile_version="old"),
        ),
    ):
        assert not validate_release_report(report, artifact_root=tmp_path).passed
