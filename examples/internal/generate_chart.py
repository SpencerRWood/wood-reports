"""Consumer-owned synthetic chart; Wood Reports does not construct charts."""

import argparse
import csv
import json
from importlib.metadata import version
from pathlib import Path

from wood_charts import load_theme
from wood_charts.charts.core import line_chart
from wood_charts.export import export_chart


def generate(destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite {destination}")
    with Path(__file__).with_name("weekly-traffic.csv").open(newline="") as source:
        rows = list(csv.DictReader(source))
    theme = load_theme("base")
    figure = line_chart(
        {
            "week": [row["week"] for row in rows],
            "sessions": [int(row["sessions"]) for row in rows],
        },
        x="week",
        y="sessions",
        theme=theme,
        title="Synthetic weekly sessions",
        subtitle="Six-week fixture — not observed traffic",
        source="internal weekly-traffic.csv (synthetic)",
        x_axis_title="Week",
        y_axis_title="Sessions",
        layout_overrides={"showlegend": False, "margin": {"t": 180}},
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    export_chart(figure, destination, theme=theme)
    print(  # noqa: T201 -- bounded result from an executable example
        json.dumps({"chart": str(destination), "wood_charts": version("wood-charts")})
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    generate(parser.parse_args().destination)
