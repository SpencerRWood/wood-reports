"""Centralized chart artifact resolution and portable-tree materialization."""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from wood_reports.model import (
    Appendix,
    ChartReference,
    Finding,
    Report,
    Section,
    resolve_chart_artifact,
)


def materialize_chart_assets(
    report: Report, *, artifact_root: Path, assets: Path
) -> Report:
    """Copy chart files into ``assets`` and return a report with local references.

    The input report is immutable; output references are relative to the generated
    TeX document's parent, which keeps standalone output and workspaces portable.
    """
    assets.mkdir(parents=True, exist_ok=True)
    ordinal = 0

    def chart(value: ChartReference) -> ChartReference:
        nonlocal ordinal
        source = resolve_chart_artifact(value, artifact_root)
        ordinal += 1
        name = f"{ordinal}-{source.name}"
        target = assets / name
        shutil.copy2(source, target)
        return replace(value, artifact=Path("assets") / name)

    def section(value: Section) -> Section:
        return replace(
            value,
            content=tuple(
                chart(item) if isinstance(item, ChartReference) else item
                for item in value.content
            ),
        )

    def appendix(value: Appendix) -> Appendix:
        return replace(
            value,
            content=tuple(
                chart(item) if isinstance(item, ChartReference) else item
                for item in value.content
            ),
        )

    def finding(value: Finding) -> Finding:
        return replace(
            value,
            visual=chart(value.visual)
            if isinstance(value.visual, ChartReference)
            else value.visual,
        )

    return replace(
        report,
        sections=tuple(section(value) for value in report.sections),
        appendices=tuple(appendix(value) for value in report.appendices),
        findings=tuple(finding(value) for value in report.findings),
    )
