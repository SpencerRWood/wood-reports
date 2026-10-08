from __future__ import annotations

import http.client
import json
import time
from collections.abc import Mapping
from pathlib import Path

import pytest

from wood_reports import (
    CLSICompiler,
    CLSIConfig,
    CLSICredentials,
    CompilationError,
    LatexWorkspacePublisher,
    Narrative,
    Report,
    ReportMetadata,
    Section,
    WorkspaceCompiler,
    clsi,
    clsi_workspace,
)
from wood_reports.clsi import HTTPResponse
from wood_reports.clsi_workspace import read_workspace, relative_path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    report = Report(
        ReportMetadata("Internal test"), (Section("Results", (Narrative("OK"),)),)
    )
    LatexWorkspacePublisher().publish(report, workspace, artifact_root=tmp_path)
    extension = workspace / "extensions" / "body.tex"
    extension.parent.mkdir()
    extension.write_text("Human-maintained extension")
    (workspace / "generated" / "build" / "stale.pdf").write_bytes(b"stale")
    return workspace


class Transport:
    def __init__(self) -> None:
        self.requests: list[
            tuple[str, str, Mapping[str, str], bytes | None, float]
        ] = []
        self.status = "success"
        self.http_status = 200
        self.cleanup_status = 204
        self.pdf = b"%PDF-test"
        self.log = b"Useful compiler diagnostic\n"
        self.error: Exception | None = None
        self.unsafe_url: str | None = None
        self.extra_outputs: list[object] = []
        self.response_body: bytes | None = None
        self.missing_pdf = False
        self.duplicate_pdf = False

    def request(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        deadline: float,
        max_bytes: int,
    ) -> HTTPResponse:
        assert 0 < max_bytes <= 32 * 1024 * 1024
        self.requests.append((method, url, headers, body, deadline))
        if method == "DELETE":
            return HTTPResponse(self.cleanup_status, b"")
        if self.error:
            raise self.error
        if method == "POST":
            base = url.removesuffix("/compile")
            outputs: list[object] = [
                {"type": "log", "url": base + "/build/test/output/output.log"}
            ]
            if not self.missing_pdf:
                outputs.append(
                    {
                        "type": "pdf",
                        "url": self.unsafe_url
                        or base + "/build/test/output/output.pdf",
                    }
                )
            outputs.extend(self.extra_outputs)
            if self.duplicate_pdf:
                outputs.append(outputs[-1])
            response = self.response_body
            if response is None:
                response = json.dumps(
                    {"compile": {"status": self.status, "outputFiles": outputs}}
                ).encode()
            return HTTPResponse(self.http_status, response)
        return HTTPResponse(200, self.pdf if url.endswith(".pdf") else self.log)


def compiler(transport: Transport) -> CLSICompiler:
    return CLSICompiler(
        CLSIConfig("https://clsi.example", 10),
        CLSICredentials("fixture", "private"),
        transport=transport,
    )


def test_complete_workspace_authenticates_every_request_and_preserves_source(
    workspace: Path, tmp_path: Path
) -> None:
    transport = Transport()
    backend: WorkspaceCompiler = compiler(transport)
    before = {
        p.relative_to(workspace): p.read_bytes()
        for p in workspace.rglob("*")
        if p.is_file()
    }
    result = backend.compile(workspace, tmp_path / "output")
    assert result.status == "success"
    assert result.compiler_status == "success"
    assert result.pdf is not None
    assert result.pdf.read_bytes() == transport.pdf
    assert result.logs[0].read_text() == "Useful compiler diagnostic\n"
    payload = json.loads(transport.requests[0][3] or b"")["compile"]
    assert payload["rootResourcePath"] == "generated/report.tex"
    assert payload["options"] == {
        "compiler": "lualatex",
        "timeout": 8,
        "stopOnFirstError": True,
        "syncType": "full",
    }
    resources = {item["path"]: item for item in payload["resources"]}
    assert resources["extensions/body.tex"]["content"] == "Human-maintained extension"
    assert "generated/workspace.json" in resources
    assert "generated/build/stale.pdf" not in resources
    assert all(
        request[2]["Authorization"] == "Basic Zml4dHVyZTpwcml2YXRl"
        for request in transport.requests
    )
    assert all(
        request[2]["User-Agent"] == "Wood-Reports-CLSI/1.0"
        for request in transport.requests
    )
    assert transport.requests[-1][0] == "DELETE"
    assert transport.requests[-1][1] == transport.requests[0][1].removesuffix(
        "/compile"
    )
    assert len({request[4] for request in transport.requests[:-1]}) == 1
    assert before == {
        p.relative_to(workspace): p.read_bytes()
        for p in workspace.rglob("*")
        if p.is_file()
    }
    record = json.loads(result.manifest.read_text())
    assert record["pdf"] == "report.pdf"
    assert "private" not in result.manifest.read_text()
    assert record["source_fingerprints"]["extensions/body.tex"]


