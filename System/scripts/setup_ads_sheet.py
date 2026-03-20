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
    "インプレッション",
    "リーチ",
    "フリークエンシー",
    "総クリック数",
    "リンククリック数",
    "リンククリック数（ユニーク）",
    "外部クリック数",
    "外部クリック数（ユニーク）",
    "消化金額",
    "配信ステータス",
    "広告作成日",
    "最終更新日",
    "クリエイティブID",
    "遷移先URL",
    "動画ID",
    "画像ハッシュ",
    "コンバージョン（JSON）",
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
    "CR識別キー",
    "メディアタイプ",
    "メディアID",
    "プロモーション種別",
    "遷移先URL",
    "インプレッション",
    "リーチ",
    "フリークエンシー",
    "クリック数（all）",
    "消化金額",
    "CPC",
    "CPM",
    "CTR",
    "コンバージョン数（optimization event）",
    "動画再生数",
    "動画2秒再生数",
    "動画6秒再生数",
    "動画完全再生数",
    "出稿形式レーン",
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

SOURCE_HEADERS = [
    "ソースID",
    "集客媒体",
    "データ種別",
    "取得レーン",
    "取得元",
    "取得面",
    "スクリプト",
    "対象タブ",
    "粒度",
    "主キー",
    "対象事業",
    "現状",
    "備考",
]

RULE_HEADERS = [
    "ルールID",
    "集客媒体",
    "対象タブ",
    "対象範囲",
    "追加単位",
    "実行方法",
    "重複判定キー",
    "更新方式",
    "欠損時の扱い",
    "品質判定",
    "現状",
    "備考",
]

