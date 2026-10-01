import io
import json
from collections.abc import Mapping
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

import pytest

from wood_reports import (
    DriveFile,
    GoogleDriveReader,
    SourceCompilationError,
    compile_drive_report,
    get_profile,
)
from wood_reports.sources import drive_file_id


def source_text() -> str:
    profile = get_profile("decision-memo")
    return (
        "---\ndoc_type: decision-memo\ndoc_name: drive-example\n"
        "title: Drive example\n---\n"
        + "\n".join(
            f"## {section.title}\nAuthored content.\n"
            for section in profile.sections
            if section.identity in profile.required_section_variants[0]
        )
    )


class MemoryDriveReader:
    def __init__(self, *, folder: bool = False, count: int = 1) -> None:
        self.file = DriveFile("markdown-id", "report.md", "text/markdown")
        self.folder = folder
        self.count = count

    def metadata(self, file_id: str) -> DriveFile:
        assert file_id in {"markdown-id", "folder-id"}
        return (
            DriveFile("folder-id", "Report", "application/vnd.google-apps.folder")
            if self.folder
            else self.file
        )

    def report_files(self, folder_id: str) -> tuple[DriveFile, ...]:
        assert folder_id == "folder-id"
        return (self.file,) * self.count

    def read_text(self, file_id: str) -> str:
        assert file_id == "markdown-id"
        return source_text()


@pytest.mark.parametrize("folder", [False, True])
def test_drive_file_or_folder_uses_source_metadata_without_overrides(
    folder: bool, tmp_path: Path
) -> None:
    reference = (
        "https://drive.google.com/drive/folders/folder-id"
        if folder
        else "https://drive.google.com/file/d/markdown-id/view"
    )
    report = compile_drive_report(
        reference, MemoryDriveReader(folder=folder), artifact_root=tmp_path
    )
    assert report.metadata.doc_type == "decision-memo"
    assert report.metadata.doc_name == "drive-example"


def test_explicit_drive_metadata_override_is_optional(tmp_path: Path) -> None:
    report = compile_drive_report(
        "markdown-id", MemoryDriveReader(), artifact_root=tmp_path, doc_name="override"
    )
    assert report.metadata.doc_name == "override"


@pytest.mark.parametrize("count", [0, 2])
def test_drive_folder_ambiguity_is_not_guessed(count: int, tmp_path: Path) -> None:
    with pytest.raises(SourceCompilationError, match="exactly one"):
        compile_drive_report(
            "folder-id",
            MemoryDriveReader(folder=True, count=count),
            artifact_root=tmp_path,
        )


@pytest.mark.parametrize(
    ("name", "mime"),
    [
        ("report.docx", "text/plain"),
        ("report.md", "application/vnd.google-apps.document"),
    ],
)
def test_drive_requires_stored_markdown(name: str, mime: str, tmp_path: Path) -> None:
    reader = MemoryDriveReader()
    reader.file = DriveFile("markdown-id", name, mime)
    with pytest.raises(SourceCompilationError, match="stored Markdown"):
        compile_drive_report("markdown-id", reader, artifact_root=tmp_path)


@pytest.mark.parametrize(
    "reference",
    [
        "https://evil.example/file/d/token/view",
        "http://drive.google.com/file/d/token/view",
        "https://drive.google.com/invalid",
        "id' injected",
    ],
)
def test_drive_reference_must_be_a_canonical_id_or_url(
    reference: str, tmp_path: Path
) -> None:
    with pytest.raises(SourceCompilationError, match="Drive file/folder"):
        compile_drive_report(reference, MemoryDriveReader(), artifact_root=tmp_path)


def test_drive_identity_accepts_links_with_query_parameters() -> None:
    assert (
        drive_file_id("https://drive.google.com/file/d/markdown-id/view?usp=sharing")
        == "markdown-id"
    )


def test_google_drive_reader_builds_bounded_authenticated_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    queries: list[tuple[str, Mapping[str, str]]] = []

    def read(_self: GoogleDriveReader, path: str, query: Mapping[str, str]) -> bytes:
        queries.append((path, query))
        if query.get("alt") == "media":
            return b"\xef\xbb\xbfMarkdown"
        value: object = {
            "id": "markdown-id",
            "name": "report.md",
            "mimeType": "text/markdown",
        }
        if path == "files":
            value = {"files": [value]}
        return json.dumps(value).encode()

    monkeypatch.setattr(GoogleDriveReader, "_read", read)
    reader = GoogleDriveReader("secret-token")
    assert "secret-token" not in repr(reader)
    assert reader.metadata("markdown-id").name == "report.md"
    assert reader.report_files("folder-id")[0].identity == "markdown-id"
    assert reader.read_text("markdown-id") == "Markdown"
    assert (
        queries[1][1]["q"]
        == "'folder-id' in parents and name = 'report.md' and trashed = false"
    )
    assert queries[1][1]["pageSize"] == "100"


@pytest.mark.parametrize(
    "value",
    [
        [],
        {"invalid": "metadata"},
        {"id": "id", "name": "name", "mimeType": 1},
    ],
)
def test_invalid_drive_metadata_fails_explicitly(
    value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        GoogleDriveReader, "_read", lambda *_args: json.dumps(value).encode()
    )
    with pytest.raises(ValueError, match="invalid file metadata"):
        GoogleDriveReader("token").metadata("id")


@pytest.mark.parametrize(
    "value",
    [
        {"files": [], "nextPageToken": "next"},
        {"files": [], "incompleteSearch": True},
        {"files": "not-a-list"},
    ],
)
def test_incomplete_drive_search_does_not_claim_a_unique_result(
    value: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        GoogleDriveReader, "_read", lambda *_args: json.dumps(value).encode()
    )
    with pytest.raises(ValueError, match=r"incomplete|invalid folder"):
        GoogleDriveReader("token").report_files("folder")


@pytest.mark.parametrize(("token", "timeout"), [("", 30), ("token", 0)])
def test_drive_credentials_and_timeout_are_caller_owned(
    token: str, timeout: float
) -> None:
    with pytest.raises(ValueError, match="access token"):
        GoogleDriveReader(token, timeout)


def test_drive_http_transport_uses_bearer_token_and_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def open_request(request: Any, *, timeout: float) -> io.BytesIO:
        assert request.full_url.startswith(
            "https://www.googleapis.com/drive/v3/files/id?"
        )
        assert request.get_header("Authorization") == "Bearer token"
        assert timeout == 15
        return io.BytesIO(b"source")

    monkeypatch.setattr("wood_reports.sources.urlopen", open_request)
    assert GoogleDriveReader("token", 15).read_text("id") == "source"


@pytest.mark.parametrize(
    "failure",
    [
        HTTPError("https://example.com", 403, "Forbidden", Message(), None),
        URLError("offline"),
        TimeoutError("timed out"),
    ],
)
def test_drive_transport_failures_have_actionable_nonsecret_errors(
    failure: Exception, monkeypatch: pytest.MonkeyPatch
) -> None:
    def open_request(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr("wood_reports.sources.urlopen", open_request)
    with pytest.raises(ValueError, match="Drive read") as error:
        GoogleDriveReader("secret-token").read_text("id")
    assert "secret-token" not in str(error.value)


def test_drive_input_size_is_bounded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "wood_reports.sources.urlopen",
        lambda *_args, **_kwargs: io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)),
    )
    with pytest.raises(ValueError, match="5 MiB"):
        GoogleDriveReader("token").read_text("id")
