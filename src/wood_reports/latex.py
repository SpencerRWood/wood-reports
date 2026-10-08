"""Render report models as portable, standalone LaTeX source trees."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from wood_reports.artifacts import materialize_chart_assets
from wood_reports.citations import (
    BIBLATEX_PREAMBLE,
    BibliographySource,
    bibliography_text,
    citation_inline,
)
from wood_reports.diagrams import (
    ArchitectureDiagram,
    diagram_panels,
    parse_flowchart,
    vector_panel,
)
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
    list_entries,
)
from wood_reports.profiles import semantic_id
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
        self.bibliography: tuple[BibliographySource, ...] = ()
        self.architecture = False
        self.table_number = 0
        self.landscape_all = False

    def _inline(self, text: str) -> str:
        return citation_inline(text, self.bibliography, local_reference=self._reference)

    def _reference(self, label: str, text: str) -> str:
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9:_.-]*", label) is None:
            raise LatexRenderError("references must be simple identifiers")
        self.references.add(label)
        return f"\\hyperref[{label}]{{{text}}}"

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
        self.bibliography = report.bibliography
        self.architecture = report.metadata.doc_type == "technical-architecture"
        self.landscape_all = (
            report.renderer_hints.get("latex.page_layout") == "landscape"
        )
        destination.parent.mkdir(parents=True, exist_ok=True)
        report = materialize_chart_assets(
            report, artifact_root=artifact_root, assets=destination.parent / "assets"
        )
        parts = [
            *latex_preamble(report, mixed_orientation=self.architecture),
            *(
                [
                    r"\usepackage{array,pdflscape,cleveref}",
                    r"\usetikzlibrary{arrows.meta}",
                    r"\setcounter{secnumdepth}{5}",
                    r"\let\WoodBeginLandscape\landscape",
                    r"\let\WoodEndLandscape\endlandscape",
                    r"\renewcommand{\landscape}{\WoodBeginLandscape"
                    r"\global\WoodLandscapePagetrue\fancyfoot{}}",
                    r"\renewcommand{\endlandscape}{\WoodEndLandscape"
                    r"\global\WoodLandscapePagefalse}",
                ]
                if self.architecture
                else []
            ),
            *([BIBLATEX_PREAMBLE] if report.bibliography else []),
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
        if self.landscape_all:
            parts.append(r"\begin{landscape}")
        if report.renderer_hints.get("latex.toc") == "true":
            parts.extend(
                [
                    r"\clearpage",
                    r"\tableofcontents",
                    r"\listoffigures",
                    r"\listoftables",
                    r"\clearpage",
                ]
            )
        figure, printed_bibliography = self._sections(parts, report)
        figure = self._supplement(parts, report, figure)
        if report.bibliography:
            if not printed_bibliography:
                parts.extend(
                    [
                        r"\clearpage",
                        r"\nocite{*}",
                        r"\printbibliography[heading=bibintoc,"
                        r"title={Source provenance}]",
                    ]
                )
            (destination.parent / "sources.bib").write_text(
                bibliography_text(report.bibliography), encoding="utf-8"
            )
        if self.landscape_all:
            parts.append(r"\end{landscape}")
        parts.append(r"\end{document}")
        if missing := self.references - self.labels:
            raise LatexRenderError(f"unresolved references: {sorted(missing)}")
        destination.write_text("\n".join(parts), encoding="utf-8")
        return destination

    def _supplement(self, parts: list[str], report: Report, figure: int) -> int:
        if report.findings:
            parts.append(r"\section{Findings}")
            for finding in report.findings:
                figure = self._finding(parts, finding, figure)
        if report.appendices:
            parts.append(r"\appendix")
            for appendix in report.appendices:
                parts.append(f"\\section{{{latex_escape(appendix.title)}}}")
                parts.extend(self._optional_label(appendix.renderer_hints))
                if self.architecture and not appendix.renderer_hints.get("latex.label"):
                    parts.append(self._label(semantic_id(appendix.title)))
                for item in appendix.content:
                    figure = self._content(parts, item, appendix.title, figure)
        return figure

    def _sections(self, parts: list[str], report: Report) -> tuple[int, bool]:
        figure = 0
        printed_bibliography = False
        for section in report.sections:
            if (
                self.architecture
                and section.semantic == "source-provenance"
                and report.bibliography
            ):
                parts.extend(
                    [
                        r"\clearpage",
                        r"\section{" + latex_escape(section.title) + "}",
                        self._label(
                            section.renderer_hints.get(
                                "latex.label", semantic_id(section.title)
                            )
                        ),
                    ]
                )
                for item in section.content:
                    if (
                        not isinstance(item, Narrative)
                        or item.semantic != "bibliography"
                    ):
                        figure = self._content(parts, item, section.title, figure)
                parts.extend([r"\nocite{*}", r"\printbibliography[heading=none]"])
                printed_bibliography = True
                continue
            unheaded = self.architecture and section.semantic == "document-state"
            first_diagram = self.architecture and isinstance(
                section.content[0], ArchitectureDiagram
            )
            if first_diagram and not self.landscape_all:
                parts.extend([r"\clearpage", r"\begin{landscape}"])
            if not unheaded:
                parts.append(f"\\section{{{latex_escape(section.title)}}}")
                parts.extend(self._optional_label(section.renderer_hints))
                if self.architecture and not section.renderer_hints.get("latex.label"):
                    parts.append(self._label(semantic_id(section.title)))
            for index, item in enumerate(section.content):
                if first_diagram and index == 0:
                    figure = self._diagram(parts, item, figure, open_landscape=False)
                else:
                    figure = self._content(parts, item, section.title, figure)
        return figure, printed_bibliography

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
            f"{{{self._inline(finding.narrative.text)}}}"
        )
        if finding.visual is not None:
            return self._content(parts, finding.visual, finding.title, figure, finding)
        return figure

    def _narrative(self, parts: list[str], item: Narrative) -> None:
        if reference := item.renderer_hints.get("latex.ref"):
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9:_.-]*", reference) is None:
                raise LatexRenderError("references must be simple identifiers")
            self.references.add(reference)
            parts.append(self._inline(item.text) + f" \\ref{{{reference}}}")
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
                f"\\WoodCallout{{Wood{color}}}{{{style.label}}}{{{self._inline(item.text)}}}"
            )
        elif item.kind == "heading":
            command = {
                "h3": "subsection",
                "h4": "subsubsection",
                "h5": "paragraph",
                "h6": "subparagraph",
            }.get(item.semantic or "", "subsubsection")
            star = "" if self.architecture else "*"
            parts.append(f"\\{command}{star}{{{self._inline(item.text)}}}")
            if self.architecture:
                parts.append(
                    self._label(
                        item.renderer_hints.get("latex.label", semantic_id(item.text))
                    )
                )
            else:
                parts.extend(self._optional_label(item.renderer_hints))
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
                    self._inline(item.text),
                    r"\end{WoodTechnicalParagraph}",
                ]
            )
        else:
            parts.append(self._inline(item.text) + "\n")

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

    def _list(self, parts: list[str], text: str) -> None:
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
                parts.append(f"\\item[{{{marker}}}] " + self._inline(entry.text))
            else:
                parts.append("\n" + self._inline(entry.text))
        parts.extend([r"\end{list}"] * depth)

    def _content(
        self,
        parts: list[str],
        item: object,
        title: str,
        figure: int,
        finding: Finding | None = None,
    ) -> int:
        if isinstance(item, ArchitectureDiagram):
            return self._diagram(parts, item, figure)
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
                    f"\\caption{{{self._inline(item.caption or title)}}}",
                    self._label(label),
                    r"\end{figure}",
                ]
            )
            if source := item.renderer_hints.get("latex.source"):
                parts.append(f"\\WoodSource{{{latex_escape(source)}}}")
        elif isinstance(item, PublicationTable):
            self._table(
                parts,
                replace(item, caption=item.caption or title)
                if self.architecture
                else item,
                finding,
            )
        elif isinstance(item, Narrative):
            self._narrative(parts, item)
        else:
            raise LatexRenderError("unsupported report content")
        return figure

    def _diagram(
        self,
        parts: list[str],
        diagram: object,
        figure: int,
        *,
        open_landscape: bool = True,
    ) -> int:
        if not isinstance(diagram, ArchitectureDiagram):
            raise LatexRenderError("diagram content is required")
        graph = parse_flowchart(diagram.source)
        panels = diagram_panels(graph)
        if open_landscape and not self.landscape_all:
            parts.extend([r"\clearpage", r"\begin{landscape}"])
        for index, rows in enumerate(panels):
            if index:
                parts.append(r"\clearpage")
            figure += 1
            parts.extend(
                [
                    r"\begin{center}",
                    vector_panel(graph, rows, self.bibliography),
                    r"\captionof{figure}{"
                    + self._inline(diagram.caption)
                    + f" — panel {index + 1} of {len(panels)}"
                    + "}",
                    self._label(
                        (
                            diagram.renderer_hints["latex.label"]
                            + (f"-panel-{index + 1}" if index else "")
                        )
                        if "latex.label" in diagram.renderer_hints
                        else f"fig:{figure}"
                    ),
                    r"\end{center}",
                    r"{\footnotesize\color{Woodtext_muted} Legend: arrows preserve "
                    r"source-to-target direction; dashed arrows denote "
                    r"authored uncertainty. Endpoint labels repeat across panels; "
                    r"repeated labels represent the "
                    r"same declared node. Source flowchart direction: "
                    + graph.direction
                    + r".}\par",
                    *(
                        r"{\footnotesize " + self._inline(legend) + r"}\par"
                        for legend in graph.legends
                    ),
                ]
            )
        if not self.landscape_all:
            parts.append(r"\end{landscape}")
        parts.append(r"\clearpage")
        return figure

    def _table(
        self, parts: list[str], table: PublicationTable, finding: Finding | None
    ) -> None:
        policy = self.theme.table_layout
        self.table_number += 1
        if self.architecture:
            self._architecture_table(parts, table)
            return
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
                    f"\\caption{{{self._inline(table.caption or '')}}}"
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
                parts.append(f"\\caption{{{self._inline(table.caption or '')}}}")
            if label:
                parts.append(label_command)
            parts.append(r"\end{table}")
        if table.notes:
            parts.append(
                "{\\WoodNoteFont\\color{Woodtext_muted}\\textit{"
                + self._inline(" ".join(table.notes))
                + "}}"
            )
        if source := table.renderer_hints.get("latex.source"):
            parts.append(f"\\WoodSource{{{latex_escape(source)}}}")
        parts.append(r"\endgroup")

    def _architecture_table(self, parts: list[str], table: PublicationTable) -> None:
        count = len(table.columns)
        widths = (0.24, 0.39, 0.12, 0.25) if count == 4 else (1 / count,) * count
        if count == 4 and len(table.rows) == 1 and len(str(table.rows[0][1])) > 300:
            widths = (0.15, 0.62, 0.12, 0.11)
        columns = "".join(
            r">{\RaggedRight\arraybackslash}p{\dimexpr"
            + str(width)
            + r"\linewidth-2\tabcolsep\relax}"
            for width in widths
        )
        label = table.renderer_hints.get("latex.label", f"tab:{self.table_number}")
        header = (
            r"\toprule\rowcolor{Woodprimary} "
            + " & ".join(
                r"\color{Woodbackground}\bfseries " + latex_escape(column.label)
                for column in table.columns
            )
            + r"\\\midrule"
        )
        parts.extend(
            [
                r"\begingroup\WoodTableFont\WoodTableSetup",
                r"\begin{longtable}{" + columns + "}",
                r"\caption{"
                + self._inline(
                    table.caption or f"Technical evidence {self.table_number}"
                )
                + "}"
                + self._label(label)
                + r"\\",
                header + r"\endfirsthead",
                f"\\multicolumn{{{count}}}{{l}}{{\\WoodNoteFont "
                f"Table {self.table_number} continued}}" + r"\\",
                header + r"\endhead",
                r"\midrule"
                + f"\\multicolumn{{{count}}}{{r}}{{\\WoodNoteFont "
                + "Continued on next page}"
                + r"\\\endfoot",
                r"\bottomrule\endlastfoot",
            ]
        )
        for row in table.rows:
            parts.append(
                " & ".join(
                    self._cell(value, column.format)
                    for value, column in zip(row, table.columns, strict=True)
                )
                + r"\\"
            )
        parts.extend(
            [
                r"\end{longtable}",
                self._inline(" ".join(table.notes)),
                r"\endgroup",
            ]
        )

    def _cell(self, value: TableCell, format_spec: str | None) -> str:
        if value is None:
            return ""
        try:
            text = format(value, format_spec or "")
            return self._inline(text) if self.bibliography else latex_escape(text)
        except (TypeError, ValueError) as error:
            raise LatexRenderError(
                f"invalid table format {format_spec!r}: {error}"
            ) from error
