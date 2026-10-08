import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, NameObject

from wood_reports import (
    CompilationError,
    CompilationResult,
    MarkdownReportCompiler,
    PDFValidationError,
    PublicationAPI,
    ReleasePublisher,
    scaffold_markdown,
    semantic_content_digest,
)
from wood_reports.cli import main
from wood_reports.clsi_workspace import read_workspace
from wood_reports.release import canonical_json


@pytest.fixture
def source(tmp_path: Path) -> Path:
    source = tmp_path / "report.md"
    text = scaffold_markdown("decision-memo", "release-example")
    text = text.replace(
        "title: Release Example", 'title: Release Example\nversion: "1.0.0"'
    )
    source.write_text(
        "\n".join(
            line + "\n\nInternal content." if line.startswith("## ") else line
            for line in text.splitlines()
        )
    )
    return source


class ReleaseCompiler:
    def __init__(self, fault: str = "") -> None:
        self.fault = fault
        self.calls = 0
        self.mutate: Callable[[Path], None] | None = None

    def compile(
        self,
        workspace: Path,
        destination: Path,
        *,
        resource_urls: Mapping[str, str] | None = None,
    ) -> CompilationResult:
        self.calls += 1
        inputs = read_workspace(workspace, resource_urls or {})
        destination.mkdir()
        pdf = destination / "report.pdf"
        writer = PdfWriter()
        page = writer.add_blank_page(width=100, height=100)
        stream = DecodedStreamObject()
        stream.set_data(b"0 0 m 10 10 l S")
        page[NameObject("/Contents")] = writer._add_object(stream)
        writer.write(pdf)
        if self.fault == "pdf":
            pdf.write_bytes(b"%PDF-truncated")
        log = destination / "compiler.log"
        log.write_text(
            "Overfull \\hbox (20pt too wide)"
            if self.fault == "log"
            else "Compiled successfully"
        )
        manifest = destination / "compilation.json"
        result = CompilationResult(
            "success", "success", "project", "lualatex", pdf, (log,), manifest, ()
        )
        record = {
            **asdict(result),
            "pdf": pdf.name,
            "logs": [log.name],
            "manifest": manifest.name,
            "backend": "clsi",
            "schema_version": 1,
            "source_fingerprints": inputs.fingerprints,
        }
        if self.fault == "manifest":
            record["source_fingerprints"] = {"stale": "identity"}
        manifest.write_bytes(canonical_json(record))
        if self.fault == "workspace":
            (workspace / "generated/report.tex").write_text("Changed source")
        if self.fault == "compile":
            pdf.unlink()
            raise CompilationError(
                replace(result, pdf=None, status="failed", diagnostics=("failed",))
            )
        if self.mutate is not None:
            self.mutate(workspace)
        return result


def publish(source: Path, root: Path, compiler: ReleaseCompiler | None = None) -> Path:
    result = PublicationAPI().release(
        str(source),
        root,
        compiler=compiler or ReleaseCompiler(),
        build_epoch=1700000000,
        source_revision="abc123",
    )
    assert result.validation.passed
    assert result.pdf.is_file()
    return result.directory


