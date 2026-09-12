# Production analytics integration

Wood Reports is a publication layer. A consuming analytics repository keeps its
business logic, data access, metrics, and chart construction; it supplies the resulting
models and artifacts to Wood Reports for validation and publication.

## Recommended repository shape

```
analytics-project/
├── notebooks/                 # optional exploratory work; never imported by reports
├── sql/                       # optional query definitions
├── src/analytics/
│   ├── metrics.py             # reusable, tested business metrics
│   ├── charts/                # chart builders returning local artifact Paths
│   ├── charts/registry.py     # logical chart identity -> chart builder mapping
│   ├── tables/                # PublicationTable builders from metric results
│   └── reporting/             # run parameters and orchestration
├── reports/
│   └── monthly.yaml           # declarative report structure and chart identities
└── output/                    # generated, untracked report artifacts
```

Only `reports/`, `chart_registry.py`, and `report_build.py` are necessary for a simple
report. Add notebooks, SQL, reusable metrics, charts, or table builders only when the
publication needs them. Keep `output/` out of source control; it is a caller-owned
landing zone for generated `.tex`/`.pptx` files and source artifacts.

## End-to-end example

`reports/monthly.yaml` describes report structure, not analytical computation:

```yaml
metadata:
  title: Revenue review
  subtitle: "{{ period }}"
  source: Finance ledger
sections:
  - title: Results
    content:
      - narrative: Revenue is shown against the prior period.
      - chart:
          identity: monthly-revenue
          caption: Monthly revenue
      - table:
        columns:
          - {identity: month, label: Month}
          - {identity: revenue, label: Revenue, alignment: right}
        rows:
          - [September, 1300]
findings:
  - source: findings/growth.md
    include_if: include_growth
```

`reports/findings/growth.md` supplies finding-owned semantic text and its shared
visual without a renderer-specific definition:

```markdown
---
identity: weekday_sessions
title: Weekend traffic falls sharply
subtitle: Saturday sessions are materially below the weekday baseline
source: Synthetic website data
severity: info
---
Narrative text may reference \ref{fig:weekday_sessions} in LaTeX output.
```

The consuming project resolves its logical chart identity and retains all data and chart
choices locally:

```python
from pathlib import Path

from wood_reports import (
    ChartGenerationContext,
    ReportCompiler,
    Comparison,
    ReportGenerationAPI,
    ReportRun,
    ReportGenerationPipeline,
)

ROOT = Path(__file__).parents[1]
ARTIFACTS = ROOT / "output" / "artifacts"


def build_monthly_revenue(context: ChartGenerationContext) -> Path:
    # Query metrics and construct the chart here, using the consuming project's tools.
    path = ARTIFACTS / "monthly-revenue.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    # save_chart(compute_monthly_revenue(), path, title=context.title)
    return path


period = "2026-09"
report = ReportCompiler({"period": period}).compile_file(
    ROOT / "reports" / "monthly.yaml", artifact_root=ARTIFACTS
)
resolved = ReportGenerationPipeline(
    {"monthly-revenue": build_monthly_revenue}, run_context={"period": period}
).generate(report, artifact_root=ARTIFACTS)
run = ReportRun.create(
    resolved,
    period=period,
    comparison_period="2026-08",
    values={"period": period},
    comparisons={"revenue": Comparison(1300, 1200)},
    flags={"include_growth": True},
)
result = ReportGenerationAPI().generate(
    run,
    ROOT / "output",
    artifact_root=ARTIFACTS,
    targets=("latex", "powerpoint"),
    immutable=True,
    report_id="monthly-revenue",
    definition_revision="2026.09",
)
assert all(target.status == "success" for target in result.targets)
```

The example uses `ReportCompiler`, `ReportGenerationPipeline`, and
`ReportGenerationAPI` exactly as exported by Wood Reports. It produces
`output/monthly-revenue/2026-09/report.tex`, a self-contained `assets/` tree,
`report.pptx`, and `manifest.json`; either target can be
selected independently. The `build_monthly_revenue` function is intentionally a
consumer-owned seam: Wood Reports neither queries data nor constructs charts.
