import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-clsi",
        action="store_true",
        help="Run authenticated CLSI integration checks",
    )
