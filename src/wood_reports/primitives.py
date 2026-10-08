"""Shared Markdown interpretation used by both publication renderers."""

import re
from dataclasses import dataclass

from markdown_it import MarkdownIt


@dataclass(frozen=True, slots=True)
class TextRun:
    text: str
    bold: bool = False
    italic: bool = False
    code: bool = False
    hyperlink: str | None = None


def text_runs(text: str) -> tuple[TextRun, ...]:
    """Resolve emphasis and inline code without exposing Markdown delimiters."""
    tokens = MarkdownIt().parseInline(text)[0].children or []
    bold = italic = False
    hyperlink: str | None = None
    runs: list[TextRun] = []
    for token in tokens:
        if token.type in {"strong_open", "strong_close"}:
            bold = token.type == "strong_open"
        elif token.type in {"em_open", "em_close"}:
            italic = token.type == "em_open"
        elif token.type in {"link_open", "link_close"}:
            hyperlink = (
                str(token.attrGet("href")) if token.type == "link_open" else None
            )
        elif token.type in {"softbreak", "hardbreak"}:
            runs.append(TextRun("\n", bold, italic, hyperlink=hyperlink))
        elif token.type in {"text", "code_inline"}:
            runs.append(
                TextRun(
                    token.content, bold, italic, token.type == "code_inline", hyperlink
                )
            )
    return tuple(runs)


@dataclass(frozen=True, slots=True)
class ListEntry:
    text: str
    level: int
    marker: str


def list_entries(text: str) -> tuple[ListEntry, ...]:
    """Keep list order, numbering starts, nesting, and continuation paragraphs."""
    stack: list[tuple[bool, int]] = []
    entries: list[ListEntry] = []
    marker = ""
    for token in MarkdownIt().parse(text):
        if token.type in {"bullet_list_open", "ordered_list_open"}:
            stack.append(
                (token.type == "ordered_list_open", int(token.attrGet("start") or 1))
            )
        elif token.type in {"bullet_list_close", "ordered_list_close"}:
            stack.pop()
        elif token.type == "list_item_open":
            ordered, number = stack[-1]
            marker = f"{number}." if ordered else "•"
            stack[-1] = ordered, number + 1
        elif token.type == "inline":
            entries.append(ListEntry(token.content, len(stack) - 1, marker))
            marker = ""
    return tuple(entries)


def latex_escape(text: str) -> str:
    """Escape publication text, including metadata, instead of interpreting TeX."""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


_TECHNICAL = re.compile(
    r"https?://[^\s<>]+|[\w]+(?:[/_.][\w.-]+)+",
    re.UNICODE,
)


def has_technical_text(text: str) -> bool:
    """Identify semantic code, links, paths, keys and repository identifiers."""
    return any(
        run.code or run.hyperlink or _TECHNICAL.search(run.text)
        for run in text_runs(text)
    )


def latex_identifier(text: str) -> str:
    """Wrap literal segments without introducing discretionary visible hyphens."""
    if not _TECHNICAL.search(text) and len(text) <= 16:
        return latex_escape(text)
    pieces = re.split(r"([/_.:-])", text)
    return r"\allowbreak{}".join(
        # Very long unbroken identifiers still need lossless break opportunities.
        r"\penalty500{}".join(
            r"\mbox{" + latex_escape(piece[start : start + 16]) + "}"
            for start in range(0, len(piece), 16)
        )
        for piece in pieces
        if piece
    )


def latex_prose(text: str) -> str:
    parts: list[str] = []
    position = 0
    for match in _TECHNICAL.finditer(text):
        parts.extend(
            [
                latex_escape(text[position : match.start()]),
                latex_identifier(match.group()),
            ]
        )
        position = match.end()
    parts.append(latex_escape(text[position:]))
    return "".join(parts)


def latex_text_run(run: TextRun, value: str | None = None) -> str:
    """Apply authored formatting around already-rendered inline semantics."""
    value = latex_prose(run.text) if value is None else value
    if run.code:
        value = f"\\texttt{{{latex_identifier(run.text)}}}"
    if run.italic:
        value = f"\\emph{{{value}}}"
    if run.bold:
        value = f"\\textbf{{{value}}}"
    if run.hyperlink:
        value = f"\\href{{{latex_escape(run.hyperlink)}}}{{{value}}}"
    return value


def latex_inline(text: str) -> str:
    return "".join(latex_text_run(run) for run in text_runs(text))
