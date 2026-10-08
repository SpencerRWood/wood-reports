"""Resolve local or authenticated Drive Markdown without owning authoring metadata."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from wood_reports.compiler import SourceCompilationError, TemplateValues
from wood_reports.markdown import MarkdownReportCompiler
from wood_reports.model import Report

_FOLDER = "application/vnd.google-apps.folder"
_MARKDOWN = {"text/markdown", "text/plain", "text/x-markdown"}
_MAX_SOURCE_BYTES = 5 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class DriveFile:
    identity: str
    name: str
    mime_type: str


class DriveReader(Protocol):
    """Caller-supplied authenticated read surface; independent of Wood Tools."""

    def metadata(self, file_id: str) -> DriveFile: ...

    def report_files(self, folder_id: str) -> tuple[DriveFile, ...]: ...

    def read_text(self, file_id: str) -> str: ...


def drive_file_id(reference: str) -> str:
    """Accept a raw ID or a canonical Drive file/folder URL."""
    if re.fullmatch(r"[A-Za-z0-9_-]+", reference):
        return reference
    parsed = urlparse(reference)
    if parsed.scheme == "https" and parsed.netloc == "drive.google.com":
        match = re.fullmatch(
            r"/(?:file/d|drive/folders)/([A-Za-z0-9_-]+)(?:/view)?/?", parsed.path
        )
        if match:
            return match[1]
    raise ValueError("expected a Drive file/folder URL or raw file ID")


@dataclass(frozen=True, slots=True)
class GoogleDriveReader:
    """Read stored Markdown with a caller-managed OAuth access token.

    The caller owns token acquisition/refresh. Tokens are never serialized into
    source metadata, errors, models, or manifests.
    """

    access_token: str = field(repr=False)
    timeout_seconds: float = 30

    def __post_init__(self) -> None:
        if not self.access_token.strip() or self.timeout_seconds <= 0:
            raise ValueError("Drive requires an access token and positive timeout")

    def _read(self, path: str, query: Mapping[str, str]) -> bytes:
        request = Request(
            f"https://www.googleapis.com/drive/v3/{path}?{urlencode(query)}",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:  # noqa: S310
                payload = response.read(_MAX_SOURCE_BYTES + 1)
        except HTTPError as error:
            error.close()
            raise ValueError(
                f"Drive read failed (HTTP {error.code}); check access and token"
            ) from None
        except (URLError, TimeoutError) as error:
            raise ValueError(
                "Drive read unavailable; check connection and timeout"
            ) from error
        if len(payload) > _MAX_SOURCE_BYTES:
            raise ValueError("Drive source exceeds the 5 MiB input limit")
        return cast(bytes, payload)

    def _json(self, path: str, query: Mapping[str, str]) -> dict[str, object]:
        value = json.loads(self._read(path, query))
        if not isinstance(value, dict):
            raise ValueError("Drive returned invalid file metadata")
        return value

    @staticmethod
    def _file(value: object) -> DriveFile:
        if not isinstance(value, dict) or not all(
            isinstance(value.get(key), str) for key in ("id", "name", "mimeType")
        ):
            raise ValueError("Drive returned invalid file metadata")
        return DriveFile(value["id"], value["name"], value["mimeType"])

    def metadata(self, file_id: str) -> DriveFile:
        identity = drive_file_id(file_id)
        return self._file(
            self._json(
                f"files/{identity}",
                {
                    "fields": "id,name,mimeType",
                    "supportsAllDrives": "true",
                },
            )
        )

    def report_files(self, folder_id: str) -> tuple[DriveFile, ...]:
        identity = drive_file_id(folder_id)
        response = self._json(
            "files",
            {
                "q": f"'{identity}' in parents "
                "and name = 'report.md' and trashed = false",
                "fields": "files(id,name,mimeType),nextPageToken,incompleteSearch",
                "pageSize": "100",
                "includeItemsFromAllDrives": "true",
                "supportsAllDrives": "true",
            },
        )
        if response.get("nextPageToken") or response.get("incompleteSearch"):
            raise ValueError(
                "Drive folder search is incomplete; select an explicit Markdown file"
            )
        values = response.get("files")
        if not isinstance(values, list):
            raise ValueError("Drive returned invalid folder contents")
        return tuple(self._file(value) for value in values)

    def read_text(self, file_id: str) -> str:
        identity = drive_file_id(file_id)
        return self._read(
            f"files/{identity}", {"alt": "media", "supportsAllDrives": "true"}
        ).decode("utf-8-sig")


def read_drive_markdown(reference: str, reader: DriveReader) -> tuple[Path, str]:
    """Resolve one stored Markdown source without changing its authoring content."""
    source = Path("drive-report.md")
    try:
        file = reader.metadata(drive_file_id(reference))
        if file.mime_type == _FOLDER:
            matches = reader.report_files(file.identity)
            if len(matches) != 1 or matches[0].name != "report.md":
                raise ValueError(
                    "Drive folder must contain exactly one report.md; "
                    "select an explicit file if ambiguous"
                )
            file = matches[0]
        source = Path(f"drive-{file.identity}.md")
        if file.mime_type not in _MARKDOWN or not file.name.lower().endswith(".md"):
            raise ValueError(
                "Drive input must be a stored Markdown file (.md), "
                "not a native Google Doc"
            )
        text = reader.read_text(file.identity)
    except (ValueError, OSError) as error:
        raise SourceCompilationError(source, "drive", str(error)) from error
    return source, text


def compile_drive_report(  # noqa: PLR0913
    reference: str,
    reader: DriveReader,
    *,
    artifact_root: Path,
    values: TemplateValues | None = None,
    doc_type: str | None = None,
    doc_name: str | None = None,
) -> Report:
    """Resolve one report.md; validate charts against caller-provided artifacts."""
    source, text = read_drive_markdown(reference, reader)
    return MarkdownReportCompiler(values).compile_text(
        text,
        source=source,
        artifact_root=artifact_root,
        doc_type=doc_type,
        doc_name=doc_name,
    )
