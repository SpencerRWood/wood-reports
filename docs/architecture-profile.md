# Architecture document profile

`technical-architecture@1.0.0` consumes source-owned Markdown through the existing
compiler, `Report`, shared Wood Analytics components, portable workspace, CLSI
LuaLaTeX backend and immutable publisher. It does not collect architecture facts,
attest runtime health, run Architecture Docs orchestration, publish production
documents or ingest RAG content.

## Authoring and navigation

Required metadata: `doc_type: technical-architecture`, slug `doc_name`, and `title`.
Releases also require `version`. Required semantic sections: `Summary` and
`Source provenance`. Other authored `##` headings retain their titles and semantic
identities. `###` through `######` retain their hierarchy; `Appendix` uses technical
appendix numbering. Leading generation-state and limitation paragraphs survive.

Set `toc: "true"` for a separate page with clickable contents, figures and tables.
`page_layout: landscape` selects landscape body composition. Otherwise text and
tables are portrait, with landscape diagram panels. Mixed pages reuse the shared
logo, typography, colors, confidentiality footer and page numbers in their
displayed orientation. Existing profiles retain their shared branding behavior.

Headings accept Pandoc-style IDs: `### Components {#components}`. Ordinary links
such as `[Components](#components)` provide clickable references. Tables accept
an immediately following `Table: Caption {#tbl:inventory}` paragraph. Diagrams
accept a plain `mermaid` fence or Pandoc attributes `{.mermaid #fig:context}`.
The first panel retains that ID; later panels append `-panel-2`, etc. Automatic
IDs remain `fig:1`, `tab:1`, etc. Unresolved references and duplicate labels fail
explicitly; authored IDs distinguish repeated custom headings.

## Deterministic vector diagrams

The pinned `wood-mermaid-relationship-panels@1.0.0` renderer accepts Mermaid
`flowchart`/`graph` directions LR, RL, TD, TB and BT; separately declared quoted
rectangular nodes; labeled directed `-->` and uncertain `-.->` edges; nested
quoted `subgraph` boundaries; and `%% legend: ...` comments. Context, component,
dependency, orchestration and deployment views share this source contract.

Each relationship appears once with its exact endpoint labels, direction and
relationship label. Isolated nodes remain present. Boundary membership appears
on endpoint nodes. Panels contain at most seven rows, repeat endpoint labels and
have captions, legends and stable references. Source direction is recorded;
layout deliberately uses readable relationship rows rather than the Mermaid
layout engine. The Overview yields six vector panels. Original `.mmd` sources
and independent diagram/profile/brand/theme versions are retained.

Other diagram languages, node shapes, inline declarations, style directives and
unlabeled edges fail explicitly. This is a strict Mermaid subset. No binary asset
host, shell escape, new compiler service or image change is required.

## Shared bibliography contract

Every profile supports structured `references` and Pandoc-style `[@stable-key]`
or `[@first; @second]` citations. Established linked source footnotes `[^key]`
are also supported, including the canonical Overview. Literal code is excluded.
Unsupported locators, unknown metadata fields and missing keys fail explicitly.

```yaml
references:
  - id: declaration-at-revision
    type: webpage
    title: Repository architecture declaration
    short-title: Repository / architecture.toml / revision
    URL: https://example.com/repository/blob/revision/architecture.toml
    repository: organization/repository
    path: architecture.toml
    revision: revision
    source-type: repository file
    evidence-state: declared; verified
    observation-timestamp: '2026-10-08T12:00:00Z'
    note: Declared intent; deployment health is not attested.
```

`id`, `type`, `title`, `short-title`, `URL` and `note` follow CSL/Pandoc conventions.
The remaining explicit fields extend CSL to preserve architecture provenance.
CSL `type` and architecture `source-type` retain separate meanings. This example
illustrates the schema only. Missing evidence remains `not provided`; absent
local source URLs remain absent. Source footnotes retain their aliases and derive
stable keys from URL/revision or local source identity. Commit-addressed files,
mutable metadata, stale evidence and uncommitted evidence stay distinguishable.
Entries deduplicate by identity/revision, conflicting provenance fails, distinct
revisions remain distinct, and every alias/citation occurrence survives.

The shared renderer uses biblatex/biber, hyperref, descriptive source labels,
external source links and individually clickable citation-page back-references.
Every citation occurrence has a PDF destination carrying its stable key. The
architecture preamble also loads cleveref; ordinary links and navigation lists
provide figure/table/section navigation. PowerPoint rejects bibliography and
diagram content explicitly. Existing profiles without that content stay compatible.

Generated `latexmkrc` selects the installed biber binary using TeX Live's
`kpsewhich --var-value=SELFAUTOLOC`. CLSI receives the file through supported
`flags`. This resolves the container's missing PATH entry without modifying
infrastructure. LuaLaTeX → biber → LuaLaTeX runs continue under latexmk until
navigation stabilizes; three TeX passes are a minimum, not a ceiling. Missing
biber is a hard failure. There is no numbered-reference downgrade or alternate
local compiler fallback in the publication path.

Release publication requires retained successful biber evidence and checks every
bibliography destination, source URL, citation occurrence/link and citing-page
back-reference. Results appear in `citation-validation.json`. Existing #434 PDF
and integrity gates remain in force. Only two informational probes for optional
biblatex defaults are distinguished from actual missing assets, which still fail.
Very large labels/evidence entries that cannot fit a page fail the typography
gate; they are not clipped or discarded. Bibliography entries stay together.

## Overview fixture and upstream #528 work

The [Overview fixture](../examples/architecture/overview.md) preserves the exact
canonical body used for the final #530 shared-layout review. Body SHA-256:
`7ca52fe2afc804b0627fc67144b2d2682956d68306fa7ac4f5176bc0bec30f83`.
Only consumer front matter was added, including structured metadata for the same
71 identities. It is historical design evidence, not a new architecture observation.

Regressions preserve 37 nodes, 37 typed relationships, 43 inventory rows, 71 source
entries, 95 citation occurrences, six diagram panels and every provided URL and
limitation. There are 70 URLs; source #71 has none and is explicitly uncommitted.
Live verification exercises actual CLSI compilation and PDF navigation.

For #528, Architecture Docs must own canonical stable IDs and structured source
provenance, including observation timestamps and full revisions when available.
Emit supported diagram syntax, explicit IDs for repeated headings, and authored
diagram/table captions. Existing source footnotes remain consumable. Missing
timestamps, unpinned metadata and uncommitted evidence must remain disclosed.
No production generator was changed. Repository-grouped bibliographies and
spatial graph layouts are future design options. Dagster remains the future
operational owner of generation, rendering and publication.
