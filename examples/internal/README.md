# Internal publication corpus

These four authored examples exercise the initial Wood Reports profiles using
Wood Reports v0.20.0 and the centralized design system from Story 530. Every
scenario and data value is synthetic. No customer, production, architecture,
secret, or operational evidence is collected.

| Source | Purpose | Representative content |
| --- | --- | --- |
| project-brief.md | Illustrative reporting pilot | Scope, deliverables, callouts, table |
| analytics-report.md | Six-week synthetic traffic review | Metrics, table, Wood Charts PNG, limitations |
| assessment-report.md | Illustrative publication readiness | Current-state table, findings, recommendations |
| decision-memo.md | Illustrative review-workflow choice | Options table, decision, rationale, risks |

All four have YAML front matter, required semantic sections, nested headings,
lists, callouts, an appendix, confidentiality and pinned documentation links.
These ordinary Markdown hyperlinks are the existing profiles' citation surface.
No new bibliography syntax, biblatex/biber, architecture profile or diagrams are
introduced. The analytics figure and table share the same six source rows:
7,000 sessions, 280 conversions, aggregate conversion rate 4%, and first-to-last
session change 32%. These are fixture arithmetic, not business findings.

## Source and output ownership

Canonical sources live here and in the approved
[Wood Reports/Examples/Internal folder](https://drive.google.com/drive/folders/1SOukvuC3cMqmgLCH63hApKaThNRgSplN).
The `assets` subfolder contains the chart PNG. Validated PDFs and manifests live
separately in [Internal/Outputs](https://drive.google.com/drive/folders/1HrD4dzjXtvoNIsL_w4rC42r_QOLTVnr8).
The previously existing sibling Examples/Outputs folder is preserved.

`publish.py` is consumer-owned executable documentation. It invokes the installed
native CLI entry point (`python -m wood_reports`) for profile inspection, source
validation and `build --release`. It never replaces the compiler, renderers,
workspace publisher, shared theme or release validator. It independently audits
every packaged artifact checksum after release. Any failing profile fails the
corpus; partial results must not be published as complete acceptance evidence.

## Local preparation

From the repository root:

```sh
uv sync --frozen --group dev
uv run python examples/internal/publish.py validate --output /private/tmp/internal-source-attempt-1
uv run pytest tests/unit/test_internal_examples.py -q
```

The checked-in PNG is intentionally part of this synthetic example. Regenerate
to a **new** path using the pinned development dependency wood-charts v0.3.0:

```sh
uv run python examples/internal/generate_chart.py /private/tmp/internal-chart-attempt-1/weekly-sessions.png
```

Plotly/Kaleido requires an available Chrome/Chromium and uses the installed IBM
Plex fonts. Wood Charts owns chart geometry and labels; its base theme supplies
the aligned palette. Compare a regenerated figure before intentionally updating
the canonical example asset. The generator refuses to overwrite an existing file.

## Live native CLI publication

Use the exact `[tool.wood_reports.clsi]` table in this directory's pyproject.toml.
Its publication configuration selects strict IBM Plex font checks while reusing
the shared default branding, colors, typography, page furniture and table policy.
Inject `WOOD_REPORTS_CLSI_USERNAME` and `WOOD_REPORTS_CLSI_PASSWORD` into the command
process using the application's secret manager. Never write them into this corpus.

The existing CLSI protocol requires a caller-published URL for binary resources.
Provide an external JSON file mapping `generated/assets/1-weekly-sessions.png` to
a CLSI-reachable URL serving the **exact checked-in PNG bytes**. Signed URLs must
remain external inputs; do not commit or upload the resource map. No publisher,
image build, infrastructure deployment, service or scheduler is installed by the
example runner. The caller owns resource availability and cleanup.

```sh
uv run python examples/internal/publish.py release \
  --output /private/tmp/internal-release-attempt-1 \
  --build-epoch 1791460800 \
  --resource-urls /private/tmp/internal-resources.json
```

`--source-revision` is optional and must identify the actual source revision. It
is deliberately absent for uncommitted working-tree examples; release manifests
then retain a null revision rather than attributing these files to an older commit.
Explicit timestamps stabilize manifest semantics, not remote PDF bytes.

Each attempt directory must be new. Released report versions are immutable;
failed attempts retain diagnostics. Regeneration in a fresh attempt directory
does not overwrite canonical Markdown, known-good releases or client outputs.
Source-resolution JSON, release JSON, compiler logs, validation records and the
bounded `corpus.json` summary remain under the chosen output directory. A release
contains separate `delivered`, `source`, `compilation`, `validation.json` and
`release.json` artifacts through the existing ReleasePublisher.

## Regression and acceptance evidence

Offline corpus tests check all profile contracts and shared workspace components,
table/callout/appendix semantics, exact local chart copying, numerical claims,
missing-chart rejection, native CLI execution and overwrite refusal. They reuse
the production APIs without a fake compiler.

The existing opt-in `tests/integration/test_clsi_live.py` gains one corpus check.
It reuses the existing readiness fixture and runs the real native CLI for all
four profiles. Supply `WOOD_REPORTS_INTERNAL_CHART_URL` for the exact PNG and
the existing `WOOD_REPORTS_CLSI_TEST_RESOURCE_URL` for the one-pixel compiler test.
Both are test-only resource inputs. Optionally set
`WOOD_REPORTS_INTERNAL_OUTPUT` to a new directory to retain the corpus release
outside pytest's temporary tree for Drive publication.

```sh
wood repo validate --json
# Inject compiler credentials and the two test-resource URLs first.
wood repo verify --json
```

The repository-owned CLSI check now includes the two existing integration tests
and the full corpus test within the existing 60-second verification budget.
The corpus test requires nonempty releases,
all source hyperlink destinations, branding/confidentiality text and a byte-exact
decoded RGB match between the authored PNG and the figure embedded in the PDF.
This supplements local source/workspace/PDF fingerprints and release checksums.

The Story 530 pixel harness and its pinned baselines remain unchanged. This Story
does not create a second visual-regression framework. Review actual corpus pages
separately: source/PDF validation does not certify visual quality, analytical
accuracy, PDF/A or production readiness. A bounded acceptance report accompanies
the published outputs; full diagnostics remain in the saved local records and
release packages. Do not mark the corpus accepted if any profile fails.
