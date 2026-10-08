"""Opt-in pixel regressions with exact compiler, rasterizer and font inputs."""

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path
from typing import Literal

import pymupdf
import pytest
from PIL import Image, ImageChops

from wood_reports import (
    CompilationResult,
    LatexWorkspacePublisher,
    MarkdownReportCompiler,
    Narrative,
    PublicationBranding,
    PublicationTable,
    PublicationTableLayout,
    TableColumn,
    scaffold_markdown,
    validate_pdf,
)

FIXTURES = Path(__file__).parents[1] / "fixtures/publication-visual"


@pytest.mark.parametrize("profile", ["assessment-report", "decision-memo"])
@pytest.mark.parametrize("density", ["comfortable", "compact"])
def test_shared_table_pagination_and_technical_extraction(
    profile: str, density: str, pinned_engine: str, tmp_path: Path
) -> None:
    """Compile boundaries, real multipage rows, code, links and both profiles."""
    source = "\n".join(
        line + "\n\nInternal layout verification." if line.startswith("## ") else line
        for line in scaffold_markdown(profile, "layout-verification").splitlines()
    )
    report = MarkdownReportCompiler().compile_text(source)
    columns = (TableColumn("id", "Identifier"), TableColumn("value", "Value"))
    small = PublicationTable(
        columns,
        tuple((f"small{i:03}", i) for i in range(4)),
        caption="Small boundary table",
        renderer_hints={"latex.layout": "longtable"},
    )
    long = PublicationTable(
        columns,
        tuple((f"row{i:03}", i) for i in range(95)),
        caption="Multipage table",
        renderer_hints={"latex.layout": "longtable"},
    )
    technical = Narrative(
        "Inspect `tool.wood_reports.publication.table_layout` and "
        "`src/wood_reports/latex_components.py` in "
        "SpencerRWood/synthetic-website-analytics-platform. "
        "[Repository](https://github.com/SpencerRWood/wood-reports) preserves evidence."
    )
    report = replace(
        report,
        theme=replace(
            report.theme,
            table_layout=PublicationTableLayout(density=density),
            branding=PublicationBranding(font_policy="strict"),
        ),
        sections=(
            replace(report.sections[0], content=(small, long, technical)),
            *report.sections[1:],
        ),
    )
    workspace = tmp_path / "workspace"
    output = LatexWorkspacePublisher().publish(
        report, workspace, artifact_root=tmp_path
    )
    extensions = workspace / "extensions"
    extensions.mkdir()
    (extensions / "preamble.tex").write_text(
        r"\newcounter{BoundaryTable}"
        r"\AddToHook{env/longtable/before}{"
        r"\ifnum\value{BoundaryTable}<2\clearpage"
        r"\vspace*{0.82\textheight}\stepcounter{BoundaryTable}\fi}"
    )
    compile_workspace(pinned_engine, output, tmp_path / "layout.log")
    log = output.parent / "build/report.log"
    result = validate_pdf(
        CompilationResult(
            "success",
            "success",
            "local-layout",
            "lualatex",
            output.parent / "build/report.pdf",
            (log,),
            tmp_path / "compile.json",
            (),
        )
    )
    assert result.passed, result.issues
    assert not any(
        d.category in {"infinite-glue-shrinkage", "overfull-box"}
        for d in result.compiler_diagnostics
    )
    with pymupdf.open(output.parent / "build/report.pdf") as document:  # type: ignore[no-untyped-call]
        texts = [page.get_text() for page in document]
        small_fragments = [t for t in texts if "small000" in t or "small003" in t]
        assert len(small_fragments) == 1
        fragments = [
            sum(f"row{i:03}" in text for i in range(95))
            for text in texts
            if "row0" in text
        ]
        assert len(fragments) >= 2
        assert fragments[0] >= 3
        assert fragments[-1] >= 2
        assert sum(fragments) == 95
        for text in texts:
            if "row0" in text:
                assert "Identifier" in text
                assert "Value" in text
        extracted = "".join(texts).replace("\n", "").replace(" ", "")
        assert "tool.wood_reports.publication.table_layout" in extracted
        assert "src/wood_reports/latex_components.py" in extracted
        assert "SpencerRWood/synthetic-website-analytics-platform." in extracted
        assert any(
            link.get("uri") == "https://github.com/SpencerRWood/wood-reports"
            for page in document
            for link in page.get_links()
        )


def compile_workspace(engine: str, output: Path, log: Path) -> None:
    environment = {**os.environ, "SOURCE_DATE_EPOCH": "1700000000", "TZ": "UTC"}
    with log.open("w") as stream:
        for _ in range(2):
            result = subprocess.run(  # noqa: S603 -- resolved compiler, fixed arguments
                [
                    engine,
                    "-no-shell-escape",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-output-directory=build",
                    "report.tex",
                ],
                cwd=output.parent,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
                timeout=40,
                check=False,
            )
            assert result.returncode == 0, f"Compilation failed: {log}"


