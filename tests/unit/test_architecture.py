"""Architecture facts and provenance survive the native publication boundary."""

import hashlib
import json
import re
from collections import Counter
from dataclasses import replace
from pathlib import Path

import pytest

from wood_reports import (
    ArchitectureDiagram,
    BibliographySource,
    LatexRenderer,
    LatexWorkspacePublisher,
    MarkdownReportCompiler,
    Narrative,
    PublicationTable,
    ReportCompiler,
    SourceCompilationError,
    get_profile,
    scaffold_markdown,
    validate_release_report,
)
from wood_reports.citations import (
    bibliography_text,
    citation_inline,
    citation_keys,
    deduplicate,
    footnote_sources,
    structured_sources,
)
from wood_reports.clsi_workspace import read_workspace
from wood_reports.diagrams import diagram_panels, parse_flowchart, vector_panel
from wood_reports.tex_diagnostics import diagnostic_log_text, parse_tex_diagnostics

SOURCE = Path("examples/architecture/overview.md")


def test_canonical_overview_content_and_all_source_mappings_are_preserved() -> None:
    source = SOURCE.read_text()
    original = source.split("---\n", 2)[2].lstrip("\n")
    assert hashlib.sha256(original.encode()).hexdigest() == (
        "7ca52fe2afc804b0627fc67144b2d2682956d68306fa7ac4f5176bc0bec30f83"
    )
    report = ReportCompiler().compile_file(SOURCE)
    assert report == ReportCompiler().compile_file(SOURCE)
    assert report.metadata.doc_type == "technical-architecture"
    assert report.theme.brand_identity == "wood-analytics"
    tables = [
        item
        for section in report.sections
        for item in section.content
        if isinstance(item, PublicationTable)
    ]
    assert [len(table.rows) for table in tables] == [1, 43, 37, 1]
    diagram = next(
        item
        for section in report.sections
        for item in section.content
        if isinstance(item, ArchitectureDiagram)
    )
    graph = parse_flowchart(diagram.source)
    assert len(graph.nodes) == 37
    assert len(graph.edges) == 37
    assert len(diagram_panels(graph)) == 6
    assert Counter(edge.label.replace(" ", "_") for edge in graph.edges) == Counter(
        {"contains": 9, "depends_on": 25, "orchestrates": 1, "uses_storage": 2}
    )
    diagram_source = re.search(r"```mermaid\n(.*?)\n```", original, re.S)
    assert diagram_source is not None
    assert diagram.source == diagram_source[1]
    definitions = re.findall(r"^\[\^(\d+)\]:", original, re.M)
    assert len(report.bibliography) == len(definitions) == 71
    assert {alias for entry in report.bibliography for alias in entry.aliases} == set(
        definitions
    )
    before = Counter(re.findall(r"\[\^(\d+)\](?!:)", original))
    after = Counter(
        key for text in report.citation_texts() for key in citation_keys(text)
    )
    assert before == after
    assert sum(after.values()) == 95
    assert {entry.url for entry in report.bibliography if entry.url} == set(
        re.findall(r"\]\((https?://[^)]+)\)", original)
    )
    assert validate_release_report(report, artifact_root=SOURCE.parent).passed


def test_uncommitted_and_unpinned_evidence_is_never_presented_as_pinned() -> None:
    report = ReportCompiler().compile_file(SOURCE)
    local = report.bibliography[-1]
    assert local.aliases == ("71",)
    assert local.revision == "uncommitted"
    assert local.evidence_state == "verified; uncommitted"
    assert local.url == ""
    assert local.path == "architecture.toml"
    assert local.observed_at == "not provided"
    assert "no pinned revision" in local.limitations
    _, sources = footnote_sources(
        "[^mutable]: [File](https://github.com/org/repo/blob/main/file.yml); stale."
    )
    assert sources[0].revision == "main"
    assert "Unpinned" in sources[0].limitations
    assert sources[0].evidence_state == "stale"


def test_native_workspace_declares_independent_versions_and_biber_sequence(
    tmp_path: Path,
) -> None:
    report = ReportCompiler().compile_file(SOURCE)
    entrypoint = LatexWorkspacePublisher().publish(
        report, tmp_path, artifact_root=SOURCE.parent
    )
    manifest = json.loads((entrypoint.parent / "workspace.json").read_text())
    assert manifest["brand"]["revision"] == report.theme.brand_revision
    assert manifest["profile"] == {
        "identity": "technical-architecture",
        "version": "1.0.0",
    }
    assert manifest["diagrams"]["version"] == "1.0.0"
    assert manifest["bibliography"]["sequence"] == [
        "lualatex",
        "biber",
        "lualatex",
        "lualatex",
    ]
    assert manifest["build"]["argv"][0] == "latexmk"
    assert (entrypoint.parent / "sources.bib").read_text().count("@online{") == 71
    assert (entrypoint.parent / "assets/diagram-1.mmd").is_file()
    inputs = read_workspace(tmp_path, {})
    assert inputs.flags == ("-r", "generated/latexmkrc")
    aliases = {
        name: entry.key
        for entry in report.bibliography
        for name in (entry.key, *entry.aliases)
    }
    expected_keys = Counter(
        aliases[key] for text in report.citation_texts() for key in citation_keys(text)
    )
    actual_keys = Counter(
        key
        for group in re.findall(r"\\woodcite\{([^}]+)\}", entrypoint.read_text())
        for key in group.split(",")
    )
    assert actual_keys == expected_keys
    assert (
        sum(
            len(group.split(","))
            for group in re.findall(r"\\woodcite\{([^}]+)\}", entrypoint.read_text())
        )
        == 95
    )
    assert (
        r"\usetikzlibrary{arrows.meta}"
        in (entrypoint.parent / "components.tex").read_text()
    )


