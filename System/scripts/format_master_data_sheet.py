#!/usr/bin/env python3
"""マスタデータ用スプレッドシートの体裁を整える。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sheets_manager  # noqa: E402


SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w/edit?usp=sharing"

HEADER_BG = {"red": 0.357, "green": 0.584, "blue": 0.976}
HEADER_TEXT = {"red": 1, "green": 1, "blue": 1}
ZEBRA_BG = {"red": 0.91, "green": 0.941, "blue": 0.996}
WHITE = {"red": 1, "green": 1, "blue": 1}
TAB_BLUE = {"red": 0.357, "green": 0.584, "blue": 0.976}


def column_letter(index: int) -> str:
    result = ""
    while index > 0:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def estimate_width(values: list[str]) -> int:
    width = 0
    for value in values:
        current = 0
        for char in str(value):
            current += 14 if ord(char) > 127 else 7
        width = max(width, current)
    return min(max(width + 36, 90), 360)


def used_dimensions(ws) -> tuple[int, int, list[list[str]]]:
    values = ws.get_all_values()
    if not values:
        return 1, 1, [[]]
    used_rows = len(values)
    used_cols = max(len(row) for row in values) if values else 1
    return used_rows, max(used_cols, 1), values


def fetch_sheet_metadata(spreadsheet, sheet_id: int) -> dict:
    metadata = spreadsheet.fetch_sheet_metadata()
    for sheet in metadata.get("sheets", []):
        if sheet.get("properties", {}).get("sheetId") == sheet_id:
            return sheet
    return {}


def build_delete_existing_requests(sheet_meta: dict) -> list[dict]:
    requests: list[dict] = []
    for band in sheet_meta.get("bandedRanges", []):
        band_id = band.get("bandedRangeId")
        if band_id:
            requests.append({"deleteBanding": {"bandedRangeId": band_id}})
    for protected in sheet_meta.get("protectedRanges", []):
        range_info = protected.get("range", {})
        if range_info.get("startRowIndex") == 0 and range_info.get("endRowIndex") == 1:
            protected_id = protected.get("protectedRangeId")
            if protected_id:
                requests.append({"deleteProtectedRange": {"protectedRangeId": protected_id}})
    return requests


def apply_formatting(spreadsheet, ws) -> None:
    used_rows, used_cols, values = used_dimensions(ws)
    last_col = column_letter(used_cols)
    data_end_row = max(used_rows, 2)
    sheet_meta = fetch_sheet_metadata(spreadsheet, ws.id)

    requests = build_delete_existing_requests(sheet_meta)
    requests.append(
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": ws.id,
                    "gridProperties": {"frozenRowCount": 1, "columnCount": used_cols},
                    "tabColorStyle": {"rgbColor": TAB_BLUE},
                },
                "fields": "gridProperties.frozenRowCount,gridProperties.columnCount,tabColorStyle",
            }
        }
    )

    for index in range(used_cols):
        sample_values = []
        for row in values[: min(len(values), 30)]:
            sample_values.append(row[index] if index < len(row) else "")
        width = estimate_width(sample_values)
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": index,
                        "endIndex": index + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )

    requests.append(
        {
            "updateDimensionProperties": {
                "range": {
                    "sheetId": ws.id,
                    "dimension": "ROWS",
                    "startIndex": 0,
                    "endIndex": 1,
                },
                "properties": {"pixelSize": 36},
                "fields": "pixelSize",
            }
        }
    )
    requests.append(
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": data_end_row,
                        "startColumnIndex": 0,
                        "endColumnIndex": used_cols,
                    }
                }
            }
        }
    )
    requests.append(
        {
            "updateBorders": {
                "range": {
                    "sheetId": ws.id,
                    "startRowIndex": 0,
                    "endRowIndex": data_end_row,
                    "startColumnIndex": 0,
                    "endColumnIndex": used_cols,
                },
                "top": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "bottom": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "left": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "right": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
                "innerHorizontal": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
                "innerVertical": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
            }
        }
    )
    requests.append(
        {
            "addBanding": {
                "bandedRange": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 1,
                        "endRowIndex": max(ws.row_count, data_end_row + 1),
                        "startColumnIndex": 0,
                        "endColumnIndex": used_cols,
                    },
                    "rowProperties": {
                        "firstBandColor": WHITE,
                        "secondBandColor": ZEBRA_BG,
                    },
                }
            }
        }
    )
    requests.append(
        {
            "addProtectedRange": {
                "protectedRange": {
                    "range": {
                        "sheetId": ws.id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": used_cols,
                    },
                    "description": "ヘッダー行（変更注意）",
                    "warningOnly": True,
                }
            }
        }
    )

    spreadsheet.batch_update({"requests": requests})

    ws.format(
        f"A1:{last_col}1",
        {
            "backgroundColor": HEADER_BG,
            "textFormat": {
                "bold": True,
                "fontSize": 12,
                "foregroundColor": HEADER_TEXT,
                "fontFamily": "Arial",
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
        },
    )

    if data_end_row >= 2:
        ws.format(
            f"A2:{last_col}{data_end_row}",
            {
                "textFormat": {"fontFamily": "Arial", "fontSize": 10, "bold": False},
                "verticalAlignment": "MIDDLE",
            },
        )


def main() -> None:
    spreadsheet_id, _ = sheets_manager.extract_spreadsheet_id(SPREADSHEET_URL)
    client = sheets_manager.get_client("kohara")
    spreadsheet = client.open_by_key(spreadsheet_id)

    for ws in spreadsheet.worksheets():
        apply_formatting(spreadsheet, ws)
        print(f"formatted={ws.title}")


if __name__ == "__main__":
    main()
