# Architecture Overview design fixture

This frozen native example preserves the canonical body from the final 14-page
shared-branding prototype. Profile and structured source metadata were added
only to front matter. Regressions assert the original body checksum, 37 nodes,
37 relationships, 43 inventory rows, 71 source mappings and 95 citation occurrences.
No architecture facts or production publications are regenerated.

Use the existing CLI with process-injected CLSI credentials:

```sh
wood-report validate examples/architecture/overview.md --json
wood-report build examples/architecture/overview.md --release \
  --output /path/to/new/design-attempt --build-epoch 1791489600 --json
```

This produces an immutable design-test artifact directory, not a software release
or production publication. The ordinary publisher performs PDF, biber, navigation
and integrity gates, retaining the model, workspace, original Mermaid, `.bib`,
compiler logs, validation and checksums. No adapter, alternate report service or
#530 harness is used.

The required `architecture-biber-publication` Wood check exercises this exact
fixture against live CLSI. Set `WOOD_REPORTS_ARCHITECTURE_OUTPUT` to a new directory
to retain accepted artifacts outside pytest's temporary tree. The existing
internal corpus check shares the authenticated compiler fixture and keeps its scope.

See [the profile contract](../../docs/architecture-profile.md) for supported
syntax, metadata, design limitations and upstream #528 work. Preserve older Drive
prototypes and production files. Do not ingest these design artifacts into RAG.
