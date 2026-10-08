"""Validate bibliography navigation against semantic source occurrences."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from wood_reports.citations import citation_keys
from wood_reports.model import Report

type Entry = tuple[tuple[int, float], str]


@dataclass(frozen=True, slots=True)
class _Navigation:
    citation_pages: dict[str, set[int]]
    link_counts: Counter[str]
    urls: set[str]
    backrefs: dict[str, set[int]]
    internal: int
    citation_rectangles: dict[str, list[tuple[int, tuple[float, ...]]]]


def _read_navigation(
    reader: PdfReader, entries: list[Entry], issues: list[str]
) -> _Navigation:
    citation_pages: dict[str, set[int]] = defaultdict(set)
    link_counts: Counter[str] = Counter()
    urls: set[str] = set()
    backrefs: dict[str, set[int]] = defaultdict(set)
    internal = 0
    rectangles: dict[str, list[tuple[int, tuple[float, ...]]]] = defaultdict(list)
    destinations = reader.named_destinations
    page_references = {page.indirect_reference for page in reader.pages}
    for page_number, page in enumerate(reader.pages):
        for annotation in page.get("/Annots", []):
            item = annotation.get_object()
            action = item.get("/A", {})
            if action.get("/S") == "/URI":
                urls.add(str(action.get("/URI", "")))
                continue
            target = item.get("/Dest", action.get("/D"))
            if not isinstance(target, str):
                if target is not None and (
                    not isinstance(target, list)
                    or not target
                    or target[0] not in page_references
                ):
                    issues.append("broken internal array destination")
                continue
            internal += 1
            if target not in destinations:
                issues.append(f"broken internal destination: {target}")
                continue
            destination_page = reader.get_destination_page_number(destinations[target])
            if destination_page is None or not 0 <= destination_page < len(
                reader.pages
            ):
                issues.append(f"invalid internal destination page: {target}")
                continue
            if target.startswith("cite.0@"):
                key = target.removeprefix("cite.0@")
                link_counts[key] += 1
                citation_pages[key].add(page_number + 1)
                rectangle = tuple(float(value) for value in item.get("/Rect", []))
                rectangles[key].append((page_number, rectangle))
            elif target.startswith("page."):
                rectangle = item.get("/Rect", [0, 0, 0, 0])
                position = (page_number, -float(rectangle[3]))
                preceding = [entry for entry in entries if entry[0] <= position]
                if preceding:
                    page_label = target.removeprefix("page.")
                    if page_label.isdecimal():
                        backrefs[preceding[-1][1]].add(int(page_label))
                    else:
                        issues.append(f"invalid citation page label: {target}")
    return _Navigation(
        citation_pages, link_counts, urls, backrefs, internal, rectangles
    )


def _validate_occurrence_anchors(
    reader: PdfReader,
    occurrences: Counter[str],
    navigation: _Navigation,
    issues: list[str],
) -> int:
    counts: Counter[str] = Counter()
    for name, destination in reader.named_destinations.items():
        if not name.startswith("wood-citation."):
            continue
        _, separator, key = name.partition("@")
        if not separator:
            issues.append("invalid citation occurrence destination")
            continue
        counts[key] += 1
        page = reader.get_destination_page_number(destination)
        x, y = float(destination.left or 0), float(destination.top or 0)
        if not any(
            page == link_page
            and len(rectangle) == 4
            and rectangle[0] - 2 <= x <= rectangle[2] + 2
            and rectangle[1] - 12 <= y <= rectangle[3] + 12
            for link_page, rectangle in navigation.citation_rectangles[key]
        ):
            issues.append(f"citation occurrence lacks its bibliography link: {name}")
    for key, expected in occurrences.items():
        if counts[key] < expected:
            issues.append(f"missing citation occurrence destinations: {key}")
    return sum(counts.values())


def validate_biber_processing(logs: tuple[Path, ...]) -> str:
    """Require retained evidence of successful biber processing; no fallback."""
    bibliography_logs = [path for path in logs if path.suffix == ".blg"]
    if len(bibliography_logs) != 1:
        raise ValueError("bibliography requires one retained biber log")
    text = bibliography_logs[0].read_text(encoding="utf-8", errors="replace")
    version = re.search(r"INFO - This is Biber ([0-9.]+)", text)
    if (
        version is None
        or not re.search(r"INFO - Output to .+\.bbl", text)
        or re.search(r"(?:WARN|ERROR) -", text)
    ):
        raise ValueError("bibliography processing did not complete cleanly with biber")
    return version[1]


@dataclass(frozen=True, slots=True)
class CitationValidation:
    issues: tuple[str, ...]
    entries: int
    citation_occurrences: int
    inline_links: int
    source_urls: int
    back_references: int
    internal_links: int
    occurrence_destinations: int = 0

    @property
    def passed(self) -> bool:
        return not self.issues

    def require_passed(self) -> None:
        if self.issues:
            raise ValueError("; ".join(self.issues))


def validate_citation_navigation(report: Report, pdf: Path) -> CitationValidation:
    """Check destinations, every source mapping, external URLs and per-entry backrefs.

    A wrapped citation can produce several PDF link rectangles. Require at least
    one functional rectangle per semantic occurrence; preserve the exact logical
    occurrence multiset separately in the report and generated LaTeX evidence.
    """
    reader = PdfReader(pdf)
    destinations = reader.named_destinations
    issues: list[str] = []
    aliases = {
        name: source.key
        for source in report.bibliography
        for name in (source.key, *source.aliases)
    }
    occurrences = Counter(
        aliases[key] for text in report.citation_texts() for key in citation_keys(text)
    )
    # Entry intervals use PDF reading order, including entries split over pages.
    entries: list[Entry] = []
    for source in report.bibliography:
        target = f"cite.0@{source.key}"
        if target not in destinations:
            issues.append(f"missing bibliography destination: {source.key}")
            continue
        destination = destinations[target]
        page_index = reader.get_destination_page_number(destination)
        if page_index is None or page_index < 0 or page_index >= len(reader.pages):
            issues.append(f"invalid bibliography destination: {source.key}")
            continue
        entries.append(((page_index, -float(destination.top or 0)), source.key))
    entries.sort()
    navigation = _read_navigation(reader, entries, issues)
    anchors = _validate_occurrence_anchors(reader, occurrences, navigation, issues)
    for key, count in occurrences.items():
        if navigation.link_counts[key] < count:
            issues.append(f"missing inline citation occurrences: {key}")
        if navigation.citation_pages[key] != navigation.backrefs[key]:
            issues.append(f"incorrect citation page back-references: {key}")
    expected_urls = {source.url for source in report.bibliography if source.url}
    missing_urls = expected_urls - navigation.urls
    if missing_urls:
        issues.append(f"missing external source URLs: {len(missing_urls)}")
    return CitationValidation(
        tuple(issues),
        len(entries),
        sum(occurrences.values()),
        sum(navigation.link_counts.values()),
        len(expected_urls & navigation.urls),
        sum(len(pages) for pages in navigation.backrefs.values()),
        navigation.internal,
        anchors,
    )
