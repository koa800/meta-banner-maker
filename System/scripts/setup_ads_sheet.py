#!/usr/bin/env python3
"""
広告データ収集シートの初期設計
スプレッドシート設計ルール（Skills/6_システム/スプレッドシート設計ルール.md）準拠
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from sheets_manager import get_client

SPREADSHEET_ID = "11lVHxkA0geY7TEVKoujYrv1JyxWhzxqSepNhFxnFZlo"

# 色定義（スキル準拠）
HEADER_BG = {"red": 0.357, "green": 0.584, "blue": 0.976}  # 青
HEADER_TEXT = {"red": 1, "green": 1, "blue": 1}  # 白
ZEBRA_BG = {"red": 0.91, "green": 0.941, "blue": 0.996}  # 薄い青
WHITE = {"red": 1, "green": 1, "blue": 1}

# --- Meta広告 ---
META_HEADERS = [
    "日付",
    "広告アカウント名",
    "広告アカウントID",
    "キャンペーンID",
    "キャンペーン名",
    "広告セットID",
    "広告セット名",
    "広告ID",
    "広告名",
    "配信ステータス",
    "広告作成日",
    "最終更新日",
    "クリエイティブID",
    "メディアタイプ",
    "メディアID",
    "遷移先URL",
    "インプレッション",
    "リーチ",
    "フリークエンシー",
    "リンククリック数",
    "ユニークリンククリック数",
    "消化金額",
    "リンクCPC",
    "CPM",
    "リンクCTR",
]

# --- TikTok広告 ---
TIKTOK_HEADERS = [
    "日付",
    "広告アカウント名",
    "広告アカウントID",
    "キャンペーンID",
    "キャンペーン名",
    "広告グループID",
    "広告グループ名",
    "広告ID",
    "広告名",
    "配信ステータス",
    "広告作成日",
    "最終更新日",
    "クリエイティブID",
    "メディアタイプ",
    "メディアID",
    "遷移先URL",
    "インプレッション",
    "リーチ",
    "フリークエンシー",
    "クリック数",
    "消化金額",
    "CPC",
    "CPM",
    "CTR",
    "コンバージョン数",
    "コンバージョン単価",
    "動画再生数",
    "動画2秒再生数",
    "動画6秒再生数",
    "動画完全再生数",
]

# --- X (Twitter)広告 ---
X_HEADERS = [
    "日付",
    "広告アカウント名",
    "広告アカウントID",
    "キャンペーンID",
    "キャンペーン名",
    "広告グループID",
    "広告グループ名",
    "広告ID",
    "広告名",
    "配信ステータス",
    "広告作成日",
    "最終更新日",
    "クリエイティブID",
    "メディアタイプ",
    "メディアID",
    "遷移先URL",
    "インプレッション",
    "リーチ",
    "フリークエンシー",
    "リンククリック数",
    "消化金額",
    "CPC",
    "CPM",
    "CTR",
    "エンゲージメント数",
    "エンゲージメント率",
]

TABS = {
    "Meta": META_HEADERS,
    "TikTok": TIKTOK_HEADERS,
    "X": X_HEADERS,
}

# タブ色（RGB 0-1）
TAB_COLOR_BLUE = {"red": 0.357, "green": 0.584, "blue": 0.976}


def estimate_column_width(header):
    """カラム名から適切な列幅を推定（全角≒14px, 半角≒7px + 余白20px）"""
    width = 0
    for char in header:
        if ord(char) > 127:
            width += 14
        else:
            width += 7
    return max(width + 40, 80)  # 最低80px


def apply_formatting(sh, ws, headers):
    """スキル準拠の書式を適用"""
    sheet_id = ws.id
    col_count = len(headers)
    col_letter = chr(ord("A") + col_count - 1) if col_count <= 26 else "Z"

    # --- ヘッダー書式（青背景 / 白文字 / 太字 / fontSize 12 / 中央揃え / Arial）---
    header_range = f"A1:{col_letter}1"
    ws.format(header_range, {
        "backgroundColor": HEADER_BG,
        "textFormat": {
            "bold": True,
            "fontSize": 12,
            "foregroundColor": HEADER_TEXT,
            "fontFamily": "Arial",
        },
        "horizontalAlignment": "CENTER",
        "verticalAlignment": "MIDDLE",
    })

    # --- フリーズ行1 ---
    requests = []
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "gridProperties": {"frozenRowCount": 1},
            },
            "fields": "gridProperties.frozenRowCount",
        }
    })

    # --- タブ色 ---
    requests.append({
        "updateSheetProperties": {
            "properties": {
                "sheetId": sheet_id,
                "tabColorStyle": {"rgbColor": TAB_COLOR_BLUE},
            },
            "fields": "tabColorStyle",
        }
    })

    # --- 列幅 ---
    for i, header in enumerate(headers):
        width = estimate_column_width(header)
        requests.append({
            "updateDimensionProperties": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "COLUMNS",
                    "startIndex": i,
                    "endIndex": i + 1,
                },
                "properties": {"pixelSize": width},
                "fields": "pixelSize",
            }
        })

    # --- ヘッダー行の高さ ---
    requests.append({
        "updateDimensionProperties": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": 0,
                "endIndex": 1,
            },
            "properties": {"pixelSize": 36},
            "fields": "pixelSize",
        }
    })

    # --- 罫線（ヘッダー行 + データ領域100行分）---
    # 外枠太線
    requests.append({
        "updateBorders": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 101,
                "startColumnIndex": 0,
                "endColumnIndex": col_count,
            },
            "top": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "bottom": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "left": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "right": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "innerHorizontal": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
            "innerVertical": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
        }
    })

    # ヘッダー下太線
    requests.append({
        "updateBorders": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": col_count,
            },
            "bottom": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
        }
    })

    # --- 交互色（addBanding）---
    requests.append({
        "addBanding": {
            "bandedRange": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": 1000,
                    "startColumnIndex": 0,
                    "endColumnIndex": col_count,
                },
                "rowProperties": {
                    "firstBandColor": WHITE,
                    "secondBandColor": ZEBRA_BG,
                },
            }
        }
    })

    # --- データ行のデフォルト書式（Arial / fontSize 10）---
    requests.append({
        "repeatCell": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 1,
                "endRowIndex": 1000,
                "startColumnIndex": 0,
                "endColumnIndex": col_count,
            },
            "cell": {
                "userEnteredFormat": {
                    "textFormat": {
                        "fontFamily": "Arial",
                        "fontSize": 10,
                        "bold": False,
                    },
                }
            },
            "fields": "userEnteredFormat.textFormat",
        }
    })

    # --- ヘッダー行保護（警告モード）---
    requests.append({
        "addProtectedRange": {
            "protectedRange": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": col_count,
                },
                "description": "ヘッダー行（変更注意）",
                "warningOnly": True,
            }
        }
    })

    sh.batch_update({"requests": requests})


def main():
    client = get_client("kohara")
    sh = client.open_by_key(SPREADSHEET_ID)

    existing_sheets = {ws.title: ws for ws in sh.worksheets()}

    for tab_name, headers in TABS.items():
        # 既存タブがあれば削除して再作成（書式を完全リセット）
        if tab_name in existing_sheets:
            sh.del_worksheet(existing_sheets[tab_name])
            print(f"[{tab_name}] 既存タブを削除。")

        ws = sh.add_worksheet(title=tab_name, rows=1000, cols=len(headers))
        print(f"[{tab_name}] タブを新規作成。")

        # ヘッダー書き込み
        ws.update([headers], "A1")

        # 書式適用
        apply_formatting(sh, ws, headers)

        print(f"[{tab_name}] 書式設定完了（{len(headers)}列）")

    # デフォルトの「シート1」を削除
    existing_sheets = {ws.title: ws for ws in sh.worksheets()}
    if "シート1" in existing_sheets:
        sh.del_worksheet(existing_sheets["シート1"])
        print("「シート1」を削除。")

    print("\n設計完了！")


if __name__ == "__main__":
    main()
