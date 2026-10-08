from pathlib import Path

import pytest

from wood_reports import (
    ChartReference,
    MarkdownReportCompiler,
    Narrative,
    PublicationTable,
    ReportCompiler,
    SourceCompilationError,
    get_profile,
    list_profiles,
    scaffold_markdown,
)


def authored_source(
    doc_type: str = "decision-memo", content: str = "Authored content."
) -> str:
    profile = get_profile(doc_type)
    headings = [
        section.title
        for section in profile.sections
        if section.identity in profile.required_section_variants[0]
    ]
    return (
        f"---\ndoc_type: {doc_type}\ndoc_name: internal-example\n"
        "title: Internal example\n---\n\n"
        + "\n\n".join(f"## {heading}\n\n{content}" for heading in headings)
    )


@pytest.mark.parametrize("doc_type", [profile.identity for profile in list_profiles()])
def test_all_initial_profiles_compile_deterministically(
    doc_type: str, tmp_path: Path
) -> None:
    source = tmp_path / "report.md"
    source.write_text(authored_source(doc_type), encoding="utf-8")
    compiler = ReportCompiler()
    first = compiler.compile_file(source)
    assert first == compiler.compile_file(source)
    assert first.metadata.doc_type == doc_type
    assert first.metadata.doc_name == "internal-example"
    assert first.metadata.profile_version == "1.0.0"
    assert (
        first.sections[0].semantic
        == get_profile(doc_type).required_section_variants[0][0]
    )


def test_compiles_the_approved_lighter_analytics_variant() -> None:
    text = "---\ndoc_type: analytics-report\ndoc_name: monthly-kpis\ntitle: KPIs\n---\n"
    headings = (
        "Executive Summary",
        "KPI Overview",
        "Key Findings",
        "Supporting Analysis",
        "Recommendations",
    )
    text += "\n".join(f"## {heading}\nContent.\n" for heading in headings)
    report = MarkdownReportCompiler().compile_text(text)
    assert [section.semantic for section in report.sections] == [
        "executive-summary",
        "key-metrics",
        "findings",
        "interpretation",
        "recommendations-or-implications",
    ]


def test_compiles_semantic_blocks_tables_charts_and_appendices(tmp_path: Path) -> None:
    (tmp_path / "trend.png").touch()
    text = (
        authored_source()
        + r"""

## Appendix

### Supporting data

- First point
- Second point

1. First action
2. Second action

| Metric | Value |
| :--- | ---: |
| Revenue | 100 |
| Escaped pipe | a\|b |

![Revenue trend](trend.png)

![Registered chart](chart:revenue-trend)

> [!RISK] Keep assumptions explicit.
>
> Include the underlying uncertainty.

```python
print("reproducible")
```
"""
    )
    report = MarkdownReportCompiler().compile_text(text, artifact_root=tmp_path)
    assert len(report.appendices) == 1
    blocks = report.appendices[0].content
    assert blocks[0] == Narrative("Supporting data", kind="heading", semantic="h3")
    assert isinstance(blocks[1], Narrative)
    assert blocks[1].semantic == "bullet"
    assert isinstance(blocks[2], Narrative)
    assert blocks[2].semantic == "ordered"
    table = blocks[3]
    assert isinstance(table, PublicationTable)
    assert table.columns[1].alignment == "right"
    assert table.rows == (("Revenue", "100"), ("Escaped pipe", "a|b"))
    assert blocks[4] == ChartReference(
        artifact=Path("trend.png"), caption="Revenue trend"
    )
    assert blocks[5] == ChartReference(
        identity="revenue-trend", caption="Registered chart"
    )
    assert isinstance(blocks[6], Narrative)
    assert blocks[6].semantic == "risk"
    assert isinstance(blocks[7], Narrative)
    assert blocks[7].kind == "code"


