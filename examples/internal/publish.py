"""Execute the internal corpus through the installed native report CLI.

This consumer script owns no rendering, compiler, branding or validation logic.
The final checksum audit independently checks the artifacts the release API made.
"""

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

CORPUS = Path(__file__).resolve().parent
PROFILES = ("project-brief", "analytics-report", "assessment-report", "decision-memo")


def command(output: Path, name: str, arguments: list[str]) -> dict:
    result = subprocess.run(  # noqa: S603 -- fixed executable, argument list, no shell
        [sys.executable, "-m", "wood_reports", *arguments, "--json"],
        capture_output=True,
        text=True,
        timeout=150,
        check=False,
    )
    (output / f"{name}.json").write_text(result.stdout, encoding="utf-8")
    (output / f"{name}.stderr.log").write_text(result.stderr, encoding="utf-8")
    payload = json.loads(result.stdout)
    if result.returncode or payload.get("status") != "success":
        raise RuntimeError(f"{name} failed; inspect {output / (name + '.json')}")
    return payload["data"]


def audit_release(directory: Path) -> dict:
    manifest = json.loads((directory / "release.json").read_text())
    for relative, expected in manifest["artifacts"].items():
        path = directory / relative
        if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
            raise ValueError("artifact escaped its immutable release directory")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"artifact checksum mismatch: {relative}")
    pdf = directory / manifest["pdf"]["path"]
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if digest != manifest["pdf"]["sha256"]:
        raise ValueError("delivered PDF digest mismatch")
    if manifest["validation"]["status"] != "passed":
        raise ValueError("release PDF validation did not pass")
    return {
        "pdf": str(pdf),
        "manifest": str(directory / "release.json"),
        "pdf_sha256": digest,
        "pages": manifest["validation"]["pages"],
        "checked_artifacts": len(manifest["artifacts"]),
    }


def publish(args: argparse.Namespace) -> dict:
    if args.action == "release" and (
        args.build_epoch is None or args.resource_urls is None
    ):
        raise ValueError("release requires --build-epoch and --resource-urls")
    # Never reuse a populated attempt or overwrite a known-good corpus.
    args.output.mkdir(parents=True, exist_ok=False)
    documents = {}
    for profile in PROFILES:
        command(args.output, f"{profile}-profile", ["profile", "show", profile])
        validated = command(
            args.output,
            f"{profile}-source",
            ["validate", str(CORPUS / f"{profile}.md"), "--artifact-root", str(CORPUS)],
        )
        if validated["document"]["doc_type"] != profile:
            raise ValueError(f"unexpected profile for {profile}")
        documents[profile] = {"source_validation": "passed"}
    # All sources must pass before the first remote compilation.
    if args.action == "release":
        for profile in PROFILES:
            arguments = [
                "build",
                str(CORPUS / f"{profile}.md"),
                "--release",
                "--artifact-root",
                str(CORPUS),
                "--config",
                str(CORPUS / "pyproject.toml"),
                "--output",
                str(args.output / "releases"),
                "--build-epoch",
                str(args.build_epoch),
            ]
            if args.source_revision:
                arguments += ["--source-revision", args.source_revision]
            if profile == "analytics-report":
                arguments += ["--resource-urls", str(args.resource_urls)]
            released = command(args.output, f"{profile}-release", arguments)
            documents[profile].update(audit_release(Path(released["directory"])))
    return {"status": "passed", "action": args.action, "documents": documents}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "release"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-epoch", type=int)
    parser.add_argument("--source-revision")
    parser.add_argument("--resource-urls", type=Path)
    options = parser.parse_args()
    try:
        summary = publish(options)
    except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as error:
        print(json.dumps({"status": "failed", "error": str(error)}))  # noqa: T201
        raise SystemExit(1) from error
    (options.output / "corpus.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, sort_keys=True))  # noqa: T201