def test_binary_resources_use_explicit_publisher_urls_without_serializing_them(
    workspace: Path, tmp_path: Path
) -> None:
    binary = workspace / "extensions" / "chart.png"
    binary.write_bytes(b"\x00\xff\x80")
    with pytest.raises(ValueError, match="caller-published"):
        compiler(Transport()).compile(workspace, tmp_path / "missing")
    transport = Transport()
    result = compiler(transport).compile(
        workspace,
        tmp_path / "output",
        resource_urls={
            "extensions/chart.png": "https://assets.example/chart.png?signature=private-token"
        },
    )
    payload = json.loads(transport.requests[0][3] or b"")["compile"]
    resource = next(
        item for item in payload["resources"] if item["path"] == "extensions/chart.png"
    )
    assert resource == {
        "path": "extensions/chart.png",
        "url": "https://assets.example/chart.png?signature=private-token",
    }
    assert "private-token" not in result.manifest.read_text()


@pytest.mark.parametrize(
    "status",
    [
        "error",
        "failure",
        "timedout",
        "stopped-on-first-error",
        "terminated",
        "compile-in-progress",
        "retry",
        "unavailable",
        "validation-root",
    ],
)
def test_compiler_failure_keeps_logs_and_never_downloads_or_publishes_pdf(
    workspace: Path, tmp_path: Path, status: str
) -> None:
    transport = Transport()
    transport.status = status
    with pytest.raises(CompilationError, match=status) as error:
        compiler(transport).compile(workspace, tmp_path / "failed")
    result = error.value.result
    assert result.status == "failed"
    assert result.compiler_status == status
    assert result.pdf is None
    assert result.logs[0].exists()
    assert not (tmp_path / "failed" / "report.pdf").exists()
    assert not any(
        request[0] == "GET" and request[1].endswith(".pdf")
        for request in transport.requests
    )
    assert transport.requests[-1][0] == "DELETE"


@pytest.mark.parametrize(
    ("status", "action"),
    [
        (401, "credentials"),
        (403, "allowlisting"),
        (404, "editor"),
        (413, "size"),
        (429, "capacity"),
        (502, "health"),
        (504, "timeout"),
        (302, "logs"),
    ],
)
def test_http_errors_are_actionable_and_cleanup_is_attempted(
    workspace: Path, tmp_path: Path, status: int, action: str
) -> None:
    transport = Transport()
    transport.http_status = status
    with pytest.raises(CompilationError, match=action) as error:
        compiler(transport).compile(workspace, tmp_path / "failed")
    assert error.value.result.compiler_status == "unavailable"
    assert error.value.result.manifest.exists()
    assert transport.requests[-1][0] == "DELETE"


@pytest.mark.parametrize("failure", [TimeoutError("sensitive"), OSError("sensitive")])
def test_transport_failures_are_sanitized_and_cleanup_has_a_separate_budget(
    workspace: Path, tmp_path: Path, failure: Exception
) -> None:
    transport = Transport()
    transport.error = failure
    with pytest.raises(CompilationError) as error:
        compiler(transport).compile(workspace, tmp_path / "failed")
    assert "sensitive" not in str(error.value)
    assert "sensitive" not in error.value.result.manifest.read_text()
    assert 0 < transport.requests[-1][4] - time.monotonic() <= 5


@pytest.mark.parametrize(
    "url",
    [
        "https://attacker.example/project/x/file.pdf",
        "http://clsi.example/file.pdf",
        "https://clsi.example/project/other/file.pdf",
        "https://user:secret@clsi.example/file.pdf",
    ],
)
def test_unsafe_output_is_never_requested(
    workspace: Path, tmp_path: Path, url: str
) -> None:
    transport = Transport()
    transport.unsafe_url = url
    with pytest.raises(CompilationError):
        compiler(transport).compile(workspace, tmp_path / "failed")
    assert [request[0] for request in transport.requests] == ["POST", "DELETE"]


