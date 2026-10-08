"""Allow the installed CLI to be invoked as python -m wood_reports."""

from wood_reports.cli import main

raise SystemExit(main())
