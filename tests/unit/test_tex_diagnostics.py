from dataclasses import replace
from pathlib import Path

import pytest

from wood_reports import PublicationTableLayout, PublicationTheme
from wood_reports.primitives import has_technical_text, latex_inline
from wood_reports.tex_diagnostics import parse_tex_diagnostics


def test_classification_counts_and_source_context() -> None:
    text = (
        "ignored error Infinite glue shrinkage found in box being split\n"
        "ignored: Infinite glue shrinkage found in box being split\n"
        "! Undefined control sequence.\nl.42 \\badcommand\n"
        "Package wood-reports Error: Font unavailable: IBM Plex Sans.\n"
        "! LaTeX Error: File 'missing.svg' not found.\n"
        "Overfull \\hbox (2.5pt too wide) in paragraph at lines 8--12\n"
        "Underfull \\hbox (badness 999) in paragraph at lines 13--14\n"
        "Underfull \\hbox (badness 6641) in paragraph at lines 15--17\n"
        "LaTeX Warning: Reference 'table' undefined on input line 20.\n"
        "LaTeX Warning: Citation 'source' undefined.\n"
        "Package longtable Warning: Table widths have changed.\n"
        "! Emergency stop.\n"
    )
    result = {d.category: d for d in parse_tex_diagnostics(text)}
    assert result["infinite-glue-shrinkage"].occurrence_count == 2
    assert result["infinite-glue-shrinkage"].severity == "error"
    assert result["infinite-glue-shrinkage"].contexts[0].source_lines is None
    assert result["undefined-control-sequence"].contexts[0].source_lines == "42"
    assert result["missing-font"].severity == "error"
    assert result["missing-asset"].severity == "error"
    assert result["overfull-box"].contexts[0].magnitude == 2.5
    assert result["underfull-box"].occurrence_count == 1
    assert result["underfull-box"].contexts[0].source_lines == "15--17"
    assert result["unresolved-reference"].severity == "warning"
    assert result["unresolved-reference"].contexts[0].source_lines == "20"
    assert result["unresolved-citation"].severity == "warning"
    assert result["page-table-break"].severity == "warning"
    assert result["tex-structural"].occurrence_count == 1


@pytest.mark.parametrize("threshold", [-1, 10001, True, 1.5])
def test_invalid_badness_threshold(threshold: int) -> None:
    with pytest.raises(ValueError, match="underfull_badness"):
        parse_tex_diagnostics("", underfull_badness=threshold)


@pytest.mark.parametrize(
    "value",
    [
        {"density": "tiny"},
        {"comfortable_row_inches": 0},
        {"compact_row_inches": float("inf")},
        {"compact_row_inches": "small"},
        {"minimum_first_rows": 0},
        {"minimum_last_rows": True},
        {"keep_together_rows": 21},
    ],
)
def test_invalid_table_policy(value: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="table_layout"):
        PublicationTableLayout(**value).validate()  # type: ignore[arg-type]


def test_table_density_is_shared_configuration(tmp_path: Path) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[tool.wood_reports.publication.table_layout]\ndensity = "compact"\n'
        "minimum_first_rows = 4\n"
    )
    theme = PublicationTheme.from_pyproject(path)
    assert theme.table_layout.row_inches == 0.22
    assert theme.table_layout.minimum_first_rows == 4
    assert replace(theme.table_layout, density="comfortable").row_inches == 0.28


@pytest.mark.parametrize(
    "text",
    [
        "SpencerRWood/synthetic-website-analytics-platform",
        "src/wood_reports/latex_components.py",
        "tool.wood_reports.publication",
        "`extremelylonguninterruptedidentifier0123456789`",
        "[Evidence](https://github.com/SpencerRWood/wood-reports)",
    ],
)
def test_technical_primitives_preserve_literals_and_links(text: str) -> None:
    assert has_technical_text(text)
    rendered = latex_inline(text)
    assert r"\-" not in rendered
    if text.startswith("[Evidence]"):
        assert (
            rendered == r"\href{https://github.com/SpencerRWood/wood-reports}{Evidence}"
        )
    else:
        assert r"\allowbreak{}" in rendered or r"\penalty500{}" in rendered


def test_plain_prose_keeps_justification_and_code_semantics() -> None:
    assert not has_technical_text("Plain readable prose.")
    assert not has_technical_text("Evidence-based and well-supported prose.")
    assert latex_inline("Evidence-based prose.") == "Evidence-based prose."
    assert has_technical_text("Inspect `wood-reports` for evidence.")
    assert latex_inline("`code`") == r"\texttt{code}"
