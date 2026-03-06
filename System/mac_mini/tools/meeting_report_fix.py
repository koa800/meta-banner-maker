"""挿入済みの経営会議資料のフォーマット修正 + テーブルセル埋め"""

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


def fix_report():
    service = get_docs_service()
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    # セクション区切りを探して、新しいセクションの範囲を特定
    section_break_idx = None
    for element in body:
        if "sectionBreak" in element and element.get("startIndex", 0) > 1:
            section_break_idx = element["startIndex"]
            break

    if section_break_idx is None:
        # セクション区切りが見つからない場合、ドキュメント全体を対象
        section_break_idx = body[-1].get("endIndex", 9999999)
        print(f"No section break found, using end of doc: {section_break_idx}")

    print(f"New section ends at index {section_break_idx}")

    # ===== Step 1: 全体のフォーマットをリセット =====
    requests = []

    # テキスト部分の範囲（テーブル内は除く）を集める
    text_ranges = []
    for element in body:
        if element.get("startIndex", 0) >= section_break_idx:
            break
        if "paragraph" in element:
            start = element["startIndex"]
            end = element["endIndex"]
            text_ranges.append((start, end))

    # 全テキストのフォーマットリセット（デフォルトに戻す）
    for start, end in text_ranges:
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "textStyle": {
                    "bold": False,
                    "underline": False,
                    "fontSize": {"magnitude": 11, "unit": "PT"},
                },
                "fields": "bold,underline,fontSize",
            }
        })
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": start, "endIndex": end},
                "paragraphStyle": {"alignment": "START"},
                "fields": "alignment",
            }
        })

    # テーブル内のセルもリセット
    for element in body:
        if element.get("startIndex", 0) >= section_break_idx:
            break
        if "table" in element:
            for row in element["table"]["tableRows"]:
                for cell in row["tableCells"]:
                    for content in cell["content"]:
                        if "paragraph" in content:
                            s = content["startIndex"]
                            e = content["endIndex"]
                            requests.append({
                                "updateTextStyle": {
                                    "range": {"startIndex": s, "endIndex": e},
                                    "textStyle": {
                                        "bold": False,
                                        "underline": False,
                                        "fontSize": {"magnitude": 10, "unit": "PT"},
                                    },
                                    "fields": "bold,underline,fontSize",
                                }
                            })

    print(f"Step 1: Resetting {len(requests)} format ranges...")
    if requests:
        service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": requests}
        ).execute()

    # ===== Step 2: 正しいフォーマット適用 =====
    print("Step 2: Applying correct formatting...")

    # ドキュメントを再読み込み
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    fmt_requests = []

    def find_text_range(search_text):
        """テキストを含む段落の範囲を返す"""
        for element in body:
            if element.get("startIndex", 0) >= section_break_idx:
                break
            if "paragraph" in element:
                for el in element["paragraph"]["elements"]:
                    if "textRun" in el:
                        content = el["textRun"]["content"]
                        if search_text in content:
                            pos = content.find(search_text)
                            start = el["startIndex"] + pos
                            return start, start + len(search_text)
        return None, None

    # タイトル: 太字 + 下線 + 20pt + 中央
    s, e = find_text_range("2026/3/6　アドネス経営会議")
    if s:
        fmt_requests.extend([
            {"updateTextStyle": {
                "range": {"startIndex": s, "endIndex": e},
                "textStyle": {
                    "bold": True, "underline": True,
                    "fontSize": {"magnitude": 20, "unit": "PT"},
                },
                "fields": "bold,underline,fontSize",
            }},
            {"updateParagraphStyle": {
                "range": {"startIndex": s, "endIndex": e + 1},
                "paragraphStyle": {"alignment": "CENTER"},
                "fields": "alignment",
            }},
        ])

    # セクション見出し: 太字 + 14pt
    section_headers = [
        "【総評】", "＜NEWS！＞", "【3月目標と現状】",
        "過去7日間推移", "【プロジェクト進捗】",
        "【ボトルネックと改善アクション】", "【その他・共有事項】",
    ]
    for header in section_headers:
        s, e = find_text_range(header)
        if s:
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
    s, e = find_text_range("2/5")
    if s:
        fmt_requests.append({
            "updateTextStyle": {
                "range": {"startIndex": s, "endIndex": e},
                "textStyle": {"bold": True, "fontSize": {"magnitude": 13, "unit": "PT"}},
                "fields": "bold,fontSize",
            }
        })

    if fmt_requests:
        service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": fmt_requests}
        ).execute()
    print("Formatting fixed.")

    # ===== Step 3: テーブルセルを埋める =====
    print("Step 3: Filling table cells...")

    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    # 新セクション内の全テーブルを取得
    tables = []
    for element in body:
        si = element.get("startIndex", 0)
        if si >= section_break_idx:
            break
        if "table" in element:
            tables.append(element)

    print(f"  Found {len(tables)} tables")

    def get_cell_index(table_element, row, col):
        cell = table_element["table"]["tableRows"][row]["tableCells"][col]
        return cell["content"][0]["paragraph"]["elements"][0]["startIndex"]

    all_cell_requests = []

    if len(tables) >= 1:
        t = tables[0]
        cells = [
            (0, 0, "3月の目標"),
            (0, 1, "①着金売上：4億円（1億円/週）\n②集客数：4万人（1万人/週）"),
            (1, 0, "3月の進捗状況\n(3/1〜3/4)"),
            (1, 1, "集客数: 3,347（+13.5%）  個別予約数: 191（+41.5%）\n"
                    "着金売上: ¥6,799,654（-82.7%）  ROAS: 56%（-86.9%）\n"
                    "広告費: ¥12,039,542  CPA: ¥3,597\n"
                    "個別予約CPO: ¥63,034  粗利: ¥-5,239,888\n\n"
                    "[ここに月次KPIスクショを貼付]\n\n"
                    "目標に対して、着金売上・ROAS共に大幅未達。月初のため着金ラグの影響あり。"),
            (2, 0, "過去12週間推移"),
            (2, 1, "集客数は直近2週で回復傾向。個別予約数は1月後半のピークから減少トレンド。\n"
                    "CPAは3,000〜4,000円台で安定推移。\n\n"
                    "[ここに過去12週グラフスクショを貼付]"),
            (3, 0, "3月着地予想"),
            (3, 1, "粗利：¥-40,608,832（赤字見込み）\n"
                    "着金売上：¥52,697,319（約5,270万円）\n"
                    "集客数：25,939人\n"
                    "※月初4日の日割り計算。着金ラグにより上振れの可能性あり。"),
        ]
        for row, col, text in cells:
            all_cell_requests.append({
                "insertText": {
                    "location": {"index": get_cell_index(t, row, col)},
                    "text": text,
                }
            })

    if len(tables) >= 2:
        t = tables[1]
        cells = [
            (0, 0, "集客数"), (0, 1, "個別予約数"),
            (0, 2, "着金売上"), (0, 3, "ROAS"),
            (1, 0, "6,296\n+21.9%"), (1, 1, "326\n-21.8%"),
            (1, 2, "¥46,012,462\n+4.8%"), (1, 3, "218%\n-11.7%"),
            (2, 0, "広告費\n¥21,144,193"), (2, 1, "CPA\n¥3,358"),
            (2, 2, "個別予約CPO\n¥64,859"), (2, 3, "粗利\n¥24,868,269"),
        ]
        for row, col, text in cells:
            all_cell_requests.append({
                "insertText": {
                    "location": {"index": get_cell_index(t, row, col)},
                    "text": text,
                }
            })

    if len(tables) >= 3:
        t = tables[2]
        cells = [
            (0, 0, "主なプロジェクト"), (0, 1, "評価"), (0, 2, "詳細情報"),
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
        for row, col, text in cells:
            all_cell_requests.append({
                "insertText": {
                    "location": {"index": get_cell_index(t, row, col)},
                    "text": text,
                }
            })

    if len(tables) >= 4:
        t = tables[3]
        cells = [
            (0, 0, "ボトルネック"), (0, 1, "改善アクション"),
            (1, 0, "着金売上が目標ペースの約1/15\nROAS 56%で基準300%を大幅下回る"),
            (1, 1, "甲原さんに確認：\n具体的なアクションを追記してください"),
        ]
        for row, col, text in cells:
            all_cell_requests.append({
                "insertText": {
                    "location": {"index": get_cell_index(t, row, col)},
                    "text": text,
                }
            })

    # 後ろから挿入
    all_cell_requests.sort(
        key=lambda r: r["insertText"]["location"]["index"], reverse=True
    )

    if all_cell_requests:
        service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": all_cell_requests}
        ).execute()
        print(f"  Filled {len(all_cell_requests)} cells.")

    # ===== Step 4: テーブル内ヘッダー行を太字に =====
    print("Step 4: Bold table headers...")
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    tables = []
    for element in body:
        si = element.get("startIndex", 0)
        if si >= section_break_idx:
            break
        if "table" in element:
            tables.append(element)

    bold_requests = []
    for t in tables:
        first_row = t["table"]["tableRows"][0]
        for cell in first_row["tableCells"]:
            for content in cell["content"]:
                if "paragraph" in content:
                    s = content["startIndex"]
                    e = content["endIndex"]
                    bold_requests.append({
                        "updateTextStyle": {
                            "range": {"startIndex": s, "endIndex": e},
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    })
        # 月目標テーブルの左列も太字に
        if t == tables[0]:
            for row in t["table"]["tableRows"]:
                cell = row["tableCells"][0]
                for content in cell["content"]:
                    if "paragraph" in content:
                        s = content["startIndex"]
                        e = content["endIndex"]
                        bold_requests.append({
                            "updateTextStyle": {
                                "range": {"startIndex": s, "endIndex": e},
                                "textStyle": {"bold": True},
                                "fields": "bold",
                            }
                        })

    if bold_requests:
        service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": bold_requests}
        ).execute()

    print("Done! Report formatted and tables filled.")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    fix_report()
