"""Create validated, isolated recurring report invocations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from wood_reports.model import Report

type RunValue = str | int | float | bool | None


class ReportRunError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        self.field = field
        super().__init__(f"{field}: {message}")


@dataclass(frozen=True, slots=True)
class Comparison:
    current: RunValue
    comparison: RunValue | None = None
    benchmark: RunValue | None = None
    target: RunValue | None = None


@dataclass(frozen=True, slots=True)
class ReportRun:
    definition: Report
    period: str
    comparison_period: str | None
    values: Mapping[str, RunValue]
    comparisons: Mapping[str, Comparison]
    flags: Mapping[str, bool]

    def materialize(self) -> Report:
        """Return renderer-ready structure after applying precomputed flag decisions."""
        included = []
        for finding in self.definition.findings:
            if finding.include_if is None:
                included.append(finding)
                continue
            try:
                include = self.flags[finding.include_if]
            except KeyError as error:
                raise ReportRunError(
                    f"flags.{finding.include_if}",
                    "is required by a finding include_if condition",
                ) from error
            if include:
                included.append(replace(finding, include_if=None))
        return replace(self.definition, findings=tuple(included))

    @classmethod
    def create(  # noqa: PLR0913
        cls,
        definition: Report,
        *,
        period: str,
        comparison_period: str | None = None,
        values: Mapping[str, RunValue] | None = None,
        comparisons: Mapping[str, Comparison] | None = None,
        flags: Mapping[str, bool] | None = None,
    ) -> ReportRun:
        if not period.strip():
            raise ReportRunError("period", "must not be blank")
        values = values or {}
        flags = flags or {}
        if not all(isinstance(flag, bool) for flag in flags.values()):
            raise ReportRunError("flags", "values must be booleans")
        return cls(
            definition,
            period,
            comparison_period,
            dict(values),
            dict(comparisons or {}),
            dict(flags),
        )
