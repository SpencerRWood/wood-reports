import base64
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from wood_reports import (
    Appendix,
    ChartReference,
    LatexWorkspaceError,
    LatexWorkspacePublisher,
    Narrative,
    PublicationTable,
    Report,
    ReportMetadata,
    Section,
    TableColumn,
)


def report_with_chart(chart: Path) -> Report:
    return Report(
        ReportMetadata("Monthly report"),
        (Section("Results", (Narrative("Summary"), ChartReference(chart))),),
    )


def test_publishes_self_contained_source_tree(tmp_path: Path) -> None:
    artifact = tmp_path / "charts" / "trend.png"
    artifact.parent.mkdir()
    artifact.write_bytes(b"chart")

    output = LatexWorkspacePublisher().publish(
        report_with_chart(Path("charts/trend.png")),
        tmp_path / "workspace",
        artifact_root=tmp_path,
    )

    assert output == tmp_path / "workspace" / "generated" / "report.tex"
    assert "assets/1-trend.png" in output.read_text()
    assert (output.parent / "assets" / "1-trend.png").read_bytes() == b"chart"


def test_regeneration_preserves_human_extensions(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    extension = workspace / "extensions" / "appendix.tex"
    extension.parent.mkdir(parents=True)
    extension.write_text("Human maintained", encoding="utf-8")
    artifact = tmp_path / "trend.png"
    artifact.write_bytes(b"first")
    publisher = LatexWorkspacePublisher()

    publisher.publish(
        report_with_chart(Path("trend.png")), workspace, artifact_root=tmp_path
    )
    artifact.write_bytes(b"second")
    publisher.publish(
        report_with_chart(Path("trend.png")), workspace, artifact_root=tmp_path
    )

    assert extension.read_text(encoding="utf-8") == "Human maintained"
    assert (
        workspace / "generated" / "assets" / "1-trend.png"
    ).read_bytes() == b"second"


def test_rejects_an_ambiguous_ownership_boundary() -> None:
    with pytest.raises(LatexWorkspaceError, match="must differ"):
        LatexWorkspacePublisher(
            generated_directory="sources", extensions_directory="sources"
        )


def test_workspace_is_deterministic_and_declares_portable_build(tmp_path: Path) -> None:
    chart = tmp_path / "chart {unsafe}.png"
    chart.write_bytes(b"chart")
    report = report_with_chart(chart)
    publisher = LatexWorkspacePublisher()
    first = publisher.publish(report, tmp_path / "first", artifact_root=tmp_path)
    second = publisher.publish(report, tmp_path / "second", artifact_root=tmp_path)
    for path in first.parent.rglob("*"):
        if path.is_file():
            assert (
                path.read_bytes()
                == (second.parent / path.relative_to(first.parent)).read_bytes()
            )
            assert str(tmp_path).encode() not in path.read_bytes()
    manifest = json.loads((first.parent / "workspace.json").read_text())
    assert manifest["engine"] == "lualatex"
    assert manifest["entrypoint"] == "generated/report.tex"
    assert manifest["theme"]["identity"] == "wood-analytics"
    assert manifest["build"]["passes"] == 2
    assert "assets/1-chart__unsafe_.png" in first.read_text()


@pytest.mark.parametrize("change", ["edit", "extra", "manifest", "symlink"])
def test_modified_generated_tree_is_not_silently_overwritten(
    tmp_path: Path, change: str
) -> None:
    report = Report(ReportMetadata("Test"), (Section("Results", (Narrative("Text"),)),))
    workspace = tmp_path / "workspace"
    publisher = LatexWorkspacePublisher()
    output = publisher.publish(report, workspace, artifact_root=tmp_path)
    if change == "edit":
        output.write_text("Human edits")
    elif change == "extra":
        (output.parent / "human.tex").write_text("Human edits")
    elif change == "manifest":
        (output.parent / "workspace.json").write_text("{}")
    else:
        (output.parent / "link").symlink_to(output)
    with pytest.raises(LatexWorkspaceError):
        publisher.publish(report, workspace, artifact_root=tmp_path)
    assert output.exists()


@pytest.mark.parametrize(
    "name", ["../generated", "/absolute/generated", "x{y}", "x y", "."]
)
def test_workspace_directory_names_are_bounded(name: str) -> None:
    with pytest.raises(LatexWorkspaceError):
        LatexWorkspacePublisher(generated_directory=name)


def test_rejects_symlink_ownership_directory(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    (tmp_path / "generated").symlink_to(target, target_is_directory=True)
    report = Report(ReportMetadata("Test"), (Section("Results", (Narrative("Text"),)),))
    with pytest.raises(LatexWorkspaceError, match="symlinks"):
        LatexWorkspacePublisher().publish(report, tmp_path, artifact_root=tmp_path)


def test_workspace_compiles_with_lualatex_and_human_extensions(tmp_path: Path) -> None:
    engine = shutil.which("lualatex")
    if engine is None:
        pytest.skip("LuaLaTeX is not installed")
    report = Report(
        ReportMetadata(
            "Branded & portable",
            source="Dataset 100%",
            doc_type="analytics-report",
            doc_name="monthly",
            profile_version="1.0.0",
        ),
        (
            Section(
                "Results",
                (
                    Narrative("See table", renderer_hints={"latex.ref": "tab:values"}),
                    Narrative("See figure", renderer_hints={"latex.ref": "fig:trend"}),
                    ChartReference(
                        Path("chart.png"),
                        caption="Trend",
                        renderer_hints={
                            "latex.label": "fig:trend",
                            "latex.source": "Chart & data",
                        },
                    ),
                    PublicationTable(
                        (TableColumn("value", "Value"),),
                        (("100%",),),
                        caption="Results",
                        notes=("A source note",),
                        renderer_hints={"latex.label": "tab:values"},
                    ),
                    Narrative(
                        r"\textbf{Explicit \emph{formatting}}", {"latex.raw": "inline"}
                    ),
                ),
            ),
        ),
        appendices=(Appendix("Details", (Narrative("Escaped _ # $ { }"),)),),
    )
    (tmp_path / "chart.png").write_bytes(
        base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGNg0M8BAADO"
            "AJxI2GK/AAAAAElFTkSuQmCC"
        )
    )
    workspace = tmp_path / "original"
    extensions = workspace / "extensions"
    extensions.mkdir(parents=True)
    (extensions / "preamble.tex").write_text(
        r"\newcommand{\HumanText}{Human extension}"
    )
    (extensions / "body.tex").write_text(r"\HumanText")
    publisher = LatexWorkspacePublisher()
    publisher.publish(report, workspace, artifact_root=tmp_path)
    relocated = tmp_path / "relocated"
    shutil.move(workspace, relocated)
    output = relocated / "generated/report.tex"
    manifest = json.loads((output.parent / "workspace.json").read_text())
    assert manifest["profile"] == {"identity": "analytics-report", "version": "1.0.0"}
    argv = [engine, *manifest["build"]["argv"][1:]]
    for _ in range(manifest["build"]["passes"]):
        result = subprocess.run(  # noqa: S603
            argv, cwd=output.parent, capture_output=True, timeout=60, check=False
        )
        assert result.returncode == 0, result.stdout.decode(errors="replace")
    assert (output.parent / "build/report.pdf").stat().st_size > 0
    assert (
        "undefined references" not in (output.parent / "build/report.log").read_text()
    )
    publisher.publish(report, relocated, artifact_root=tmp_path)
