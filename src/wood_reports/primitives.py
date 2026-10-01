"""Shared Markdown interpretation used by both publication renderers."""

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


def latex_inline(text: str) -> str:
    parts: list[str] = []
    for run in text_runs(text):
        value = latex_escape(run.text)
        if run.code:
            value = f"\\texttt{{{value}}}"
        if run.italic:
            value = f"\\emph{{{value}}}"
        if run.bold:
            value = f"\\textbf{{{value}}}"
        if run.hyperlink:
            value = f"\\href{{{latex_escape(run.hyperlink)}}}{{{value}}}"
        parts.append(value)
    return "".join(parts)
