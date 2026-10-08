"""Opt-in deployed compiler acceptance; missing requested credentials fail clearly."""

import base64
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfReader

from wood_reports import (
    CLSICompiler,
    CLSIConfig,
    CLSICredentials,
    CompilationError,
    LatexWorkspacePublisher,
    ReportCompiler,
    scaffold_markdown,
)
from wood_reports.cli import main


@pytest.fixture
def backend(request: pytest.FixtureRequest) -> CLSICompiler:
    if not request.config.getoption("--run-clsi"):
        pytest.skip("CLSI integration requires --run-clsi and injected credentials")
    values = {
        key: os.environ.get(key, "")
        for key in ("WOOD_REPORTS_CLSI_USERNAME", "WOOD_REPORTS_CLSI_PASSWORD")
    }
    if not all(values.values()):
        pytest.fail("Inject WOOD_REPORTS_CLSI_USERNAME and WOOD_REPORTS_CLSI_PASSWORD")
    configured = CLSIConfig.from_pyproject(Path("pyproject.toml"))
    return CLSICompiler(
        CLSIConfig(configured.url, min(configured.timeout_seconds, 20)),
        CLSICredentials(
            values["WOOD_REPORTS_CLSI_USERNAME"], values["WOOD_REPORTS_CLSI_PASSWORD"]
        ),
    )


def test_deployed_clsi_compiles_branded_markdown_and_retains_failure_logs(
    backend: CLSICompiler, tmp_path: Path
) -> None:
    if not os.environ.get("WOOD_REPORTS_CLSI_TEST_RESOURCE_URL"):
        pytest.fail(
            "Provide a CLSI-reachable publisher URL for the PNG integration fixture"
        )
    source = tmp_path / "report.md"
    chart = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNg0M8BAADO"
        "AJxI2GK/AAAAAElFTkSuQmCC"
    )
    (tmp_path / "chart.png").write_bytes(chart)
    scaffold = scaffold_markdown("decision-memo", "internal-compiler-verification")
    source.write_text(
        "\n".join(
            line + "\n\nInternal compiler verification."
            if line.startswith("## ")
            else line
            for line in scaffold.splitlines()
        )
        + "\n\n## Appendix\n\n### Compiler asset\n\n![Internal chart](chart.png)\n"
    )
    report = ReportCompiler().compile_file(source, artifact_root=tmp_path)
    workspace = tmp_path / "workspace"
    LatexWorkspacePublisher().publish(report, workspace, artifact_root=tmp_path)
    extensions = workspace / "extensions"
    extensions.mkdir()
    (extensions / "extra.png").write_bytes(chart)
    (extensions / "body.tex").write_text(
        r"\includegraphics[width=1cm]{../extensions/extra.png}"
    )
    resources = {
        "generated/assets/1-chart.png": os.environ[
            "WOOD_REPORTS_CLSI_TEST_RESOURCE_URL"
        ],
        "extensions/extra.png": os.environ["WOOD_REPORTS_CLSI_TEST_RESOURCE_URL"],
    }
    result = backend.compile(workspace, tmp_path / "success", resource_urls=resources)
    assert result.pdf is not None
    assert result.pdf.read_bytes().startswith(b"%PDF-")
    assert result.logs
    assert (extensions / "extra.png").read_bytes() == chart
    (extensions / "body.tex").write_text(r"\UndefinedWoodReportsCommand")
    with pytest.raises(CompilationError) as error:
        backend.compile(workspace, tmp_path / "failure", resource_urls=resources)
    failure = error.value.result
    assert failure.pdf is None
    assert failure.status == "failed"
    assert failure.logs
    assert any("Undefined" in path.read_text(errors="replace") for path in failure.logs)
    assert not (tmp_path / "failure" / "report.pdf").exists()


