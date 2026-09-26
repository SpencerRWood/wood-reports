# Wood Reports

Wood Reports is a typed Python publication library for analytics repositories. It compiles
one report definition into format-appropriate PowerPoint and LaTeX outputs while leaving
analysis, metrics, and chart construction to the consuming project.

## Initial scope

- A renderer-neutral report model for sections, findings, charts, and publication tables.
- Declarative YAML and Markdown authoring compiled into that model.
- Independent PowerPoint and LaTeX renderers that share report semantics.
- Deterministic, validated report runs and manifests for recurring publication.

`wood-charts` remains responsible for chart construction and exported chart artifacts;
Wood Reports owns their placement and report-level publication treatment.

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

The checked-in `.wood/config/config.json` contains the nonsecret project settings
and an `env://OPENPROJECT_API_TOKEN` reference. Sign in with your Infisical user
account and use the installed `wood-project` CLI through the repository launcher:

```sh
infisical login --domain=https://dev-infisical.woodhost.cloud/api --method=user --interactive
./scripts/dev wood-project story next 358 --json
```

The launcher reads the shared OpenProject token from `Infrastructure Dev/dev:/openproject`.
Local development does not require a plaintext `.env` or `.env.resolved` file.

## Status

The project is initialized from the Python library template. Product scope and the initial
V0.1 story backlog are maintained in the Wood Reports Google Drive project folder.
