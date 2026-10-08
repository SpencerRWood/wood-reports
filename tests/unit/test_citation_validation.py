"""Navigation gates reject missing, misdirected and incomplete evidence links."""

from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import (
    ArrayObject,
    DictionaryObject,
    NameObject,
    NullObject,
    NumberObject,
    TextStringObject,
)

from wood_reports import BibliographySource, Narrative, Report, ReportMetadata, Section
from wood_reports.citation_validation import (
    validate_biber_processing,
    validate_citation_navigation,
)


def navigation_pdf(tmp_path: Path, omit: str = "") -> tuple[Report, Path]:
    writer = PdfWriter()
    for _ in range(2):
        writer.add_blank_page(width=600, height=800)
    if omit != "destination":
        writer.add_named_destination("cite.0@evidence", 1)
    writer.add_named_destination("page.1", 0)
    writer.add_named_destination("page.2", 1)
    if omit != "anchor":
        anchor = writer.add_named_destination("wood-citation.1@evidence", 0)
        page_reference = writer.pages[0].indirect_reference
        assert page_reference is not None
        anchor_dictionary = anchor.get_object()
        assert isinstance(anchor_dictionary, DictionaryObject)
        anchor_dictionary[NameObject("/D")] = ArrayObject(
            [
                page_reference,
                NameObject("/XYZ"),
                NumberObject(200 if omit == "anchor-position" else 10),
                NumberObject(610),
                NullObject(),
            ]
        )

    def link(page: int, destination: str, *, uri: bool = False) -> None:
        action = DictionaryObject(
            {
                NameObject("/S"): NameObject("/URI" if uri else "/GoTo"),
                NameObject("/URI" if uri else "/D"): TextStringObject(destination),
            }
        )
        writer.add_annotation(
            page,
            DictionaryObject(
                {
                    NameObject("/Subtype"): NameObject("/Link"),
                    NameObject("/Rect"): ArrayObject(
                        [NumberObject(n) for n in (10, 600, 100, 620)]
                    ),
                    NameObject("/A"): action,
                }
            ),
        )

    if omit != "inline":
        link(0, "cite.0@evidence")
    if omit != "url":
        link(1, "https://example.com/evidence", uri=True)
    if omit != "backref":
        link(1, "page.2" if omit == "incorrect-backref" else "page.1")
    if omit == "broken-reference":
        link(0, "section.missing")
    path = tmp_path / "navigation.pdf"
    writer.write(path)
    report = Report(
        ReportMetadata("Navigation"),
        (Section("Evidence", (Narrative("Evidence [@evidence]."),)),),
        bibliography=(
            BibliographySource(
                "evidence", "Evidence", "https://example.com/evidence", "Evidence"
            ),
        ),
    )
    return report, path


def test_citation_destinations_urls_and_per_entry_backrefs_are_verified(
    tmp_path: Path,
) -> None:
    report, pdf = navigation_pdf(tmp_path)
    result = validate_citation_navigation(report, pdf)
    result.require_passed()
    assert result.passed
    assert (
        result.entries
        == result.citation_occurrences
        == result.source_urls
        == result.back_references
        == 1
    )
    assert result.internal_links == 2
    assert result.occurrence_destinations == 1


@pytest.mark.parametrize(
    ("omit", "expected"),
    [
        ("destination", "missing bibliography destination"),
        ("inline", "missing inline citation occurrences"),
        ("url", "missing external source URLs"),
        ("backref", "incorrect citation page back-references"),
        ("incorrect-backref", "incorrect citation page back-references"),
        ("broken-reference", "broken internal destination"),
        ("anchor", "missing citation occurrence destinations"),
        ("anchor-position", "citation occurrence lacks its bibliography link"),
    ],
)
def test_incomplete_navigation_fails_closed(
    tmp_path: Path, omit: str, expected: str
) -> None:
    report, pdf = navigation_pdf(tmp_path, omit)
    result = validate_citation_navigation(report, pdf)
    assert not result.passed
    with pytest.raises(ValueError, match=expected):
        result.require_passed()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "INFO - This is BibTeX 0.99\nINFO - Output to output.bbl",
        "INFO - This is Biber 2.21\nERROR - failed",
        "INFO - This is Biber 2.21\nINFO - Output to output.bbl\nWARN - missing key",
    ],
)
def test_bibliography_processing_requires_clean_real_biber_evidence(
    tmp_path: Path, text: str
) -> None:
    path = tmp_path / "compiler.blg"
    path.write_text(text)
    with pytest.raises(ValueError, match="processing did not complete"):
        validate_biber_processing((path,))


def test_biber_version_and_completion_are_attested(tmp_path: Path) -> None:
    path = tmp_path / "compiler.blg"
    path.write_text("INFO - This is Biber 2.21\nINFO - Output to output.bbl\n")
    assert validate_biber_processing((path,)) == "2.21"
    with pytest.raises(ValueError, match="one retained biber log"):
        validate_biber_processing(())
