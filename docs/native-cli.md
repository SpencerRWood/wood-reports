# Native report CLI

Install `wood-reports` with Python 3.14 or newer. The distribution owns the
`wood-report` executable; `python -m wood_reports` exposes the same interface.
Wood Tools is not a runtime dependency. Commands use `PublicationAPI`, the
installed profile contracts, Markdown compiler, LaTeX workspace publisher, and
CLSI compiler; consuming applications can call those same Python APIs directly.

```sh
wood-report profile list --json
wood-report profile show decision-memo --json
wood-report create --profile decision-memo --name migration-decision --output report.md
# Fill every required section before validating.
wood-report validate report.md --json
wood-report preview report.md --output previews/attempt-1 --json
wood-report build report.md --output builds/attempt-1 --json
```

`create` produces a profile scaffold with YAML front matter and required headings.
Unfilled sections are deliberately rejected by validation. Existing source files
are never overwritten. `validate` performs deterministic **source** validation,
including profile metadata/sections, supported content, and local asset paths.
It does not contact CLSI or attest to a PDF. Logical chart identities require
consumer-owned resolution before rendering; the CLI does not construct charts.

`preview` and non-release `build` compile a branded workspace through CLSI and
return its PDF, compilation manifest, logs, and sorted unique warning lines.
Each `--output` must be new. Source workspace files are under `workspace/` and
compiler artifacts under `compilation/`. Failed attempts retain diagnostics;
retry using a fresh directory. Neither command delivers a client release.

Configuration reads exactly `[tool.wood_reports.clsi]` in `--config` (default
`pyproject.toml`). `WOOD_REPORTS_CLSI_URL` explicitly overrides the origin.
Inject `WOOD_REPORTS_CLSI_USERNAME` and `WOOD_REPORTS_CLSI_PASSWORD` from your
secret manager into the command process. Credentials are never CLI arguments or
artifact metadata. For binary resources pass `--resource-urls resources.json`,
a JSON object mapping workspace-relative paths to CLSI-reachable URLs; see
[the compiler contract](clsi-compilation.md) for transport and size limits.

```sh
# Inject WOOD_REPORTS_DRIVE_ACCESS_TOKEN using your OAuth credential provider.
wood-report create --drive https://drive.google.com/file/d/FILE_ID/view --output report.md --artifact-root artifacts
wood-report validate FILE_ID --drive --artifact-root artifacts --json
wood-report preview FILE_ID --drive --artifact-root artifacts --output previews/drive-1 --json
```

Drive inputs may be a Markdown file ID, canonical file URL, or folder URL
containing exactly one `report.md`. Drive `create` imports and validates the
original Markdown without changing its profile/name. Local assets must already
exist under `--artifact-root`; no asset uploads, token acquisition, or refresh
are implicit.

`build --release` is exposed and fails closed before creating outputs or
contacting CLSI. Strict PDF validation and release packaging belong to the
successor Story #434. Until that backend is implemented, it returns an explicit
unavailable error; a preview PDF is never silently treated as a release.

All operations accept `--json`. Results have `schema_version`, `command`,
`status`, and `data` on success; failures include `error` and, for compilation
failures, retained artifact paths in `data`. Source validation results explicitly
declare `validation_scope: source`. Exit codes are 0 for success, 1 for operation
failure, and 2 for invalid command syntax (argparse usage on stderr).
