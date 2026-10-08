import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption("--run-publication-visual", action="store_true")
    parser.addoption("--update-publication-visual", action="store_true")
    parser.addoption(
        "--run-clsi",
        action="store_true",
        help="Run authenticated CLSI integration checks",
    )