@pytest.mark.parametrize(
    "scenario",
    [
        "missing",
        "invalid",
        "duplicate",
        "cleanup",
        "metadata",
        "json",
        "status",
        "oversized",
        "fatal-log",
    ],
)
def test_invalid_results_never_publish_pdf(
    workspace: Path, tmp_path: Path, scenario: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = Transport()
    if scenario == "missing":
        transport.missing_pdf = True
    elif scenario == "invalid":
        transport.pdf = b"not a PDF"
    elif scenario == "duplicate":
        transport.duplicate_pdf = True
    elif scenario == "cleanup":
        transport.cleanup_status = 500
    elif scenario == "metadata":
        transport.extra_outputs = [None]
    elif scenario == "json":
        transport.response_body = b"not json"
    elif scenario == "status":
        transport.status = "unknown"
    elif scenario == "fatal-log":
        transport.log = b"! Undefined control sequence.\nFatal error occurred\n"
    else:
        monkeypatch.setattr(clsi, "_MAX_PDF_BYTES", 2)
    with pytest.raises(CompilationError) as error:
        compiler(transport).compile(workspace, tmp_path / "failed")
    assert error.value.result.pdf is None
    assert not (tmp_path / "failed" / "report.pdf").exists()


def test_success_without_a_tex_log_is_rejected(workspace: Path, tmp_path: Path) -> None:
    transport = Transport()
    original = CLSICompiler._output
    # Retain stdout but omit the TeX log from the server's response contract.
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            CLSICompiler,
            "_output",
            staticmethod(
                lambda output, base: (
                    ("stdout", original(output, base)[1])
                    if isinstance(output, dict) and output.get("type") == "log"
                    else original(output, base)
                )
            ),
        )
        with pytest.raises(CompilationError, match="lacks the TeX log"):
            compiler(transport).compile(workspace, tmp_path / "failed")


def test_existing_destination_is_never_replaced(
    workspace: Path, tmp_path: Path
) -> None:
    destination = tmp_path / "previous"
    destination.mkdir()
    previous = destination / "report.pdf"
    previous.write_bytes(b"previous successful build")
    transport = Transport()
    with pytest.raises(FileExistsError):
        compiler(transport).compile(workspace, destination)
    assert previous.read_bytes() == b"previous successful build"
    assert not transport.requests
    with pytest.raises(ValueError, match="outside"):
        compiler(transport).compile(workspace, workspace / "output")


@pytest.mark.parametrize(
    "path", ["", "../file", "/file", "a/../file", "a//file", "a\\file", "./file"]
)
def test_relative_paths_are_portable_and_cannot_escape(path: str) -> None:
    with pytest.raises(ValueError, match="workspace paths"):
        relative_path(path)


def test_workspace_preflight_rejects_unsafe_and_oversized_inputs(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(ValueError, match="outside"):
        read_workspace(workspace, {"missing": "https://assets.example/file"})
    link = workspace / "extensions" / "link"
    link.symlink_to(workspace.parent)
    with pytest.raises(ValueError, match="symlink"):
        read_workspace(workspace, {})
    link.unlink()
    monkeypatch.setattr(clsi_workspace, "MAX_WORKSPACE_BYTES", 1)
    with pytest.raises(ValueError, match="limits"):
        read_workspace(workspace, {})


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("entrypoint", "../outside.tex"),
        ("entrypoint", "generated/missing.tex"),
        ("engine", "shell"),
        ("build", {}),
        ("build", None),
    ],
)
def test_workspace_manifest_requires_supported_metadata(
    workspace: Path, field: str, value: object
) -> None:
    path = workspace / "generated" / "workspace.json"
    manifest = json.loads(path.read_text())
    manifest[field] = value
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="workspace"):
        read_workspace(workspace, {})


@pytest.mark.parametrize(
    "url",
    [
        "http://clsi.example",
        "https://user:password@clsi.example",
        "https://clsi.example/login",
        "https://clsi.example?token=secret",
        "https://clsi.example#fragment",
        "https://clsi.example:invalid",
        "https://clsi.example/ bad",
    ],
)
def test_configuration_rejects_non_api_or_unsafe_urls(url: str) -> None:
    with pytest.raises(ValueError, match=r"CLSI|HTTPS"):
        CLSIConfig(url)


@pytest.mark.parametrize("timeout", [0, -1, 181, float("nan"), float("inf"), True])
def test_timeout_is_finite_positive_and_bounded(timeout: float) -> None:
    with pytest.raises(ValueError, match="timeout_seconds"):
        CLSIConfig("https://clsi.example", timeout)


