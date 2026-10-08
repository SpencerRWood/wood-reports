# Wood Analytics publication design system

## Shared publication layout

Every installed document profile uses the same table policy, configured under
`[tool.wood_reports.publication.table_layout]`:

```toml
[tool.wood_reports.publication.table_layout]
density = "comfortable" # or "compact"
comfortable_row_inches = 0.28
compact_row_inches = 0.22
minimum_first_rows = 3
minimum_last_rows = 2
keep_together_rows = 6
```

Density changes row spacing, never font size. LaTeX measures the actual header
and body group, then uses `Needspace` for that height plus caption/outer
spacing. Short longtables reserve their complete body. Standard starred row
endings protect the first three and final two rows; interior rows remain
breakable. Headers repeat through `endhead`. Tables exceeding the threshold
use longtable automatically unless a layout or width hint is explicitly selected.
Explicit longtable with a width hint remains unsupported. Existing
short table floats remain whole. Captions, alignment, rules, notes and source
references retain their existing semantics. If the measured group exceeds a
page, grouping relaxes with a visible compiler warning.

Row stretch is local to shared table groups; it does not affect the title's
author block. The existing `spacing.table_row_inches` is the comfortable
slide height; compact density scales it by the compact/comfortable ratio.
Page row heights use the policy above, bounded below by the existing font baseline.

