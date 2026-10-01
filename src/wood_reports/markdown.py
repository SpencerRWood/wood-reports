"""Compile profile-compliant Markdown directly into the shared Report model."""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from markdown_it import MarkdownIt
from markdown_it.token import Token

from wood_reports.compiler import ReportCompiler, SourceCompilationError, TemplateValues
from wood_reports.model import (
    Appendix,
    ChartReference,
    Narrative,
    PublicationTable,
    Report,
    ReportContent,
    ReportMetadata,
    ReportValidationError,
    Section,
    TableColumn,
)
from wood_reports.profiles import DocumentProfile, ProfileValidationError, get_profile


def _frontmatter(text: str, source: Path) -> tuple[dict[str, str], str]:
    lines = text.removeprefix("\ufeff").replace("\r\n", "\n").splitlines()
    if not lines or lines[0] != "---":
        raise SourceCompilationError(source, "frontmatter", "must begin with ---")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise SourceCompilationError(
            source, "frontmatter", "must be closed with ---"
        ) from error
    raw = "\n".join(lines[1:end])
    try:
        node = yaml.compose(raw)
        if isinstance(node, yaml.MappingNode):
            if not all(isinstance(key, yaml.ScalarNode) for key, _ in node.value):
                raise SourceCompilationError(
                    source, "frontmatter", "metadata keys must be scalar text"
                )
            names = [key.value for key, _ in node.value]
            if len(names) != len(set(names)):
                raise SourceCompilationError(
                    source, "frontmatter", "duplicate metadata key"
                )
        values = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise SourceCompilationError(source, "frontmatter", str(error)) from error
    if not isinstance(values, dict) or not all(
        isinstance(key, str) and isinstance(value, str) for key, value in values.items()
    ):
        raise SourceCompilationError(
            source,
            "frontmatter",
            "requires text keys and values; quote dates and versions",
        )
    return values, "\n".join(lines[end + 1 :])


