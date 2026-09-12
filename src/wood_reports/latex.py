"""Render report models as portable, standalone LaTeX source trees."""

from __future__ import annotations

from pathlib import Path

from wood_reports.artifacts import materialize_chart_assets
from wood_reports.model import (
    ChartReference,
    Finding,
    Narrative,
    PublicationTable,
    Report,
    TableCell,
)


class LatexRenderError(ValueError):
    pass


DEFAULT_AUTHOR = "Spencer Wood"


class LatexRenderer:
    def render(self, report: Report, destination: Path, *, artifact_root: Path) -> Path:
        report.validate(artifact_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        report = materialize_chart_assets(
            report, artifact_root=artifact_root, assets=destination.parent / "assets"
        )
        parts = [
            r"\documentclass{article}",
            r"\usepackage{graphicx}",
            r"\usepackage{booktabs}",
            r"\usepackage{longtable}",
            r"\begin{document}",
            f"\\title{{{report.metadata.title}}}",
            f"\\author{{{report.metadata.author or DEFAULT_AUTHOR}}}",
            r"\maketitle",
        ]
        if report.metadata.subtitle:
            parts.append(report.metadata.subtitle)
        if report.metadata.source:
            parts.append(f"\\textit{{Source: {report.metadata.source}}}")
        figure = 0
        for section in report.sections:
            parts.append(f"\\section{{{section.title}}}")
            for item in section.content:
                figure = self._content(parts, item, section.title, figure)
        if report.findings:
            parts.append(r"\section{Findings}")
            for finding in report.findings:
                parts.append(f"\\subsection{{{finding.title}}}")
                if finding.subtitle:
                    parts.append(f"\\textit{{{finding.subtitle}}}")
                if finding.source:
                    parts.append(f"\\textit{{Source: {finding.source}}}")
                parts.append(finding.narrative.text)
                if finding.visual is not None:
                    figure = self._content(
                        parts, finding.visual, finding.title, figure, finding
                    )
        parts.append(r"\end{document}")
        destination.write_text("\n".join(parts), encoding="utf-8")
        return destination

    def _content(
        self,
        parts: list[str],
        item: object,
        title: str,
        figure: int,
        finding: Finding | None = None,
    ) -> int:
        if isinstance(item, ChartReference):
            if item.artifact is None:
                raise LatexRenderError("chart requires a resolved artifact")
            figure += 1
            label = item.renderer_hints.get(
                "latex.label", f"fig:{finding.identity if finding else figure}"
            )
            parts.extend(
                [
                    r"\begin{figure}[htbp]",
                    r"\centering",
                    f"\\includegraphics[width=\\linewidth]{{{item.artifact.as_posix()}}}",
                    f"\\caption{{{item.caption or title}}}",
                    f"\\label{{{label}}}",
                    r"\end{figure}",
                ]
            )
        elif isinstance(item, PublicationTable):
            self._table(parts, item, finding)
        elif isinstance(item, Narrative):
            parts.append(item.text)
        else:
            raise LatexRenderError("unsupported report content")
        return figure

    def _table(
        self, parts: list[str], table: PublicationTable, finding: Finding | None
    ) -> None:
        long = table.renderer_hints.get("latex.layout") == "longtable"
        if long and table.renderer_hints.get("latex.width"):
            raise LatexRenderError("longtable cannot use latex.width")
        cols = "".join(
            {"left": "l", "center": "c", "right": "r"}[c.alignment]
            for c in table.columns
        )
        env = "longtable" if long else "tabular"
        label = table.renderer_hints.get(
            "latex.label", f"tab:{finding.identity}" if finding else ""
        )
        if long:
            parts.append(f"\\begin{{longtable}}{{{cols}}}")
            if table.caption:
                parts.append(
                    f"\\caption{{{table.caption}}}"
                    + (f"\\label{{{label}}}" if label else r"\\")
                )
        else:
            parts.extend(
                [r"\begin{table}[htbp]", r"\centering", f"\\begin{{{env}}}{{{cols}}}"]
            )
        parts.extend(
            [
                r"\toprule",
                " & ".join(c.label for c in table.columns) + r" \\",
                r"\midrule" + (r"\endhead" if long else ""),
            ]
        )
        parts.extend(
            " & ".join(
                self._cell(v, c.format) for v, c in zip(row, table.columns, strict=True)
            )
            + r" \\"
            for row in table.rows
        )
        parts.extend([r"\bottomrule", f"\\end{{{env}}}"])
        if not long:
            if table.caption:
                parts.append(f"\\caption{{{table.caption}}}")
            if label:
                parts.append(f"\\label{{{label}}}")
            parts.append(r"\end{table}")
        if table.notes:
            parts.append("\\textit{" + " ".join(table.notes) + "}")

    @staticmethod
    def _cell(value: TableCell, format_spec: str | None) -> str:
        if value is None:
            return ""
        try:
            return format(value, format_spec or "").replace("%", r"\%")
        except (TypeError, ValueError) as error:
            raise LatexRenderError(
                f"invalid table format {format_spec!r}: {error}"
            ) from error
