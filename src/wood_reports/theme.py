"""Versioned publication tokens; chart construction remains in wood-charts."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field, fields
from importlib.resources import files


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
class PrimitiveStyle:
    """A semantic style without renderer-specific hints."""

    color: str
    bold: bool = False
    label: str | None = None


@dataclass(frozen=True, slots=True)
class PublicationTheme:
    """Immutable, consumer-facing design contract. Overrides need a new revision."""

    identity: str = "wood-analytics"
    revision: str = "1.0.0"
    brand_revision: str = "1.0.0"
    wordmark: str = "Wood Analytics"
    colors: PublicationColors = field(default_factory=PublicationColors)
    typography: PublicationTypography = field(default_factory=PublicationTypography)
    geometry: PublicationGeometry = field(default_factory=PublicationGeometry)
    spacing: PublicationSpacing = field(default_factory=PublicationSpacing)
    page_numbers: bool = True

    @property
    def wordmark_svg(self) -> str:
        """Bundled vector wordmark; native renderers use editable text equivalents."""
        return files("wood_reports").joinpath("assets/wordmark.svg").read_text()

    def validate(self) -> None:
        for name in ("identity", "revision", "brand_revision", "wordmark"):
            if not getattr(self, name).strip():
                raise ValueError(f"theme.{name} must not be blank")
        for token in fields(self.colors):
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", getattr(self.colors, token.name)):
                raise ValueError(f"theme.colors.{token.name} must be a hex color")
        for group in (self.geometry, self.spacing):
            for token in fields(group):
                value = getattr(group, token.name)
                if not math.isfinite(value) or value <= 0:
                    raise ValueError(f"theme.{token.name} must be finite and positive")
        for token in fields(self.typography):
            value = getattr(self.typography, token.name)
            if isinstance(value, str):
                if not value.strip():
                    raise ValueError(f"theme.typography.{token.name} must not be blank")
            elif value <= 0:
                raise ValueError(f"theme.typography.{token.name} must be positive")
        geometry = self.geometry
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
