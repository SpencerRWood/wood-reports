"""Publish generated LaTeX sources without taking ownership of extensions."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from wood_reports.latex import LatexRenderer
from wood_reports.model import Report


class LatexWorkspaceError(ValueError):
    """Raised when a workspace layout would blur its ownership boundary."""


class LatexWorkspacePublisher:
    """Publish a self-contained, mutable LaTeX source workspace.

    ``generated`` is owned exclusively by Wood Reports and is replaced on each
    publication.  ``extensions`` is reserved for human-maintained files and is
    never created, removed, or modified by this publisher.  A synchronization
    service can consequently copy the whole workspace without needing a Wood
    Reports-specific integration.
    """

    def __init__(
        self,
        renderer: LatexRenderer | None = None,
        *,
        generated_directory: str = "generated",
        extensions_directory: str = "extensions",
    ) -> None:
        self._renderer = renderer or LatexRenderer()
        self._generated_directory = self._directory_name(generated_directory)
        self._extensions_directory = self._directory_name(extensions_directory)
        if self._generated_directory == self._extensions_directory:
            raise LatexWorkspaceError(
                "generated and human-maintained directories must differ"
            )

    def publish(self, report: Report, workspace: Path, *, artifact_root: Path) -> Path:
        """Render ``report`` and its chart assets into the generated source tree.

        The returned path is the generated ``report.tex``.  Existing extension
        files remain untouched, including when the generated tree is replaced.
        """
        report.validate(artifact_root)
        workspace = workspace.absolute()
        generated = workspace / self._generated_directory
        extensions = workspace / self._extensions_directory
        if generated.is_symlink() or extensions.is_symlink():
            raise LatexWorkspaceError(
                "workspace ownership directories cannot be symlinks"
            )
        if generated.exists() and not generated.is_dir():
            raise LatexWorkspaceError(f"generated path is not a directory: {generated}")
        if generated.exists():
            self._check_generated(generated)

        workspace.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=workspace, prefix=".wood-reports-") as temporary:
            staging = Path(temporary) / self._generated_directory
            staging.mkdir()
            (staging / "build").mkdir()
            self._renderer.render(
                report,
                staging / "report.tex",
                artifact_root=artifact_root,
            )
            source = staging / "report.tex"
            text = source.read_text(encoding="utf-8")
            preamble_text, body_text = text.split(r"\begin{document}", 1)
            document_class, components = preamble_text.split("\n", 1)
            (staging / "components.tex").write_text(components, encoding="utf-8")
            (staging / "assets").mkdir(exist_ok=True)
            (staging / "assets" / "brand.svg").write_text(
                report.theme.wordmark_svg, encoding="utf-8"
            )
            text = (
                document_class
                + "\n"
                + r"\input{components.tex}"
                + "\n"
                + r"\begin{document}"
                + body_text
            )
            preamble = (
                f"\\InputIfFileExists{{../{self._extensions_directory}/preamble.tex}}"
                "{}{}"
            )
            body = (
                f"\\InputIfFileExists{{../{self._extensions_directory}/body.tex}}"
                "{}{}"
            )
            source.write_text(
                text.replace(
                    r"\begin{document}", preamble + "\n" + r"\begin{document}"
                ).replace(r"\end{document}", body + "\n" + r"\end{document}"),
                encoding="utf-8",
            )
            document = asdict(report.metadata)
            document.pop("renderer_hints")
            manifest = {
                "schema_version": 1,
                "entrypoint": f"{self._generated_directory}/report.tex",
                "engine": "lualatex",
                "build": {
                    "working_directory": self._generated_directory,
                    "argv": [
                        "lualatex",
                        "-no-shell-escape",
                        "-interaction=nonstopmode",
                        "-halt-on-error",
                        "-output-directory=build",
                        "report.tex",
                    ],
                    "passes": 2,
                    "output_directory": f"{self._generated_directory}/build",
                },
                "profile": {
                    "identity": report.metadata.doc_type,
                    "version": report.metadata.profile_version,
                },
                "brand": {
                    "identity": report.theme.brand_identity,
                    "revision": report.theme.brand_revision,
                    "asset": "assets/brand.svg",
                    "font_policy": report.theme.branding.font_policy,
                },
                "document": document,
                "theme": asdict(report.theme),
                "ownership": {
                    "generated": self._generated_directory,
                    "human": self._extensions_directory,
                },
                "files": self._fingerprints(staging),
            }
            (staging / "workspace.json").write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            if generated.exists():
                shutil.rmtree(generated)
            staging.replace(generated)
        return generated / "report.tex"

    @staticmethod
    def _fingerprints(directory: Path) -> dict[str, str]:
        result = {}
        for path in sorted(directory.rglob("*")):
            if path.is_symlink():
                raise LatexWorkspaceError("generated files cannot be symlinks")
            if path.relative_to(directory).parts[0] == "build":
                continue
            if path.is_file() and path != directory / "workspace.json":
                result[path.relative_to(directory).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        return result

    def _check_generated(self, generated: Path) -> None:
        try:
            manifest = json.loads((generated / "workspace.json").read_text())
            valid = (
                manifest["schema_version"] == 1
                and manifest["ownership"]
                == {
                    "generated": self._generated_directory,
                    "human": self._extensions_directory,
                }
                and manifest["files"] == self._fingerprints(generated)
            )
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise LatexWorkspaceError(
                "generated tree has no valid ownership manifest; move it aside first"
            ) from error
        if not valid:
            raise LatexWorkspaceError(
                "generated tree was modified; move edits to extensions "
                "before publishing"
            )

    @staticmethod
    def _directory_name(name: str) -> str:
        path = Path(name)
        if (
            not name
            or path.is_absolute()
            or len(path.parts) != 1
            or name in {".", ".."}
            or re.fullmatch(r"[A-Za-z0-9_-]+", name) is None
        ):
            raise LatexWorkspaceError(
                "workspace directory names must be single relative paths"
            )
        return name