@pytest.mark.parametrize(
    "profile",
    [
        "project-brief",
        "analytics-report",
        "assessment-report",
        "decision-memo",
        "technical-architecture",
    ],
)
def test_shared_structured_citations_work_in_every_profile(
    profile: str, tmp_path: Path
) -> None:
    text = scaffold_markdown(profile, "citation-example")
    text = text.replace(
        "title: Citation Example",
        "title: Citation Example\nreferences:\n  - id: source-key\n"
        "    title: Descriptive source\n    URL: https://example.com/source\n"
        "    revision: abc1234\n    evidence-state: verified\n"
        "    observation-timestamp: '2026-10-08T12:00:00Z'\n"
        "    note: Declared evidence only",
    )
    text = "\n".join(
        line + "\n\n**Evidence [@source-key].**" if line.startswith("## ") else line
        for line in text.splitlines()
    )
    report = MarkdownReportCompiler().compile_text(text)
    assert report.bibliography[0].observed_at == "2026-10-08T12:00:00Z"
    latex = (
        LatexRenderer()
        .render(report, tmp_path / "report.tex", artifact_root=tmp_path)
        .read_text()
    )
    assert r"\textbf{Evidence \woodcite{source-key}.}" in latex
    assert "backend=biber" in latex
    assert "abc1234" in bibliography_text(report.bibliography)
    assert latex.count(r"\woodcite{source-key}") == len(
        get_profile(profile).required_section_variants[0]
    )


def test_deduplication_preserves_occurrences_aliases_and_distinct_revisions() -> None:
    first = BibliographySource(
        "source-a",
        "First",
        "https://example.com/file",
        "Readable",
        revision="abc",
        aliases=("1",),
    )
    duplicate = replace(first, key="source-b", aliases=("2",))
    sources = deduplicate(
        (
            first,
            duplicate,
            replace(first, key="source-c", revision="def", aliases=("3",)),
        )
    )
    assert len(sources) == 2
    assert sources[0].aliases == ("1", "source-b", "2")
    assert (
        citation_inline("[^1] [^2] [@source-b; @source-c]", sources).count("source-a")
        == 3
    )
    assert deduplicate((first, replace(first, aliases=("2",))))[0].aliases == ("1", "2")
    with pytest.raises(ValueError, match="conflicting provenance"):
        deduplicate((first, replace(duplicate, evidence_state="stale")))
    with pytest.raises(ValueError, match="duplicate bibliography"):
        deduplicate((first, first))


@pytest.mark.parametrize(
    "value", ["[@missing]", "[^missing]", "[@source, p. 12]", "[@source malformed]"]
)
def test_unresolved_and_unsupported_citations_fail_explicitly(value: str) -> None:
    with pytest.raises(ValueError, match="citation"):
        citation_inline(value, ())


def test_literal_code_is_not_interpreted_as_a_citation() -> None:
    assert citation_keys("Literal `[@not-a-citation]`.") == ()
    assert r"\texttt{[@x]}" in citation_inline("`[@x]`", ())


@pytest.mark.parametrize(
    "value",
    [
        {},
        [{"id": "only-id"}],
        [{"id": "x", "title": "T", "URL": "https://example.com", "unknown": "x"}],
        "not-a-list",
    ],
)
def test_invalid_structured_metadata_fails_without_losing_fields(value: object) -> None:
    with pytest.raises(ValueError, match="references"):
        structured_sources(value)


@pytest.mark.parametrize(
    "url",
    [
        "file:///private/test",
        "https://user:password@example.com",
        "https://example.com/{unsafe}",
        "https://example.com/\\input",
    ],
)
def test_bibliography_urls_cannot_inject_tex_or_credentials(url: str) -> None:
    with pytest.raises(ValueError, match="safe external URL"):
        BibliographySource("source", "Title", url, "Label").validate()


@pytest.mark.parametrize(
    "diagram",
    [
        "sequenceDiagram\nA->>B: unsupported",
        'flowchart LR\na["A"]\na -->|"uses"| missing',
        'flowchart LR\na["A"]\na["Duplicate"]',
        'flowchart LR\na["A"]\nstyle a fill:red',
        'flowchart LR\nsubgraph estate["Estate"]\na["A"]',
        "flowchart LR\nend",
    ],
)
def test_unsupported_or_incomplete_diagrams_fail_explicitly(diagram: str) -> None:
    with pytest.raises(ValueError, match=r"diagram|Mermaid"):
        parse_flowchart(diagram)


