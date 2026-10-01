# Markdown authoring

New client documents use one `report.md` with YAML front matter and profile-recognized
`##` headings. Profiles are typed, validated, versioned Python definitions in
`wood_reports.profiles`. The installed profile supplies its purpose, metadata contract,
section guidance, approved section variants, permitted content, and callout kinds.
The compiled result is the same renderer-neutral `Report` used by Python consumers.

```markdown
---
doc_type: decision-memo
doc_name: internal-platform-decision
title: Internal platform decision
author: Wood Analytics
version: '1.0'
confidentiality: Internal
---

## Executive Summary
Adopt the proposed platform after the pilot meets its acceptance criteria.

## Decision
Choose the platform for the next reporting increment.

## Options
- Extend the existing platform.
- Adopt the proposed platform.

## Recommendation
Run a bounded pilot of the proposed platform.

## Rationale
| Criterion | Proposed platform |
| :--- | ---: |
| Supported integrations | 4 |

## Risks
> [!RISK] Confirm operational ownership before adoption.
```

```python
from pathlib import Path
from wood_reports import ReportCompiler, get_profile, scaffold_markdown

report = ReportCompiler().compile_file(Path("report.md"))
profile = get_profile(report.metadata.doc_type)
draft = scaffold_markdown("project-brief", "new-engagement")
```

`doc_type`, a lowercase slug `doc_name`, and nonblank `title` are required. Optional
text metadata includes subtitle, author, source, client, project, engagement, version,
audience, confidentiality, period, and comparison_period. Quote dates and versions to
keep YAML values textual. Unknown fields and duplicate keys fail validation.

The initial profiles are project-brief, analytics-report, assessment-report, and
decision-memo. Inspect `list_profiles()` or `get_profile()` for their exact required
and optional sections. Analytics supports both the detailed section contract and a
lighter Executive Summary / KPI Overview / Key Findings / Supporting Analysis /
Recommendations variant. Assessments evaluate current state rather than answering
what analytical data shows. Empty scaffolds must be authored before compilation.

Use `###` or deeper headings for subsections. Markdown prose retains inline notation;
lists, code samples, tables, charts, and semantic callouts have typed content semantics.
Appendix content compiles into `Report.appendices`. Chart references occupy a standalone
paragraph: `![Caption](charts/trend.png)` references a caller-owned local artifact,
and `![Caption](chart:revenue-trend)` declares a logical chart for the consuming registry.
Remote image URLs, absolute paths, and parent traversal are rejected. Supported callouts
use blockquotes with `[!SUMMARY]`, `[!FINDING]`, `[!RECOMMENDATION]`, `[!RISK]`,
`[!DECISION]`, `[!METRIC]`, or `[!NOTE]`, followed by prose.

Jinja supports named precomputed values and the existing `presentation` filter.
Substitutions occur within already-parsed blocks; they cannot add sections or change
report structure. Unsupported block syntax fails explicitly. Themes and renderer
presentation of the new semantics belong to the following publication stories.

## Drive sources

Store Markdown as a Drive file, or place exactly one `report.md` in a Drive folder.
Native Google Docs are not Markdown sources. The reader accepts a raw file ID or a
canonical Drive file/folder URL, rejects ambiguous folders, and bounds input size.

```python
from wood_reports import GoogleDriveReader, compile_drive_report

# The caller acquires and refreshes its OAuth token with Drive read access.
reader = GoogleDriveReader(access_token)
report = compile_drive_report(drive_url, reader, artifact_root=Path("artifacts"))
```

Metadata comes from the source. Optional `doc_type` and `doc_name` arguments are explicit
overrides for recovery or automation. A caller can supply the `DriveReader` protocol
instead of the OAuth HTTP adapter. Local chart artifacts remain caller-owned and must
be supplied under `artifact_root`; logical charts resolve downstream. The library does
not acquire credentials or depend on Wood Tools. Native CLI commands are delivered by
the separate R2 CLI story, using this same compilation API.

## Existing YAML consumers

Existing YAML composition remains available through the explicit
`ReportCompiler.compile_yaml_file()` compatibility API. Calling `compile_file()` on
`.yaml` or `.yml` emits a deprecation warning. New client documents use Markdown;
they require no separately authored `report.yaml` or LaTeX. Existing analytics definitions
and their typed runtime model continue to work while callers migrate.
