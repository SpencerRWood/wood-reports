"""Validate and snapshot portable compiler inputs before any remote execution."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from wood_reports.compilation import validated_url

MAX_WORKSPACE_BYTES = 12 * 1024 * 1024
MAX_REQUEST_BYTES = 16 * 1024 * 1024
MAX_FILES = 1000
ENGINES = {"lualatex", "xelatex", "pdflatex", "latex"}


def relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("workspace paths must be relative POSIX paths")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in value.split("/")):
        raise ValueError("workspace paths cannot escape the workspace")
    return value


@dataclass(frozen=True, slots=True)
class CompilationInputs:
    engine: str
    entrypoint: str
    resources: tuple[dict[str, str], ...]
    fingerprints: dict[str, str]
    flags: tuple[str, ...] = ()


def _manifest(workspace: Path) -> tuple[str, str, PurePosixPath]:
    if workspace.is_symlink() or not workspace.is_dir():
        raise ValueError("workspace must be a regular directory")
    manifests = list(workspace.glob("*/workspace.json"))
    if len(manifests) != 1:
        raise ValueError("workspace requires one generated/workspace.json manifest")
    manifest_path = manifests[0]
    if (
        manifest_path.is_symlink()
        or manifest_path.parent.is_symlink()
        or manifest_path.stat().st_size > 1024 * 1024
    ):
        raise ValueError("workspace manifest is invalid or too large")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported workspace manifest schema")
    entrypoint = relative_path(manifest.get("entrypoint"))
    engine = manifest.get("engine")
    if not isinstance(engine, str) or engine not in ENGINES:
        raise ValueError("workspace engine is not supported by CLSI")
    build = manifest.get("build")
    if not isinstance(build, dict):
        raise ValueError("workspace requires build metadata")
    output = PurePosixPath(relative_path(build.get("output_directory")))
    return entrypoint, engine, output


def _resource(name: str, content: bytes, urls: Mapping[str, str]) -> dict[str, str]:
    if name in urls:
        return {"path": name, "url": validated_url(urls[name], allow_http=True)}
    try:
        text = content.decode("utf-8")
        if "\x00" in text:
            raise UnicodeError
    except UnicodeError:
        raise ValueError(
            f"binary resource {name} requires a caller-published URL reachable by CLSI"
        ) from None
    return {"path": name, "content": text}


def read_workspace(
    workspace: Path, resource_urls: Mapping[str, str]
) -> CompilationInputs:
    """Include generated and human source files, excluding disposable builds."""
    entrypoint, engine, output = _manifest(workspace)
    fingerprints: dict[str, str] = {}
    resources: list[dict[str, str]] = []
    total = 0
    for path in sorted(workspace.rglob("*")):
        name = path.relative_to(workspace).as_posix()
        if path.is_symlink():
            raise ValueError("workspace cannot contain symlinks")
        if PurePosixPath(name).is_relative_to(output):
            continue
        if path.is_dir():
            continue
        if not path.is_file():
            raise ValueError("workspace must contain only regular files")
        relative_path(name)
        if (
            path.stat().st_size + total > MAX_WORKSPACE_BYTES
            or len(resources) >= MAX_FILES
        ):
            raise ValueError("workspace exceeds compilation input limits")
        with path.open("rb") as source:
            content = source.read(MAX_WORKSPACE_BYTES - total + 1)
        total += len(content)
        if total > MAX_WORKSPACE_BYTES:
            raise ValueError("workspace changed or exceeded compilation input limits")
        fingerprints[name] = hashlib.sha256(content).hexdigest()
        resources.append(_resource(name, content, resource_urls))
    if entrypoint not in fingerprints or PurePosixPath(entrypoint).suffix != ".tex":
        raise ValueError("workspace entrypoint must identify an included .tex file")
    if set(resource_urls) - fingerprints.keys():
        raise ValueError("resource URLs refer to files outside the compilation inputs")
    configuration = str(PurePosixPath(entrypoint).parent / "latexmkrc")
    flags = ("-r", configuration) if configuration in fingerprints else ()
    return CompilationInputs(engine, entrypoint, tuple(resources), fingerprints, flags)