MANAGEMENT_TABS = {
    "データソース管理": {
        "headers": SOURCE_HEADERS,
        "rows": [
            ["meta_insights_raw", "Meta", "実績", "本取得", "Meta Graph API", "act_{id}/insights", "fetch_meta_ads_to_sheet.py", "Meta", "1日 x 1広告ID", "日付+広告アカウントID+広告ID", "スキルプラス", "運用中", "raw本体"],
            ["meta_ad_metadata", "Meta", "広告メタ情報", "補完", "Meta Graph API", "ad fields / creative fields", "fetch_meta_ads_to_sheet.py", "Meta", "1広告ID x 最新メタ", "広告ID", "スキルプラス", "運用中", "作成日 更新日 URL 動画 画像ハッシュ"],
            ["meta_account_status", "Meta", "収集状況", "監視", "Meta Graph API", "account / campaign / adset / ad status", "fetch_meta_ads_to_sheet.py", "Meta収集状況", "1広告アカウント", "広告アカウントID", "スキルプラス", "運用中", "稼働状態 制限状態 判定理由"],
            ["tiktok_report_raw", "TikTok", "実績", "本取得", "TikTok Marketing API", "report/integrated/get", "fetch_tiktok_ads_report.py", "TikTok", "1日 x 1広告ID", "日付+広告アカウントID+広告ID", "スキルプラス", "運用中", "raw本体"],
            ["tiktok_ad_metadata", "TikTok", "広告メタ情報", "補完", "TikTok Marketing API", "ad/get", "fetch_tiktok_ads_report.py", "TikTok", "1広告ID x 最新メタ", "広告ID", "スキルプラス", "運用中", "広告名 ステータス CR識別キー URL候補"],
            ["tiktok_adgroup_metadata", "TikTok", "広告グループ情報", "補完", "TikTok Marketing API", "adgroup/get", "fetch_tiktok_ads_report.py", "TikTok", "1広告グループ x 最新メタ", "広告グループID", "スキルプラス", "運用中", "プロモーション種別"],
            ["tiktok_ads_manager_list", "TikTok", "URL補完", "fallback", "TikTok Ads Manager", "internal ad/list", "fetch_tiktok_ads_report.py", "TikTok", "1広告ID x fallback", "広告ID", "スキルプラス", "運用中", "通常出稿のURL補完"],
            ["tiktok_smart_plus_detail", "TikTok", "URL補完", "fallback", "TikTok Ads Manager", "procedural_detail", "fetch_tiktok_ads_report.py", "TikTok", "1広告ID x fallback", "広告ID", "スキルプラス", "運用中", "Smart+のURL補完"],
            ["tiktok_bulk_export", "TikTok", "URL補完", "fallback", "TikTok Ads Manager", "Bulk export", "fetch_tiktok_ads_report.py", "TikTok", "1広告ID x fallback", "広告ID", "スキルプラス", "予備", "Smart+以外でURLが残欠の時だけ"],
            ["x_report_raw", "X", "実績", "本取得", "X Ads API", "stats", "未作成", "X", "1日 x 1広告ID", "日付+広告アカウントID+広告ID", "スキルプラス", "未実装", "raw本体はこれから"],
            ["x_entity_metadata", "X", "広告メタ情報", "補完", "X Ads API", "line_items / promoted_tweets", "未作成", "X", "1広告ID x 最新メタ", "広告ID", "スキルプラス", "未実装", "広告名 URL CR補完想定"],
        ],
    },
    "データ追加ルール": {
        "headers": RULE_HEADERS,
        "rows": [
            ["meta_raw_append", "Meta", "Meta", "スキルプラス事業", "1日 x 1広告ID", "追記", "日付+広告アカウントID+広告ID", "重複行は追加しない", "値なしは空欄保持", "IDは文字列保持", "運用中", "raw本体"],
            ["meta_status_replace", "Meta", "Meta収集状況", "スキルプラス事業", "1広告アカウント", "全面更新", "広告アカウントID", "毎回作り直し", "0件と停止中を分離", "稼働中 / 停止中 / Meta制限を判定", "運用中", "監視用"],
            ["meta_gap_refresh", "Meta", "Meta", "稼働中アカウントの直近ギャップ", "不足日単位", "差分再取得", "日付+広告アカウントID+広告ID", "欠損日だけ補完", "欠損日は再取得対象", "収集状況で最新性確認", "運用中", "--refresh-running-gaps"],
            ["tiktok_raw_append", "TikTok", "TikTok", "スキルプラス事業", "1日 x 1広告ID", "追記", "日付+広告アカウントID+広告ID", "重複行は追加しない", "値なしは空欄保持", "URL欠損件数をサマリー保存", "運用中", "raw本体"],
            ["tiktok_url_fallback", "TikTok", "TikTok", "URLが空の広告", "1広告ID", "補完", "広告ID", "public API後にfallback実行", "未取得は内部サマリーへ残す", "missing_landing_page_details を保存", "運用中", "Smart+ を優先補完"],
            ["tiktok_token_reauth", "TikTok", "TikTok", "認証 fail 時", "1token", "再認可", "app_id+access_token", "再認可後に再診断", "refresh_token なし前提", "health check で判定", "運用中", "browser再認可方式"],
            ["x_raw_append", "X", "X", "スキルプラス事業", "1日 x 1広告ID", "追記", "日付+広告アカウントID+広告ID", "重複行は追加しない", "値なしは空欄保持", "raw未実装", "未実装", "今後実装"],
            ["x_metadata_fill", "X", "X", "URLやCRが必要な広告", "1広告ID", "補完", "広告ID", "public API後に補完", "未取得は内部サマリーへ残す", "raw未実装", "未実装", "今後実装"],
        ],
    },
}

LEGACY_MANAGEMENT_TABS = [
    "Metaデータソース管理",
    "Metaデータ追加ルール",
    "TikTokデータソース管理",
    "TikTokデータ追加ルール",
    "Xデータソース管理",
    "Xデータ追加ルール",
]

# タブ色（RGB 0-1）
TAB_COLOR_BLUE = {"red": 0.357, "green": 0.584, "blue": 0.976}