def test_native_cli_deployed_clsi_preview(
    backend: CLSICompiler,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    source = tmp_path / "report.md"
    source.write_text(
        "\n".join(
            line + "\n\nNative CLI verification." if line.startswith("## ") else line
            for line in scaffold_markdown("decision-memo", "native-cli-verification")
            .replace(
                "title: Native Cli Verification",
                'title: Native Cli Verification\nversion: "1.0.0"',
            )
            .splitlines()
        )
    )
    monkeypatch.setattr("wood_reports.cli._compiler", lambda _config: backend)
    output = tmp_path / "preview"
    assert main(["validate", str(source), "--json"]) == 0
    capsys.readouterr()
    assert main(["preview", str(source), "--output", str(output), "--json"]) == 0
    assert '"status": "success"' in capsys.readouterr().out
    assert (output / "compilation/report.pdf").read_bytes().startswith(b"%PDF-")
    assert (output / "compilation/compilation.json").exists()
    releases = tmp_path / "releases"
    assert (
        main(
            [
                "build",
                str(source),
                "--release",
                "--output",
                str(releases),
                "--build-epoch",
                "1700000000",
                "--json",
            ]
        )
        == 0
    )
    released = json.loads(capsys.readouterr().out)["data"]
    assert Path(released["pdf"]).is_file()
    manifest = json.loads(Path(released["manifest"]).read_text())
    assert manifest["validation"]["status"] == "passed"
    assert manifest["source"]["semantic_sha256"]
    assert manifest["pdf"]["sha256"]


def test_internal_corpus_native_cli_releases_all_profiles(
    backend: CLSICompiler, tmp_path: Path
) -> None:
    """Real CLI/CLSI acceptance; no fake compiler or source/workspace adapter."""
    del backend  # Reuse the existing credential/configuration readiness fixture.
    resource_url = os.environ.get("WOOD_REPORTS_INTERNAL_CHART_URL")
    if not resource_url:
        pytest.fail("Provide WOOD_REPORTS_INTERNAL_CHART_URL for the corpus PNG bytes")
    resources = tmp_path / "resources.json"
    resources.write_text(
        json.dumps({"generated/assets/1-weekly-sessions.png": resource_url})
    )
    corpus = Path(__file__).parents[2] / "examples" / "internal"
    output = Path(
        os.environ.get(
            "WOOD_REPORTS_INTERNAL_OUTPUT", str(tmp_path / "internal-releases")
        )
    )
    result = subprocess.run(  # noqa: S603 -- fixed local CLI and authored fixture
        [
            sys.executable,
            str(corpus / "publish.py"),
            "release",
            "--output",
            str(output),
            "--build-epoch",
            "1791460800",
            "--resource-urls",
            str(resources),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    summary = json.loads((output / "corpus.json").read_text())
    assert summary["status"] == "passed"
    assert len(summary["documents"]) == 4
    for record in summary["documents"].values():
        assert record["pages"] > 0
        assert record["checked_artifacts"] > 0
    for profile, record in summary["documents"].items():
        reader = PdfReader(record["pdf"])
        text = "\n".join(page.extract_text() for page in reader.pages)
        compact_text = re.sub(r"\s+", "", text)
        assert "Internal" in text
        assert "syntheticexample" in compact_text
        assert "WoodAnalytics" in compact_text
        assert "Appendix" in text
        links = {
            annotation.get_object()["/A"]["/URI"]
            for page in reader.pages
            for annotation in page.get("/Annots", [])
            if annotation.get_object().get("/A", {}).get("/URI")
        }
        expected = set(
            re.findall(r"\]\((https://[^)]+)\)", (corpus / f"{profile}.md").read_text())
        )
        assert expected <= links
        if profile == "analytics-report":
            assert "7,000" in text
            assert "280" in text
            assert "4.00%" in text
            with Image.open(corpus / "assets/weekly-sessions.png") as source:
                expected_pixels = source.convert("RGB").tobytes()
            assert any(
                image.image.convert("RGB").tobytes() == expected_pixels
                for page in reader.pages
                for image in page.images
                if image.image is not None
            )
