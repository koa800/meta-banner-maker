"""経営会議資料を Google Docs に自動挿入するスクリプト（v2: 2段階挿入）"""

import json
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CREDENTIALS_DIR = Path(__file__).resolve().parent.parent.parent / "credentials"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"
DOC_ID = "18D5fgk5G2xjgmpM7fORQuwcnD6oemZrNzPeDWNozO7s"


def get_docs_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), [
        "https://www.googleapis.com/auth/documents",
    ])
    return build("docs", "v1", credentials=creds)


def create_march_6_report():
    service = get_docs_service()

    # ===== STEP 1: テキスト全体を先頭に挿入 =====
    # セクション区切り（ページ区切り）を最初に入れて、既存コンテンツと分離
    full_text = (
        "2026/3/6　アドネス経営会議\n"
        "\n"
        "【総評】\n"
        "3/4\n"
        "2/5\n"
        "└月初4日間の着金売上は680万円で目標ペース（1億円/週）に大幅未達。"
        "ROAS 56%と低水準。ただし週次の集客数は+21.9%と上昇傾向、CPA 3,358円は許容範囲内。"
        "着金のタイムラグを考慮しても、現時点では厳しい状況。\n"
        "\n"
        "＜NEWS！＞\n"
        "☑（甲原さんに確認：今週のニュースがあれば追記してください）\n"
        "\n"
        "【3月目標と現状】\n"
        "\n"  # ← ここにテーブル1を後挿入
        "\n"
        "過去7日間推移（2/27〜3/5）\n"
        "\n"  # ← ここにテーブル2を後挿入
        "\n"
        "【プロジェクト進捗】\n"
        "\n"  # ← ここにテーブル3を後挿入
        "\n"
        "【ボトルネックと改善アクション】\n"
        "\n"  # ← ここにテーブル4を後挿入
        "\n"
        "【その他・共有事項】\n"
        "・（甲原さんに確認：共有事項があれば追記してください）\n"
    )

    # Step 1a: テキスト挿入
    requests = [
        {"insertText": {"location": {"index": 1}, "text": full_text}},
    ]

    # Step 1b: セクション区切り（テキストの末尾 = 既存コンテンツの直前）
    end_idx = 1 + len(full_text)
    requests.append({
        "insertSectionBreak": {
            "location": {"index": end_idx - 1},
            "sectionType": "NEXT_PAGE",
        }
    })

    print("Step 1: Inserting text...")
    service.documents().batchUpdate(
        documentId=DOC_ID, body={"requests": requests}
    ).execute()
    print("Text inserted.")

    # ===== STEP 2: フォーマット適用 =====
    print("Step 2: Applying formatting...")

    fmt_requests = []

    # タイトル行のインデックスを特定
    title = "2026/3/6　アドネス経営会議\n"
    title_start = 1
    title_end = title_start + len(title) - 1  # \n の前まで

    # タイトル: 太字 + 下線 + フォントサイズ20 + 中央揃え
    fmt_requests.append({
        "updateTextStyle": {
            "range": {"startIndex": title_start, "endIndex": title_end},
            "textStyle": {
                "bold": True,
                "underline": True,
                "fontSize": {"magnitude": 20, "unit": "PT"},
            },
            "fields": "bold,underline,fontSize",
        }
    })
    fmt_requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": title_start, "endIndex": title_end + 1},
            "paragraphStyle": {"alignment": "CENTER"},
            "fields": "alignment",
        }
    })

    # セクション見出しを太字 + フォントサイズ
    sections = [
        "【総評】", "＜NEWS！＞", "【3月目標と現状】",
        "過去7日間推移（2/27〜3/5）",
        "【プロジェクト進捗】", "【ボトルネックと改善アクション】",
        "【その他・共有事項】",
    ]
    for section in sections:
        pos = full_text.find(section)
        if pos >= 0:
            s = 1 + pos
            e = s + len(section)
            fmt_requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": s, "endIndex": e},
                    "textStyle": {
                        "bold": True,
                        "fontSize": {"magnitude": 14, "unit": "PT"},
                    },
                    "fields": "bold,fontSize",
                }
            })

    # 評価 "2/5" を太字
    rating_text = "2/5"
    pos = full_text.find(rating_text)
    if pos >= 0:
        s = 1 + pos
        e = s + len(rating_text)
        fmt_requests.append({
            "updateTextStyle": {
                "range": {"startIndex": s, "endIndex": e},
                "textStyle": {"bold": True},
                "fields": "bold",
            }
        })

    service.documents().batchUpdate(
        documentId=DOC_ID, body={"requests": fmt_requests}
    ).execute()
    print("Formatting applied.")

    # ===== STEP 3: テーブル挿入 =====
    print("Step 3: Inserting tables...")

    # 現在のドキュメントを読み取り、テーブル挿入位置を特定
    doc = service.documents().get(documentId=DOC_ID).execute()
    body_content = doc["body"]["content"]

    # テキスト内の目印を検索してインデックスを取得
    def find_paragraph_index_after(search_text):
        """指定テキストを含む段落の次の段落の開始インデックスを返す"""
        for i, element in enumerate(body_content):
            if "paragraph" in element:
                para_text = ""
                for el in element["paragraph"]["elements"]:
                    if "textRun" in el:
                        para_text += el["textRun"]["content"]
                if search_text in para_text:
                    # 次の要素の開始インデックス
                    if i + 1 < len(body_content):
                        return body_content[i + 1]["startIndex"]
        return None

    # テーブル挿入位置を特定（後ろから挿入してインデックスずれを防ぐ）
    table_insertions = []

    # テーブル4: ボトルネック（2列）
    idx = find_paragraph_index_after("【ボトルネックと改善アクション】")
    if idx:
        table_insertions.append(("bottleneck", idx, 2, 2))

    # テーブル3: プロジェクト進捗（3列）
    idx = find_paragraph_index_after("【プロジェクト進捗】")
    if idx:
        table_insertions.append(("project", idx, 4, 3))

    # テーブル2: 過去7日間推移（KPIカード代替, 4列2行）
    idx = find_paragraph_index_after("過去7日間推移")
    if idx:
        table_insertions.append(("weekly", idx, 3, 4))

    # テーブル1: 月目標と現状（2列4行）
    idx = find_paragraph_index_after("【3月目標と現状】")
    if idx:
        table_insertions.append(("monthly", idx, 4, 2))

    # 後ろから挿入
    table_insertions.sort(key=lambda x: x[1], reverse=True)

    for name, insert_idx, rows, cols in table_insertions:
        print(f"  Inserting table '{name}' at index {insert_idx} ({rows}x{cols})")
        service.documents().batchUpdate(
            documentId=DOC_ID,
            body={"requests": [
                {"insertTable": {
                    "rows": rows, "columns": cols,
                    "location": {"index": insert_idx},
                }}
            ]}
        ).execute()

    print("Tables inserted.")

    # ===== STEP 4: テーブルセル内容を埋める =====
    print("Step 4: Filling table cells...")

    doc = service.documents().get(documentId=DOC_ID).execute()
    body_content = doc["body"]["content"]

    # 挿入されたテーブルを順番に取得
    tables = []
    for element in body_content:
        if "table" in element:
            tables.append(element)
            # セクション区切り後のテーブル（既存の2/20以降）は無視
        if "sectionBreak" in element:
            break

    print(f"  Found {len(tables)} tables in new section")

    # 各テーブルのセルにテキストを挿入
    all_cell_requests = []

    # テーブル内のセル開始インデックスを取得するヘルパー
    def get_cell_index(table_element, row, col):
        cell = table_element["table"]["tableRows"][row]["tableCells"][col]
        return cell["content"][0]["paragraph"]["elements"][0]["startIndex"]

    if len(tables) >= 1:
        # テーブル1: 月目標と現状
        t = tables[0]
        monthly_cells = [
            (0, 0, "3月の目標"),
            (0, 1, "①着金売上：4億円（1億円/週）\n②集客数：4万人（1万人/週）"),
            (1, 0, "3月の進捗状況\n(3/1〜3/4)"),
            (1, 1, "集客数: 3,347（+13.5%）  個別予約数: 191（+41.5%）\n"
                    "着金売上: ¥6,799,654（-82.7%）  ROAS: 56%（-86.9%）\n"
                    "広告費: ¥12,039,542  CPA: ¥3,597\n"
                    "個別予約CPO: ¥63,034  粗利: ¥-5,239,888\n\n"
                    "目標に対して、着金売上・ROAS共に大幅未達。月初のため着金ラグの影響あり。"),
            (2, 0, "過去12週間推移"),
            (2, 1, "集客数は直近2週で回復傾向。個別予約数は1月後半のピークから減少トレンド。\n"
                    "CPAは3,000〜4,000円台で安定推移。\n\n"
                    "[ここに過去12週グラフスクショを貼付]"),
            (3, 0, "3月着地予想"),
            (3, 1, "粗利：¥-40,608,832（赤字見込み）\n"
                    "着金売上：¥52,697,319（約5,270万円）\n"
                    "集客数：25,939人\n"
                    "※月初4日の日割り計算。着金ラグにより実績は上振れる可能性あり。"),
        ]
        for row, col, text in monthly_cells:
            all_cell_requests.append({
                "insertText": {
                    "location": {"index": get_cell_index(t, row, col)},
                    "text": text,
                }
            })

    if len(tables) >= 2:
        # テーブル2: 過去7日間KPI
        t = tables[1]
        weekly_cells = [
            (0, 0, "集客数"),
            (0, 1, "個別予約数"),
            (0, 2, "着金売上"),
            (0, 3, "ROAS"),
            (1, 0, "6,296\n+21.9%"),
            (1, 1, "326\n-21.8%"),
            (1, 2, "¥46,012,462\n+4.8%"),
            (1, 3, "218%\n-11.7%"),
            (2, 0, "広告費: ¥21,144,193"),
            (2, 1, "CPA: ¥3,358"),
            (2, 2, "個別予約CPO: ¥64,859"),
            (2, 3, "粗利: ¥24,868,269"),
        ]
        for row, col, text in weekly_cells:
            all_cell_requests.append({
                "insertText": {
                    "location": {"index": get_cell_index(t, row, col)},
                    "text": text,
                }
            })

    if len(tables) >= 3:
        # テーブル3: プロジェクト進捗
        t = tables[2]
        project_cells = [
            (0, 0, "主なプロジェクト"),
            (0, 1, "評価"),
            (0, 2, "詳細情報"),
            (1, 0, "①Web広告から集客数4万人"),
            (1, 1, "やや良い"),
            (1, 2, "・集客数は回復傾向（週次+21.9%）\n・CPA改善中だが着金転換率に課題"),
            (2, 0, "②サブスク導線で単月ROAS100%"),
            (2, 1, "悪い"),
            (2, 2, "・ROAS 56%（月次）/218%（週次）と基準未達\n・着金売上の改善が急務"),
            (3, 0, "③UGC口コミ発生プロジェクト"),
            (3, 1, "（確認）"),
            (3, 2, "・甲原さんに進捗を確認してください"),
        ]
        for row, col, text in project_cells:
            all_cell_requests.append({
                "insertText": {
                    "location": {"index": get_cell_index(t, row, col)},
                    "text": text,
                }
            })

    if len(tables) >= 4:
        # テーブル4: ボトルネック
        t = tables[3]
        bn_cells = [
            (0, 0, "ボトルネック"),
            (0, 1, "改善アクション"),
            (1, 0, "着金売上が目標ペースの約1/15\nROAS 56%で基準300%を大幅下回る"),
            (1, 1, "甲原さんに確認：具体的なアクションを追記してください"),
        ]
        for row, col, text in bn_cells:
            all_cell_requests.append({
                "insertText": {
                    "location": {"index": get_cell_index(t, row, col)},
                    "text": text,
                }
            })

    # セルは後ろから挿入（インデックスずれ防止）
    all_cell_requests.sort(
        key=lambda r: r["insertText"]["location"]["index"], reverse=True
    )
    if all_cell_requests:
        service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": all_cell_requests}
        ).execute()

    print("All table cells filled.")
    print(f"\nReport created! View at:")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    create_march_6_report()
