# Validated PDF releases

`ReleasePublisher` accepts an existing `Report` and a `WorkspaceCompiler`.
`PublicationAPI.release` loads local or Drive Markdown, then calls the same
publisher. The native CLI's `build --release` delegates to that API. Analysis,
chart generation, orchestration, and delivery channels remain consumer-owned.

```sh
wood-report build report.md --release --output releases \
  --build-epoch 1700000000 --source-revision SOURCE_REVISION --json
```

Set `version: "1.0.0"` in report front matter. The source's `doc_name` and report
version select `releases/<doc_name>/<version>/`. Existing versions are never
replaced, even with identical inputs. Publish changed reports with a new version;
retry a failed attempt with the same version once its cause is fixed. Competing
successful attempts cannot replace a populated delivered directory.

Every release checks installed profile metadata/sections/version, report assets,
authoring placeholders (`TODO`, `TBD`, `FIXME`, `PLACEHOLDER`, unresolved template
values), and machine-local paths. The existing renderer rejects unresolved chart
identities and LaTeX labels. Compilation must succeed without diagnostics and
provide retained logs. Undefined references/citations, missing files/glyphs,
fatal errors, and overfull horizontal/vertical boxes greater than **5 points**
block release. Cosmetic underfull boxes and smaller overfull boxes are allowed.

Reports with bibliography metadata also require clean retained biber evidence,
every citation occurrence's PDF destination and bibliography link, all source
URLs, and accurate citing-page back-references. `citation-validation.json`
records those gates; release metadata records the observed biber version.

`validate_pdf(CompilationResult)` is also a standalone Python API. It returns
sorted, deterministic `ValidationIssue` records, page count, and a SHA-256 digest;
`require_passed()` raises `PDFValidationError`. It requires a nonencrypted PDF
with a header, EOF marker, parseable page tree and decoded content streams, and
at least one nonempty page content stream. Extracted PDF text is also checked
for placeholders and machine-local paths. Structural validation cannot establish
visual quality, content accuracy, or PDF/A compliance. Source-only CLI `validate`
continues to declare `validation_scope: source`; release adds the PDF gates.

The publisher snapshots the existing portable workspace and requires its exact
fingerprints in the existing CLSI compilation manifest. It rejects changed
workspace inputs, source assets, PDFs or compiler evidence during packaging.
The completed directory appears only after all gates, checksums and manifest
writes succeed, through a rename on the same filesystem:

```text
<doc_name>/<version>/
  delivered/report.pdf
  source/report.json
  source/workspace/generated/   # LaTeX, assets, workspace manifest
  compilation/                 # Original compiler PDF, logs, compilation manifest
  validation.json
  release.json
```

Only `delivered/report.pdf` is the delivered artifact. The original compiler
snapshot is retained separately for provenance. Failed compilation, validation,
or packaging attempts remain under `releases/.attempts/` for diagnosis and never
appear as delivered versions. Compilation exceptions retain their diagnostic
paths; validation failures retain `validation.json` in the attempt. Do not treat
PDFs under `.attempts` as validated or publish that diagnostic directory.

`release.json` records document identity/title/version, installed wood-reports
and renderer versions, profile version, theme/brand revisions, source identity,
optional caller-supplied source revision, semantic digest, compiler backend and
engine, explicit UTC build timestamp, validation policy/status/page count, PDF
digest, and checksums of every packaged file except the manifest itself.
`source/report.json` is the renderer-neutral model snapshot; physical asset paths
become asset names/checksums so machine locations do not alter semantic identity.
`semantic_content_digest` excludes theme settings and renderer hints; presentation
revisions are recorded separately and the complete model snapshot is checksummed.
The source revision is `null` when the caller does not supply one; no Git context
is silently inferred from an unrelated working directory.

Provide `build_epoch` to the Python API, or `--build-epoch`/`SOURCE_DATE_EPOCH` to
the CLI. Canonical JSON and explicit timestamps make manifest generation
deterministic for an exact artifact snapshot. Repeated semantic inputs retain
the same semantic digest across output locations. The external CLSI/TeX engine
can emit differing PDF bytes/logs and per-attempt project IDs, which remain
faithfully checksummed in each manifest; this library does not claim byte-for-byte
reproducibility of remote compilation. Credentials and resource URLs are never
included in the release manifest.

Binary assets retain the existing CLSI transport contract: the caller supplies
reachable resource URLs and owns matching their bytes to the local workspace
snapshot. CLSI does not return a remote-input checksum attestation. The publisher
binds the local snapshot and returned artifacts without inventing that attestation.