def test_versioned_package_and_complete_provenance(source: Path) -> None:
    directory = publish(source, source.parent / "releases")
    manifest = json.loads((directory / "release.json").read_text())
    assert directory.name == "1.0.0"
    assert directory.parent.name == "release-example"
    assert [path.name for path in (directory / "delivered").iterdir()] == ["report.pdf"]
    assert manifest["doc_type"] == "decision-memo"
    assert manifest["doc_name"] == "release-example"
    assert manifest["report_version"] == "1.0.0"
    assert manifest["renderer"]["identity"] == "latex"
    assert manifest["wood_reports_version"]
    assert manifest["profile_version"] == "1.0.0"
    assert manifest["profile"] == {"identity": "decision-memo", "revision": "1.0.0"}
    assert manifest["brand"] == {"identity": "wood-analytics", "revision": "1.0.0"}
    assert manifest["theme"]["revision"]
    assert manifest["source"]["revision"] == "abc123"
    assert manifest["source"]["identity"] == "report.md"
    assert manifest["timestamp"] == "2023-11-14T22:13:20+00:00"
    assert manifest["compiler"]["backend"] == "clsi"
    assert manifest["validation"]["status"] == "passed"
    assert (
        manifest["pdf"]["sha256"]
        == hashlib.sha256((directory / "delivered/report.pdf").read_bytes()).hexdigest()
    )
    for name, digest in manifest["artifacts"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest
    assert "source/workspace/generated/report.tex" in manifest["artifacts"]
    assert "source/workspace/generated/components.tex" in manifest["artifacts"]
    assert "source/workspace/generated/assets/brand.svg" in manifest["artifacts"]
    assert "source/report.json" in manifest["artifacts"]
    assert "compilation/compilation.json" in manifest["artifacts"]
    assert "validation.json" in manifest["artifacts"]


def test_repeatable_manifest_and_location_independent_semantic_digest(
    source: Path,
) -> None:
    first = publish(source, source.parent / "first")
    second = publish(source, source.parent / "second")
    assert (first / "release.json").read_bytes() == (
        second / "release.json"
    ).read_bytes()


def test_successful_versions_cannot_be_overwritten(source: Path) -> None:
    root = source.parent / "releases"
    first = publish(source, root)
    before = {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }
    compiler = ReleaseCompiler()
    with pytest.raises(FileExistsError):
        publish(source, root, compiler)
    assert compiler.calls == 0
    assert before == {
        path.relative_to(first): path.read_bytes()
        for path in first.rglob("*")
        if path.is_file()
    }


@pytest.mark.parametrize("fault", ["pdf", "log", "manifest", "workspace", "compile"])
def test_failure_never_publishes_and_retry_is_safe(source: Path, fault: str) -> None:
    root = source.parent / "releases"
    with pytest.raises((ValueError, CompilationError), match=r"."):
        publish(source, root, ReleaseCompiler(fault))
    assert not (root / "release-example/1.0.0").exists()
    assert not list(root.rglob("release.json"))
    assert list((root / ".attempts").iterdir())
    result = publish(source, root)
    assert (result / "delivered/report.pdf").exists()


def test_preflight_failure_does_not_create_attempt(source: Path) -> None:
    source.write_text(source.read_text().replace("Internal content.", "TODO finish"))
    root = source.parent / "releases"
    with pytest.raises(PDFValidationError):
        publish(source, root)
    assert not root.exists()


@pytest.mark.parametrize("epoch", [-1, True])
def test_invalid_timestamp_fails_before_creation(source: Path, epoch: int) -> None:
    with pytest.raises(ValueError, match="build_epoch"):
        PublicationAPI().release(
            str(source),
            source.parent / "releases",
            compiler=ReleaseCompiler(),
            build_epoch=epoch,
        )
    assert not (source.parent / "releases").exists()


def test_version_path_traversal_is_rejected(source: Path) -> None:
    source.write_text(source.read_text().replace('"1.0.0"', '"../escape"'))
    with pytest.raises(ValueError, match="safe path"):
        publish(source, source.parent / "releases")
    assert not (source.parent / "escape").exists()


def test_missing_identity_fails_before_creation(source: Path) -> None:
    report = MarkdownReportCompiler().compile_file(source)
    with pytest.raises(ValueError, match="source_identity"):
        ReleasePublisher().publish(
            report,
            source.parent / "releases",
            compiler=ReleaseCompiler(),
            artifact_root=source.parent,
            source_identity="",
            build_epoch=0,
        )


def test_changed_asset_after_compile_is_rejected(source: Path) -> None:
    asset = source.parent / "chart.svg"
    asset.write_text('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>')
    # A changed source asset is detected even after the compiler snapshots it.
    from wood_reports import ChartReference  # noqa: PLC0415

    report = MarkdownReportCompiler().compile_file(source)
    section = replace(
        report.sections[0],
        content=(*report.sections[0].content, ChartReference(artifact=asset)),
    )
    report = replace(report, sections=(section, *report.sections[1:]))
    compiler = ReleaseCompiler()

    def mutate_asset(_workspace: Path) -> None:
        asset.write_text("changed")

    compiler.mutate = mutate_asset
    with pytest.raises(ValueError, match="assets changed"):
        ReleasePublisher().publish(
            report,
            source.parent / "releases",
            compiler=compiler,
            artifact_root=source.parent,
            source_identity="report",
            build_epoch=0,
        )


def test_cli_release_uses_backend_and_epoch(
    source: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("wood_reports.cli._compiler", lambda _config: ReleaseCompiler())
    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1700000000")
    root = source.parent / "releases"
    assert (
        main(["build", str(source), "--release", "--output", str(root), "--json"]) == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["release"] is True
    assert Path(payload["data"]["pdf"]).exists()
    assert (
        main(
            [
                "build",
                str(source),
                "--release",
                "--output",
                str(root),
                "--build-epoch",
                "1700000000",
                "--json",
            ]
        )
        == 1
    )
    assert json.loads(capsys.readouterr().out)["status"] == "failed"


@pytest.mark.parametrize("directory", ["release-example", ".attempts"])
def test_release_rejects_symlink_ownership_directories(
    source: Path, directory: str
) -> None:
    root = source.parent / "releases"
    root.mkdir()
    external = source.parent / "external"
    external.mkdir()
    (root / directory).symlink_to(external, target_is_directory=True)
    with pytest.raises(ValueError, match="symlinks"):
        publish(source, root)
    assert not list(external.iterdir())


def test_concurrent_completed_output_is_preserved(source: Path) -> None:
    root = source.parent / "releases"
    final = root / "release-example/1.0.0"

    def competitor(_workspace: Path) -> None:
        final.mkdir(parents=True)
        (final / "known-good").write_text("preserve")

    compiler = ReleaseCompiler()
    compiler.mutate = competitor
    with pytest.raises(FileExistsError):
        publish(source, root, compiler)
    assert (final / "known-good").read_text() == "preserve"
    assert not (final / "delivered").exists()


@pytest.mark.parametrize(
    "fault",
    ["manifest-write", "rename", "changed-pdf", "changed-log", "changed-packaged-file"],
)
def test_packaging_failures_cannot_publish(
    source: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    from wood_reports import release  # noqa: PLC0415

    root = source.parent / "releases"
    if fault == "manifest-write":
        original_write = Path.write_bytes

        def fail_write(path: Path, content: bytes) -> int:
            if path.name == "release.json":
                raise OSError("manifest write failed")
            return original_write(path, content)

        monkeypatch.setattr(Path, "write_bytes", fail_write)
    elif fault == "rename":

        def fail_rename(_path: Path, _target: Path) -> Path:
            raise OSError("rename failed")

        monkeypatch.setattr(Path, "rename", fail_rename)
    elif fault in {"changed-pdf", "changed-log"}:
        original_verify = ReleasePublisher._verify_compilation

        def mutate_evidence(
            compilation: CompilationResult, fingerprints: dict[str, str]
        ) -> None:
            original_verify(compilation, fingerprints)
            path = compilation.pdf if fault == "changed-pdf" else compilation.logs[0]
            assert path is not None
            path.write_bytes(b"changed after validation")

        monkeypatch.setattr(
            ReleasePublisher, "_verify_compilation", staticmethod(mutate_evidence)
        )
    else:
        original_manifest = release.release_manifest

        def mutate_snapshot(*args: object, **kwargs: object) -> dict[str, object]:
            # Mutation occurs after artifact checksums were computed.
            for path in root.rglob("report.json"):
                path.write_text("changed snapshot")
            return original_manifest(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(release, "release_manifest", mutate_snapshot)
    with pytest.raises((OSError, ValueError), match=r"."):
        publish(source, root)
    assert not (root / "release-example/1.0.0").exists()


def test_missing_or_unresolved_assets_do_not_compile(source: Path) -> None:
    from wood_reports import ChartReference  # noqa: PLC0415

    report = MarkdownReportCompiler().compile_file(source)
    for chart in (
        ChartReference(artifact=Path("missing.png")),
        ChartReference(identity="unresolved"),
    ):
        with_chart = replace(
            report,
            sections=(
                replace(report.sections[0], content=(chart,)),
                *report.sections[1:],
            ),
        )
        compiler = ReleaseCompiler()
        with pytest.raises(ValueError, match=r"."):
            ReleasePublisher().publish(
                with_chart,
                source.parent / "releases",
                compiler=compiler,
                artifact_root=source.parent,
                source_identity="report",
                build_epoch=0,
            )
        assert compiler.calls == 0


def test_semantic_digest_tracks_content_independently_of_presentation(
    source: Path,
) -> None:
    report = MarkdownReportCompiler().compile_file(source)
    digest = semantic_content_digest(report, artifact_root=source.parent)
    themed = replace(
        report,
        theme=replace(report.theme, revision="2.0.0"),
        renderer_hints={"latex.label": "different"},
    )
    assert semantic_content_digest(themed, artifact_root=source.parent) == digest
    changed = replace(
        report, metadata=replace(report.metadata, title="Changed meaning")
    )
    assert semantic_content_digest(changed, artifact_root=source.parent) != digest


def test_cli_reports_structured_pdf_validation_failure(
    source: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "wood_reports.cli._compiler", lambda _config: ReleaseCompiler("log")
    )
    output = source.parent / "releases"
    assert (
        main(
            [
                "build",
                str(source),
                "--release",
                "--output",
                str(output),
                "--build-epoch",
                "0",
                "--json",
            ]
        )
        == 1
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]["validation"]["issues"][0]["code"] == "tex-overfull"
    assert not (output / "release-example/1.0.0").exists()
