# Repository Guidance

## Purpose and boundaries
- Maintain reusable PowerPoint and LaTeX publication from one renderer-neutral report model.
- Analysis and metrics belong to consuming repos; chart construction belongs to `wood-charts`.

## Development
- Keep YAML and Markdown authoring, validation, and both renderers aligned with the shared report semantics.
- Treat report manifests and public model fields as consumer-facing contracts.

## Validation
- Run `uv sync --frozen --group dev`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`, and `uv run pytest --cov=wood_reports --cov-report=term-missing`.
- Run `uv run pre-commit run --all-files` and `uv build` when publication packaging changes.

## Architecture constraints
- Avoid renderer-specific meaning in the shared report model.
- Keep generated publication artifacts separate from source definitions.

## Safety
- Do not commit customer data or local report exports as generic examples.

## Branching strategy

- This repository uses **trunk-based development**. Create short-lived change branches from current `main` and target PRs to `main`.
- Follow the [canonical branching and delivery policy](https://github.com/SpencerRWood/codex-config/blob/main/docs/branching-policy.md), available through the installed codex-config source path. Verify the strategy, release association, fetched base and PR target before implementation and record them in Story evidence. Story completion does not authorize publication or deployment; retain existing review, CI, security and rollback requirements.
