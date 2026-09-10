"""Render report models as standalone LaTeX documents."""

from __future__ import annotations

from pathlib import Path

from wood_reports.model import ChartReference, PublicationTable, Report


class LatexRenderError(ValueError):
    pass


class LatexRenderer:
    def render(self, report: Report, destination: Path, *, artifact_root: Path) -> Path:
        report.validate(artifact_root)
        parts = [
            r"\documentclass{article}",
            r"\usepackage{graphicx}",
            r"\usepackage{booktabs}",
            r"\usepackage{longtable}",
            r"\begin{document}",
            f"\\title{{{report.metadata.title}}}",
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
                if isinstance(item, ChartReference):
                    if item.artifact is None:
                        raise LatexRenderError("chart requires a resolved artifact")
                    figure += 1
                    label = item.renderer_hints.get("latex.label", f"fig:{figure}")
                    parts.extend(
                        [
                            r"\begin{figure}[htbp]",
                            r"\centering",
                            f"\\includegraphics[width=\\linewidth]{{{item.artifact.as_posix()}}}",
                            f"\\caption{{{item.caption or section.title}}}",
                            f"\\label{{{label}}}",
                            r"\end{figure}",
                        ]
                    )
                elif isinstance(item, PublicationTable):
                    long = item.renderer_hints.get("latex.layout") == "longtable"
                    if long and item.renderer_hints.get("latex.width"):
                        raise LatexRenderError("longtable cannot use latex.width")
                    environment = "longtable" if long else "tabular"
                    parts.extend(
                        [
                            r"\begin{table}[htbp]",
                            r"\centering",
                            "\\begin{"
                            + environment
                            + "}{"
                            + "".join(
                                "lcr"[{"left": 0, "center": 1, "right": 2}[c.alignment]]
                                for c in item.columns
                            )
                            + "}",
                            r"\toprule",
                            " & ".join(c.label for c in item.columns) + r" \\",
                            r"\midrule" if not long else r"\midrule\endhead",
                        ]
                    )
                    parts.extend(
                        " & ".join("" if v is None else str(v) for v in row) + r" \\"
                        for row in item.rows
                    )
                    parts.extend(
                        [
                            r"\bottomrule",
                            "\\end{" + environment + "}",
                            f"\\caption{{{item.caption}}}" if item.caption else "",
                            "\\textit{" + " ".join(item.notes) + "}"
                            if item.notes
                            else "",
                            r"\end{table}",
                        ]
                    )
                else:
                    parts.append(item.text)
        if report.appendices:
            parts.append(r"\appendix")
            for appendix in report.appendices:
                parts.append(f"\\section{{{appendix.title}}}")
                parts.extend(
                    item.text for item in appendix.content if hasattr(item, "text")
                )
        parts.append(r"\end{document}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            "\n".join(part for part in parts if part), encoding="utf-8"
        )
        return destination
