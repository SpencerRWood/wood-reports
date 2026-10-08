"""Replaceable workspace-to-PDF compilation, separate from report rendering."""

from __future__ import annotations

import math
import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol
from urllib.parse import urlsplit


def validated_url(value: str, *, allow_http: bool = False) -> str:
    """Validate API HTTPS or an explicitly supplied internal resource URL."""
    parsed = urlsplit(value)
    if (
        parsed.scheme not in ({"https", "http"} if allow_http else {"https"})
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
        or any(character.isspace() for character in value)
    ):
        raise ValueError("CLSI and resource URLs require credential-free HTTPS")
    # Validate the port here rather than leaking an invalid URL in transport errors.
    try:
        _ = parsed.port
    except ValueError:
        raise ValueError("CLSI URL has an invalid port") from None
    return value


@dataclass(frozen=True, slots=True)
class CLSIConfig:
    """Compiler API configuration; the Overleaf editor URL is independent."""

    url: str
    timeout_seconds: float = 120

    def __post_init__(self) -> None:
        validated_url(self.url)
        parsed = urlsplit(self.url)
        if parsed.query or parsed.path not in {"", "/"}:
            raise ValueError("CLSI URL must be an API origin without a path or query")
        if (
            isinstance(self.timeout_seconds, bool)
            or not math.isfinite(self.timeout_seconds)
            or not 1 <= self.timeout_seconds <= 180
        ):
            raise ValueError("CLSI timeout_seconds must be between 1 and 180")

    @classmethod
    def from_pyproject(cls, path: Path) -> CLSIConfig:
        """Read exactly [tool.wood_reports.clsi], with an explicit URL override."""
        document = tomllib.loads(path.read_text(encoding="utf-8"))
        try:
            settings = document.get("tool", {}).get("wood_reports", {}).get("clsi", {})
        except AttributeError:
            raise ValueError("invalid [tool.wood_reports.clsi] configuration") from None
        if not isinstance(settings, dict) or set(settings) - {"url", "timeout_seconds"}:
            raise ValueError("invalid [tool.wood_reports.clsi] configuration")
        url = os.environ.get("WOOD_REPORTS_CLSI_URL", settings.get("url"))
        timeout = settings.get("timeout_seconds", 120)
        if not isinstance(url, str) or not isinstance(timeout, (int, float)):
            raise ValueError("CLSI requires url and numeric timeout_seconds")
        return cls(url, timeout)


@dataclass(frozen=True, slots=True)
class CLSICredentials:
    """Caller-managed credentials; never written to artifacts or repr output."""

    username: str = field(repr=False)
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        if not self.username or not self.password or ":" in self.username:
            raise ValueError("CLSI requires a username and password")
        if any(c in self.username + self.password for c in "\r\n"):
            raise ValueError("CLSI credentials cannot contain newlines")


@dataclass(frozen=True, slots=True)
class CompilationResult:
    status: Literal["success", "failed"]
    compiler_status: str
    project_id: str
    engine: str
    pdf: Path | None
    logs: tuple[Path, ...]
    manifest: Path
    diagnostics: tuple[str, ...]


class CompilationError(RuntimeError):
    """Compilation failed; retained logs and diagnostics are available in result."""

    def __init__(self, result: CompilationResult) -> None:
        self.result = result
        super().__init__("; ".join(result.diagnostics))


class WorkspaceCompiler(Protocol):
    """Compile a portable workspace without changing its source or report model."""

    def compile(
        self,
        workspace: Path,
        destination: Path,
        *,
        resource_urls: Mapping[str, str] | None = None,
    ) -> CompilationResult:
        """Return a PDF result, or raise CompilationError with retained evidence.

        Binary resources use caller-published, CLSI-reachable URLs keyed by
        workspace-relative paths. The caller owns their upload and expiry.
        """
        ...
