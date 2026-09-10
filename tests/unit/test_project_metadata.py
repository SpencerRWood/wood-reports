import tomllib
from importlib import import_module
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]


def load_pyproject() -> dict[str, Any]:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def test_package_can_be_imported() -> None:
    package = import_module("wood_reports")

    assert package.__doc__ == "Reusable publication primitives for analytical reports."


def test_project_metadata_describes_wood_reports() -> None:
    pyproject = load_pyproject()
    project = pyproject["project"]

    assert project["name"] == "wood-reports"
    assert project["description"] == (
        "Reusable publication layer for PowerPoint and LaTeX analytical reports."
    )
    assert project["requires-python"] == ">=3.14"
    assert project["dependencies"] == [
        "jinja2>=3.1",
        "python-pptx>=1.0",
        "pyyaml>=6.0",
    ]


def test_project_declares_typed_src_package() -> None:
    pyproject = load_pyproject()
    project = pyproject["project"]
    tool = pyproject["tool"]

    assert (ROOT / "src" / "wood_reports" / "py.typed").is_file()
    assert "Typing :: Typed" in project["classifiers"]
    assert tool["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "src/wood_reports",
    ]
