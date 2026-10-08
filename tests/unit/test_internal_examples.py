"""The authored corpus is executable documentation, not an alternate renderer."""

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from wood_reports import LatexWorkspacePublisher, PublicationAPI, ReportCompiler
from wood_reports.compiler import SourceCompilationError
from wood_reports.model import ChartReference, Narrative, PublicationTable
from wood_reports.pdf_validation import validate_release_report

CORPUS = Path(__file__).parents[2] / "examples" / "internal"
PROFILES = ("project-brief", "analytics-report", "assessment-report", "decision-memo")


@pytest.mark.parametrize("profile", PROFILES)
def test_authored_corpus_preserves_supported_model_and_workspace(
    profile: str, tmp_path: Path
) -> None:
    source = CORPUS / f"{profile}.md"
    report = PublicationAPI().validate(str(source), artifact_root=CORPUS)
    assert report == ReportCompiler().compile_file(source)
    assert report.metadata.doc_type == profile
    assert report.metadata.version == "1.0.0"
    assert "synthetic" in (report.metadata.confidentiality or "")
    assert validate_release_report(report, artifact_root=CORPUS).passed
    assert report.appendices
    blocks = [item for section in report.sections for item in section.content]
    assert any(isinstance(item, PublicationTable) for item in blocks)
    assert any(
        isinstance(item, Narrative) and item.kind == "callout" for item in blocks
    )
    entrypoint = LatexWorkspacePublisher().publish(
        report, tmp_path / "workspace", artifact_root=CORPUS
    )
    text = entrypoint.read_text()
    assert "WoodBrandLogo" in (entrypoint.parent / "components.tex").read_text()
    assert "\\href{https://github.com/SpencerRWood/wood-reports/blob/v0.20.0/" in text
    if profile == "analytics-report":
        charts = [item for item in blocks if isinstance(item, ChartReference)]
        assert len(charts) == 1
        assert charts[0].artifact == Path("assets/weekly-sessions.png")
        copied = entrypoint.parent / "assets" / "1-weekly-sessions.png"
        assert copied.read_bytes() == (CORPUS / charts[0].artifact).read_bytes()


def test_analytics_fixture_totals_match_authored_claims() -> None:
    with (CORPUS / "weekly-traffic.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    sessions = [int(row["sessions"]) for row in rows]
    conversions = [int(row["conversions"]) for row in rows]
    assert sum(sessions) == 7000
    assert sum(conversions) == 280
    assert sum(conversions) / sum(sessions) == 0.04
    assert (sessions[-1] - sessions[0]) / sessions[0] == 0.32
    assert sessions[2] - sessions[1] == -40
    assert (CORPUS / "assets/weekly-sessions.png").read_bytes().startswith(b"\x89PNG")


def test_corpus_analytics_requires_its_declared_chart(tmp_path: Path) -> None:
    source = tmp_path / "analytics-report.md"
    source.write_text((CORPUS / source.name).read_text())
    with pytest.raises(SourceCompilationError, match="does not exist"):
        PublicationAPI().validate(str(source))


def test_native_corpus_runner_validates_all_profiles_without_network(
    tmp_path: Path,
) -> None:
    output = tmp_path / "source-check"
    result = subprocess.run(  # noqa: S603 -- fixed local executable and fixture
        [
            sys.executable,
            str(CORPUS / "publish.py"),
            "validate",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((output / "corpus.json").read_text())
    assert set(summary["documents"]) == set(PROFILES)
    for profile in PROFILES:
        record = json.loads((output / f"{profile}-source.json").read_text())
        assert record["data"]["validation_scope"] == "source"
        assert record["data"]["document"]["doc_type"] == profile
    repeated = subprocess.run(  # noqa: S603 -- fixed local executable and fixture
        [
            sys.executable,
            str(CORPUS / "publish.py"),
            "validate",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert repeated.returncode == 1
    assert (output / "corpus.json").read_text() == json.dumps(summary, indent=2) + "\n"
