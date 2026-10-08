import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest

from wood_reports import (
    CompilationError,
    CompilationResult,
    DriveFile,
    PublicationAPI,
    SourceCompilationError,
    get_profile,
    scaffold_markdown,
)
from wood_reports.cli import main


def authored_text(profile: str = "decision-memo") -> str:
    return "\n".join(
        line + "\n\nAuthored internal content." if line.startswith("## ") else line
        for line in scaffold_markdown(profile, "cli-example").splitlines()
    )


@pytest.fixture
def source(tmp_path: Path) -> Path:
    path = tmp_path / "report.md"
    path.write_text(authored_text())
    return path


class MemoryCompiler:
    def __init__(self, *, failed: bool = False, raises: bool = True) -> None:
        self.failed = failed
        self.raises = raises
        self.calls = 0

    def compile(
        self,
        workspace: Path,
        destination: Path,
        *,
        resource_urls: Mapping[str, str] | None = None,
    ) -> CompilationResult:
        self.calls += 1
        assert (workspace / "generated/report.tex").exists()
        assert resource_urls is None or resource_urls == {"chart.png": "https://x.test"}
        destination.mkdir()
        log = destination / "output.log"
        log.write_text(
            "LaTeX Warning: Review this.\nUnderfull box\nLaTeX Warning: Review this.\n"
        )
        pdf = None if self.failed else destination / "report.pdf"
        if pdf is not None:
            pdf.write_bytes(b"%PDF-1.5\npreview\n%%EOF\n")
        manifest = destination / "compilation.json"
        manifest.write_text("{}")
        result = CompilationResult(
            "failed" if self.failed else "success",
            "error" if self.failed else "success",
            "project",
            "lualatex",
            pdf,
            (log,),
            manifest,
            ("compiler failed",) if self.failed else (),
        )
        if self.failed and self.raises:
            raise CompilationError(result)
        return result


class MemoryDrive:
    def metadata(self, file_id: str) -> DriveFile:
        return DriveFile(file_id, "report.md", "text/markdown")

    def report_files(self, folder_id: str) -> tuple[DriveFile, ...]:
        raise AssertionError(folder_id)

    def read_text(self, file_id: str) -> str:
        assert file_id == "drive-id"
        return authored_text()