@pytest.fixture(scope="module")
def pinned_engine(request: pytest.FixtureRequest) -> str:
    if not request.config.getoption("--run-publication-visual"):
        pytest.skip(
            "visual evidence requires --run-publication-visual "
            "and pinned fonts/compiler"
        )
    config = json.loads((FIXTURES / "environment.json").read_text())
    engine = shutil.which("lualatex")
    fontconfig = shutil.which("fc-match")
    assert engine, "Install the pinned LuaLaTeX"
    assert fontconfig, "Install fontconfig"
    banner = subprocess.run(  # noqa: S603 -- resolved executable, fixed arguments
        [engine, "--version"], check=True, capture_output=True, text=True
    ).stdout.splitlines()[0]
    assert banner == config["compiler"], "Compiler differs from the visual evidence pin"
    assert version("pymupdf") == config["rasterizer"]
    for family, checksum in config["fonts"].items():
        font = subprocess.run(  # noqa: S603 -- resolved executable, pinned font queries
            [fontconfig, "--format=%{file}", family],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert hashlib.sha256(Path(font).read_bytes()).hexdigest() == checksum, (
            f"Font differs from pin: {family}"
        )
    return engine


@pytest.mark.parametrize(
    ("profile", "corner"),
    [
        ("project-brief", "top-left"),
        ("analytics-report", "top-right"),
        ("assessment-report", "bottom-left"),
        ("decision-memo", "bottom-right"),
    ],
)
@pytest.mark.parametrize("custom", [False, True])
def test_profile_publication_pixels(  # noqa: PLR0913, PLR0917
    profile: str,
    corner: Literal["top-left", "top-right", "bottom-left", "bottom-right"],
    custom: bool,
    pinned_engine: str,
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    content = (FIXTURES / "content.md").read_text()
    text = scaffold_markdown(profile, "visual-evidence").replace(
        "title: Visual Evidence", "title: Visual Evidence\nconfidentiality: Internal"
    )
    text = "\n".join(
        line + "\n\n" + content if line.startswith("## ") else line
        for line in text.splitlines()
    )
    text += (
        "\n\n## Appendix\n\n```python\nvalue = 42\n```\n\n"
        "| Measure | Value |\n| --- | ---: |\n| Coverage | 42 |\n"
    )
    report = MarkdownReportCompiler().compile_text(text)
    branding = (
        replace(
            PublicationBranding.from_svg(FIXTURES / "replacement.svg"),
            corner=corner,
            font_policy="strict",
        )
        if custom
        else PublicationBranding(corner=corner, font_policy="strict")
    )
    report = replace(report, theme=replace(report.theme, branding=branding))
    workspace = tmp_path / "workspace"
    output = LatexWorkspacePublisher().publish(
        report, workspace, artifact_root=tmp_path
    )
    extensions = workspace / "extensions"
    extensions.mkdir()
    (extensions / "body.tex").write_text(
        r"\newpage\section*{Continuation}\WoodSource{Internal fixture}"
    )
    log = tmp_path / "visual-build.log"
    compile_workspace(pinned_engine, output, log)
    assert "Font unavailable" not in log.read_text()
    assert "Overfull" not in (output.parent / "build/report.log").read_text()
    with pymupdf.open(output.parent / "build/report.pdf") as document:  # type: ignore[no-untyped-call]
        assert len(document) >= 2
        assert "Internal" in document[0].get_text()
        assert document[0].rect.width == 612
        assert document[0].rect.height == 792
        fonts = {font[3] for page in document for font in page.get_fonts()}
        assert any("IBMPlexSans" in font for font in fonts)
        assert any("IBMPlexMono" in font for font in fonts)
        for label, index in (("cover", 0), ("body", len(document) - 1)):
            image = document[index].get_pixmap(dpi=144, alpha=False)
            actual = tmp_path / f"{label}.png"
            image.save(actual)
            expected = (
                FIXTURES
                / f"{profile}-{'replacement' if custom else 'placeholder'}-{label}.png"
            )
            if request.config.getoption("--update-publication-visual"):
                shutil.copyfile(actual, expected)
            assert expected.exists(), f"Missing visual baseline: {expected}"
            with Image.open(actual) as current, Image.open(expected) as reference:
                difference = ImageChops.difference(current, reference)
                if difference.getbbox() is not None:
                    difference.save(tmp_path / f"{label}-difference.png")
                assert difference.getbbox() is None, f"Visual regression: {tmp_path}"


@pytest.mark.parametrize(
    ("visible", "cover"), [(False, False), (False, True), (True, False), (True, True)]
)
def test_compiled_cover_visibility(
    visible: bool, cover: bool, pinned_engine: str, tmp_path: Path
) -> None:
    source = scaffold_markdown("decision-memo", "visibility-evidence")
    source = "\n".join(
        line + "\n\nInternal evidence." if line.startswith("## ") else line
        for line in source.splitlines()
    )
    report = MarkdownReportCompiler().compile_text(source)
    branding = replace(
        PublicationBranding.from_svg(FIXTURES / "replacement.svg"),
        visible=visible,
        cover_visible=cover,
        font_policy="strict",
    )
    report = replace(report, theme=replace(report.theme, branding=branding))
    workspace = tmp_path / "workspace"
    output = LatexWorkspacePublisher().publish(
        report, workspace, artifact_root=tmp_path
    )
    extensions = workspace / "extensions"
    extensions.mkdir()
    (extensions / "body.tex").write_text(
        r"\newpage\section*{Continuation}Internal evidence."
    )
    compile_workspace(pinned_engine, output, tmp_path / "visual-build.log")
    x, y = branding.position(8.5, 11)
    region = pymupdf.Rect(  # type: ignore[no-untyped-call]
        x * 72, y * 72, (x + branding.width) * 72, (y + branding.height) * 72
    )
    with pymupdf.open(output.parent / "build/report.pdf") as document:  # type: ignore[no-untyped-call]
        for index, expected in ((0, cover), (len(document) - 1, visible)):
            image = document[index].get_pixmap(dpi=144, clip=region, alpha=False)
            image.save(tmp_path / f"visibility-{index}.png")
            samples = image.samples
            pixels = sum(
                all(
                    abs(samples[offset + component] - channel) <= 2
                    for component, channel in enumerate((18, 52, 86))
                )
                for offset in range(0, len(samples), 3)
            )
            assert (pixels > 100) == expected
