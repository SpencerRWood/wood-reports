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
from wood_reports.primitives import latex_escape, latex_inline, list_entries
from wood_reports.theme import PublicationTheme


class LatexRenderError(ValueError):
    pass


DEFAULT_AUTHOR = "Spencer Wood"


class LatexRenderer:
    def render(self, report: Report, destination: Path, *, artifact_root: Path) -> Path:
        return _LatexDocument(report.theme).render(
            report, destination, artifact_root=artifact_root
        )


class _LatexDocument:
    def __init__(self, theme: PublicationTheme) -> None:
        self.theme = theme

    def render(self, report: Report, destination: Path, *, artifact_root: Path) -> Path:
        report.validate(artifact_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        report = materialize_chart_assets(
            report, artifact_root=artifact_root, assets=destination.parent / "assets"
        )
        parts = [
            *self._preamble(report),
            r"\begin{document}",
            f"\\title{{{latex_escape(report.metadata.title)}}}",
            f"\\author{{{latex_escape(report.metadata.author or DEFAULT_AUTHOR)}}}",
            r"\date{}",
            r"\maketitle",
            r"\WoodWordmark",
        ]
        if report.metadata.subtitle:
            parts.append(latex_escape(report.metadata.subtitle))
        if report.metadata.source:
            parts.append(f"\\WoodSource{{{latex_escape(report.metadata.source)}}}")
        if report.metadata.confidentiality:
            parts.append(
                f"\\WoodConfidentiality{{{latex_escape(report.metadata.confidentiality)}}}"
            )
        figure = 0
        for section in report.sections:
            parts.append(f"\\section{{{latex_escape(section.title)}}}")
            for item in section.content:
                figure = self._content(parts, item, section.title, figure)
        if report.findings:
            parts.append(r"\section{Findings}")
            for finding in report.findings:
                figure = self._finding(parts, finding, figure)
        if report.appendices:
            parts.append(r"\appendix")
            for appendix in report.appendices:
                parts.append(f"\\section{{{latex_escape(appendix.title)}}}")
                for item in appendix.content:
                    figure = self._content(parts, item, appendix.title, figure)
        parts.append(r"\end{document}")
        destination.write_text("\n".join(parts), encoding="utf-8")
        return destination

    def _finding(self, parts: list[str], finding: Finding, figure: int) -> int:
        parts.append(f"\\subsection{{{latex_escape(finding.title)}}}")
        if finding.subtitle:
            parts.append(f"\\textit{{{latex_escape(finding.subtitle)}}}")
        if finding.source:
            parts.append(f"\\WoodSource{{{latex_escape(finding.source)}}}")
        color = {"info": "primary", "warning": "warning", "critical": "critical"}[
            finding.severity
        ]
        parts.append(
            f"\\WoodCallout{{Wood{color}}}{{{finding.severity.title()}}}"
            f"{{{latex_inline(finding.narrative.text)}}}"
        )
        if finding.visual is not None:
            return self._content(parts, finding.visual, finding.title, figure, finding)
        return figure

    def _preamble(self, report: Report) -> list[str]:
        theme = self.theme
        geometry = theme.geometry
        typography = theme.typography
        parts = [
            f"\\documentclass[{typography.page_body}pt]{{article}}",
            r"\usepackage{graphicx,booktabs,longtable}",
            r"\usepackage[table]{xcolor}",
            r"\usepackage{geometry,fancyhdr,caption,titlesec,iftex}",
            r"\usepackage[hidelinks]{hyperref}",
            f"\\geometry{{paperwidth={geometry.page_width}in,"
            f"paperheight={geometry.page_height}in,"
            f"margin={geometry.page_margin}in,headheight=15pt}}",
            r"\ifPDFTeX",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage{helvet}",
            r"\renewcommand{\familydefault}{\sfdefault}",
            r"\else",
            r"\usepackage{fontspec}",
            r"\IfFontExistsTF{"
            + latex_escape(typography.family)
            + r"}{\setsansfont{"
            + latex_escape(typography.family)
            + r"}}{\IfFontExistsTF{"
            + latex_escape(typography.fallback)
            + r"}{\setsansfont{"
            + latex_escape(typography.fallback)
            + r"}}{\setsansfont{lmsans10-regular.otf}}}",
            r"\IfFontExistsTF{"
            + latex_escape(typography.code_family)
            + r"}{\setmonofont{"
            + latex_escape(typography.code_family)
            + r"}}{\setmonofont{lmmono10-regular.otf}}",
            r"\renewcommand{\familydefault}{\sfdefault}",
            r"\fi",
        ]
        parts.extend(
            f"\\definecolor{{Wood{name}}}{{HTML}}{{{getattr(theme.colors, name)[1:]}}}"
            for name in (
                "primary",
                "secondary",
                "text_primary",
                "text_muted",
                "grid",
                "background",
                "warning",
                "critical",
            )
        )
        parts.extend(
            [
                r"\color{Woodtext_primary}",
                r"\pagecolor{Woodbackground}",
                f"\\setlength{{\\parskip}}{{{theme.spacing.paragraph_points}pt}}",
                r"\setlength{\parindent}{0pt}",
                r"\pagestyle{fancy}\fancyhf{}",
                r"\fancyhead[L]{\small\color{Woodprimary} "
                + latex_escape(theme.wordmark)
                + "}",
                r"\fancyfoot[L]{\small\color{Woodtext_muted} "
                + latex_escape(report.metadata.confidentiality or "")
                + "}",
                r"\fancyfoot[R]{\small\thepage}"
                if theme.page_numbers
                else r"\fancyfoot[R]{}",
                r"\fancypagestyle{plain}{\fancyhf{}"
                + r"\fancyfoot[L]{\small\color{Woodtext_muted} "
                + latex_escape(report.metadata.confidentiality or "")
                + "}"
                + (r"\fancyfoot[R]{\thepage}" if theme.page_numbers else "")
                + "}",
                r"\titleformat{\section}{\color{Woodprimary}\sffamily\bfseries"
                + f"\\fontsize{{{typography.page_heading}}}"
                + f"{{{typography.page_heading + 3}}}"
                + r"\selectfont}{\thesection}{1em}{}",
                r"\titleformat{\subsection}{\color{Woodprimary}\sffamily\bfseries}"
                r"{\thesubsection}{1em}{}",
                r"\DeclareCaptionFont{woodcaption}{"
                + f"\\fontsize{{{typography.caption}}}{{{typography.caption + 2}}}"
                + r"\selectfont\color{Woodtext_muted}}",
                r"\captionsetup{font=woodcaption,labelfont=bf}",
                r"\newcommand{\WoodWordmark}{{\color{Woodprimary}\Large\bfseries "
                + latex_escape(theme.wordmark)
                + "}}",
                r"\newcommand{\WoodSource}[1]{\par{\small\color{Woodtext_muted}"
                r"\textit{Source: #1}}\par}",
                r"\newcommand{\WoodConfidentiality}[1]{\par{\small\bfseries #1}\par}",
                r"\newcommand{\WoodCallout}[3]{\par\noindent"
                r"\fcolorbox{#1}{Woodbackground}{\parbox{"
                r"\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{"
                r"\color{#1}\textbf{#2}\par\color{Woodtext_primary}#3}}\par}",
            ]
        )
        return parts

    def _narrative(self, parts: list[str], item: Narrative) -> None:
        style = self.theme.primitive(item.kind, item.semantic)
        if item.kind == "callout":
            color = "warning" if item.semantic == "risk" else "primary"
            parts.append(
                f"\\WoodCallout{{Wood{color}}}{{{style.label}}}{{{latex_inline(item.text)}}}"
            )
        elif item.kind == "heading":
            command = "subsection" if item.semantic == "h3" else "subsubsection"
            parts.append(f"\\{command}*{{{latex_inline(item.text)}}}")
        elif item.kind == "list":
            self._list(parts, item.text)
        elif item.kind == "code":
            text = (
                latex_escape(item.text).replace(" ", r"\ ").replace("\n", r"\newline{}")
            )
            parts.append(f"{{\\ttfamily {text}}}\\par")
        else:
            parts.append(latex_inline(item.text) + "\n")

    @staticmethod
    def _list(parts: list[str], text: str) -> None:
        depth = 0
        for entry in list_entries(text):
            while depth > entry.level + 1:
                parts.append(r"\end{list}")
                depth -= 1
            while depth < entry.level + 1:
                parts.append(r"\begin{list}{}{\setlength{\leftmargin}{2em}}")
                depth += 1
            if entry.marker:
                marker = (
                    r"\textbullet"
                    if entry.marker == "•"
                    else latex_escape(entry.marker)
                )
                parts.append(f"\\item[{{{marker}}}] " + latex_inline(entry.text))
            else:
                parts.append("\n" + latex_inline(entry.text))
        parts.extend([r"\end{list}"] * depth)

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
                    f"\\includegraphics[width={self.theme.spacing.figure_width_fraction}\\linewidth]{{\\detokenize{{{item.artifact.as_posix()}}}}}",
                    f"\\caption{{{latex_escape(item.caption or title)}}}",
                    f"\\label{{{label}}}",
                    r"\end{figure}",
                ]
            )
        elif isinstance(item, PublicationTable):
            self._table(parts, item, finding)
        elif isinstance(item, Narrative):
            self._narrative(parts, item)
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
                    f"\\caption{{{latex_escape(table.caption)}}}"
                    + (f"\\label{{{label}}}" if label else "")
                    + r"\\"
                )
        else:
            parts.extend(
                [r"\begin{table}[htbp]", r"\centering", f"\\begin{{{env}}}{{{cols}}}"]
            )
        parts.extend(
            [
                r"\toprule",
                r"\rowcolor{Woodprimary} "
                + " & ".join(
                    r"\color{Woodbackground}\bfseries " + latex_escape(c.label)
                    for c in table.columns
                )
                + r" \\",
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
                parts.append(f"\\caption{{{latex_escape(table.caption)}}}")
            if label:
                parts.append(f"\\label{{{label}}}")
            parts.append(r"\end{table}")
        if table.notes:
            parts.append(
                "{\\small\\color{Woodtext_muted}\\textit{"
                + latex_escape(" ".join(table.notes))
                + "}}"
            )

    @staticmethod
    def _cell(value: TableCell, format_spec: str | None) -> str:
        if value is None:
            return ""
        try:
            return latex_escape(format(value, format_spec or ""))
        except (TypeError, ValueError) as error:
            raise LatexRenderError(
                f"invalid table format {format_spec!r}: {error}"
            ) from error
