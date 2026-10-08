---
doc_type: project-brief
doc_name: internal-publication-pilot
title: Internal Publication Pilot
subtitle: Representative project brief
author: Wood Analytics
project: Internal publication examples
version: '1.0.0'
audience: Internal reviewers
confidentiality: Internal — synthetic example
source: Authored synthetic planning scenario; no client data
---

## Executive Summary

Run a small internal pilot to make recurring analytical reports easier to review.
This document is an **illustrative planning scenario**, not an approved engagement.

> [!SUMMARY] Success means a reviewer can follow the question, evidence, conclusion, and recommended next action in a validated PDF.

## Context

The example team assembles a weekly review from a six-week synthetic dataset.
The pilot separates reusable analysis from publication and makes source notes visible.
The [Wood Reports publication contract](https://github.com/SpencerRWood/wood-reports/blob/v0.20.0/docs/publication-design-system.md)
defines the shared branding used by these examples.

## Objectives

- Produce one clear narrative from precomputed inputs.
- Keep the Markdown source readable outside the PDF.
- Preserve the distinction between source, compiler logs, and delivered output.

## Scope

### Included work

Profile validation, shared branding, a representative table, source links, and a
versioned PDF are included. Customer data, automated scheduling, and external
delivery are outside this illustrative pilot.

## Approach

1. Author a profile-compliant Markdown document.
2. Validate its Report model and portable LaTeX workspace.
3. Compile with CLSI and apply the release gates before sharing the PDF.

## Deliverables

| Deliverable | Intended use | Review owner |
| --- | --- | --- |
| Markdown source | Content review | Analyst |
| Validated PDF | Visual review | Reviewer |
| Release manifest | Artifact traceability | Maintainer |

## Success Criteria

All required sections are present, the compiler succeeds, no unresolved source
references remain, and the release manifest identifies the exact delivered PDF.
The reviewer also checks typography and page composition separately.

## Risks

> [!RISK] A structurally valid PDF can still be hard to read. Human visual review remains part of acceptance.

## Next Steps

The example reviewer records presentation feedback before adopting the pilot.
This is a demonstration of workflow, not an instruction to deploy a service.

## Appendix

### Sources and evidence limits

The scenario is authored for internal regression testing. It contains no measured
customer or operational claims. The linked publication contract is pinned to
Wood Reports v0.20.0. The [release documentation](https://github.com/SpencerRWood/wood-reports/blob/v0.20.0/docs/pdf-releases.md)
describes validation and immutable packaging.