class MarkdownReportCompiler:
    """Deterministic source validation with no renderer or LLM dependency."""

    def __init__(self, values: TemplateValues | None = None) -> None:
        self._text_compiler = ReportCompiler(values)
        self._parser = MarkdownIt("commonmark", {"html": False}).enable("table")

    def compile_text(
        self,
        text: str,
        *,
        source: Path = Path("report.md"),
        artifact_root: Path | None = None,
        doc_type: str | None = None,
        doc_name: str | None = None,
    ) -> Report:
        metadata, body = _frontmatter(text, source)
        if doc_type is not None:
            metadata["doc_type"] = doc_type
        if doc_name is not None:
            metadata["doc_name"] = doc_name
        try:
            profile = get_profile(metadata.get("doc_type", ""))
            sections, appendices, semantics = self._sections(body, source, profile)
            profile.validate_instance(metadata, semantics)
        except ProfileValidationError as error:
            raise SourceCompilationError(source, "profile", str(error)) from error
        fields = {
            name: self._render(value, source, f"frontmatter.{name}")
            for name, value in metadata.items()
        }
        report = Report(
            ReportMetadata(
                title=fields["title"],
                doc_type=fields["doc_type"],
                doc_name=fields["doc_name"],
                profile_version=profile.version,
                subtitle=fields.get("subtitle"),
                author=fields.get("author"),
                source=fields.get("source"),
                client=fields.get("client"),
                project=fields.get("project"),
                engagement=fields.get("engagement"),
                version=fields.get("version"),
                audience=fields.get("audience"),
                confidentiality=fields.get("confidentiality"),
                period=fields.get("period"),
                comparison_period=fields.get("comparison_period"),
            ),
            tuple(sections),
            appendices=tuple(appendices),
        )
        try:
            report.validate(artifact_root or source.parent)
        except ReportValidationError as error:
            raise SourceCompilationError(source, error.element, str(error)) from error
        return report

    def compile_file(
        self,
        source: Path,
        *,
        artifact_root: Path | None = None,
    ) -> Report:
        try:
            text = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise SourceCompilationError(source, "source", str(error)) from error
        return self.compile_text(text, source=source, artifact_root=artifact_root)

    def _render(self, text: str, source: Path, field: str) -> str:
        return self._text_compiler._render_text(text, source, field)

    def _sections(
        self,
        body: str,
        source: Path,
        profile: DocumentProfile,
    ) -> tuple[list[Section], list[Appendix], tuple[str, ...]]:
        tokens = self._parser.parse(body)
        sections: list[Section] = []
        appendices: list[Appendix] = []
        semantics: list[str] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            if token.type != "heading_open" or token.tag not in {"h1", "h2"}:
                raise SourceCompilationError(
                    source, "body", "content must follow a profile section heading (##)"
                )
            heading = tokens[index + 1].content
            if token.tag == "h1":
                if index != 0:
                    raise SourceCompilationError(
                        source, "body", "only one leading document title (#) is allowed"
                    )
                index += 3
                continue
            rule = profile.section(heading)
            semantics.append(rule.identity)
            index += 3
            start = index
            while index < len(tokens) and not (
                tokens[index].type == "heading_open"
                and tokens[index].tag in {"h1", "h2"}
                and tokens[index].level == 0
            ):
                index += 1
            content = self._content(
                tokens[start:index], source, profile, body.splitlines()
            )
            if not content:
                raise SourceCompilationError(
                    source, f"sections.{rule.identity}", "must contain authored content"
                )
            if rule.identity == "appendix":
                appendices.append(Appendix(heading, content))
            else:
                sections.append(Section(heading, content, semantic=rule.identity))
        return sections, appendices, tuple(semantics)

    def _content(  # noqa: PLR0912, PLR0915
        self,
        tokens: list[Token],
        source: Path,
        profile: DocumentProfile,
        lines: list[str],
    ) -> tuple[ReportContent, ...]:
        content: list[ReportContent] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            field = f"body.line[{token.map[0] + 1}]" if token.map else "body"
            if token.type == "paragraph_open":
                inline = tokens[index + 1]
                images = [
                    child for child in inline.children or [] if child.type == "image"
                ]
                if images:
                    if len(inline.children or []) != 1:
                        raise SourceCompilationError(
                            source,
                            field,
                            "chart references must occupy a standalone paragraph",
                        )
                    item: ReportContent = self._chart(images[0], source, field)
                    kind = "chart"
                else:
                    item = Narrative(self._render(inline.content, source, field))
                    kind = "prose"
                index += 3
            elif token.type == "table_open":
                end = self._closing(tokens, index, "table_close")
                if token.map is not None:
                    self._validate_table_width(
                        lines[token.map[0] : token.map[1]], source, field
                    )
                item = self._table(tokens[index + 1 : end], source, field)
                kind = "table"
                index = end + 1
            elif token.type in {"bullet_list_open", "ordered_list_open"}:
                end = self._closing(tokens, index, token.type.replace("open", "close"))
                self._require_prose_inlines(tokens[index:end], source, field)
                text = (
                    "\n".join(lines[token.map[0] : token.map[1]]) if token.map else ""
                )
                marker = "ordered" if token.type == "ordered_list_open" else "bullet"
                item = Narrative(
                    self._render(text, source, field), kind="list", semantic=marker
                )
                kind = "list"
                index = end + 1
            elif token.type == "blockquote_open":
                end = self._closing(tokens, index, "blockquote_close")
                self._require_prose_inlines(tokens[index:end], source, field)
                text = "\n\n".join(
                    child.content
                    for child in tokens[index:end]
                    if child.type == "inline"
                )
                match = re.fullmatch(r"\[!([A-Za-z]+)\]\s*(.+)", text, re.DOTALL)
                if not match or match[1].lower() not in profile.callouts:
                    raise SourceCompilationError(
                        source,
                        field,
                        "callouts require a supported [!KIND] marker and content",
                    )
                if any(
                    child.type
                    not in {
                        "blockquote_open",
                        "blockquote_close",
                        "paragraph_open",
                        "paragraph_close",
                        "inline",
                    }
                    for child in tokens[index:end]
                ):
                    raise SourceCompilationError(
                        source, field, "callouts support prose only"
                    )
                item = Narrative(
                    self._render(match[2], source, field),
                    kind="callout",
                    semantic=match[1].lower(),
                )
                kind = "callout"
                index = end + 1
            elif token.type == "heading_open":
                item = Narrative(
                    self._render(tokens[index + 1].content, source, field),
                    kind="heading",
                    semantic=token.tag,
                )
                kind = "heading"
                index += 3
            elif token.type in {"fence", "code_block"}:
                item = Narrative(
                    token.content.rstrip(), kind="code", semantic=token.info or None
                )
                kind = "code"
                index += 1
            else:
                raise SourceCompilationError(
                    source, field, f"unsupported Markdown block {token.type}"
                )
            if kind not in profile.permitted_content:
                raise SourceCompilationError(source, field, f"profile forbids {kind}")
            content.append(item)
        return tuple(content)

    @staticmethod
    def _require_prose_inlines(tokens: list[Token], source: Path, field: str) -> None:
        if any(
            child.type == "image" for token in tokens for child in token.children or []
        ):
            raise SourceCompilationError(
                source, field, "chart references must occupy a standalone paragraph"
            )

    @staticmethod
    def _validate_table_width(lines: list[str], source: Path, field: str) -> None:
        widths = []
        for line in lines:
            text = line.strip().removeprefix("|").removesuffix("|")
            widths.append(len(re.split(r"(?<!\\)\|", text)))
        if len(set(widths)) != 1:
            raise SourceCompilationError(
                source,
                field,
                "table rows must match the header width; escape literal pipes",
            )

    @staticmethod
    def _closing(tokens: list[Token], start: int, closing: str) -> int:
        level = tokens[start].level
        return next(
            index
            for index in range(start + 1, len(tokens))
            if tokens[index].type == closing and tokens[index].level == level
        )

    def _chart(self, token: Token, source: Path, field: str) -> ChartReference:
        target = str(token.attrGet("src") or "")
        caption = self._render(token.content, source, field) if token.content else None
        if target.startswith("chart:"):
            identity = target.removeprefix("chart:")
            if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", identity):
                raise SourceCompilationError(
                    source, field, "chart identity must be a slug"
                )
            return ChartReference(identity=identity, caption=caption)
        if (
            not target
            or ":" in target
            or Path(target).is_absolute()
            or ".." in Path(target).parts
        ):
            raise SourceCompilationError(
                source, field, "chart requires a portable local path or chart:identity"
            )
        return ChartReference(artifact=Path(target), caption=caption)

    def _table(self, tokens: list[Token], source: Path, field: str) -> PublicationTable:
        labels: list[str] = []
        alignments: list[str] = []
        rows: list[tuple[str, ...]] = []
        row: list[str] = []
        header = False
        for index, token in enumerate(tokens):
            if token.type == "thead_open":
                header = True
            elif token.type == "thead_close":
                header = False
            elif token.type == "tr_open":
                row = []
            elif token.type == "tr_close" and not header:
                rows.append(tuple(row))
            elif token.type in {"th_open", "td_open"}:
                cell = self._render(tokens[index + 1].content, source, field)
                if header:
                    labels.append(cell)
                    alignments.append(
                        str(token.attrGet("style") or "text-align:left").split(":")[-1]
                    )
                else:
                    row.append(cell)
        columns = tuple(
            TableColumn(
                f"column-{index + 1}",
                label,
                alignment="right"
                if alignment == "right"
                else "center"
                if alignment == "center"
                else "left",
            )
            for index, (label, alignment) in enumerate(
                zip(labels, alignments, strict=True)
            )
        )
        return PublicationTable(columns, tuple(rows))