def to_a1_column_letter(column_number):
    """1始まりの列番号をA1表記の列記号へ変換する。"""
    result = []
    number = column_number
    while number > 0:
        number, remainder = divmod(number - 1, 26)
        result.append(chr(ord("A") + remainder))
    return "".join(reversed(result))


def estimate_column_width(header):
    """カラム名から適切な列幅を推定（全角≒14px, 半角≒7px + 余白20px）"""
    width = 0
    for char in header:
        if ord(char) > 127:
            width += 14
        else:
            width += 7
    return max(width + 80, 120)  # 少し広めに取り、最低120px


def apply_formatting(sh, ws, headers, include_table_styles=True, include_protection=True):
    """スキル準拠の書式を適用"""
    sheet_id = ws.id
    col_count = len(headers)
    col_letter = to_a1_column_letter(col_count)

    # --- ヘッダー書式（青背景 / 白文字 / 太字 / fontSize 11 / 中央揃え / Arial）---
    header_range = f"A1:{col_letter}1"
    ws.format(header_range, {
        "backgroundColor": HEADER_BG,
        "textFormat": {
            "bold": True,
            "fontSize": 11,
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

    # --- ヘッダー行の黒枠 ---
    requests.append({
        "updateBorders": {
            "range": {
                "sheetId": sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 0,
                "endColumnIndex": col_count,
            },
            "top": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "bottom": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "left": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "right": {"style": "SOLID_MEDIUM", "color": {"red": 0, "green": 0, "blue": 0}},
            "innerVertical": {"style": "SOLID", "color": {"red": 0.8, "green": 0.8, "blue": 0.8}},
        }
    })

    if include_table_styles:
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

    if include_protection:
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


def ensure_reference_tab(sh, existing_sheets, tab_name, headers, rows):
    values = [headers] + rows
    ws = existing_sheets.get(tab_name)
    target_rows = max(len(values) + 20, 100)
    if ws is None:
        ws = sh.add_worksheet(title=tab_name, rows=target_rows, cols=len(headers))
    else:
        if ws.row_count < target_rows:
            ws.resize(rows=target_rows)
        if ws.col_count < len(headers):
            ws.resize(cols=len(headers))
    ws.clear()
    ws.update(range_name="A1", values=values, value_input_option="RAW")
    apply_formatting(sh, ws, headers)
    return ws


def ensure_management_tabs(sh):
    current_sheets = {ws.title: ws for ws in sh.worksheets()}
    for tab_name in LEGACY_MANAGEMENT_TABS:
        ws = current_sheets.get(tab_name)
        if ws is not None:
            sh.del_worksheet(ws)
            current_sheets = {sheet.title: sheet for sheet in sh.worksheets()}
    for tab_name, config in MANAGEMENT_TABS.items():
        ensure_reference_tab(
            sh,
            current_sheets,
            tab_name,
            config["headers"],
            config["rows"],
        )
        current_sheets = {ws.title: ws for ws in sh.worksheets()}


def main():
    reformat_only = "--reformat-only" in sys.argv
    client = get_client("kohara")
    sh = client.open_by_key(SPREADSHEET_ID)

    existing_sheets = {ws.title: ws for ws in sh.worksheets()}

    if reformat_only:
        for tab_name, headers in TABS.items():
            if tab_name not in existing_sheets:
                continue
            ws = existing_sheets[tab_name]
            current_headers = ws.row_values(1) or headers
            apply_formatting(sh, ws, current_headers, include_table_styles=False, include_protection=False)
            print(f"[{tab_name}] 既存タブにヘッダー体裁を再適用。")
        ensure_management_tabs(sh)
        print("\n既存タブの再整形完了！")
        return

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

    ensure_management_tabs(sh)

    # デフォルトの「シート1」を削除
    existing_sheets = {ws.title: ws for ws in sh.worksheets()}
    if "シート1" in existing_sheets:
        sh.del_worksheet(existing_sheets["シート1"])
        print("「シート1」を削除。")

    print("\n設計完了！")


if __name__ == "__main__":
    main()
