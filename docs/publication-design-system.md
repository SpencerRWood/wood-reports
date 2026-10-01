# Wood Analytics publication design system

Every report uses the immutable `WOOD_ANALYTICS_THEME` through `Report.theme`.
The initial theme identity is `wood-analytics`, theme revision `1.0.0`, and brand
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
| Branding | Bundled vector wordmark in `assets/wordmark.svg`; editable text wordmark in native outputs |
| Headers and footers | Wordmark and report title on standard slides; wordmark in page headers; page numbering and supplied confidentiality in footers |
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

Python consumers may create a new frozen theme using `dataclasses.replace` and
attach it to a report. Assign a new theme/brand revision whenever changing tokens
or branding. The bundled SVG represents the default brand; a custom brand must
supply its own external vector asset. Renderers use the theme's native text
wordmark. Invalid colors, sizes, and geometry fail before writing outputs.

Generation manifests record `theme.identity`, `theme.revision`, and
`theme.brand_revision` from the materialized report. PowerPoint core properties
also carry these revisions. Font availability is a machine prerequisite, not an
assertion made by a manifest. Portable workspace orchestration remains owned by
the following branded LaTeX workspace story.
