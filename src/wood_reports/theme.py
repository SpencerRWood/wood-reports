"""Versioned publication tokens; chart construction remains in wood-charts."""

from __future__ import annotations

import math
import re
import tomllib
from dataclasses import dataclass, field, fields
from importlib.resources import files
from pathlib import Path
from xml.sax.saxutils import escape

from wood_reports.branding import PublicationBranding, parse_logo


@dataclass(frozen=True, slots=True)
class PublicationColors:
    """Shared values match wood-charts' bundled base theme."""

    primary: str = "#002F6C"
    secondary: str = "#4A90C2"
    text_primary: str = "#1B1B1B"
    text_secondary: str = "#4B5563"
    text_muted: str = "#6B7280"
    neutral_light: str = "#D1D5DB"
    grid: str = "#E5E7EB"
    background: str = "#FFFFFF"
    warning: str = "#92400E"
    critical: str = "#991B1B"


@dataclass(frozen=True, slots=True)
class PublicationTypography:
    family: str = "IBM Plex Sans"
    fallback: str = "Arial"
    code_family: str = "IBM Plex Mono"
    title: int = 32
    heading: int = 22
    body: int = 18
    table: int = 11
    caption: int = 11
    note: int = 9
    page_body: int = 11
    page_heading: int = 16


@dataclass(frozen=True, slots=True)
class PublicationGeometry:
    """Physical geometry in inches for both publication targets."""

    slide_width: float = 13.333
    slide_height: float = 7.5
    slide_margin: float = 0.65
    content_top: float = 1.45
    content_height: float = 5.25
    page_width: float = 8.5
    page_height: float = 11.0
    page_margin: float = 0.8


@dataclass(frozen=True, slots=True)
class PublicationSpacing:
    paragraph_points: float = 8
    table_row_inches: float = 0.4
    figure_width_fraction: float = 1.0


@dataclass(frozen=True, slots=True)
class PublicationTableLayout:
    """Shared pagination and density, independent of document profile."""

    density: str = "comfortable"
    comfortable_row_inches: float = 0.28
    compact_row_inches: float = 0.22
    minimum_first_rows: int = 3
    minimum_last_rows: int = 2
    keep_together_rows: int = 6

    @property
    def row_inches(self) -> float:
        return (
            self.compact_row_inches
            if self.density == "compact"
            else self.comfortable_row_inches
        )

    def validate(self) -> None:
        if self.density not in {"comfortable", "compact"}:
            raise ValueError("table_layout.density must be comfortable or compact")
        for name in ("comfortable_row_inches", "compact_row_inches"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (float, int)):
                raise ValueError(f"table_layout.{name} must be numeric")
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"table_layout.{name} must be finite and positive")
        for name in ("minimum_first_rows", "minimum_last_rows", "keep_together_rows"):
            value = getattr(self, name)
            if type(value) is not int or not 1 <= value <= 20:
                raise ValueError(f"table_layout.{name} must be an integer from 1 to 20")


@dataclass(frozen=True, slots=True)
class PrimitiveStyle:
    """A semantic style without renderer-specific hints."""

    color: str
    bold: bool = False
    label: str | None = None


