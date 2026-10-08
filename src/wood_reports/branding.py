"""One bounded SVG and placement contract for every publication profile.

Logos use filled vector paths, rectangles and plain text. Curves are sampled
deterministically into editable polygons in both renderers. Unsupported SVG
features are rejected rather than silently dropped or fetched from the network.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree

from svg.path import Close, Line, Move, parse_path


@dataclass(frozen=True, slots=True)
class PublicationBranding:
    corner: Literal["top-left", "top-right", "bottom-left", "bottom-right"] = (
        "top-right"
    )
    width: float = 2.2
    height: float = 0.35
    offset_x: float = 0.6
    offset_y: float = 0.35
    visible: bool = True
    cover_visible: bool = True
    logo_svg: str | None = None
    font_policy: Literal["fallback", "strict"] = "fallback"

    @classmethod
    def from_svg(cls, path: Path) -> PublicationBranding:
        """Snapshot asset bytes centrally; outputs never depend on this path."""
        try:
            if path.stat().st_size > 256_000:
                raise ValueError("branding.logo_svg exceeds 256000 bytes")
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            raise ValueError(
                f"branding.logo_svg cannot read {path}: {error}"
            ) from error
        parse_logo(text)
        return cls(logo_svg=text)

    def validate(self, width: float, height: float) -> None:
        if self.corner not in {"top-left", "top-right", "bottom-left", "bottom-right"}:
            raise ValueError("branding.corner must name a supported document corner")
        if self.font_policy not in {"fallback", "strict"}:
            raise ValueError("branding.font_policy must be fallback or strict")
        if not isinstance(self.visible, bool) or not isinstance(
            self.cover_visible, bool
        ):
            raise ValueError("branding visibility options must be booleans")
        for name in ("width", "height", "offset_x", "offset_y"):
            value = getattr(self, name)
            minimum = 0 if name.startswith("offset") else 1e-6
            if (
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not math.isfinite(value)
                or value < minimum
            ):
                raise ValueError(f"branding.{name} must be finite and nonnegative")
        if self.width + self.offset_x > width or self.height + self.offset_y > height:
            raise ValueError("branding size and offsets exceed the document bounds")

    def position(self, width: float, height: float) -> tuple[float, float]:
        self.validate(width, height)
        return (
            self.offset_x
            if self.corner.endswith("left")
            else width - self.offset_x - self.width,
            self.offset_y
            if self.corner.startswith("top")
            else height - self.offset_y - self.height,
        )


@dataclass(frozen=True, slots=True)
class LogoShape:
    contours: tuple[tuple[complex, ...], ...]
    color: str
    text: str = ""
    font_size: float = 0
    bold: bool = False


@dataclass(frozen=True, slots=True)
class VectorLogo:
    width: float
    height: float
    shapes: tuple[LogoShape, ...]


def _number(value: str) -> float:
    number = float(value)
    if not math.isfinite(number) or abs(number) > 100_000:
        raise ValueError("branding.logo_svg coordinates must be finite and bounded")
    return number


def _contours(data: str) -> tuple[tuple[complex, ...], ...]:
    if re.search(r"[^MmLlHhVvCcSsQqTtAaZz0-9eE.,+\s-]", data):
        raise ValueError("branding.logo_svg contains an unsupported path command")
    segments = parse_path(data)
    if not segments or len(segments) > 512:
        raise ValueError("branding.logo_svg path must have 1 to 512 segments")
    contours: list[tuple[complex, ...]] = []
    points: list[complex] = []
    for segment in segments:
        if isinstance(segment, Move):
            if points:
                contours.append(tuple(points))
            points = [segment.end]
        else:
            if not points:
                raise ValueError("branding.logo_svg paths must begin with M")
            samples = 1 if isinstance(segment, (Line, Close)) else 64
            points.extend(
                segment.point(index / samples) for index in range(1, samples + 1)
            )
    if points:
        contours.append(tuple(points))
    for contour in contours:
        if len(contour) < 3:
            raise ValueError(
                "branding.logo_svg requires filled shapes with at least 3 points"
            )
        for point in contour:
            _number(str(point.real))
            _number(str(point.imag))
    return tuple(contours)


def parse_logo(text: str) -> VectorLogo:  # noqa: PLR0912, PLR0915
    """Validate the supported SVG subset before any publication output is written."""
    if not isinstance(text, str) or len(text.encode()) > 256_000 or "<!" in text:
        raise ValueError("branding.logo_svg must be bounded SVG without declarations")
    try:
        root = ElementTree.fromstring(text)  # noqa: S314 -- declarations rejected above
        if root.tag != "{http://www.w3.org/2000/svg}svg":
            raise ValueError("root must be an SVG element in the SVG namespace")
        viewbox = [
            _number(value) for value in root.attrib["viewBox"].replace(",", " ").split()
        ]
        if len(viewbox) != 4 or viewbox[:2] != [0, 0] or min(viewbox[2:]) <= 0:
            raise ValueError(
                "viewBox must be 0 0 followed by positive width and height"
            )
        shapes: list[LogoShape] = []
        elements = list(root.iter())
        if len(elements) > 128:
            raise ValueError("maximum 128 SVG elements")
        allowed = {
            "svg": {"width", "height", "viewBox", "role", "aria-label"},
            "path": {"d", "fill", "fill-rule"},
            "rect": {"x", "y", "width", "height", "fill"},
            "text": {"x", "y", "fill", "font-size", "font-weight", "font-family"},
            "g": set(),
            "title": set(),
            "desc": set(),
        }
        for element in elements:
            tag = element.tag.removeprefix("{http://www.w3.org/2000/svg}")
            if tag not in allowed or element.attrib.keys() - allowed[tag]:
                raise ValueError(
                    f"unsupported {tag} element or attributes; "
                    "use plain filled paths, rectangles or text"
                )
            if tag in {"svg", "g", "title", "desc"}:
                continue
            color = element.get("fill", "#000000")
            if not re.fullmatch(r"#[0-9A-Fa-f]{6}", color):
                raise ValueError("fills must be six-digit hex colors")
            if tag == "path":
                if element.get("fill-rule", "nonzero") != "nonzero":
                    raise ValueError("only nonzero fill-rule is supported")
                shapes.append(LogoShape(_contours(element.attrib["d"]), color))
                continue
            x, y = (_number(element.get(key, "0")) for key in ("x", "y"))
            if tag == "rect":
                width, height = (
                    _number(element.attrib[key]) for key in ("width", "height")
                )
                if min(width, height) <= 0:
                    raise ValueError("rectangle dimensions must be positive")
                points = (
                    complex(x, y),
                    complex(x + width, y),
                    complex(x + width, y + height),
                    complex(x, y + height),
                )
                shapes.append(LogoShape((points,), color))
            else:
                if list(element) or not (element.text or "").strip():
                    raise ValueError("text must be plain and nonblank")
                size = _number(element.get("font-size", "16"))
                if size <= 0 or element.get("font-weight", "400") not in {
                    "400",
                    "700",
                    "normal",
                    "bold",
                }:
                    raise ValueError(
                        "text requires positive font-size and normal/bold weight"
                    )
                if (
                    element.get("font-family", "IBM Plex Sans").split(",")[0]
                    != "IBM Plex Sans"
                ):
                    raise ValueError(
                        "text must use IBM Plex Sans; outline other fonts as paths"
                    )
                shapes.append(
                    LogoShape(
                        ((complex(x, y),),),
                        color,
                        element.text or "",
                        size,
                        element.get("font-weight") in {"700", "bold"},
                    )
                )
        if not shapes:
            raise ValueError("logo requires at least one visible shape")
        count = 0
        for shape in shapes:
            for contour in shape.contours:
                count += len(contour)
                if count > 32_000:
                    raise ValueError("logo exceeds 32000 sampled points")
                if any(
                    not (0 <= p.real <= viewbox[2] and 0 <= p.imag <= viewbox[3])
                    for p in contour
                ):
                    raise ValueError("logo geometry lies outside its viewBox")
        return VectorLogo(viewbox[2], viewbox[3], tuple(shapes))
    except (
        KeyError,
        TypeError,
        ValueError,
        ElementTree.ParseError,
        ZeroDivisionError,
    ) as error:
        raise ValueError(f"branding.logo_svg: {error}") from error


def require_fonts(families: tuple[str, ...]) -> None:
    """Strict native rendering requires exact host fonts on the rendering machine."""
    executable = shutil.which("fc-match")
    if executable is None:
        raise ValueError("strict font validation requires fontconfig (fc-match)")
    for family in families:
        result = subprocess.run(  # noqa: S603 -- executable resolved, no shell
            [executable, "--format=%{family}", "--", family],
            capture_output=True,
            text=True,
            timeout=10,
            check=True,
        )
        if family not in result.stdout.split(","):
            raise ValueError(
                f"publication font unavailable: {family}; "
                "install it or select font_policy='fallback'"
            )
