from pathlib import Path

import pytest

from wood_reports import (
    ChartReference,
    Finding,
    PublicationTable,
    ReportCompiler,
    SourceCompilationError,
)


def write_sources(tmp_path: Path) -> Path:
    chart = tmp_path / "artifacts" / "trend.png"
    chart.parent.mkdir()
    chart.touch()
    (tmp_path / "findings").mkdir()
    (tmp_path / "findings" / "growth.md").write_text(
        """---
identity: revenue-growth
title: Revenue increased
severity: info
renderer_hints:
  style: highlight
---
Revenue reached {{ revenue | presentation(",.0f") }} this period.
""",
        encoding="utf-8",
    )
    report = tmp_path / "report.yaml"
    report.write_text(
        """metadata:
  title: Monthly report
  author: Wood Analytics
renderer_hints:
  theme: executive
sections:
  - title: Overview
    content:
      - narrative: Revenue performance summary.
      - chart:
          artifact: artifacts/trend.png
          caption: Revenue trend
      - table:
          columns:
            - identity: month
              label: Month
            - identity: revenue
              label: Revenue
              alignment: right
              format: currency
          rows:
            - [January, 1000]
          caption: Monthly revenue
          notes: [Unaudited]
findings:
  - source: findings/growth.md
appendices:
  - title: Notes
    content:
      - narrative: Definitions and source notes.
""",
        encoding="utf-8",
    )
    return report


def test_compiles_yaml_and_markdown_into_the_public_domain_model(
    tmp_path: Path,
) -> None:
    report = ReportCompiler({"revenue": 1234.5}).compile_file(write_sources(tmp_path))

    assert report.metadata.title == "Monthly report"
    assert isinstance(report.sections[0].content[1], ChartReference)
    assert isinstance(report.sections[0].content[2], PublicationTable)
    assert report.sections[0].content[2].columns[1].alignment == "right"
    assert isinstance(report.findings[0], Finding)
    assert report.findings[0].narrative.text == "Revenue reached 1,234 this period."
    assert report.appendices[0].title == "Notes"


def test_compiles_finding_semantics_and_shared_chart_visual(tmp_path: Path) -> None:
    chart = tmp_path / "chart.png"
    chart.touch()
    (tmp_path / "finding.md").write_text(
        "---\nidentity: weekday-sessions\ntitle: Weekend traffic falls\n"
        "subtitle: Below weekday baseline\nsource: Synthetic data\n---\n"
        "Narrative.",
        encoding="utf-8",
    )
    source = tmp_path / "report.yaml"
    source.write_text(
        "metadata: {title: Report}\n"
        "sections: [{title: Overview, content: [{narrative: Text}]}]\n"
        "findings: [{source: finding.md, include_if: show, "
        "visual: {chart: {artifact: chart.png}}}]\n",
        encoding="utf-8",
    )
    finding = ReportCompiler().compile_file(source).findings[0]
    assert (finding.subtitle, finding.source, finding.include_if) == (
        "Below weekday baseline",
        "Synthetic data",
        "show",
    )
    assert isinstance(finding.visual, ChartReference)


def test_invalid_yaml_field_identifies_its_source_and_field(tmp_path: Path) -> None:
    source = tmp_path / "report.yaml"
    source.write_text("metadata: []\nsections: []\n", encoding="utf-8")

    with pytest.raises(SourceCompilationError) as error:
        ReportCompiler().compile_file(source)

    assert error.value.source == source
    assert error.value.field == "metadata"


def test_malformed_yaml_identifies_the_source_yaml_field(tmp_path: Path) -> None:
    source = tmp_path / "report.yaml"
    source.write_text("metadata: [\n", encoding="utf-8")

    with pytest.raises(SourceCompilationError) as error:
        ReportCompiler().compile_file(source)

    assert error.value.source == source
    assert error.value.field == "yaml"