@dataclass(frozen=True, slots=True)
class PublicationTheme:
    """Immutable, consumer-facing design contract. Overrides need a new revision."""

    identity: str = "wood-analytics"
    revision: str = "1.1.0"
    brand_revision: str = "1.0.0"
    wordmark: str = "Wood Analytics"
    colors: PublicationColors = field(default_factory=PublicationColors)
    typography: PublicationTypography = field(default_factory=PublicationTypography)
    geometry: PublicationGeometry = field(default_factory=PublicationGeometry)
    spacing: PublicationSpacing = field(default_factory=PublicationSpacing)
    page_numbers: bool = True
    branding: PublicationBranding = field(default_factory=PublicationBranding)
    brand_identity: str = "wood-analytics"
    table_layout: PublicationTableLayout = field(default_factory=PublicationTableLayout)

    @classmethod
    def from_pyproject(cls, path: Path) -> PublicationTheme:
        """Read the supported publication table from one explicitly selected file."""
        with path.open("rb") as source:
            config = tomllib.load(source)
        try:
            options = dict(
                config.get("tool", {}).get("wood_reports", {}).get("publication", {})
            )
            groups = {
                "colors": PublicationColors,
                "typography": PublicationTypography,
                "geometry": PublicationGeometry,
                "spacing": PublicationSpacing,
                "table_layout": PublicationTableLayout,
            }
            for name, factory in groups.items():
                if name in options:
                    options[name] = factory(**options[name])
            if "branding" in options:
                branding = dict(options["branding"])
                if "svg_path" in branding:
                    if "logo_svg" in branding:
                        raise ValueError("configure svg_path or logo_svg, never both")
                    asset = path.parent / branding.pop("svg_path")
                    branding["logo_svg"] = PublicationBranding.from_svg(asset).logo_svg
                options["branding"] = PublicationBranding(**branding)
            theme = cls(**options)
            theme.validate()
            return theme
        except (AttributeError, TypeError, ValueError) as error:
            raise ValueError(f"tool.wood_reports.publication: {error}") from error

    @property
    def wordmark_svg(self) -> str:
        """The centrally configured, portable vector brand asset."""
        if self.branding.logo_svg is not None:
            return self.branding.logo_svg
        return (
            files("wood_reports")
            .joinpath("assets/wordmark.svg")
            .read_text()
            .replace("Wood Analytics", escape(self.wordmark, {'"': "&quot;"}))
            .replace("#002F6C", self.colors.primary)
        )

    def validate(self) -> None:  # noqa: PLR0912
        for name in (
            "identity",
            "revision",
            "brand_identity",
            "brand_revision",
            "wordmark",
        ):
            if (
                not isinstance(getattr(self, name), str)
                or not getattr(self, name).strip()
            ):
                raise ValueError(f"theme.{name} must not be blank")
        if not isinstance(self.page_numbers, bool):
            raise ValueError("theme.page_numbers must be a boolean")
        for token in fields(self.colors):
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", getattr(self.colors, token.name)):
                raise ValueError(f"theme.colors.{token.name} must be a hex color")
        for group in (self.geometry, self.spacing):
            for token in fields(group):
                value = getattr(group, token.name)
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or value <= 0
                ):
                    raise ValueError(f"theme.{token.name} must be finite and positive")
        for token in fields(self.typography):
            value = getattr(self.typography, token.name)
            if isinstance(value, str):
                if not value.strip():
                    raise ValueError(f"theme.typography.{token.name} must not be blank")
            elif (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise ValueError(f"theme.typography.{token.name} must be positive")
        geometry = self.geometry
        self.table_layout.validate()
        self.branding.validate(geometry.page_width, geometry.page_height)
        self.branding.validate(geometry.slide_width, geometry.slide_height)
        parse_logo(self.wordmark_svg)
        if (
            geometry.slide_margin * 2 >= geometry.slide_width
            or geometry.content_top + geometry.content_height >= geometry.slide_height
            or geometry.page_margin * 2
            >= min(geometry.page_width, geometry.page_height)
            or self.spacing.figure_width_fraction > 1
        ):
            raise ValueError("theme geometry must leave room for publication content")

    def primitive(self, kind: str, semantic: str | None = None) -> PrimitiveStyle:
        """Resolve block intent deterministically; reject unknown callout intent."""
        if kind == "callout":
            if semantic not in {
                "summary",
                "finding",
                "recommendation",
                "risk",
                "decision",
                "metric",
                "note",
            }:
                raise ValueError(f"unsupported callout semantic: {semantic!r}")
            return PrimitiveStyle(
                self.colors.warning if semantic == "risk" else self.colors.primary,
                bold=True,
                label=semantic.title(),
            )
        if kind == "heading":
            return PrimitiveStyle(self.colors.primary, bold=True)
        if kind not in {"prose", "list", "code"}:
            raise ValueError(f"unsupported narrative kind: {kind!r}")
        return PrimitiveStyle(self.colors.text_primary)

    def finding_color(self, severity: str) -> str:
        return {
            "info": self.colors.primary,
            "warning": self.colors.warning,
            "critical": self.colors.critical,
        }[severity]


WOOD_ANALYTICS_THEME = PublicationTheme()
