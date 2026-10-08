"""Deterministic TeX log classification, separate from compiler exit status."""

import re
from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True, slots=True)
class DiagnosticContext:
    log_line: int
    message: str
    source_lines: str | None = None
    magnitude: float | None = None


@dataclass(frozen=True, slots=True)
class CompilerDiagnostic:
    category: str
    severity: Literal["error", "warning"]
    occurrence_count: int
    log: str
    contexts: tuple[DiagnosticContext, ...]


_PATTERNS = (
    ("infinite-glue-shrinkage", "error", r"Infinite glue shrinkage[^\n]*"),
    ("undefined-control-sequence", "error", r"Undefined control sequence[^\n]*"),
    ("missing-font", "error", r"Font unavailable:[^\n]*|fontspec Error:[^\n]*"),
    ("missing-asset", "error", r"(?:File|file) [^\n]+not found|not found:[^\n]*"),
    ("missing-glyph", "error", r"Missing character:[^\n]*"),
    (
        "unresolved-reference",
        "warning",
        r"(?:Reference[^\n]+undefined|undefined references)[^\n]*",
    ),
    (
        "unresolved-citation",
        "warning",
        r"(?:Citation[^\n]+undefined|undefined citations)[^\n]*",
    ),
    (
        "overfull-box",
        "warning",
        r"Overfull \\[hv]box \(([\d.]+)pt too (?:wide|high)\)[^\n]*",
    ),
    ("underfull-box", "warning", r"Underfull \\[hv]box \(badness (\d+)\)[^\n]*"),
    (
        "page-table-break",
        "warning",
        r"(?:Float too large for page|longtable Warning:[^\n]*|"
        r"Table start group exceeds page|Table widths have changed)[^\n]*",
    ),
    (
        "tex-structural",
        "error",
        r"^![^\n]*|Fatal error[^\n]*|Latexmk: Errors[^\n]*|"
        r"(?:LaTeX|Package \S+) Error:[^\n]*",
    ),
)


def parse_tex_diagnostics(
    text: str, *, log: str = "compiler.log", underfull_badness: int = 1000
) -> tuple[CompilerDiagnostic, ...]:
    """Count occurrences once per authoritative log, with available context.

    Badness 1000 includes visibly stretched paragraphs without rejecting a
    structurally sound PDF. Full raw logs remain the diagnostic authority.
    """
    if type(underfull_badness) is not int or not 0 <= underfull_badness <= 10000:
        raise ValueError("underfull_badness must be an integer from 0 to 10000")
    diagnostics: list[CompilerDiagnostic] = []
    claimed: list[tuple[int, int]] = []
    for category, severity, pattern in _PATTERNS:
        contexts: list[DiagnosticContext] = []
        for match in re.finditer(pattern, text, re.I | re.M):
            if any(
                start < match.end() and end > match.start() for start, end in claimed
            ):
                continue
            claimed.append(match.span())
            magnitude = float(match[1]) if match.lastindex else None
            if category == "underfull-box" and (
                magnitude is not None and magnitude < underfull_badness
            ):
                continue
            nearby = match.group()
            for line in text[match.end() : match.end() + 240].splitlines()[:4]:
                if re.match(
                    r"!|(?:LaTeX|Package|ignored|Overfull|Underfull|Fatal)", line
                ):
                    break
                nearby += "\n" + line
            source = re.search(
                r"(?:(?:at lines?|input line) (\d+(?:--\d+)?)|^l\.(\d+))",
                nearby,
                re.M,
            )
            contexts.append(
                DiagnosticContext(
                    text.count("\n", 0, match.start()) + 1,
                    match.group(),
                    (source[1] or source[2]) if source else None,
                    magnitude,
                )
            )
        if contexts:
            diagnostics.append(
                CompilerDiagnostic(
                    category,
                    "error" if severity == "error" else "warning",
                    len(contexts),
                    log,
                    tuple(contexts),
                )
            )
    return tuple(diagnostics)
