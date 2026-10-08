"""Authenticated, bounded CLSI compilation and disposable project lifecycle."""

from __future__ import annotations

import base64
import http.client
import json
import re
import ssl
import time
import uuid
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol
from urllib.parse import unquote, urlsplit

from wood_reports.clsi_workspace import MAX_REQUEST_BYTES, read_workspace, relative_path
from wood_reports.compilation import (
    CLSIConfig,
    CLSICredentials,
    CompilationError,
    CompilationResult,
    validated_url,
)

_USER_AGENT = "Wood-Reports-CLSI/1.0"
_MAX_PDF_BYTES = 32 * 1024 * 1024
_MAX_LOG_BYTES = 4 * 1024 * 1024
_MAX_JSON_BYTES = 1024 * 1024
_CLEANUP_SECONDS = 5


@dataclass(frozen=True, slots=True)
class HTTPResponse:
    status: int
    body: bytes


class CLSITransport(Protocol):
    """Injectable network boundary; implementations must honor the deadline."""

    def request(  # noqa: PLR0913
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        deadline: float,
        max_bytes: int,
    ) -> HTTPResponse: ...


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("compilation deadline exceeded")
    return remaining


class HTTPCLSITransport:
    """Direct certificate-validated HTTPS; no redirects or ambient proxy auth."""

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
        parsed = urlsplit(validated_url(url))
        assert parsed.hostname is not None  # noqa: S101
        connection = http.client.HTTPSConnection(
            parsed.hostname,
            port=parsed.port,
            timeout=_remaining(deadline),
            context=ssl.create_default_context(),
        )
        try:
            connection.connect()
            assert connection.sock is not None  # noqa: S101
            sock = connection.sock
            sock.settimeout(_remaining(deadline))
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            connection.request(method, path, body=body, headers=dict(headers))
            sock.settimeout(_remaining(deadline))
            response = connection.getresponse()
            chunks: list[bytes] = []
            size = 0
            while True:
                sock.settimeout(_remaining(deadline))
                chunk = response.read1(min(64 * 1024, max_bytes + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
                if size > max_bytes:
                    raise ValueError("CLSI response exceeds the artifact size limit")
            return HTTPResponse(response.status, b"".join(chunks))
        finally:
            connection.close()


def _http_diagnostic(status: int) -> str:
    actions = {
        401: "check CLSI credentials",
        403: "check network allowlisting and client access",
        404: "check the CLSI API URL, distinct from the Overleaf editor URL",
        413: "reduce workspace size",
        429: "compiler capacity is busy; retry deliberately later",
        502: "check compiler service health",
        504: "check compiler health and the configured timeout",
    }
    return f"CLSI HTTP {status}: {actions.get(status, 'check compiler service logs')}"


class CLSICompiler:
    """Preferred production backend; never falls back after a failed compile."""

    def __init__(
        self,
        config: CLSIConfig,
        credentials: CLSICredentials,
        *,
        transport: CLSITransport | None = None,
    ) -> None:
        self.config = config
        self._credentials = credentials
        self._transport = transport or HTTPCLSITransport()

    def _request(
        self,
        method: str,
        url: str,
        deadline: float,
        max_bytes: int,
        body: bytes | None = None,
    ) -> HTTPResponse:
        auth = base64.b64encode(
            f"{self._credentials.username}:{self._credentials.password}".encode()
        ).decode()
        response = self._transport.request(
            method,
            url,
            headers={
                "Authorization": f"Basic {auth}",
                "User-Agent": _USER_AGENT,
                "Content-Type": "application/json",
            },
            body=body,
            deadline=deadline,
            max_bytes=max_bytes,
        )
        if response.status not in {200, 204}:
            raise ValueError(_http_diagnostic(response.status))
        if len(response.body) > max_bytes:
            raise ValueError("CLSI response exceeds the artifact size limit")
        return response

    def compile(
        self,
        workspace: Path,
        destination: Path,
        *,
        resource_urls: Mapping[str, str] | None = None,
    ) -> CompilationResult:
        """Retain diagnostics on failure; publish a PDF only after success/cleanup.

        Destination must be new and outside the source workspace. Each call uses
        a fresh remote project; failed builds cannot reuse a previous PDF.
        """
        inputs = read_workspace(workspace, resource_urls or {})
        if destination.resolve().is_relative_to(workspace.resolve()):
            raise ValueError(
                "compilation artifacts must be outside the source workspace"
            )
        project = uuid.uuid4().hex[:24]
        payload = json.dumps(
            {
                "compile": {
                    "options": {
                        "compiler": inputs.engine,
                        "timeout": max(1, int(self.config.timeout_seconds * 0.8)),
                        "stopOnFirstError": True,
                        "syncType": "full",
                    },
                    "rootResourcePath": inputs.entrypoint,
                    "resources": inputs.resources,
                }
            }
        ).encode()
        if len(payload) > MAX_REQUEST_BYTES:
            raise ValueError("encoded workspace exceeds the CLSI request limit")
        destination.mkdir(parents=True, exist_ok=False)
        deadline = time.monotonic() + self.config.timeout_seconds
        base = self.config.url.rstrip("/") + f"/project/{project}"
        diagnostics: list[str] = []
        logs: list[Path] = []
        status = "unavailable"
        pdf: bytes | None = None
        try:
            response = self._request(
                "POST", base + "/compile", deadline, _MAX_JSON_BYTES, payload
            )
            status, output_files = self._outputs(response.body)
            pdf = self._download(
                output_files,
                base=base,
                status=status,
                destination=destination,
                deadline=deadline,
                logs=logs,
            )
            if status != "success":
                raise ValueError(
                    f"CLSI compilation {status}; inspect retained compiler logs"
                )
            if pdf is None or not pdf.startswith(b"%PDF-"):
                raise ValueError("CLSI reported success without a valid PDF header")
        except (OSError, http.client.HTTPException, ValueError) as error:
            diagnostics.append(self._diagnostic(error))
        finally:
            # Cleanup has its own small budget even when the compilation expired.
            try:
                self._request(
                    "DELETE", base, time.monotonic() + _CLEANUP_SECONDS, _MAX_JSON_BYTES
                )
            except (OSError, http.client.HTTPException, ValueError) as error:
                diagnostics.append(
                    "remote project cleanup failed: " + self._diagnostic(error)
                )
        pdf_path: Path | None = None
        if not diagnostics and pdf is not None:
            staged = destination / ".report.pdf.part"
            try:
                staged.write_bytes(pdf)
                pdf_path = staged.replace(destination / "report.pdf")
            except OSError as error:
                diagnostics.append(self._diagnostic(error))
        return self._finish(
            CompilationResult(
                "failed" if diagnostics else "success",
                status,
                project,
                inputs.engine,
                pdf_path,
                tuple(logs),
                destination / "compilation.json",
                tuple(diagnostics),
            ),
            inputs.entrypoint,
            inputs.fingerprints,
        )

    def _download(  # noqa: PLR0913
        self,
        output_files: list[object],
        *,
        base: str,
        status: str,
        destination: Path,
        deadline: float,
        logs: list[Path],
    ) -> bytes | None:
        pdf = None
        artifacts = [self._output(output, base) for output in output_files]
        artifacts.sort(key=lambda item: item[0] == "pdf")
        for index, (kind, url) in enumerate(artifacts):
            if kind not in {"pdf", "log", "stdout", "stderr", "blg"}:
                continue
            if kind == "pdf" and status != "success":
                continue
            if kind == "pdf":
                self._check_logs(logs)
            limit = _MAX_PDF_BYTES if kind == "pdf" else _MAX_LOG_BYTES
            content = self._request("GET", url, deadline, limit).body
            if kind == "pdf":
                if pdf is not None:
                    raise ValueError("CLSI returned more than one PDF")
                pdf = content
            else:
                path = destination / f"compiler-{index}.{kind}"
                path.write_bytes(content)
                logs.append(path)
        return pdf

    @staticmethod
    def _check_logs(logs: list[Path]) -> None:
        if not any(path.suffix == ".log" for path in logs):
            raise ValueError(
                "CLSI success lacks the TeX log; cannot verify compilation"
            )
        for path in logs:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            if any(
                line.startswith("! ")
                or "Fatal error occurred" in line
                or "Latexmk: Errors, so" in line
                for line in lines
            ):
                raise ValueError(
                    "compiler logs report TeX errors despite CLSI success; "
                    "inspect retained compiler logs"
                )

    @staticmethod
    def _finish(
        result: CompilationResult,
        entrypoint: str,
        fingerprints: dict[str, str],
    ) -> CompilationResult:
        record = asdict(result)
        record["schema_version"] = 1
        record["backend"] = "clsi"
        record["pdf"] = result.pdf.name if result.pdf else None
        record["logs"] = [path.name for path in result.logs]
        record["manifest"] = result.manifest.name
        record["entrypoint"] = entrypoint
        record["source_fingerprints"] = fingerprints
        result.manifest.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
        if result.diagnostics:
            raise CompilationError(result)
        return result

    @staticmethod
    def _outputs(body: bytes) -> tuple[str, list[object]]:
        response = json.loads(body)
        compile_result = response.get("compile") if isinstance(response, dict) else None
        if not isinstance(compile_result, dict):
            raise ValueError("CLSI returned an invalid compile response")
        status = compile_result.get("status")
        outputs = compile_result.get("outputFiles", [])
        if (
            not isinstance(status, str)
            or (
                status
                not in {
                    "success",
                    "error",
                    "failure",
                    "timedout",
                    "terminated",
                    "stopped-on-first-error",
                    "compile-in-progress",
                    "retry",
                    "unavailable",
                }
                and re.fullmatch(r"validation-[a-z0-9-]{1,40}", status) is None
            )
            or not isinstance(outputs, list)
            or len(outputs) > 30
        ):
            raise ValueError("CLSI returned invalid compile status or output files")
        return status, outputs

    @staticmethod
    def _output(output: object, base: str) -> tuple[str, str]:
        if not isinstance(output, dict):
            raise ValueError("CLSI returned invalid artifact metadata")
        kind, url = output.get("type"), output.get("url")
        if not isinstance(kind, str) or not isinstance(url, str):
            raise ValueError("CLSI artifact requires type and URL")
        validated_url(url)
        parsed, expected = urlsplit(url), urlsplit(base)
        if (
            parsed.netloc != expected.netloc
            or parsed.query
            or not parsed.path.startswith(expected.path + "/")
        ):
            raise ValueError(
                "CLSI artifact URL is outside this project and HTTPS origin"
            )
        relative_path(unquote(parsed.path.removeprefix(expected.path + "/")))
        return kind, url

    @staticmethod
    def _diagnostic(error: Exception) -> str:
        if isinstance(error, TimeoutError):
            return "CLSI deadline exceeded; check compiler load and timeout_seconds"
        if isinstance(error, ValueError):
            # JSON decoder errors are bounded and contain no upstream response body.
            return str(error)[:500]
        return (
            "CLSI transport or artifact I/O failed; "
            "check connectivity and output permissions"
        )
