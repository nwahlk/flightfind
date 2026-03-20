"""Export helpers for run summaries."""

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


class FlightExporter:
    """Write normalized run results to CSV and Excel."""

    def __init__(self, output_dir: Path):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_run_summary(self, rows: List[Dict[str, Any]], format: str = "csv") -> Path:
        """Write the latest run summary to CSV or Excel file."""

        if format == "xlsx":
            return self._export_to_excel(rows)
        else:
            return self._export_to_csv(rows)

    def _export_to_csv(self, rows: List[Dict[str, Any]]) -> Path:
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

    def _export_to_excel(self, rows: List[Dict[str, Any]]) -> Path:
        """Write the latest run summary to an Excel file with formatting."""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"flight_prices_{timestamp}.xlsx"

        fieldnames = [
            ("route_from", "出发城市"),
            ("route_to", "到达城市"),
            ("flight_date", "出发日期"),
            ("flight_no", "航班号"),
            ("airline", "航空公司"),
            ("price", "价格(元)"),
            ("threshold", "阈值"),
            ("is_low_price", "低价标记"),
            ("source", "数据源"),
            ("departure_time", "起飞时间"),
            ("arrival_time", "到达时间"),
            ("departure_airport", "出发机场"),
            ("arrival_airport", "到达机场"),
            ("status", "状态"),
            ("message", "备注"),
        ]

        wb = Workbook()
        ws = wb.active
        ws.title = "航班价格"

        # 写入表头
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")
        for col, (key, label) in enumerate(fieldnames, 1):
            cell = ws.cell(row=1, column=col, value=label)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")

        # 写入数据
        low_price_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        for row_idx, row_data in enumerate(rows, 2):
            for col, (key, _) in enumerate(fieldnames, 1):
                value = row_data.get(key, "")
                cell = ws.cell(row=row_idx, column=col, value=value)
                cell.alignment = Alignment(horizontal="center", vertical="center")

                # 低价航班高亮
                if row_data.get("is_low_price") == "yes":
                    cell.fill = low_price_fill

        # 自动调整列宽
        for col in range(1, len(fieldnames) + 1):
            max_length = 0
            column = get_column_letter(col)
            for row in ws.iter_rows(min_row=1, max_row=ws.max_row, min_col=col, max_col=col):
                for cell in row:
                    try:
                        if cell.value:
                            max_length = max(max_length, len(str(cell.value)))
                    except:
                        pass
            adjusted_width = min(max_length + 2, 30)
            ws.column_dimensions[column].width = adjusted_width

        # 冻结首行
        ws.freeze_panes = "A2"

        wb.save(output_path)
        return output_path

    def export_flights_to_excel(
        self,
        flights: List[Dict[str, Any]],
        route_from: str,
        route_to: str,
        flight_date,
        threshold: int,
    ) -> Path:
        """导出航班列表到Excel（详细版）"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"flights_{route_from}_{route_to}_{flight_date}_{timestamp}.xlsx"
        output_path = self.output_dir / filename

        wb = Workbook()
        ws = wb.active
        ws.title = f"{route_from}-{route_to}"

        # 标题行
        ws.merge_cells("A1:H1")
        title_cell = ws.cell(row=1, column=1, value=f"{route_from} → {route_to} ({flight_date}) 低价阈值: ¥{threshold}")
        title_cell.font = Font(bold=True, size=14)
        title_cell.alignment = Alignment(horizontal="center")

        # 表头
        headers = ["航班号", "航空公司", "价格", "起飞时间", "到达时间", "出发机场", "到达机场", "是否低价"]
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(bold=True, color="FFFFFF")

        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=3, column=col, value=header)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        # 数据行
        low_price_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        sorted_flights = sorted(flights, key=lambda x: x.get("price", 99999))

        for row_idx, flight in enumerate(sorted_flights, 4):
            price = flight.get("price", 0)
            is_low = price <= threshold

            data = [
                flight.get("flight_no", ""),
                flight.get("airline", ""),
                f"¥{price}",
                flight.get("metadata", {}).get("departure_time", ""),
                flight.get("metadata", {}).get("arrival_time", ""),
                flight.get("departure_airport", ""),
                flight.get("arrival_airport", ""),
                "是" if is_low else "否",
            ]

            for col, value in enumerate(data, 1):
                cell = ws.cell(row=row_idx, column=col, value=value)
                cell.alignment = Alignment(horizontal="center")
                if is_low:
                    cell.fill = low_price_fill

        # 自动列宽
        for col in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(col)].width = 15

        ws.freeze_panes = "A4"
        wb.save(output_path)
        return output_path