def test_content_requires_exactly_one_declared_type(tmp_path: Path) -> None:
    source = tmp_path / "report.yaml"
    source.write_text(
        """metadata: {title: Report}
sections:
  - title: Overview
    content:
      - narrative: Text
        chart: {artifact: chart.png}
""",
        encoding="utf-8",
    )

    with pytest.raises(SourceCompilationError) as error:
        ReportCompiler().compile_file(source)

    assert error.value.field == "sections[0].content[0]"


def test_invalid_table_alignment_identifies_its_field(tmp_path: Path) -> None:
    source = tmp_path / "report.yaml"
    source.write_text(
        """metadata: {title: Report}
sections:
  - title: Overview
    content:
      - table:
          columns: [{identity: name, label: Name, alignment: diagonal}]
          rows: []
""",
        encoding="utf-8",
    )

    with pytest.raises(SourceCompilationError) as error:
        ReportCompiler().compile_file(source)

    assert error.value.field == "sections[0].content[0].table.columns[0].alignment"


def test_chart_accepts_stable_logical_identity(tmp_path: Path) -> None:
    source = tmp_path / "report.yaml"
    source.write_text(
        """metadata: {title: Report, source: Finance ledger}
sections:
  - title: Overview
    content: [{chart: {identity: revenue-trend}}]
""",
        encoding="utf-8",
    )

    report = ReportCompiler().compile_file(source)

    assert report.metadata.source == "Finance ledger"
    assert report.sections[0].content[0] == ChartReference(identity="revenue-trend")


def test_chart_rejects_identity_and_artifact_together(tmp_path: Path) -> None:
    source = tmp_path / "report.yaml"
    source.write_text(
        """metadata: {title: Report}
sections:
  - title: Overview
    content: [{chart: {identity: revenue-trend, artifact: trend.png}}]
""",
        encoding="utf-8",
    )

    with pytest.raises(SourceCompilationError) as error:
        ReportCompiler().compile_file(source)

    assert error.value.field == "sections[0].content[0].chart"


def test_missing_markdown_finding_identifies_the_referencing_source(
    tmp_path: Path,
) -> None:
    source = tmp_path / "report.yaml"
    source.write_text(
        """metadata: {title: Report}
sections: [{title: Overview, content: [{narrative: Text}]}]
findings: [{source: findings/missing.md}]
""",
        encoding="utf-8",
    )

    with pytest.raises(SourceCompilationError) as error:
        ReportCompiler().compile_file(source)

    assert error.value.source == tmp_path / "findings" / "missing.md"
    assert error.value.field == "source"


def test_structural_or_analytical_templates_are_rejected(tmp_path: Path) -> None:
    source = write_sources(tmp_path)
    finding = tmp_path / "findings" / "growth.md"
    finding.write_text(
        """---
identity: revenue-growth
title: Revenue increased
---
{% if revenue > 0 %}Revenue increased{% endif %}
""",
        encoding="utf-8",
    )

    with pytest.raises(SourceCompilationError) as error:
        ReportCompiler({"revenue": 1}).compile_file(source)

    assert error.value.source == finding
    assert error.value.field == "body"
    assert "named values" in str(error.value)


def test_markdown_requires_frontmatter(tmp_path: Path) -> None:
    source = write_sources(tmp_path)
    finding = tmp_path / "findings" / "growth.md"
    finding.write_text("No frontmatter", encoding="utf-8")

    with pytest.raises(SourceCompilationError) as error:
        ReportCompiler().compile_file(source)

    assert error.value.source == finding
    assert error.value.field == "frontmatter"


def test_missing_referenced_artifact_identifies_the_yaml_element(
    tmp_path: Path,
) -> None:
    source = write_sources(tmp_path)
    (tmp_path / "artifacts" / "trend.png").unlink()

    with pytest.raises(SourceCompilationError) as error:
        ReportCompiler({"revenue": 1}).compile_file(source)

    assert error.value.source == source
    assert error.value.field == "sections[0].content[1]"
