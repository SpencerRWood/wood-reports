"""Versioned, deterministic vector rendering of a strict Mermaid flowchart subset.

The source remains owned by the Markdown author. Unsupported syntax is an error,
never a partially rendered graph. Relationship panels repeat endpoint labels to
keep large technical estates readable without changing direction or membership.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from wood_reports.citations import BibliographySource, citation_inline

RENDERER_ID = "wood-mermaid-relationship-panels"
RENDERER_VERSION = "1.0.0"


@dataclass(frozen=True, slots=True)
class DiagramNode:
    identity: str
    label: str
    boundary: str | None = None


@dataclass(frozen=True, slots=True)
class DiagramEdge:
    source: str
    target: str
    label: str
    uncertain: bool = False


@dataclass(frozen=True, slots=True)
class DiagramGraph:
    nodes: tuple[DiagramNode, ...]
    edges: tuple[DiagramEdge, ...]
    direction: str
    legends: tuple[str, ...] = ()


def parse_flowchart(source: str) -> DiagramGraph:  # noqa: PLR0912
    nodes: dict[str, DiagramNode] = {}
    edges: list[DiagramEdge] = []
    boundaries: list[str] = []
    legends: list[str] = []
    lines = source.strip().splitlines()
    header = (
        re.fullmatch(r"(?:flowchart|graph) (LR|RL|TD|TB|BT)", lines[0])
        if lines
        else None
    )
    if header is None:
        raise ValueError("diagram requires a Mermaid flowchart direction")
    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("%% legend: "):
            legends.append(line.removeprefix("%% legend: "))
            continue
        if line.startswith("%%"):
            raise ValueError(
                "unsupported diagram comment; only explicit legend comments "
                "are supported"
            )
        if boundary := re.fullmatch(r'subgraph [A-Za-z][\w-]*\["([^"\n]+)"\]', line):
            boundaries.append(boundary[1])
        elif line == "end":
            if not boundaries:
                raise ValueError("diagram has an unmatched boundary end")
            boundaries.pop()
        elif node := re.fullmatch(r'([A-Za-z][\w-]*)\["([^"\n]+)"\]', line):
            if node[1] in nodes:
                raise ValueError("diagram has a duplicate node")
            nodes[node[1]] = DiagramNode(
                node[1], node[2], " / ".join(boundaries) or None
            )
        elif edge := re.fullmatch(
            r'([A-Za-z][\w-]*) (-->|-\.->)\|"([^"\n]+)"\| ([A-Za-z][\w-]*)', line
        ):
            edges.append(DiagramEdge(edge[1], edge[4], edge[3], edge[2] == "-.->"))
        else:
            raise ValueError(f"unsupported Mermaid syntax: {line}")
    if boundaries:
        raise ValueError("diagram has an unclosed boundary")
    if not nodes or any(
        edge.source not in nodes or edge.target not in nodes for edge in edges
    ):
        raise ValueError("diagram requires declared nodes for every relationship")
    return DiagramGraph(tuple(nodes.values()), tuple(edges), header[1], tuple(legends))


@dataclass(frozen=True, slots=True)
class ArchitectureDiagram:
    """Source-owned diagram; also usable by future technical document profiles."""

    source: str
    caption: str
    renderer_hints: dict[str, str] = field(default_factory=dict)

    def validate(self, element: str) -> None:
        try:
            parse_flowchart(self.source)
            if not self.caption.strip():
                raise ValueError("diagram caption is required")
        except ValueError as error:
            raise ValueError(f"{element}: {error}") from error


def _node_text(node: DiagramNode, sources: tuple[BibliographySource, ...]) -> str:
    label = citation_inline(node.label, sources)
    if node.boundary:
        label += (
            r"\\{\footnotesize Boundary: "
            + citation_inline(node.boundary, sources)
            + "}"
        )
    return label


def diagram_panels(
    graph: DiagramGraph,
) -> tuple[tuple[DiagramEdge | DiagramNode, ...], ...]:
    connected = {
        identity for edge in graph.edges for identity in (edge.source, edge.target)
    }
    rows: tuple[DiagramEdge | DiagramNode, ...] = (
        *graph.edges,
        *(node for node in graph.nodes if node.identity not in connected),
    )
    # Seven relationship rows fit a landscape page at a readable nine-point size.
    return tuple(rows[index : index + 7] for index in range(0, len(rows), 7))


def vector_panel(
    graph: DiagramGraph,
    rows: tuple[DiagramEdge | DiagramNode, ...],
    sources: tuple[BibliographySource, ...] = (),
) -> str:
    nodes = {node.identity: node for node in graph.nodes}
    parts = [
        r"\begin{tikzpicture}[>=Stealth,woodnode/.style={draw=Woodprimary,"
        r"rounded corners=2pt,fill=Woodbackground,text width=7.6cm,"
        r"minimum height=1.35cm,align=left,inner sep=5pt,"
        r"font=\fontsize{9}{11}\selectfont}]"
    ]
    for index, row in enumerate(rows):
        y = -index * 1.95
        source = nodes[row.source] if isinstance(row, DiagramEdge) else row
        parts.append(
            f"\\node[woodnode] (a{index}) at (0,{y}) {{{_node_text(source, sources)}}};"
        )
        if isinstance(row, DiagramEdge):
            parts.append(
                f"\\node[woodnode] (b{index}) at (12,{y}) "
                f"{{{_node_text(nodes[row.target], sources)}}};"
            )
            style = "dashed," if row.uncertain else ""
            parts.append(
                f"\\draw[{style}->,Woodprimary,thick] (a{index}.east) -- "
                r"node[above,font=\footnotesize,align=center,text width=3cm] "
                f"{{{citation_inline(row.label, sources)}}} (b{index}.west);"
            )
        else:
            parts.append(
                r"\node[font=\footnotesize,text=Woodtext_muted,align=left] "
                f"at (12,{y}) {{No relationship declared in this source graph.}};"
            )
    parts.append(r"\end{tikzpicture}")
    return "\n".join(parts)
