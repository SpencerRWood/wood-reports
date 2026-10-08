"""Real architecture publication with biber, links, provenance and immutable bytes."""

import hashlib
import json
import os
import re
from pathlib import Path

import pytest
from pypdf import PdfReader

from wood_reports import (
    CLSICompiler,
    PublicationTable,
    ReleasePublisher,
    ReportCompiler,
)
from wood_reports.citation_validation import validate_citation_navigation
from wood_reports.diagrams import ArchitectureDiagram, diagram_panels, parse_flowchart
from wood_reports.primitives import text_runs


def _contains_typeset_text(extracted: str, authored: str) -> bool:
    """Allow line-end hyphenation while retaining authored punctuation."""
    line_break = "\x00"
    extracted = re.sub(r"-[ \t]*\n", line_break, extracted)
    compact = re.sub(r"\s+", "", extracted)
    characters = (
        f"[-{line_break}]" if character == "-" else re.escape(character)
        for character in re.sub(r"\s+", "", authored)
    )
    pattern = f"{line_break}?".join(characters)
    return re.search(pattern, compact) is not None


@pytest.mark.parametrize("backend", [55], indirect=True)
def test_architecture_overview_live_biber_publication(
    backend: CLSICompiler, tmp_path: Path
) -> None:
    source = Path("examples/architecture/overview.md")
    report = ReportCompiler().compile_file(source)
    output = Path(
        os.environ.get("WOOD_REPORTS_ARCHITECTURE_OUTPUT", str(tmp_path / "releases"))
    )
    result = ReleasePublisher().publish(
        report,
        output,
        compiler=backend,
        artifact_root=source.parent,
        source_identity=(
            "Architecture Docs canonical Markdown "
            "sha256:7ca52fe2afc804b0627fc67144b2d2682956d68306fa7ac4f5176bc0bec30f83"
        ),
        build_epoch=1791489600,
    )
    assert result.validation.passed
    citations = validate_citation_navigation(report, result.pdf)
    citations.require_passed()
    assert citations.entries == 71
    assert citations.citation_occurrences == 95
    assert citations.occurrence_destinations == 95
    assert citations.source_urls == 70
    assert citations.back_references >= 71
    logs = list((result.directory / "compilation").glob("*.blg"))
    assert logs
    assert re.search(r"INFO - This is Biber \d+\.\d+", logs[0].read_text())
    assert not re.search(r"(?:ERROR|WARN) -", logs[0].read_text())
    reader = PdfReader(result.pdf)
    text = "\n".join(page.extract_text() for page in reader.pages)
    for section in report.sections:
        for item in section.content:
            if isinstance(item, ArchitectureDiagram):
                graph = parse_flowchart(item.source)
                assert len(graph.nodes) == len(graph.edges) == 37
                assert len(diagram_panels(graph)) == 6
                for node in graph.nodes:
                    assert _contains_typeset_text(text, node.label)
            elif isinstance(item, PublicationTable):
                for row in item.rows:
                    for cell in row[:3]:
                        if isinstance(cell, str):
                            plain = "".join(run.text for run in text_runs(cell))
                            assert _contains_typeset_text(text, plain)
    assert sum(page.get("/Rotate", 0) == 90 for page in reader.pages) == 6
    for prefix, expected in (("figure.", 6), ("table.", 4), ("section.", 5)):
        targets = {
            str(annotation.get_object().get("/A", {}).get("/D", ""))
            for page in reader.pages
            for annotation in page.get("/Annots", [])
        }
        assert (
            len({target for target in targets if target.startswith(prefix)}) >= expected
        )
    workspace = result.directory / "source/workspace/generated"
    rendered = (workspace / "report.tex").read_text()
    assert (
        sum(
            len(keys.split(","))
            for keys in re.findall(r"\\woodcite\{([^}]+)\}", rendered)
        )
        == 95
    )
    manifest = json.loads(result.manifest.read_text())
    assert manifest["bibliography"]["navigation"] == "validated"
    for relative, expected_hash in manifest["artifacts"].items():
        assert (
            hashlib.sha256((result.directory / relative).read_bytes()).hexdigest()
            == expected_hash
        )