def test_metadata_and_precomputed_values_are_preserved() -> None:
    text = authored_source(content="Revenue: {{ revenue | presentation(',d') }}.")
    text = text.replace(
        "title: Internal example",
        """title: Internal example
client: Internal
project: Reporting
engagement: Quarterly review
author: Analyst
version: '1.2'
audience: Leadership
confidentiality: Internal
period: '2026-09'
comparison_period: '2026-08'""",
    )
    report = MarkdownReportCompiler({"revenue": 1200}).compile_text(text)
    assert report.metadata.client == "Internal"
    assert report.metadata.version == "1.2"
    assert report.metadata.period == "2026-09"
    assert report.metadata.comparison_period == "2026-08"
    assert report.sections[0].content == (Narrative("Revenue: 1,200."),)


@pytest.mark.parametrize(
    ("old", "new", "message"),
    [
        ("doc_name: internal-example", "doc_name: Invalid Name", "slug"),
        ("doc_type: decision-memo", "doc_type: unknown", "unsupported profile"),
        ("doc_name: internal-example\n", "", "doc_name"),
        ("title: Internal example", "title: ''", "title"),
        ("title: Internal example", "title: [One, Two]", "text keys and values"),
        ("title: Internal example", "title: [", "frontmatter"),
        ("title: Internal example", "title: Internal\ntitle: Duplicate", "duplicate"),
        (
            "title: Internal example",
            "title: Internal\nfont: Comic Sans",
            "unsupported fields",
        ),
        ("## Risks", "## Styling", "unrecognized"),
        ("## Risks", "## Decision", "duplicate semantic"),
        ("## Risks", "### Risks", "missing required"),
        ("Authored content.", "{% if revenue %}Yes{% endif %}", "named values"),
        ("Authored content.", "{{ missing }}", "template rendering failed"),
    ],
)
def test_invalid_sources_identify_source_and_failure(
    old: str, new: str, message: str
) -> None:
    source = Path("client/report.md")
    with pytest.raises(SourceCompilationError, match=message) as error:
        MarkdownReportCompiler().compile_text(
            authored_source().replace(old, new), source=source
        )
    assert error.value.source == source


@pytest.mark.parametrize(
    "text", ["No front matter", "---\nnot-closed", "---\n- item\n---\n"]
)
def test_missing_or_non_mapping_frontmatter_fails(text: str) -> None:
    with pytest.raises(SourceCompilationError, match="frontmatter"):
        MarkdownReportCompiler().compile_text(text)


@pytest.mark.parametrize(
    "content",
    [
        "---",
        "Text ![chart](chart:trend)",
        "> Not a semantic callout",
        "> [!UNKNOWN] Unsupported.",
        "> [!RISK] One\n> - Nested list",
        "![chart](chart:Invalid)",
        "![chart](https://example.com/chart.png)",
        "![chart](/tmp/chart.png)",
        "![chart](../chart.png)",
        "![chart]()",
        "![chart](missing.png)",
    ],
)
def test_unsupported_or_missing_content_fails_explicitly(content: str) -> None:
    with pytest.raises(SourceCompilationError):
        MarkdownReportCompiler().compile_text(authored_source(content=content))


def test_section_structure_cannot_be_injected_by_template_values() -> None:
    report = MarkdownReportCompiler({"text": "## Decision\nInjected"}).compile_text(
        authored_source(content="{{ text }}")
    )
    assert len(report.sections) == 6
    assert report.sections[0].content == (Narrative("## Decision\nInjected"),)


def test_crlf_and_bom_are_supported_without_consuming_body_rules() -> None:
    text = "\ufeff" + authored_source(
        content="Content.\n\n---\n\nMore content."
    ).replace("\n", "\r\n")
    with pytest.raises(SourceCompilationError, match="hr"):
        MarkdownReportCompiler().compile_text(text)
    report = MarkdownReportCompiler().compile_text(
        "\ufeff" + authored_source().replace("\n", "\r\n")
    )
    assert report.metadata.doc_name == "internal-example"


