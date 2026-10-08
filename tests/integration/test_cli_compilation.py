"""Exercise the installed lifecycle through real CLSI orchestration, with fake IO."""

import json
from collections.abc import Mapping
from pathlib import Path

import pytest

from wood_reports import scaffold_markdown
from wood_reports.cli import main
from wood_reports.clsi import HTTPCLSITransport, HTTPResponse


@pytest.mark.parametrize("failed", [False, True])
def test_cli_markdown_to_clsi_pdf_and_failure_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failed: bool,
) -> None:
    requests: list[str] = []

    def request(  # noqa: PLR0913
        _self: HTTPCLSITransport,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        deadline: float,
        max_bytes: int,
    ) -> HTTPResponse:
        assert headers["Authorization"].startswith("Basic ")
        assert deadline > 0
        assert max_bytes > 0
        requests.append(method)
        if method == "POST":
            assert body is not None
            compile_request = json.loads(body)["compile"]
            assert compile_request["rootResourcePath"] == "generated/report.tex"
            assert any(
                resource["path"] == "generated/workspace.json"
                for resource in compile_request["resources"]
            )
            base = url.removesuffix("/compile")
            return HTTPResponse(
                200,
                json.dumps(
                    {
                        "compile": {
                            "status": "error" if failed else "success",
                            "outputFiles": [
                                {
                                    "type": "log",
                                    "url": base + "/build/test/output/output.log",
                                },
                                {
                                    "type": "pdf",
                                    "url": base + "/build/test/output/output.pdf",
                                },
                            ],
                        }
                    }
                ).encode(),
            )
        if method == "DELETE":
            return HTTPResponse(204, b"")
        return HTTPResponse(
            200,
            b"%PDF-preview" if url.endswith(".pdf") else b"LaTeX Warning: Review.\n",
        )

    monkeypatch.setattr(HTTPCLSITransport, "request", request)
    monkeypatch.setenv("WOOD_REPORTS_CLSI_USERNAME", "fixture")
    monkeypatch.setenv("WOOD_REPORTS_CLSI_PASSWORD", "secret-cli-fixture-password")
    monkeypatch.delenv("WOOD_REPORTS_CLSI_URL", raising=False)
    config = tmp_path / "pyproject.toml"
    config.write_text('[tool.wood_reports.clsi]\nurl = "https://clsi.example"\n')
    source = tmp_path / "report.md"
    source.write_text(
        "\n".join(
            line + "\n\nInternal content." if line.startswith("## ") else line
            for line in scaffold_markdown(
                "decision-memo", "cli-integration"
            ).splitlines()
        )
    )
    output = tmp_path / "preview"
    assert main(
        [
            "preview",
            str(source),
            "--config",
            str(config),
            "--output",
            str(output),
            "--json",
        ]
    ) == (1 if failed else 0)
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == ("failed" if failed else "success")
    assert (output / "compilation/report.pdf").exists() is not failed
    assert (output / "compilation/compilation.json").exists()
    assert requests[-1] == "DELETE"
    assert "secret-cli-fixture-password" not in json.dumps(payload)
