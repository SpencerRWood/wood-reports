# Wood Reports

Wood Reports is a typed Python publication library for analytics repositories. It compiles
one report definition into format-appropriate PowerPoint and LaTeX outputs while leaving
analysis, metrics, and chart construction to the consuming project.

## Initial scope

- A renderer-neutral report model for sections, findings, charts, and publication tables.
- Profile-compliant Markdown authoring compiled into that model.
- Independent PowerPoint and LaTeX renderers that share report semantics.
- Deterministic, validated report runs and manifests for recurring publication.

`wood-charts` remains responsible for chart construction and exported chart artifacts;
Wood Reports owns their placement and report-level publication treatment.

## Authoring

New client documents use `report.md` with YAML front matter and semantic headings.
The initial profiles are project-brief, analytics-report, assessment-report, and
decision-memo. Compile local files with `ReportCompiler.compile_file()` or Drive
Markdown with `compile_drive_report()`. See [Markdown authoring](docs/markdown-authoring.md)
for profile contracts, supported blocks, Drive credentials, and the explicit legacy
YAML compatibility API.

## Analytics integration

See [the production analytics integration guide](docs/production-analytics-integration.md)
for the recommended optional repository layers and a verified programmatic example that
resolves logical charts and produces both LaTeX and PowerPoint outputs.

## Development

```bash
uv sync --frozen --group dev
uv run pre-commit install
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov=wood_reports --cov-report=term-missing
uv run pre-commit run --all-files
```

The package uses a typed `src/` layout. New code belongs in `src/wood_reports/` and tests
in `tests/`.

## OpenProject setup

`[tool.wood.openproject]` in `pyproject.toml` selects Wood Reports project 4 and
R2 initiative 426. Inject credentials from Infisical and use the public `wood` CLI:

```sh
infisical login --domain=https://dev-infisical.woodhost.cloud/api --method=user --interactive
infisical run --env=dev --path=/openproject --projectId=7ea10433-2eeb-4c57-95a9-b793dd40c7a4 -- wood story next --json
```

Infisical supplies the shared OpenProject credentials from `Infrastructure Dev/dev:/openproject`.
Local development does not require a plaintext `.env` or `.env.resolved` file.

## Status

The R2 client publication backlog is maintained in OpenProject and the existing
implementation workbook in the Wood Reports Google Drive project folder.

## Publication design system

Both renderers use the versioned [Wood Analytics publication theme](docs/publication-design-system.md)
with shared Markdown primitives and tokens aligned with wood-charts. Generated
manifests record the theme and brand revisions.

See [portable LaTeX workspaces](docs/latex-workspaces.md) for deterministic source
publication, LuaLaTeX build metadata, cross-references, and human extensions.
