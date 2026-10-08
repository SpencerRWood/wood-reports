"""Shared, source-preserving bibliography and Markdown citation contract."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from wood_reports.primitives import latex_inline, latex_prose, latex_text_run, text_runs

CITATION = re.compile(
    r"\[\^([^\]\s]+)\]|\[((?:-?@[A-Za-z0-9][\w:./-]*(?:\s*;\s*)?)+)\]"
)
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9:._/-]*")


@dataclass(frozen=True, slots=True)
class BibliographySource:
    """Stable source identity; absent evidence remains explicitly absent."""

    key: str
    title: str
    url: str
    label: str
    repository: str = "not provided"
    path: str = "not provided"
    revision: str = "not provided"
    source_type: str = "not provided"
    evidence_state: str = "not provided"
    observed_at: str = "not provided"
    limitations: str = "not provided"
    aliases: tuple[str, ...] = ()
    bibliographic_type: str = "webpage"

    def validate(self) -> None:
        if (
            not KEY.fullmatch(self.key)
            or not self.title.strip()
            or not self.label.strip()
        ):
            raise ValueError("bibliography requires a stable key, title and label")
        parsed = urlsplit(self.url)
        if self.url and (
            parsed.scheme not in {"https", "http"}
            or not parsed.netloc
            or parsed.username
            or parsed.password
            or any(character in self.url for character in "{}\\\n\r\x00")
        ):
            raise ValueError("bibliography source requires a safe external URL")
        if any(not KEY.fullmatch(alias) for alias in self.aliases):
            raise ValueError("bibliography aliases must be stable citation keys")

    @property
    def identity(self) -> tuple[str, str]:
        return self.url or f"{self.repository}/{self.path}", self.revision

    @property
    def provenance(self) -> str:
        return "; ".join(
            f"{name}: {value}"
            for name, value in (
                ("Repository", self.repository),
                ("Path", self.path),
                ("Revision", self.revision),
                ("Source type", self.source_type),
                ("Evidence state", self.evidence_state),
                ("Observed at", self.observed_at),
                ("Evidence limitations", self.limitations),
            )
        )


def deduplicate(
    sources: tuple[BibliographySource, ...],
) -> tuple[BibliographySource, ...]:
    """Deduplicate identical evidence, rejecting contradictory provenance."""
    result: dict[tuple[str, str], BibliographySource] = {}
    aliases: set[str] = set()
    for source in sources:
        source.validate()
        names = {source.key, *source.aliases}
        previous = result.get(source.identity)
        permitted = {previous.key} if previous and previous.key == source.key else set()
        if (aliases & names) - permitted:
            raise ValueError("duplicate bibliography key or alias")
        aliases.update(names)
        if previous is None:
            result[source.identity] = source
            continue
        if any(
            getattr(previous, field) != getattr(source, field)
            for field in (
                "repository",
                "path",
                "source_type",
                "evidence_state",
                "observed_at",
                "limitations",
                "bibliographic_type",
            )
        ):
            raise ValueError(
                "same source identity and revision has conflicting provenance"
            )
        result[source.identity] = replace(
            previous,
            aliases=(
                *previous.aliases,
                *((source.key,) if source.key != previous.key else ()),
                *source.aliases,
            ),
        )
    return tuple(result.values())


def _keys(text: str) -> tuple[str, ...]:
    return tuple(
        key
        for match in CITATION.finditer(text)
        for key in (
            (match[1],) if match[1] else tuple(re.findall(r"@([\w:./-]+)", match[2]))
        )
    )


def citation_keys(text: str) -> tuple[str, ...]:
    return tuple(
        key for run in text_runs(text) if not run.code for key in _keys(run.text)
    )


def citation_inline(
    text: str,
    sources: tuple[BibliographySource, ...],
    *,
    local_reference: Callable[[str, str], str] | None = None,
) -> str:
    names = {
        name: entry.key for entry in sources for name in (entry.key, *entry.aliases)
    }
    parts: list[str] = []
    for run in text_runs(text):
        if run.code:
            parts.append(latex_text_run(run))
            continue
        fragments: list[str] = []
        position = 0
        for match in CITATION.finditer(run.text):
            fragments.append(latex_prose(run.text[position : match.start()]))
            keys = _keys(match.group())
            try:
                fragments.append(
                    r"\woodcite{" + ",".join(names[key] for key in keys) + "}"
                )
            except KeyError as error:
                raise ValueError(f"unresolved citation: {error.args[0]}") from error
            position = match.end()
        remainder = CITATION.sub("", run.text)
        if re.search(r"\[(?:-?@|\^)", remainder):
            raise ValueError(
                "unsupported citation syntax; use [@stable-key] or source footnotes"
            )
        fragments.append(latex_prose(run.text[position:]))
        if local_reference and run.hyperlink and run.hyperlink.startswith("#"):
            value = latex_text_run(replace(run, hyperlink=None), "".join(fragments))
            parts.append(local_reference(run.hyperlink[1:], value))
        else:
            parts.append(latex_text_run(run, "".join(fragments)))
    return "".join(parts)


def footnote_sources(body: str) -> tuple[str, tuple[BibliographySource, ...]]:
    """Consume established Markdown source footnotes without rewriting facts."""
    sources: list[BibliographySource] = []
    retained: list[str] = []
    for line in body.splitlines():
        match = re.fullmatch(
            r"\[\^([^\]]+)\]: \[([^\]]+)\]\((https?://[^\s)]+)\)(.*)", line
        )
        if match is None:
            local = re.fullmatch(r"\[\^([^\]]+)\]: Local worktree: ([^;]+); (.+)", line)
            if local:
                alias, location, evidence = local.groups()
                parts = location.split("/")
                if len(parts) < 3:
                    raise ValueError("local source requires repository and path")
                digest = hashlib.sha256(line.split(": ", 1)[1].encode()).hexdigest()[
                    :12
                ]
                sources.append(
                    BibliographySource(
                        key=f"source-{digest}",
                        title=f"Local worktree: {location}",
                        url="",
                        label=f"{parts[1]} / {'/'.join(parts[2:])} / uncommitted",
                        repository="/".join(parts[:2]),
                        path="/".join(parts[2:]),
                        revision="uncommitted"
                        if "uncommitted" in evidence
                        else "not provided",
                        source_type="local worktree",
                        bibliographic_type="document",
                        evidence_state=evidence.rstrip("."),
                        limitations=(
                            "Local worktree evidence; no pinned revision, source URL "
                            "or observation timestamp provided; "
                            "deployment health is not attested."
                        ),
                        aliases=(alias,),
                    )
                )
                continue
            if re.match(r"\[\^[^\]]+\]:", line):
                raise ValueError(
                    "source footnotes require a linked title and provenance text"
                )
            retained.append(line)
            continue
        alias, title, url, note = match.groups()
        path_parts = urlsplit(url).path.strip("/").split("/")
        github = urlsplit(url).hostname == "github.com" and len(path_parts) >= 2
        repository = "/".join(path_parts[:2]) if github else "not provided"
        repository_file = github and len(path_parts) >= 5 and path_parts[2] == "blob"
        pinned = (
            repository_file
            and re.fullmatch(r"[a-fA-F0-9]{7,40}", path_parts[3]) is not None
        )
        revision = path_parts[3] if repository_file else "not provided"
        path = (
            "/".join(path_parts[4:])
            if repository_file
            else "repository metadata"
            if github
            else "not provided"
        )
        evidence = note.strip(" ;.") or "not provided"
        digest = hashlib.sha256(f"{url}\n{revision}".encode()).hexdigest()[:12]
        label = path_parts[1] if github else urlsplit(url).hostname or "source"
        label += " / " + (
            path.split("/")[-1]
            if repository_file
            else "repository metadata"
            if github
            else title
        )
        if pinned:
            label += " / " + revision[:12]
        sources.append(
            BibliographySource(
                key=f"source-{digest}",
                title=title,
                url=url,
                label=label,
                repository=repository,
                path=path,
                revision=revision,
                source_type="repository file"
                if repository_file
                else "repository metadata"
                if github
                else "external source",
                evidence_state=evidence,
                limitations="Pinned URL; deployment health is not attested."
                if pinned
                else (
                    "Unpinned source; revision and observation timestamp not provided; "
                    "deployment health is not attested."
                ),
                aliases=(alias,),
            )
        )
    return "\n".join(retained), tuple(sources)


def structured_sources(value: object) -> tuple[BibliographySource, ...]:
    """Consume CSL/Pandoc references plus explicit provenance extension fields."""
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError("references must be a list of structured bibliography entries")
    fields = {
        "id": "key",
        "title": "title",
        "URL": "url",
        "short-title": "label",
        "repository": "repository",
        "path": "path",
        "revision": "revision",
        "type": "bibliographic_type",
        "source-type": "source_type",
        "evidence-state": "evidence_state",
        "observation-timestamp": "observed_at",
        "note": "limitations",
    }
    result = []
    for entry in value:
        if not isinstance(entry, dict) or set(entry) - fields.keys():
            raise ValueError("references contains unsupported entry fields")
        if not {"id", "title", "URL"} <= entry.keys() or not all(
            isinstance(item, str) for item in entry.values()
        ):
            raise ValueError("references requires text id, title, URL and metadata")
        values = {fields[key]: item for key, item in entry.items()}
        values.setdefault("label", values["title"])
        result.append(BibliographySource(**values))
    return tuple(result)


def bibliography_text(sources: tuple[BibliographySource, ...]) -> str:
    return (
        "\n\n".join(
            "@online{"
            + source.key
            + ",\n"
            + ",\n".join(
                f"  {name} = {{{value}}}"
                for name, value in (
                    ("title", latex_inline(source.title)),
                    ("shorttitle", latex_inline(source.label)),
                    ("url", source.url),
                    (
                        "note",
                        r"\newline ".join(
                            latex_inline(group)
                            for group in (
                                f"Repository: {source.repository}; "
                                f"Path: {source.path}.",
                                f"Revision: {source.revision}; "
                                f"Source type: {source.source_type}.",
                                f"Evidence state: {source.evidence_state}; "
                                f"Observed at: {source.observed_at}.",
                                f"Evidence limitations: {source.limitations}",
                            )
                        ),
                    ),
                )
            )
            + "\n}"
            for source in sources
        )
        + "\n"
    )


BIBLATEX_PREAMBLE = r"""
\usepackage[backend=biber,style=authortitle,sorting=none,
  backref=true,backrefstyle=none,block=par]{biblatex}
