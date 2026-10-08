"""Render report models as portable, standalone LaTeX source trees."""

from __future__ import annotations

import re
from pathlib import Path

from wood_reports.artifacts import materialize_chart_assets
from wood_reports.latex_components import latex_preamble
from wood_reports.model import (
    ChartReference,
    Finding,
    Narrative,
    PublicationTable,
    RendererHints,
    Report,
    TableCell,
)
from wood_reports.primitives import (
    has_technical_text,
    latex_escape,
    latex_inline,
    list_entries,
)
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
        self.labels: set[str] = set()
        self.references: set[str] = set()

    def _label(self, value: str) -> str:
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9:_.-]*", value) is None:
            raise LatexRenderError("labels must be simple identifiers")
        if value in self.labels:
            raise LatexRenderError(f"duplicate label: {value}")
        self.labels.add(value)
        return f"\\label{{{value}}}"

    def _optional_label(self, hints: RendererHints) -> list[str]:
        label = hints.get("latex.label")
        return [self._label(label)] if label else []

    def render(self, report: Report, destination: Path, *, artifact_root: Path) -> Path:
        report.validate(artifact_root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        report = materialize_chart_assets(
            report, artifact_root=artifact_root, assets=destination.parent / "assets"
        )
        parts = [
            *latex_preamble(report),
            r"\begin{document}",
            f"\\title{{{latex_escape(report.metadata.title)}}}",
            f"\\author{{{latex_escape(report.metadata.author or DEFAULT_AUTHOR)}}}",
            r"\date{}",
            r"\maketitle",
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
            parts.extend(self._optional_label(section.renderer_hints))
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
                parts.extend(self._optional_label(appendix.renderer_hints))
                for item in appendix.content:
                    figure = self._content(parts, item, appendix.title, figure)
        parts.append(r"\end{document}")
        if missing := self.references - self.labels:
            raise LatexRenderError(f"unresolved references: {sorted(missing)}")
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

    def _narrative(self, parts: list[str], item: Narrative) -> None:
        if reference := item.renderer_hints.get("latex.ref"):
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9:_.-]*", reference) is None:
                raise LatexRenderError("references must be simple identifiers")
            self.references.add(reference)
            parts.append(latex_inline(item.text) + f" \\ref{{{reference}}}")
            return
        if raw := item.renderer_hints.get("latex.raw"):
            if raw != "inline":
                raise LatexRenderError("latex.raw must explicitly select inline")
            parts.append(self._raw_inline(item.text))
            return
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
        elif has_technical_text(item.text):
            parts.extend(
                [
                    r"\begin{WoodTechnicalParagraph}",
                    latex_inline(item.text),
                    r"\end{WoodTechnicalParagraph}",
                ]
            )
        else:
            parts.append(latex_inline(item.text) + "\n")

    @staticmethod
    def _raw_inline(text: str) -> str:
        """Permit only short formatting fragments, without TeX I/O or definitions."""
        if len(text) > 4096:
            raise LatexRenderError("raw inline LaTeX exceeds 4096 characters")
        depth = 0
        position = 0
        while position < len(text):
            character = text[position]
            if character == "\\":
                command = re.match(
                    r"\\(?:textbf|textit|emph|texttt)\{", text[position:]
                )
                if command is None:
                    raise LatexRenderError(
                        "raw inline LaTeX permits formatting commands only"
                    )
                position += len(command.group())
                depth += 1
                continue
            if character == "}" and depth:
                depth -= 1
            elif character in "{}%#$&^~\x00\n\r":
                raise LatexRenderError("raw inline LaTeX contains unsupported syntax")
            position += 1
        if depth:
            raise LatexRenderError("raw inline LaTeX has unclosed formatting groups")
        return text

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
                    self._label(label),
                    r"\end{figure}",
                ]
            )
            if source := item.renderer_hints.get("latex.source"):
                parts.append(f"\\WoodSource{{{latex_escape(source)}}}")
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
        policy = self.theme.table_layout
        long = table.renderer_hints.get("latex.layout") == "longtable" or (
            not table.renderer_hints.get("latex.layout")
            and not table.renderer_hints.get("latex.width")
            and len(table.rows) > policy.keep_together_rows
        )
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
        label_command = self._label(label) if label else ""
        parts.append(r"\begingroup\WoodTableFont\WoodTableSetup")
        if long:
            reserve = (
                len(table.rows)
                if len(table.rows) <= policy.keep_together_rows
                else max(policy.minimum_first_rows, policy.minimum_last_rows)
            )
            # Measure actual header/body typography, not guessed row heights.
            parts.extend(
                [
                    f"\\sbox{{\\WoodTableStart}}{{\\begin{{tabular}}{{{cols}}}",
                    r"\toprule",
                    " & ".join(
                        r"\bfseries " + latex_escape(c.label) for c in table.columns
                    )
                    + r" \\",
                    r"\midrule",
                    *(
                        " & ".join(
                            self._cell(v, c.format)
                            for v, c in zip(row, table.columns, strict=True)
                        )
                        + r" \\"
                        for row in table.rows[:reserve]
                    ),
                    r"\bottomrule\end{tabular}}",
                    r"\WoodTableSpace",
                ]
            )
            parts.append(f"\\begin{{longtable}}{{{cols}}}")
            if table.caption or label:
                parts.append(
                    f"\\caption{{{latex_escape(table.caption or '')}}}"
                    + label_command
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
        for index, row in enumerate(table.rows):
            protected = (
                long
                and index < len(table.rows) - 1
                and (
                    len(table.rows) <= policy.keep_together_rows
                    or index < policy.minimum_first_rows - 1
                    or index >= len(table.rows) - policy.minimum_last_rows
                )
            )
            parts.append(
                " & ".join(
                    self._cell(v, c.format)
                    for v, c in zip(row, table.columns, strict=True)
                )
                + (r" \WoodProtectedRowEnd" if protected else r" \\")
            )
        parts.extend([r"\bottomrule", f"\\end{{{env}}}"])
        if not long:
            if table.caption or label:
                parts.append(f"\\caption{{{latex_escape(table.caption or '')}}}")
            if label:
                parts.append(label_command)
            parts.append(r"\end{table}")
        if table.notes:
            parts.append(
                "{\\WoodNoteFont\\color{Woodtext_muted}\\textit{"
                + latex_escape(" ".join(table.notes))
                + "}}"
            )
        if source := table.renderer_hints.get("latex.source"):
            parts.append(f"\\WoodSource{{{latex_escape(source)}}}")
        parts.append(r"\endgroup")

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
