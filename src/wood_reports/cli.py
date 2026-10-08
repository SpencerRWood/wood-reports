"""Thin native command interface; report-domain behavior lives in Python APIs."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import cast

from wood_reports.clsi import CLSICompiler
from wood_reports.compilation import CLSIConfig, CLSICredentials, CompilationError
from wood_reports.pdf_validation import PDFValidationError
from wood_reports.profiles import get_profile, list_profiles
from wood_reports.publication import PublicationAPI
from wood_reports.sources import GoogleDriveReader


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="wood-report")
    commands = parser.add_subparsers(dest="command", required=True)
    profile = commands.add_parser(
        "profile", help="Inspect installed document contracts"
    )
    profiles = profile.add_subparsers(dest="profile_command", required=True)
    profiles.add_parser("list").add_argument("--json", action="store_true")
    show = profiles.add_parser("show")
    show.add_argument("doc_type")
    show.add_argument("--json", action="store_true")
    create = commands.add_parser("create", help="Scaffold or import report Markdown")
    create.add_argument("--profile", dest="doc_type")
    create.add_argument("--name", dest="doc_name")
    create.add_argument("--drive", metavar="REFERENCE")
    create.add_argument("--output", required=True, type=Path)
    create.add_argument("--artifact-root", type=Path)
    create.add_argument("--json", action="store_true")
    for name in ("validate", "preview", "build"):
        command = commands.add_parser(name)
        command.add_argument("source", help="Markdown path or Drive reference")
        command.add_argument("--drive", action="store_true")
        command.add_argument("--artifact-root", type=Path)
        command.add_argument("--json", action="store_true")
        if name != "validate":
            command.add_argument("--output", required=True, type=Path)
            command.add_argument("--config", type=Path, default=Path("pyproject.toml"))
            command.add_argument("--resource-urls", type=Path)
        if name == "build":
            command.add_argument("--release", action="store_true")
            command.add_argument("--build-epoch", type=int)
            command.add_argument("--source-revision")
    return parser


def _reader() -> GoogleDriveReader:
    token = os.environ.get("WOOD_REPORTS_DRIVE_ACCESS_TOKEN", "")
    if not token:
        raise ValueError("inject WOOD_REPORTS_DRIVE_ACCESS_TOKEN for Drive sources")
    return GoogleDriveReader(token)


def _compiler(config: Path) -> CLSICompiler:
    names = ("WOOD_REPORTS_CLSI_USERNAME", "WOOD_REPORTS_CLSI_PASSWORD")
    values = tuple(os.environ.get(name, "") for name in names)
    if not all(values):
        raise ValueError("inject " + " and ".join(names) + " for compilation")
    return CLSICompiler(CLSIConfig.from_pyproject(config), CLSICredentials(*values))


def _resources(path: Path | None) -> dict[str, str] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(
        isinstance(key, str) and isinstance(url, str) for key, url in value.items()
    ):
        raise ValueError("resource URLs must be a JSON object mapping paths to URLs")
    return cast(dict[str, str], value)


def _execute(args: argparse.Namespace, api: PublicationAPI) -> dict[str, object]:
    if args.command == "profile":
        if args.profile_command == "list":
            return {"profiles": [asdict(profile) for profile in list_profiles()]}
        return {"profile": asdict(get_profile(args.doc_type))}
    if args.command == "create":
        path = api.create(
            args.output,
            doc_type=args.doc_type,
            doc_name=args.doc_name,
            drive_reference=args.drive,
            reader=_reader() if args.drive else None,
            artifact_root=args.artifact_root,
        )
        return {"source": str(path)}
    reader = _reader() if args.drive else None
    if args.command == "validate":
        report = api.validate(
            args.source, artifact_root=args.artifact_root, reader=reader
        )
        return {"validation_scope": "source", "document": asdict(report.metadata)}
    if args.command == "build" and args.release:
        epoch = args.build_epoch
        if epoch is None:
            configured = os.environ.get("SOURCE_DATE_EPOCH")
            if configured is None:
                raise ValueError("release requires --build-epoch or SOURCE_DATE_EPOCH")
            epoch = int(configured)
        released = api.release(
            args.source,
            args.output,
            compiler=_compiler(args.config),
            build_epoch=epoch,
            artifact_root=args.artifact_root,
            reader=reader,
            source_revision=args.source_revision,
            resource_urls=_resources(args.resource_urls),
        )
        return {
            "release": True,
            "directory": str(released.directory),
            "pdf": str(released.pdf),
            "manifest": str(released.manifest),
            "validation": asdict(released.validation),
        }
    result = api.preview(
        args.source,
        args.output,
        compiler=_compiler(args.config),
        artifact_root=args.artifact_root,
        reader=reader,
        resource_urls=_resources(args.resource_urls),
    )
    compilation = asdict(result.compilation)
    return {"compilation": compilation, "warnings": result.warnings, "release": False}


def main(argv: list[str] | None = None) -> int:
    """Return 0 on success, 1 on operation failure, 2 on invalid CLI syntax."""
    args = _parser().parse_args(argv)
    payload: dict[str, object] = {
        "schema_version": 1,
        "command": args.command,
        "status": "success",
    }
    code = 0
    try:
        payload["data"] = _execute(args, PublicationAPI())
    except CompilationError as error:
        payload.update(status="failed", error=str(error), data=asdict(error.result))
        code = 1
    except PDFValidationError as error:
        payload.update(
            status="failed", error=str(error), data={"validation": asdict(error.result)}
        )
        code = 1
    except (ValueError, OSError) as error:
        payload.update(status="failed", error=str(error))
        code = 1
    if args.json:
        print(json.dumps(payload, sort_keys=True, default=str))  # noqa: T201
    elif code:
        print(f"{args.command}: {payload['error']}")  # noqa: T201
    else:
        print(json.dumps(payload["data"], indent=2, default=str))  # noqa: T201
    return code