\usepackage{xurl}
\addbibresource{sources.bib}
\renewcommand*{\bibfont}{\small\RaggedRight\setlength{\emergencystretch}{3em}}
\setlength{\bibhang}{0pt}
\setlength{\bibitemsep}{0.6\baselineskip}
\setcounter{biburlnumpenalty}{100}
\setcounter{biburlucpenalty}{100}
\setcounter{biburllcpenalty}{100}
\newcounter{WoodCitationOccurrence}
\DeclareCiteCommand{\woodcite}{\bibopenbracket}
  {\usebibmacro{citeindex}\stepcounter{WoodCitationOccurrence}%
   \hypertarget{wood-citation.\arabic{WoodCitationOccurrence}@\thefield{entrykey}}%
     {\printtext[bibhyperref]{\printfield{shorttitle}}}}
  {\multicitedelim}{\bibclosebracket}
\DeclareBibliographyDriver{online}{%
  \begin{minipage}[t]{\linewidth}\RaggedRight%
  \printtext{\bfseries\printfield{shorttitle}}\newunit\newblock
  \printfield{title}\newunit\newblock
  \printfield{note}\newunit\newblock
  \usebibmacro{url+urldate}\newunit\newblock
  \usebibmacro{pageref}\usebibmacro{finentry}\end{minipage}}
"""

# TeX Live itself supplies the supported binary directory; no deployment path,
# PATH mutation, shell-escape, alternate engine or bibliography downgrade.
BIBLATEX_LATEXMKRC = r"""
my $wood_tex_bin = `kpsewhich --var-value=SELFAUTOLOC`;
chomp $wood_tex_bin;
die "Wood Reports requires TeX Live biber\n" unless -x "$wood_tex_bin/biber";
$biber = '"' . $wood_tex_bin . '/biber" %O %B';
"""