def test_pyproject_configuration_and_only_the_supported_url_override(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "pyproject.toml"
    path.write_text(
        '[tool.wood_reports.clsi]\nurl = "https://clsi.example"\ntimeout_seconds = 42\n'
    )
    assert CLSIConfig.from_pyproject(path) == CLSIConfig("https://clsi.example", 42)
    monkeypatch.setenv("WOOD_REPORTS_CLSI_URL", "https://override.example")
    assert CLSIConfig.from_pyproject(path).url == "https://override.example"
    monkeypatch.delenv("WOOD_REPORTS_CLSI_URL")
    path.write_text('[tool.wood_reports.clsi]\nendpoint = "https://legacy.example"\n')
    with pytest.raises(ValueError, match="configuration"):
        CLSIConfig.from_pyproject(path)
    path.write_text('[tool.wood_reports.clsi]\ntimeout_seconds = "bad"\n')
    with pytest.raises(ValueError, match="numeric"):
        CLSIConfig.from_pyproject(path)


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("", "password"),
        ("user", ""),
        ("user:name", "password"),
        ("user\n", "password"),
        ("user", "password\r"),
    ],
)
def test_credentials_are_validated_and_hidden(username: str, password: str) -> None:
    with pytest.raises(ValueError, match="CLSI"):
        CLSICredentials(username, password)
    assert (
        repr(CLSICredentials("private-user", "private-password")) == "CLSICredentials()"
    )


class Socket:
    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def settimeout(self, value: float) -> None:
        self.timeouts.append(value)


class Connection:
    status = 200

    def __init__(self) -> None:
        self.sock = Socket()
        self.chunks = [b"first", b"second", b""]
        self.closed = False
        self.path = ""
        self.error: OSError | None = None

    def connect(self) -> None:
        if self.error:
            raise self.error

    def request(
        self, method: str, path: str, *, body: bytes | None, headers: dict[str, str]
    ) -> None:
        assert method == "GET"
        assert body is None
        assert headers == {"User-Agent": "fixture"}
        self.path = path

    def getresponse(self) -> Connection:
        return self

    def read1(self, size: int) -> bytes:
        assert size > 0
        return self.chunks.pop(0)

    def close(self) -> None:
        self.closed = True


@pytest.mark.parametrize("failure", ["none", "oversized", "connect", "expired"])
def test_https_transport_reads_with_deadline_size_bound_and_always_closes(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    connection = Connection()
    monkeypatch.setattr(
        http.client, "HTTPSConnection", lambda *_args, **_kwargs: connection
    )
    if failure == "connect":
        connection.error = OSError("connection failed")
    deadline = time.monotonic() + (-1 if failure == "expired" else 10)
    transport = clsi.HTTPCLSITransport()
    if failure == "none":
        result = transport.request(
            "GET",
            "https://clsi.example/file?key=value",
            headers={"User-Agent": "fixture"},
            body=None,
            deadline=deadline,
            max_bytes=20,
        )
        assert result == HTTPResponse(200, b"firstsecond")
        assert connection.path == "/file?key=value"
        assert all(0 < timeout <= 10 for timeout in connection.sock.timeouts)
    else:
        with pytest.raises((ValueError, OSError), match=r"limit|failed|deadline"):
            transport.request(
                "GET",
                "https://clsi.example",
                headers={"User-Agent": "fixture"},
                body=None,
                deadline=deadline,
                max_bytes=2,
            )
    if failure != "expired":
        assert connection.closed


@pytest.mark.parametrize(
    "body",
    [
        b"[]",
        b"{}",
        b'{"compile":{"status":"success","outputFiles":[{}]}}',
        b'{"compile":{"status":"success","outputFiles":null}}',
    ],
)
def test_malformed_compile_and_artifact_metadata_is_rejected(
    workspace: Path, tmp_path: Path, body: bytes
) -> None:
    transport = Transport()
    transport.response_body = body
    with pytest.raises(CompilationError):
        compiler(transport).compile(workspace, tmp_path / "failed")


def test_unknown_artifact_types_are_not_downloaded(
    workspace: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = Transport()
    transport.missing_pdf = True
    # Unknown type uses a safe URL, but must never be fetched.
    original = CLSICompiler._output
    monkeypatch.setattr(
        CLSICompiler,
        "_output",
        staticmethod(
            lambda output, base: (
                ("aux", base + "/build/test/output/output.aux")
                if output == "aux"
                else original(output, base)
            )
        ),
    )
    transport.extra_outputs = ["aux"]
    with pytest.raises(CompilationError, match="valid PDF"):
        compiler(transport).compile(workspace, tmp_path / "failed")
    assert not any(request[1].endswith(".aux") for request in transport.requests)
