---
doc_type: decision-memo
doc_name: internal-report-publication-decision
title: Standardize the Internal Report Review
subtitle: Representative decision memo
author: Wood Analytics
project: Internal publication examples
version: '1.0.0'
audience: Internal reviewers
confidentiality: Internal — synthetic example
source: Authored synthetic decision scenario; no production authorization
---

## Executive Summary

For this fictional pilot, use the supported Markdown-to-PDF publication path
instead of assembling unrelated source and output files by hand. The proposal
is an internal example, not a real purchasing or deployment decision.

## Decision

> [!DECISION] Select a repeatable publication workflow with visible source, validation, and review records.

## Options

| Option | Review experience | Traceability |
| --- | --- | --- |
| Manual file assembly | Flexible, inconsistent | Caller-maintained |
| Supported publication path | Shared profile and theme | Versioned manifest |

## Recommendation

Choose the supported path for the illustrative pilot. Keep source Markdown,
compiler diagnostics, and the delivered PDF separate; retain review feedback
alongside the release record.

## Rationale

### Decision criteria

The pilot favors repeatability, readable outputs, and explicit failure behavior.
The [native CLI](https://github.com/SpencerRWood/wood-reports/blob/v0.20.0/docs/native-cli.md)
exposes validation and release through the existing publication APIs. The
[release contract](https://github.com/SpencerRWood/wood-reports/blob/v0.20.0/docs/pdf-releases.md)
rejects unvalidated artifacts rather than marking a partial PDF as delivered.

## Risks

> [!RISK] The compiler needs its configured credentials, fonts, and reachable binary resources. Missing prerequisites must fail explicitly rather than trigger a different rendering path.

## Next Steps

1. Review all four profile examples.
2. Record any unsupported formatting requirements.
3. Approve repository delivery separately from internal artifact generation.

## Appendix

### Evidence boundary

This memo exercises supported Markdown links as citations to pinned documentation.
It adds no new citation syntax, bibliography processor, architecture profile,
service, scheduler, or deployment. All scenario statements are synthetic.
