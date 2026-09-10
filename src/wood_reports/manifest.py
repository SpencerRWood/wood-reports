"""Persist deterministic report-run outputs and renderer diagnostics."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path


class OutputExistsError(FileExistsError):
    pass


@dataclass(frozen=True, slots=True)
class TargetStatus:
    target: str
    status: str
    output: str | None = None
    error: str | None = None


class RunOutputWriter:
    def write(  # noqa: PLR0913
        self,
        root: Path,
        report_id: str,
        period: str,
        parameters: dict[str, object],
        renderers: dict[str, Callable[[Path], Path]],
        *,
        replace: bool = False,
    ) -> Path:
        directory = root / report_id / period
        if directory.exists() and not replace:
            raise OutputExistsError(str(directory))
        directory.mkdir(parents=True, exist_ok=True)
        statuses = []
        for target, renderer in sorted(renderers.items()):
            try:
                statuses.append(
                    TargetStatus(target, "success", str(renderer(directory)))
                )
            except Exception as error:
                statuses.append(TargetStatus(target, "failed", error=str(error)))
        manifest = {
            "report_id": report_id,
            "period": period,
            "parameters": parameters,
            "targets": [asdict(status) for status in statuses],
        }
        path = directory / "manifest.json"
        path.write_text(
            json.dumps(manifest, sort_keys=True, indent=2), encoding="utf-8"
        )
        return path
