"""Versioned, fail-closed PDF release packaging with explicit reproducible inputs."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from tempfile import mkdtemp

from wood_reports.clsi_workspace import read_workspace
from wood_reports.compilation import CompilationResult, WorkspaceCompiler
from wood_reports.latex_workspace import LatexWorkspacePublisher
from wood_reports.model import Report
from wood_reports.pdf_validation import (
    PDFValidationResult,
    validate_pdf,
    validate_release_report,
)


def canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    ).encode("utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _semantic(value: object, root: Path) -> object:
    if isinstance(value, Path):
        path = value if value.is_absolute() else root / value
        return {"artifact": value.name, "sha256": sha256(path)}
    if isinstance(value, dict):
        return {key: _semantic(child, root) for key, child in value.items()}
    if isinstance(value, (tuple, list)):
        return [_semantic(child, root) for child in value]
    return value


def _content(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _content(child)
            for key, child in value.items()
            if key not in {"theme", "renderer_hints"}
        }
    if isinstance(value, (tuple, list)):
        return [_content(child) for child in value]
    return value


def semantic_content_digest(report: Report, *, artifact_root: Path) -> str:
    """Hash report meaning and asset bytes independently of presentation/location."""
    return hashlib.sha256(
        canonical_json(_content(_semantic(asdict(report), artifact_root)))
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class ReleaseResult:
    directory: Path
    pdf: Path
    manifest: Path
    validation: PDFValidationResult


def release_manifest(  # noqa: PLR0913
    report: Report,
    *,
    source_identity: str,
    source_revision: str | None,
    semantic_digest: str,
    build_epoch: int,
    compilation: CompilationResult,
    validation: PDFValidationResult,
    artifacts: Mapping[str, str],
) -> dict[str, object]:
    """Pure deterministic manifest construction for an exact artifact snapshot.

    Per-attempt compiler IDs remain in the retained compilation manifest, whose
    checksum is recorded. Equal input snapshots produce equal manifest bytes;
    the external TeX engine can produce different PDF/log bytes between runs.
    """
    validation.require_passed()
    metadata = report.metadata
    return {
        "schema_version": 1,
        "doc_type": metadata.doc_type,
        "doc_name": metadata.doc_name,
        "title": metadata.title,
        "report_version": metadata.version,
        "wood_reports_version": version("wood-reports"),
        "renderer": {"identity": "latex", "version": version("wood-reports")},
        "profile_version": metadata.profile_version,
        "profile": {
            "identity": metadata.doc_type,
            "revision": metadata.profile_version,
        },
        "brand": {
            "identity": report.theme.brand_identity,
            "revision": report.theme.brand_revision,
        },
        "theme": {
            "identity": report.theme.identity,
            "revision": report.theme.revision,
            "brand_revision": report.theme.brand_revision,
        },
        "source": {
            "identity": source_identity,
            "revision": source_revision,
            "semantic_sha256": semantic_digest,
        },
        "compiler": {
            "backend": "clsi",
            "engine": compilation.engine,
            "status": compilation.compiler_status,
            "manifest": "compilation/compilation.json",
        },
        "timestamp": datetime.fromtimestamp(build_epoch, UTC).isoformat(),
        "validation": {
            "status": "passed",
            "pages": validation.pages,
            "policy_version": 1,
            "overfull_limit_pt": 5.0,
        },
        "pdf": {"path": "delivered/report.pdf", "sha256": validation.pdf_sha256},
        "artifacts": dict(sorted(artifacts.items())),
    }


class ReleasePublisher:
    """Publish one immutable doc_name/version directory after every gate passes.

    Failed attempts remain only under .attempts for diagnosis. Existing versions
    are never replaced; retries after a failure use a new attempt automatically.
    """

    def publish(  # noqa: PLR0912, PLR0913, PLR0915
        self,
        report: Report,
        destination: Path,
        *,
        compiler: WorkspaceCompiler,
        artifact_root: Path,
        source_identity: str,
        build_epoch: int,
        source_revision: str | None = None,
        resource_urls: Mapping[str, str] | None = None,
    ) -> ReleaseResult:
        validate_release_report(report, artifact_root=artifact_root).require_passed()
        if (
            isinstance(build_epoch, bool)
            or not isinstance(build_epoch, int)
            or build_epoch < 0
        ):
            raise ValueError(
                "build_epoch must be an explicit nonnegative Unix timestamp"
            )
        # Validate the timestamp before creating output directories.
        datetime.fromtimestamp(build_epoch, UTC)
        if not source_identity.strip():
            raise ValueError("source_identity is required")
        name, report_version = report.metadata.doc_name, report.metadata.version
        if (
            not name
            or not report_version
            or any(
                re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", value) is None
                for value in (name, report_version)
            )
        ):
            raise ValueError("release name and version must be safe path components")
        final = destination / name / report_version
        if final.parent.is_symlink() or (destination / ".attempts").is_symlink():
            raise ValueError("release ownership directories cannot be symlinks")
        if final.exists() or final.is_symlink():
            raise FileExistsError(
                f"release already exists: {final}; use a new report version"
            )
        attempts = destination / ".attempts"
        attempts.mkdir(parents=True, exist_ok=True)
        attempt = Path(mkdtemp(prefix=f"{name}-", dir=attempts))
        source = attempt / "source"
        source.mkdir()
        semantic = canonical_json(_semantic(asdict(report), artifact_root))
        (source / "report.json").write_bytes(semantic)
        workspace = source / "workspace"
        LatexWorkspacePublisher().publish(
            report, workspace, artifact_root=artifact_root
        )
        inputs = read_workspace(workspace, resource_urls or {})
        fingerprints = inputs.fingerprints
        compilation = compiler.compile(
            workspace, attempt / "compilation", resource_urls=resource_urls
        )
        if compilation.engine != inputs.engine:
            raise ValueError("compiler engine does not match the workspace manifest")
        evidence_paths = (
            compilation.manifest,
            *compilation.logs,
            *((compilation.pdf,) if compilation.pdf is not None else ()),
        )
        for path in evidence_paths:
            if (
                path.is_symlink()
                or path.parent.resolve() != (attempt / "compilation").resolve()
            ):
                raise ValueError(
                    "compiler evidence must belong to this release attempt"
                )
        evidence_checksums = {path: sha256(path) for path in evidence_paths}
        validation = validate_pdf(compilation)
        (attempt / "validation.json").write_bytes(
            canonical_json({"passed": validation.passed, **asdict(validation)})
        )
        validation.require_passed()
        self._verify_compilation(compilation, fingerprints)
        if fingerprints != read_workspace(workspace, resource_urls or {}).fingerprints:
            raise ValueError("workspace changed during compilation")
        if semantic != canonical_json(_semantic(asdict(report), artifact_root)):
            raise ValueError("report assets changed during compilation")
        delivered = attempt / "delivered"
        delivered.mkdir()
        if compilation.pdf is None:
            raise ValueError("validated compilation must supply a PDF")
        shutil.copyfile(compilation.pdf, delivered / "report.pdf")
        artifacts = self._checksums(attempt)
        if artifacts["delivered/report.pdf"] != validation.pdf_sha256:
            raise ValueError("PDF changed after validation")
        manifest = release_manifest(
            report,
            source_identity=source_identity,
            source_revision=source_revision,
            semantic_digest=hashlib.sha256(
                canonical_json(_content(json.loads(semantic)))
            ).hexdigest(),
            build_epoch=build_epoch,
            compilation=compilation,
            validation=validation,
            artifacts=artifacts,
        )
        (attempt / "release.json").write_bytes(canonical_json(manifest))
        if artifacts != self._checksums(attempt):
            raise ValueError("release artifacts changed during packaging")
        if evidence_checksums != {path: sha256(path) for path in evidence_paths}:
            raise ValueError("compiler evidence changed after validation")
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists() or final.is_symlink():
            raise FileExistsError(f"release already exists: {final}")
        attempt.rename(final)
        return ReleaseResult(
            final, final / "delivered/report.pdf", final / "release.json", validation
        )

    @staticmethod
    def _checksums(directory: Path) -> dict[str, str]:
        checksums = {}
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise ValueError("release artifacts cannot be symlinks")
            if path.is_file() and path != directory / "release.json":
                checksums[path.relative_to(directory).as_posix()] = sha256(path)
        return checksums

    @staticmethod
    def _verify_compilation(
        compilation: CompilationResult, fingerprints: dict[str, str]
    ) -> None:
        record = json.loads(compilation.manifest.read_text(encoding="utf-8"))
        if (
            not isinstance(record, dict)
            or record.get("schema_version") != 1
            or record.get("backend") != "clsi"
            or record.get("status") != "success"
            or record.get("compiler_status") != "success"
            or record.get("engine") != compilation.engine
            or record.get("source_fingerprints") != fingerprints
            or record.get("logs") != [path.name for path in compilation.logs]
            or record.get("pdf")
            != (compilation.pdf.name if compilation.pdf is not None else None)
        ):
            raise ValueError(
                "compilation manifest does not attest to these workspace inputs"
            )