def test_profile_list_and_show_expose_full_contracts(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["profile", "list", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert len(result["data"]["profiles"]) == 4
    assert main(["profile", "show", "decision-memo", "--json"]) == 0
    profile = json.loads(capsys.readouterr().out)["data"]["profile"]
    assert profile["version"] == get_profile("decision-memo").version
    assert profile["required_section_variants"]
    assert profile["sections"][0]["guidance"]
    assert main(["profile", "show", "decision-memo"]) == 0
    assert "purpose" in capsys.readouterr().out


@pytest.mark.parametrize(
    "profile",
    ["decision-memo", "project-brief", "analytics-report", "assessment-report"],
)
def test_create_scaffolds_profiles_without_overwriting(
    profile: str, tmp_path: Path
) -> None:
    output = tmp_path / "sources/report.md"
    api = PublicationAPI()
    assert api.create(output, doc_type=profile, doc_name="example") == output
    assert output.read_text() == scaffold_markdown(profile, "example")
    with pytest.raises(FileExistsError):
        api.create(output, doc_type=profile, doc_name="example")


def test_create_drive_preserves_validated_authoring(tmp_path: Path) -> None:
    output = tmp_path / "report.md"
    PublicationAPI().create(output, drive_reference="drive-id", reader=MemoryDrive())
    assert output.read_text() == authored_text()
    report = PublicationAPI().validate(
        "drive-id", reader=MemoryDrive(), artifact_root=tmp_path
    )
    assert report.metadata.doc_name == "cli-example"


@pytest.mark.parametrize("case", ["missing-profile", "missing-reader", "override"])
def test_invalid_create_requests_do_not_write(case: str, tmp_path: Path) -> None:
    api = PublicationAPI()
    output = tmp_path / "report.md"
    if case == "missing-profile":
        with pytest.raises(ValueError, match="doc_type and doc_name"):
            api.create(output)
    elif case == "missing-reader":
        with pytest.raises(ValueError, match="authenticated reader"):
            api.create(output, drive_reference="id")
    else:
        with pytest.raises(ValueError, match="source's profile"):
            api.create(
                output, drive_reference="id", reader=MemoryDrive(), doc_name="override"
            )
    assert not output.exists()


def test_create_rejects_nonmarkdown_and_invalid_drive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Markdown"):
        PublicationAPI().create(tmp_path / "report.txt")
    with pytest.raises(SourceCompilationError):
        PublicationAPI().create(
            tmp_path / "report.md", drive_reference="bad/id", reader=MemoryDrive()
        )
    assert not (tmp_path / "report.md").exists()


def test_validation_is_repeatable_and_does_not_render(
    source: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = ["validate", str(source), "--json"]
    assert main(args) == 0
    first = capsys.readouterr().out
    assert main(args) == 0
    assert capsys.readouterr().out == first
    assert json.loads(first)["data"]["validation_scope"] == "source"
    assert list(source.parent.iterdir()) == [source]


def test_preview_reuses_workspace_compiler_and_retains_warnings(source: Path) -> None:
    compiler = MemoryCompiler()
    output = source.parent / "preview"
    result = PublicationAPI().preview(str(source), output, compiler=compiler)
    assert result.compilation.pdf == output / "compilation/report.pdf"
    assert result.warnings == ("LaTeX Warning: Review this.", "Underfull box")
    with pytest.raises(FileExistsError):
        PublicationAPI().preview(str(source), output, compiler=compiler)
    assert compiler.calls == 1
    assert result.compilation.pdf.read_bytes().startswith(b"%PDF-")


@pytest.mark.parametrize("raises", [True, False])
def test_failed_preview_retains_logs_and_retry_uses_new_directory(
    source: Path, raises: bool
) -> None:
    output = source.parent / "failure"
    with pytest.raises(CompilationError) as failure:
        PublicationAPI().preview(
            str(source), output, compiler=MemoryCompiler(failed=True, raises=raises)
        )
    assert failure.value.result.logs[0].exists()
    assert not (output / "compilation/report.pdf").exists()
    retry = PublicationAPI().preview(
        str(source), source.parent / "retry", compiler=MemoryCompiler()
    )
    assert retry.compilation.pdf is not None


def test_invalid_source_never_invokes_compiler(tmp_path: Path) -> None:
    source = tmp_path / "report.md"
    source.write_text("invalid")
    compiler = MemoryCompiler()
    with pytest.raises(SourceCompilationError):
        PublicationAPI().preview(str(source), tmp_path / "preview", compiler=compiler)
    assert compiler.calls == 0
    assert not (tmp_path / "preview").exists()


def test_drive_requires_explicit_artifact_root() -> None:
    with pytest.raises(ValueError, match="artifact_root"):
        PublicationAPI().validate("drive-id", reader=MemoryDrive())


@pytest.mark.parametrize("command", ["preview", "build"])
def test_cli_compiles_using_injected_backend(
    command: str,
    source: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("wood_reports.cli._compiler", lambda _config: MemoryCompiler())
    assert (
        main([command, str(source), "--output", str(source.parent / command), "--json"])
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["data"]["compilation"]["status"] == "success"
    assert result["data"]["release"] is False


def test_cli_failure_returns_compilation_evidence(
    source: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "wood_reports.cli._compiler", lambda _config: MemoryCompiler(failed=True)
    )
    assert (
        main(
            [
                "preview",
                str(source),
                "--output",
                str(source.parent / "failed"),
                "--json",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "failed"
    assert payload["data"]["manifest"].endswith("compilation.json")


def test_cli_applies_central_publication_config(
    source: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    config = source.parent / "pyproject.toml"
    config.write_text(
        '[tool.wood_reports.publication]\nbrand_identity = "example"\n'
        'brand_revision = "2.0.0"\nwordmark = "Internal Brand"\n'
        '[tool.wood_reports.publication.branding]\ncorner = "bottom-left"\n'
    )
    monkeypatch.setattr("wood_reports.cli._compiler", lambda _config: MemoryCompiler())
    output = source.parent / "preview"
    assert (
        main(
            [
                "preview",
                str(source),
                "--output",
                str(output),
                "--config",
                str(config),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "success"
    workspace = output / "workspace/generated"
    manifest = json.loads((workspace / "workspace.json").read_text())
    assert manifest["brand"]["identity"] == "example"
    assert manifest["brand"]["revision"] == "2.0.0"
    assert "Internal Brand" in (workspace / "components.tex").read_text()


def test_release_requires_reproducible_epoch_before_credentials_or_output(
    source: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
    output = source.parent / "release"
    assert (
        main(["build", str(source), "--release", "--output", str(output), "--json"])
        == 1
    )
    assert "SOURCE_DATE_EPOCH" in json.loads(capsys.readouterr().out)["error"]
    assert not output.exists()


def test_installed_console_and_module_entry_points() -> None:
    for command in (["wood-report"], [sys.executable, "-m", "wood_reports"]):
        result = subprocess.run(  # noqa: S603
            [*command, "profile", "list", "--json"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(result.stdout)["status"] == "success"


def test_syntax_errors_are_nonzero() -> None:
    with pytest.raises(SystemExit) as failure:
        main(["preview"])
    assert failure.value.code == 2


def test_cli_create_and_validation_errors(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "report.md"
    assert (
        main(
            [
                "create",
                "--profile",
                "decision-memo",
                "--name",
                "example",
                "--output",
                str(source),
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["data"]["source"] == str(source)
    assert main(["validate", str(source), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "failed"
    assert main(["profile", "show", "unknown"]) == 1
    assert "unsupported profile" in capsys.readouterr().out


def test_cli_drive_create_and_validate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("wood_reports.cli._reader", MemoryDrive)
    output = tmp_path / "report.md"
    assert (
        main(["create", "--drive", "drive-id", "--output", str(output), "--json"]) == 0
    )
    capsys.readouterr()
    assert output.read_text() == authored_text()
    assert (
        main(
            [
                "validate",
                "drive-id",
                "--drive",
                "--artifact-root",
                str(tmp_path),
                "--json",
            ]
        )
        == 0
    )
    assert (
        json.loads(capsys.readouterr().out)["data"]["document"]["doc_name"]
        == "cli-example"
    )


def test_missing_credentials_fail_without_creating_outputs(
    source: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in (
        "WOOD_REPORTS_CLSI_USERNAME",
        "WOOD_REPORTS_CLSI_PASSWORD",
        "WOOD_REPORTS_DRIVE_ACCESS_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    assert (
        main(
            [
                "preview",
                str(source),
                "--output",
                str(source.parent / "absent"),
                "--json",
            ]
        )
        == 1
    )
    assert "WOOD_REPORTS_CLSI_USERNAME" in capsys.readouterr().out
    assert main(["validate", "id", "--drive", "--json"]) == 1
    assert "WOOD_REPORTS_DRIVE_ACCESS_TOKEN" in capsys.readouterr().out
    assert not (source.parent / "absent").exists()


def test_cli_configuration_and_resource_map(
    source: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from wood_reports.cli import _compiler, _reader  # noqa: PLC0415

    monkeypatch.setenv("WOOD_REPORTS_CLSI_USERNAME", "fixture")
    monkeypatch.setenv("WOOD_REPORTS_CLSI_PASSWORD", "private")
    monkeypatch.setenv("WOOD_REPORTS_DRIVE_ACCESS_TOKEN", "private-token")
    config = source.parent / "pyproject.toml"
    config.write_text('[tool.wood_reports.clsi]\nurl = "https://clsi.example"\n')
    assert _compiler(config).config.url == "https://clsi.example"
    assert "private-token" not in repr(_reader())
    monkeypatch.setattr("wood_reports.cli._compiler", lambda _config: MemoryCompiler())
    resources = source.parent / "resources.json"
    resources.write_text('{"chart.png": "https://x.test"}')
    assert (
        main(
            [
                "preview",
                str(source),
                "--output",
                str(source.parent / "resources"),
                "--resource-urls",
                str(resources),
                "--json",
            ]
        )
        == 0
    )
    capsys.readouterr()
    resources.write_text('["invalid"]')
    assert (
        main(
            [
                "preview",
                str(source),
                "--output",
                str(source.parent / "invalid"),
                "--resource-urls",
                str(resources),
                "--json",
            ]
        )
        == 1
    )
    assert "JSON object" in capsys.readouterr().out
    assert not (source.parent / "invalid").exists()
