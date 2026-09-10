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
│   ├── charts.py              # chart builders returning local artifact Paths
│   ├── chart_registry.py      # logical chart identity -> chart builder mapping
│   ├── publication_tables.py  # PublicationTable builders from metric results
│   └── report_build.py        # run parameters and orchestration
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
      - type: narrative
        text: Revenue is shown against the prior period.
      - type: chart
        identity: monthly-revenue
        caption: Monthly revenue
      - type: table
        columns:
          - {identity: month, label: Month}
          - {identity: revenue, label: Revenue, alignment: right}
        rows:
          - [September, 1300]
```

The consuming project resolves its logical chart identity and retains all data and chart
choices locally:

```python
from pathlib import Path

from wood_reports import (
    ChartGenerationContext,
    ReportCompiler,
    ReportGenerationAPI,
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
result = ReportGenerationAPI().generate(
    resolved,
    ROOT / "output" / period,
    artifact_root=ARTIFACTS,
    targets=("latex", "powerpoint"),
    period=period,
)
assert all(target.status == "success" for target in result.targets)
```

The example uses `ReportCompiler`, `ReportGenerationPipeline`, and
`ReportGenerationAPI` exactly as exported by Wood Reports. It produces
`output/2026-09/report.tex` and `output/2026-09/report.pptx`; either target can be
selected independently. The `build_monthly_revenue` function is intentionally a
consumer-owned seam: Wood Reports neither queries data nor constructs charts.
