import os
from pathlib import Path

import pytest

from wood_reports import CLSICompiler, CLSIConfig, CLSICredentials


@pytest.fixture
def backend(request: pytest.FixtureRequest) -> CLSICompiler:
    """One authenticated CLSI fixture shared by all publication acceptance tests."""
    if not request.config.getoption("--run-clsi"):
        pytest.skip("CLSI integration requires --run-clsi and injected credentials")
    values = {
        key: os.environ.get(key, "")
        for key in (
            "WOOD_REPORTS_CLSI_USERNAME",
            "WOOD_REPORTS_CLSI_PASSWORD",
        )
    }
    if not all(values.values()):
        pytest.fail("Inject WOOD_REPORTS_CLSI_USERNAME and WOOD_REPORTS_CLSI_PASSWORD")
    configured = CLSIConfig.from_pyproject(Path("pyproject.toml"))
    budget = getattr(request, "param", 20)
    return CLSICompiler(
        CLSIConfig(configured.url, min(configured.timeout_seconds, budget)),
        CLSICredentials(
            values["WOOD_REPORTS_CLSI_USERNAME"], values["WOOD_REPORTS_CLSI_PASSWORD"]
        ),
    )


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-publication-visual", action="store_true")
    parser.addoption("--update-publication-visual", action="store_true")
    parser.addoption(
        "--run-clsi",
        action="store_true",
        help="Run authenticated CLSI integration checks",
    )
