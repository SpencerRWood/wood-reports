# CLSI compilation

The publication path is structured Markdown → `Report` → branded portable LaTeX
workspace → compiler → PDF. `WorkspaceCompiler` is the typed compilation boundary;
`CLSICompiler` is the production adapter. Compilation does not change report
semantics, render source, deploy services, or interact with the Overleaf browser UI.

Configure the **CLSI API origin**, independently of the editor URL, in the consuming
project's `pyproject.toml`:

```toml
[tool.wood_reports.clsi]
url = "https://clsi.woodhost.cloud"
timeout_seconds = 120
```

`CLSIConfig.from_pyproject(Path("pyproject.toml"))` reads that exact table.
`WOOD_REPORTS_CLSI_URL` explicitly overrides its URL. There is no implicit config
search, editor-URL derivation, plaintext secret loader, or local compiler fallback.
Timeouts must be finite and between 1 and 180 seconds. URLs require HTTPS without
embedded credentials; the configured compiler URL must be an origin without a
path or query. Callers own secret acquisition and rotation:

```python
import os
from pathlib import Path

from wood_reports import CLSICompiler, CLSIConfig, CLSICredentials, CompilationError

compiler = CLSICompiler(
    CLSIConfig.from_pyproject(Path("pyproject.toml")),
    CLSICredentials(
        os.environ["WOOD_REPORTS_CLSI_USERNAME"],
        os.environ["WOOD_REPORTS_CLSI_PASSWORD"],
    ),
)
try:
    result = compiler.compile(Path("workspace"), Path("artifacts/run-20261008"))
except CompilationError as error:
    # Failure has no PDF. Retained compiler logs and a manifest identify the run.
    diagnostics = error.result.diagnostics
    logs = error.result.logs
    raise
pdf = result.pdf
```

Inject credentials from the application's secret manager into the command process.
Credentials are hidden from object reprs and excluded from output manifests.
Every compiler request, output download and cleanup uses Basic authentication and
an explicit `Wood-Reports-CLSI/1.0` client identity. TLS certificate verification is
mandatory. Redirects are rejected, and output URLs must belong to the exact project
and configured HTTPS origin. Ambient proxy configuration is not used.

## Complete workspace transport

The adapter reads the workspace manifest, uses its entrypoint and engine, and
snapshots every regular source file, including human extensions and their assets.
Disposable build outputs are excluded. Symlinks, traversal paths, missing entrypoints
and unsupported engines fail before remote execution. Each run records SHA-256
fingerprints of the original inputs and uses a new CLSI project ID with full sync.

CLSI 6.1 accepts inline text strings or URL resources; it has no binary upload or
base64-content field. Callers publish binary bytes through their artifact service
and pass `resource_urls={"generated/assets/chart.png": "https://..."}`. Every binary
file requires an explicit URL; no asset is silently omitted. The adapter submits
the complete resource list with the original root document and engine unchanged.

CLSI must be able to reach the publisher from its own network; public internet
reachability is not assumed. The current compiler is on an internal network.
HTTPS resource URLs are preferred; explicitly supplied HTTP URLs support trusted
internal publishers. Compiler API and output downloads always require HTTPS.
The caller owns matching the URL content to the original bytes,
availability, upload, expiry and deletion. Signed query strings are allowed for
input resources but never persisted in compilation manifests. Missing binary
transport fails clearly; it does not silently omit figures or fall back to a
different compiler. This Story does not deploy an artifact store or publisher.

## Bounds, outputs and errors

The input snapshot admits at most 1000 files and 12 MiB of original bytes; the
encoded compile request is capped at 16 MiB, below the deployed 20 MiB limit.
The configured deadline is shared across submission and downloads. CLSI receives
a shorter server-side compile timeout and stop-on-first-error. Requests are not
automatically retried. Reads enforce the remaining time and artifact size limits:
1 MiB response metadata, 4 MiB per compiler log, 32 MiB per PDF, and at most 30
output entries. Cleanup has a separate five-second budget even after timeout.

The artifact directory must be new and outside the source workspace. Logs and
`compilation.json` survive failed builds. The manifest records adapter status,
compiler status, project ID, engine, source fingerprints, artifacts and actionable
diagnostics. HTTP errors identify credentials, allowlisting, API endpoint, payload
size, capacity or health issues without exposing upstream bodies or credentials.
CLSI failure statuses retain available logs and never download a partial PDF.

A PDF is published atomically only after successful compile status, a retained
TeX log without fatal compiler errors, a PDF header check and remote project
cleanup. CLSI can report success whenever a nonempty PDF exists, even after fatal
TeX errors; the adapter rejects that partial output based on the compiler logs.
Cleanup failures fail the operation and withhold
the PDF. Existing output directories are never overwritten. Local filesystem
configuration/input errors are raised directly before compilation; downstream
publication must consume only a successful `CompilationResult`. Downstream
[PDF validation and release packaging](pdf-releases.md) apply stricter gates
before a PDF becomes a delivered artifact.

## Integration verification

Run `wood repo verify --json` with `WOOD_REPORTS_CLSI_USERNAME` and
`WOOD_REPORTS_CLSI_PASSWORD` injected into the process, plus
`WOOD_REPORTS_CLSI_TEST_RESOURCE_URL` pointing to the integration test's PNG
fixture on a CLSI-reachable disposable publisher. The repository's required
`clsi-compilation` check compiles profile-compliant Markdown through the report
model and branded workspace, including generated and human binary assets. It then
proves that an intentional TeX failure retains logs and produces no PDF. Both
remote test projects are removed; the caller removes the fixture publisher.
Each integration attempt uses at most a 20-second compile/download budget plus
five-second cleanup, fitting both attempts inside the Wood check's 60-second limit.
Requested integration checks fail when credentials or the fixture URL
are missing; normal unit validation skips live integration unless `--run-clsi`
is provided. Full logs and the source-bound verification record are owned by Wood.