The regression's infinite glue-shrinkage messages originated in longtable's
page-output routine, not paragraph skip or table content. Its infinitely
shrinkable `vss` entered a box later split by LaTeX. Shared longtable setup
gives that glue finite shrink of one normal baseline while retaining its stretch,
scoped to the table. This applies the
[LaTeX project's finite-shrink correction](https://www.latex-project.org/news/latex2e-news/ltnews43.pdf)
without changing warning settings or replacing the output routine.

Shared inline primitives preserve technical tokens with invisible breaks at
identifier separators, and penalized breaks in long uninterrupted segments.
Prose stays IBM Plex Sans; semantic code stays IBM Plex Mono; hyperlink targets
are untouched. Technical narrative uses localized ragged-right layout; ordinary
narrative remains justified. Ordinary hyphenated words alone do not select
technical layout; semantic code, links and structured identifiers do.
No discretionary visible hyphens are inserted.

The PDF gate exposes grouped diagnostics with category, severity, count, log
location, available source lines, and badness/overflow magnitude. Compiler success,
structural gate status and visual acceptance are separate; visual acceptance
defaults to `not-assessed`. Infinite shrink, missing assets/fonts/glyphs,
undefined commands and structural failures block publication even when compilation
succeeds. Underfull badness at least 1000 and all overfull boxes remain visible.
The existing >5pt overflow and unresolved-reference/citation release gates remain.
The retained TeX `.log` is authoritative; duplicated stdout does not inflate counts.
Artifact fingerprints, PDF hashes and immutable release integrity are unchanged.

Pagination targets apply when groups fit. Existing single-line column semantics
remain; unusually tall captions and overflowing columns need authoring/configuration
review. Material overflow is reported rather than shrinking or deleting content.
Pixel checks also compile LuaLaTeX and assert real PDF structure for two profiles,
both densities, boundary tables, repeated headers, fragments, extraction and links.

Every report uses the immutable `WOOD_ANALYTICS_THEME` through `Report.theme`.
The theme identity is `wood-analytics`, shared layout revision `1.1.0`, and brand
revision `1.0.0`. YAML and profile-compliant Markdown compile to the same default.
The theme has no runtime dependency on wood-charts. A contract test compares its
shared tokens with the pinned wood-charts development dependency.

## Tokens and ownership

| Concern | Publication contract |
| --- | --- |
| Typography | IBM Plex Sans, Arial fallback; IBM Plex Mono for code; title, heading, body, table, caption, and note sizes |
| Color | Primary `#002F6C`, secondary `#4A90C2`, dark text `#1B1B1B`, secondary text `#4B5563`, muted text `#6B7280`, grid `#E5E7EB`, white background |
| Semantic accents | Primary for conclusions, summaries, recommendations, decisions, metrics, and notes; amber for risk/warning; red for critical findings; visible text labels accompany color |
| Geometry | 13.333 × 7.5 inch slides, 0.65 inch margins; 8.5 × 11 inch pages, 0.8 inch margins |
| Spacing | Paragraph separation, table row height, and figure width fraction |
| Branding | One `PublicationBranding` contract; bundled placeholder or replacement SVG rendered as vectors and editable text |
| Headers and footers | Configurable logo corner; report title on standard slides; page numbering and supplied confidentiality in footers; bottom-corner logos move conflicting footer content |
| Tables | Native tables, primary header with white text, shared body typography, column alignment/format, captions and muted notes |
| Figures | Locally materialized chart assets, captions and figure labels; original chart-intrinsic appearance retained |

Wood Reports owns report assembly, surrounding text, captions, source notes,
tables, headers/footers, confidentiality markings, and page geometry. Wood Charts
owns chart construction, axes, ticks, legends, marks, and chart-intrinsic labels.
Consumers choose the corresponding wood-charts publication theme when generating
their assets. Wood Reports does not recolor or rewrite rendered chart pixels.
The explicit `powerpoint.layout: full-frame-chart` hint delegates the entire slide
to the chart and omits report chrome, including page/confidentiality markings.

## Semantic primitives

| Markdown intent | Shared model | Branded rendering |
| --- | --- | --- |
| Paragraph | `Narrative(kind="prose")` | Body typography; editable emphasis, inline code, and hyperlinks |
| Subheading | `Narrative(kind="heading", semantic="h3"/"h4")` | Primary, emphasized heading |
| Bullet/ordered list | `Narrative(kind="list")` | List order, numbering starts, nesting, continuation paragraphs |
| `[!SUMMARY]`, `[!FINDING]`, `[!RECOMMENDATION]`, `[!RISK]`, `[!DECISION]`, `[!METRIC]`, `[!NOTE]` | `Narrative(kind="callout", semantic=...)` | Labeled box with a semantic accent |
| Fenced code | `Narrative(kind="code")` | Literal monospaced content |
| Table/figure | `PublicationTable` / `ChartReference` | Shared table and figure primitives |
| Appendix | `Appendix` | The same primitives as main report sections |

Unknown callout semantics fail instead of becoming plain prose. LaTeX escapes
publication text, including metadata and table cells; raw TeX in narrative text
is no longer interpreted. Use renderer hints for supported layout overrides.
PowerPoint preserves editable text and native tables. Standard slides include the
wordmark, supplied confidentiality marking, and page number, including the title.

## Fonts and revisions

Install IBM Plex Sans/Mono on the rendering/viewing machine for the intended font.
PowerPoint declares font names and does not embed fonts. XeLaTeX/LuaLaTeX use IBM
Plex Sans/Mono if installed, then Arial for sans text if available, and bundled
TeX Latin Modern font files otherwise; pdfLaTeX uses Helvetica.
These fallbacks preserve the semantic design but can change line wrapping.

Python consumers may create a frozen theme using `dataclasses.replace` and attach
it to a report, or pass it to `PublicationAPI(theme=theme)`. Assign a new theme
revision when changing layout tokens, and independently update `brand_identity`
and `brand_revision` when changing brand assets. Profile identities and revisions
remain owned by document profiles. All four installed profiles consume this same
contract; future architecture semantics remain profile-owned.

`PublicationBranding.from_svg(Path("logo.svg"))` snapshots a replacement asset.
It can be modified with `replace(branding, corner="bottom-left")`. Size and offsets
are inches, measured inward from the selected page/slide corner. The logo fits the
configured width/height while preserving its aspect ratio. `visible` controls body
pages/slides; `cover_visible` independently controls the first page/title slide.
Defaults are top-right, 2.2 × 0.35 inches, with offsets 0.6 × 0.35 inches; both
visibility options default to true. Full-frame chart slides retain their explicit
chrome-free behavior.

The portable SVG subset supports a zero-origin positive `viewBox`, six-digit hex
fills, filled rectangles, plain IBM Plex Sans text, and paths with lines, curves,
arcs and multiple contours under the nonzero fill rule. Curve segments use 64
deterministic samples in both targets. PowerPoint uses native editable freeforms;
LaTeX uses shared TikZ components without shell execution or binary resource URLs.
Outline other fonts and flatten transforms before importing. Gradients, strokes,
CSS, external resources, scripts, XML declarations, and unsupported elements or
attributes fail with actionable diagnostics. Assets are bounded to 256000 bytes,
128 elements and 32000 sampled points. Missing or malformed files fail before
publication; output workspaces no longer depend on the original SVG path.

`font_policy="fallback"` preserves the supported LaTeX fallbacks and reports missing
Plex fonts as compiler warnings. PowerPoint continues to declare font names without
embedding them. `font_policy="strict"` requires exact Sans/Mono fonts: LaTeX checks
on the compiler host and fails when unavailable; PowerPoint checks the rendering
host through fontconfig (`fc-match`). Strict LaTeX requires LuaLaTeX or XeLaTeX.

Generation, workspace and release manifests record independent `brand` and
`profile` identities/revisions, alongside the existing theme fields. Workspaces
also record the configured font policy and fingerprint the portable SVG and shared
`components.tex`. PowerPoint core properties carry theme/brand revisions.
Requested font names in a manifest do not attest to actual installed fonts.

## Central CLI configuration

`wood-report preview` and `build` read the publication table from their selected
`--config` file, which defaults to `pyproject.toml`. `PublicationTheme.from_pyproject`
uses the same supported interface for Python consumers. An absent publication table
uses supported defaults; unknown fields fail. There is no search for older files,
environment branding overrides, or profile-local branding configuration.

```toml
[tool.wood_reports.publication]
brand_identity = "internal-brand"
brand_revision = "2.0.0"
wordmark = "Internal Brand"

[tool.wood_reports.publication.branding]
svg_path = "assets/logo.svg" # Relative to this config file; snapshotted at load.
corner = "bottom-left"
width = 2.2
height = 0.35
offset_x = 0.6
offset_y = 0.35
visible = true
cover_visible = false
font_policy = "strict"

[tool.wood_reports.publication.typography]
caption = 11
```

The optional colors, typography, geometry and spacing tables use the existing
dataclass token names. Omit `svg_path` to use the placeholder with the configured
wordmark/primary color. Inline `logo_svg` is also supported; supplying both asset
forms is an error.

## Visual evidence

Cross-profile unit tests inspect both native outputs, configuration errors,
visibility, placement and independent manifest revisions. Pixel regression tests
use the exact LuaHBTeX, PyMuPDF and font-file hashes in
`tests/fixtures/publication-visual/environment.json`; mismatches fail explicitly.
Run `uv run pytest tests/integration/test_publication_visual.py
--run-publication-visual` on that environment. The checked-in cover/body PNGs cover
all four profiles, all corners, and placeholder/replacement SVGs. Updating a
baseline requires the additional explicit `--update-publication-visual` option and
visual review. Regular tests skip these opt-in checks rather than claim them passed.