def test_boundaries_uncertainty_legends_and_direction_survive_vector_rendering() -> (
    None
):
    graph = parse_flowchart(
        'flowchart RL\nsubgraph estate["Runtime boundary"]\n'
        'a["Context"]\nb["Deployment"]\nend\n'
        'a -.->|"declared relationship"| b\n'
        "%% legend: Deployment health unverified"
    )
    assert graph.direction == "RL"
    assert graph.nodes[0].boundary == "Runtime boundary"
    assert graph.edges[0].uncertain
    assert graph.legends == ("Deployment health unverified",)
    latex = vector_panel(graph, diagram_panels(graph)[0])
    assert "Boundary: Runtime boundary" in latex
    assert r"\draw[dashed,->" in latex
    assert "declared relationship" in latex


def test_nested_heading_navigation_appendices_and_landscape_are_native(
    tmp_path: Path,
) -> None:
    source = (
        "---\ndoc_type: technical-architecture\ndoc_name: native\ntitle: Native\n"
        "page_layout: landscape\ntoc: 'true'\n---\n## Summary\nAuthored context.\n"
        "### Components\n[Summary](#summary).\n"
        "#### Dependencies\nDirected relationships.\n"
        "##### Orchestration\nSource-owned.\n###### Deployment\nDeclared only.\n"
        "## Source provenance\nAuthored provenance.\n## Appendix\nTechnical appendix."
    )
    report = MarkdownReportCompiler().compile_text(source)
    text = (
        LatexRenderer()
        .render(report, tmp_path / "report.tex", artifact_root=tmp_path)
        .read_text()
    )
    assert r"\subsection{Components}" in text
    assert r"\subsubsection{Dependencies}" in text
    assert r"\paragraph{Orchestration}" in text
    assert r"\subparagraph{Deployment}" in text
    assert r"\hyperref[summary]{Summary}" in text
    assert r"\appendix" in text
    assert text.count(r"\begin{landscape}") == text.count(r"\end{landscape}") == 1


@pytest.mark.parametrize("option", ["toc: yes", "page_layout: diagonal"])
def test_invalid_architecture_composition_fails(option: str) -> None:
    text = scaffold_markdown("technical-architecture", "invalid").replace(
        "title: Invalid", f"title: Invalid\n{option}"
    )
    text = "\n".join(
        line + "\nAuthored content." if line.startswith("## ") else line
        for line in text.splitlines()
    )
    with pytest.raises(SourceCompilationError, match=r"frontmatter|profile"):
        MarkdownReportCompiler().compile_text(text)


def test_optional_biblatex_probes_keep_real_missing_asset_failures() -> None:
    optional = (
        "Package biblatex Info: ... file 'authortitle.dbx' not found.\n"
        "Package biblatex Info: ... file 'biblatex-dm.cfg' not found.\n"
    )
    assert diagnostic_log_text(optional) == "\n\n"
    assert parse_tex_diagnostics(optional) == ()
    required = "! LaTeX Error: File 'required.bib' not found."
    assert any(
        item.category == "missing-asset" for item in parse_tex_diagnostics(required)
    )


def test_source_semantics_are_distinct_from_assessment_sections() -> None:
    profile = get_profile("technical-architecture")
    assert (
        profile.section("Repositories and major system boundaries").identity
        == "repositories-and-major-system-boundaries"
    )
    assert profile.required_section_variants == (("summary", "source-provenance"),)
    assert "diagram" in profile.permitted_content
    assert Narrative("Authored source").kind == "prose"


def test_authored_ids_figures_tables_and_repeated_headings_resolve(
    tmp_path: Path,
) -> None:
    source = (
        "---\ndoc_type: technical-architecture\ndoc_name: identified\n"
        "title: Identified\n---\n"
        "## Summary {#scope}\n[Context](#fig:context), [Inventory](#tbl:inventory), "
        "[Evidence](#evidence), [Components](#components-a).\n"
        "### Components {#components-a}\nFirst view.\n"
        "### Components {#components-b}\nSecond view.\n"
        "## Runtime view {#runtime-a}\n```{.mermaid #fig:context}\nflowchart LR\n"
        'a["Context"]\nb["Component"]\na -->|"depends on"| b\n```\n'
        "| Name | Meaning |\n| --- | --- |\n| Component | Source-owned |\n\n"
        "Table: Component inventory {#tbl:inventory}\n"
        "## Runtime view {#runtime-b}\nA second authored view.\n"
        "## Source provenance {#evidence}\nDeclared evidence only.\n"
    )
    report = MarkdownReportCompiler().compile_text(source)
    text = (
        LatexRenderer()
        .render(report, tmp_path / "report.tex", artifact_root=tmp_path)
        .read_text()
    )
    for label in (
        "scope",
        "fig:context",
        "tbl:inventory",
        "components-a",
        "components-b",
        "runtime-a",
        "runtime-b",
        "evidence",
    ):
        assert f"\\label{{{label}}}" in text
    assert "Component inventory" in text
    assert r"\hyperref[fig:context]{Context}" in text
    assert "Table: Component inventory" not in text