def test_scaffold_is_an_unfilled_authoring_source() -> None:
    text = scaffold_markdown("decision-memo", "new-decision")
    assert "doc_name: new-decision" in text
    with pytest.raises(SourceCompilationError, match="authored content"):
        MarkdownReportCompiler().compile_text(text)


def test_explicit_identity_overrides_have_precedence() -> None:
    report = MarkdownReportCompiler().compile_text(
        authored_source().replace("doc_type: decision-memo\n", ""),
        doc_type="decision-memo",
        doc_name="explicit-override",
    )
    assert report.metadata.doc_name == "explicit-override"


def test_local_source_errors_and_unsupported_suffix(tmp_path: Path) -> None:
    with pytest.raises(SourceCompilationError, match="source"):
        ReportCompiler().compile_file(tmp_path / "missing.md")
    with pytest.raises(SourceCompilationError, match="expected Markdown"):
        ReportCompiler().compile_file(tmp_path / "report.txt")


def test_content_before_sections_and_repeated_document_title_are_rejected() -> None:
    text = authored_source().replace(
        "## Executive Summary", "Before sections.\n## Executive Summary"
    )
    with pytest.raises(SourceCompilationError, match="profile section"):
        MarkdownReportCompiler().compile_text(text)
    with pytest.raises(SourceCompilationError, match="leading document title"):
        MarkdownReportCompiler().compile_text(authored_source() + "\n# Another title\n")
    report = MarkdownReportCompiler().compile_text(
        authored_source().replace(
            "## Executive Summary", "# Internal example\n\n## Executive Summary"
        )
    )
    assert report.metadata.title == "Internal example"


def test_blank_rendered_title_and_invalid_utf8_fail(tmp_path: Path) -> None:
    with pytest.raises(SourceCompilationError, match=r"metadata\.title"):
        MarkdownReportCompiler({"title": ""}).compile_text(
            authored_source().replace("title: Internal example", "title: '{{ title }}'")
        )
    source = tmp_path / "report.md"
    source.write_bytes(b"\xff")
    with pytest.raises(SourceCompilationError, match="source"):
        MarkdownReportCompiler().compile_file(source)


def test_legacy_yaml_is_explicit_and_does_not_change_existing_models(
    tmp_path: Path,
) -> None:
    source = tmp_path / "report.yaml"
    source.write_text(
        "metadata: {title: Existing}\n"
        "sections: [{title: Overview, content: [{narrative: Text}]}]\n",
        encoding="utf-8",
    )
    with pytest.warns(DeprecationWarning, match="legacy"):
        report = ReportCompiler().compile_file(source)
    assert report == ReportCompiler().compile_yaml_file(source)
    assert report.metadata.doc_type is None


def test_nested_lists_preserve_ordering_and_indentation() -> None:
    text = "1. Parent\n   - Child\n   - Another child\n2. Second parent"
    report = MarkdownReportCompiler().compile_text(authored_source(content=text))
    block = report.sections[0].content[0]
    assert isinstance(block, Narrative)
    assert block.kind == "list"
    assert block.text == text


@pytest.mark.parametrize(
    "content",
    [
        "| A | B |\n| --- | --- |\n| 1 | 2 | 3 |",
        "| A | B |\n| --- | --- |\n| 1 |",
        "- ![Missing chart](missing.png)",
        "> [!RISK] ![Missing chart](missing.png)",
    ],
)
def test_content_cannot_silently_drop_table_cells_or_chart_assets(content: str) -> None:
    with pytest.raises(
        SourceCompilationError, match=r"header width|standalone paragraph"
    ):
        MarkdownReportCompiler().compile_text(authored_source(content=content))


def test_complex_yaml_metadata_keys_fail_as_source_errors() -> None:
    text = authored_source().replace("title: Internal example", "[complex, key]: value")
    with pytest.raises(SourceCompilationError, match="scalar text"):
        MarkdownReportCompiler().compile_text(text)
