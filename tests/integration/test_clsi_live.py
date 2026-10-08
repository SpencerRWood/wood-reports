"""Opt-in deployed compiler acceptance; missing requested credentials fail clearly."""

import base64
import os
from pathlib import Path

import pytest

from wood_reports import (
    CLSICompiler,
    CLSIConfig,
    CLSICredentials,
    CompilationError,
    LatexWorkspacePublisher,
    ReportCompiler,
    scaffold_markdown,
)


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
    if not os.environ.get("WOOD_REPORTS_CLSI_TEST_RESOURCE_URL"):
        pytest.fail(
            "Provide a CLSI-reachable publisher URL for the PNG integration fixture"
        )
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
