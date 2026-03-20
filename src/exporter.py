"""Export helpers for run summaries."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class FlightExporter:
    """Write normalized run results to CSV."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_run_summary(self, rows: List[Dict[str, Any]]) -> Path:
        """Write the latest run summary to a CSV file."""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"run_summary_{timestamp}.csv"
        fieldnames = [
            "route_from",
            "route_to",
            "flight_date",
            "flight_no",
            "airline",
            "price",
            "threshold",
            "is_low_price",
            "source",
            "departure_time",
            "arrival_time",
            "departure_airport",
            "arrival_airport",
            "status",
            "message",
        ]

        with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            for row in rows:
                writer.writerow({key: row.get(key, "") for key in fieldnames})

        return output_path
