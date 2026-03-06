"""経営会議資料 v3: 端的・視覚的・1秒で伝わる"""

from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CREDENTIALS_DIR = Path(__file__).resolve().parent.parent.parent / "credentials"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"
DOC_ID = "18D5fgk5G2xjgmpM7fORQuwcnD6oemZrNzPeDWNozO7s"


def get_service(api, version):
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ])
    return build(api, version, credentials=creds)


def delete_current_section():
    """3/6の既存セクションを削除（テーブルを個別に後ろから削除→残りテキスト削除）"""
    service = get_service("docs", "v1")

    # 繰り返しテーブルを削除（1つずつ後ろから）
    for attempt in range(10):  # 安全弁
        doc = service.documents().get(documentId=DOC_ID).execute()
        body = doc["body"]["content"]

        # セクション区切り位置
        sb_start = None
        for element in body:
            if "sectionBreak" in element and element.get("startIndex", 0) > 1:
                sb_start = element["startIndex"]
                break

        if sb_start is None:
            print("No section break found, nothing to delete")
            return

        # セクション内の最後のテーブルを探す
        last_table = None
        for element in body:
            si = element.get("startIndex", 0)
            if si >= sb_start:
                break
            if "table" in element:
                last_table = element

        if last_table is None:
            break  # テーブルなし → テキスト削除へ

        # テーブル削除
        ts = last_table["startIndex"]
        te = last_table["endIndex"]
        print(f"  Deleting table at {ts}-{te}")
        service.documents().batchUpdate(
            documentId=DOC_ID,
            body={"requests": [{
                "deleteContentRange": {
                    "range": {"startIndex": ts, "endIndex": te}
                }
            }]}
        ).execute()

    # テーブル削除後、残りのテキストを削除
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    sb_start = None
    for element in body:
        if "sectionBreak" in element and element.get("startIndex", 0) > 1:
            sb_start = element["startIndex"]
            break

    if sb_start and sb_start > 2:
        # セクション区切り直前の改行は消せないので sb_start - 1 まで
        end = sb_start - 1 if sb_start > 2 else sb_start
        print(f"Deleting text from 1 to {end}")
        service.documents().batchUpdate(
            documentId=DOC_ID,
            body={"requests": [{
                "deleteContentRange": {
                    "range": {"startIndex": 1, "endIndex": end}
                }
            }]}
        ).execute()
        print("Section deleted.")
    else:
        print("No text to delete")


def create_clean_report():
    """クリーンな資料を作成"""
    service = get_service("docs", "v1")

    # ===== STEP 1: テキスト挿入 =====
    # 端的に。スクショが語る部分は文字にしない。
    full_text = (
        "2026/3/6　アドネス経営会議\n"
        "\n"
        "【総評】\n"
        "3/4\n"
        "2/5\n"
        "└着金売上・ROAS共に目標未達。集客の勢いは回復傾向。\n"
        "\n"
        "＜NEWS！＞\n"
        "☑（今週のニュースを追記）\n"
        "\n"
        "【3月目標と現状】\n"
        "\n"  # テーブル挿入位置
        "\n"
        "過去7日間推移（2/27〜3/5）\n"
        "\n"  # テーブル挿入位置
        "\n"
        "【プロジェクト進捗】\n"
        "\n"  # テーブル挿入位置
        "\n"
        "【ボトルネックと改善アクション】\n"
        "\n"
        "【その他・共有事項】\n"
        "・\n"
    )

    requests = [
        {"insertText": {"location": {"index": 1}, "text": full_text}},
    ]

    # セクション区切り
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

    # ===== STEP 2: フォーマット =====
    print("Step 2: Formatting...")
    fmt_requests = []

    # タイトル
    title = "2026/3/6　アドネス経営会議"
    pos = full_text.find(title)
    s, e = 1 + pos, 1 + pos + len(title)
    fmt_requests.extend([
        {"updateTextStyle": {
            "range": {"startIndex": s, "endIndex": e},
            "textStyle": {"bold": True, "underline": True,
                          "fontSize": {"magnitude": 20, "unit": "PT"}},
            "fields": "bold,underline,fontSize",
        }},
        {"updateParagraphStyle": {
            "range": {"startIndex": s, "endIndex": e + 1},
            "paragraphStyle": {"alignment": "CENTER"},
            "fields": "alignment",
        }},
    ])

    # セクション見出し: 太字 + 14pt
    for header in ["【総評】", "＜NEWS！＞", "【3月目標と現状】",
                    "過去7日間推移（2/27〜3/5）", "【プロジェクト進捗】",
                    "【ボトルネックと改善アクション】", "【その他・共有事項】"]:
        pos = full_text.find(header)
        if pos >= 0:
            s, e = 1 + pos, 1 + pos + len(header)
            fmt_requests.append({
                "updateTextStyle": {
                    "range": {"startIndex": s, "endIndex": e},
                    "textStyle": {"bold": True,
                                  "fontSize": {"magnitude": 14, "unit": "PT"}},
                    "fields": "bold,fontSize",
                }
            })

    # 評価 "2/5" を太字
    pos = full_text.find("2/5")
    if pos >= 0:
        s, e = 1 + pos, 1 + pos + 3
        fmt_requests.append({
            "updateTextStyle": {
                "range": {"startIndex": s, "endIndex": e},
                "textStyle": {"bold": True,
                              "fontSize": {"magnitude": 13, "unit": "PT"}},
                "fields": "bold,fontSize",
            }
        })

    service.documents().batchUpdate(
        documentId=DOC_ID, body={"requests": fmt_requests}
    ).execute()

    # ===== STEP 3: テーブル挿入 =====
    print("Step 3: Inserting tables...")
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    section_end = None
    for element in body:
        if "sectionBreak" in element and element.get("startIndex", 0) > 1:
            section_end = element["startIndex"]
            break

    def find_next_para_index(search_text):
        for i, element in enumerate(body):
            if element.get("startIndex", 0) >= (section_end or 99999):
                break
            if "paragraph" in element:
                for el in element["paragraph"]["elements"]:
                    if "textRun" in el and search_text in el["textRun"]["content"]:
                        if i + 1 < len(body):
                            return body[i + 1]["startIndex"]
        return None

    # テーブル挿入（後ろから）
    table_defs = [
        # (name, search_text, rows, cols)
        ("project", "【プロジェクト進捗】", 4, 3),
        ("weekly", "過去7日間推移", 3, 4),
        ("monthly", "【3月目標と現状】", 4, 2),
    ]

    insertions = []
    for name, search, rows, cols in table_defs:
        idx = find_next_para_index(search)
        if idx:
            insertions.append((name, idx, rows, cols))

    insertions.sort(key=lambda x: x[1], reverse=True)
    for name, idx, rows, cols in insertions:
        print(f"  Table '{name}' at {idx} ({rows}x{cols})")
        service.documents().batchUpdate(
            documentId=DOC_ID,
            body={"requests": [{"insertTable": {
                "rows": rows, "columns": cols,
                "location": {"index": idx},
            }}]}
        ).execute()

    # ===== STEP 4: テーブルセル内容 =====
    print("Step 4: Filling cells...")
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    # section_end を再計算（テーブル挿入でインデックスがずれるため）
    section_end = None
    for element in body:
        if "sectionBreak" in element and element.get("startIndex", 0) > 1:
            section_end = element["startIndex"]
            break

    tables = []
    for element in body:
        if element.get("startIndex", 0) >= (section_end or 99999):
            break
        if "table" in element:
            tables.append(element)

    print(f"  Found {len(tables)} tables")

    def cell_idx(t, r, c):
        return t["table"]["tableRows"][r]["tableCells"][c]["content"][0]["paragraph"]["elements"][0]["startIndex"]

    all_reqs = []

    if len(tables) >= 1:
        # 月目標テーブル: 端的に。スクショが主役
        t = tables[0]
        cells = [
            (0, 0, "3月の目標"),
            (0, 1, "①着金売上：4億円（1億/週）\n②集客数：4万人（1万/週）"),
            (1, 0, "3月の進捗\n(3/1〜3/4)"),
            (1, 1, "[月次KPIスクショ]\n\n目標に対して、着金売上△ ROAS△"),
            (2, 0, "過去12週推移"),
            (2, 1, "[12週グラフスクショ]\n\n集客数は回復傾向。予約数は減少トレンド。"),
            (3, 0, "3月着地予想"),
            (3, 1, "着金売上：約5,270万円\n集客数：約25,900人\n※月初4日の日割り。着金ラグで上振れ余地あり"),
        ]
        for r, c, text in cells:
            all_reqs.append({"insertText": {
                "location": {"index": cell_idx(t, r, c)}, "text": text}})

    if len(tables) >= 2:
        # 週次KPIテーブル
        t = tables[1]
        cells = [
            (0, 0, "集客数"), (0, 1, "個別予約数"),
            (0, 2, "着金売上"), (0, 3, "ROAS"),
            (1, 0, "6,296\n+21.9%"), (1, 1, "326\n-21.8%"),
            (1, 2, "¥46,012,462\n+4.8%"), (1, 3, "218%\n-11.7%"),
            (2, 0, "広告費\n¥21,144,193"), (2, 1, "CPA\n¥3,358"),
            (2, 2, "個別予約CPO\n¥64,859"), (2, 3, "粗利\n¥24,868,269"),
        ]
        for r, c, text in cells:
            all_reqs.append({"insertText": {
                "location": {"index": cell_idx(t, r, c)}, "text": text}})

    if len(tables) >= 3:
        # プロジェクト進捗テーブル
        t = tables[2]
        cells = [
            (0, 0, "主なプロジェクト"), (0, 1, "評価"), (0, 2, "詳細情報"),
            (1, 0, "①Web広告から集客数4万人"),
            (1, 1, "やや良い"),
            (1, 2, "集客数回復傾向。CPA改善中。"),
            (2, 0, "②サブスク導線ROAS100%"),
            (2, 1, "悪い"),
            (2, 2, "ROAS基準未達。着金改善が急務。"),
            (3, 0, "③UGC口コミ発生"),
            (3, 1, "（確認）"),
            (3, 2, "甲原さんに確認"),
        ]
        for r, c, text in cells:
            all_reqs.append({"insertText": {
                "location": {"index": cell_idx(t, r, c)}, "text": text}})

    # 後ろから挿入
    all_reqs.sort(key=lambda r: r["insertText"]["location"]["index"], reverse=True)
    if all_reqs:
        service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": all_reqs}
        ).execute()

    # ===== STEP 5: ボトルネックを箇条書きで挿入 =====
    print("Step 5: Adding bottleneck bullets...")
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    # section_end を再計算
    section_end = None
    for element in body:
        if "sectionBreak" in element and element.get("startIndex", 0) > 1:
            section_end = element["startIndex"]
            break

    # 「【ボトルネックと改善アクション】」の次の段落に挿入
    bn_idx = None
    for i, element in enumerate(body):
        if element.get("startIndex", 0) >= (section_end or 99999):
            break
        if "paragraph" in element:
            for el in element["paragraph"]["elements"]:
                if "textRun" in el and "【ボトルネックと改善アクション】" in el["textRun"]["content"]:
                    if i + 1 < len(body):
                        bn_idx = body[i + 1]["startIndex"]
                    break

    if bn_idx:
        bn_text = (
            "ボトルネック：着金売上が目標の1/15。ROAS 56%で基準300%を大幅下回る\n"
            "→ アクション：（甲原さんに確認：具体的なアクションを追記）\n"
        )
        service.documents().batchUpdate(
            documentId=DOC_ID,
            body={"requests": [
                {"insertText": {"location": {"index": bn_idx}, "text": bn_text}}
            ]}
        ).execute()

    # ===== STEP 6: テーブルヘッダー太字 + 左列太字 + 色分け =====
    print("Step 6: Styling tables...")
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    # テーブル再取得
    section_end_updated = None
    for element in body:
        if "sectionBreak" in element and element.get("startIndex", 0) > 1:
            section_end_updated = element["startIndex"]
            break

    tables = []
    for element in body:
        if element.get("startIndex", 0) >= (section_end_updated or 99999):
            break
        if "table" in element:
            tables.append(element)

    style_reqs = []

    for t_idx, t in enumerate(tables):
        # ヘッダー行を太字
        first_row = t["table"]["tableRows"][0]
        for cell in first_row["tableCells"]:
            for content in cell["content"]:
                if "paragraph" in content:
                    s, e = content["startIndex"], content["endIndex"]
                    style_reqs.append({
                        "updateTextStyle": {
                            "range": {"startIndex": s, "endIndex": e},
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }
                    })

        # 月目標テーブル: 左列太字
        if t_idx == 0:
            for row in t["table"]["tableRows"]:
                cell = row["tableCells"][0]
                for content in cell["content"]:
                    if "paragraph" in content:
                        s, e = content["startIndex"], content["endIndex"]
                        style_reqs.append({
                            "updateTextStyle": {
                                "range": {"startIndex": s, "endIndex": e},
                                "textStyle": {"bold": True},
                                "fields": "bold",
                            }
                        })

        # プロジェクトテーブル: 評価列の色分け
        if t_idx == 2:
            color_map = {
                "悪い": {"red": 0.92, "green": 0.35, "blue": 0.35},      # 赤
                "やや悪い": {"red": 0.95, "green": 0.65, "blue": 0.3},   # オレンジ
                "やや良い": {"red": 0.55, "green": 0.82, "blue": 0.35},  # 黄緑
                "良い": {"red": 0.3, "green": 0.75, "blue": 0.3},        # 緑
            }
            for row_idx, row in enumerate(t["table"]["tableRows"]):
                if row_idx == 0:
                    continue  # ヘッダースキップ
                eval_cell = row["tableCells"][1]
                eval_text = ""
                for content in eval_cell["content"]:
                    if "paragraph" in content:
                        for el in content["paragraph"]["elements"]:
                            if "textRun" in el:
                                eval_text += el["textRun"]["content"].strip()

                color = color_map.get(eval_text)
                if color:
                    # セル背景色
                    style_reqs.append({
                        "updateTableCellStyle": {
                            "tableRange": {
                                "tableCellLocation": {
                                    "tableStartLocation": {"index": t["startIndex"]},
                                    "rowIndex": row_idx,
                                    "columnIndex": 1,
                                },
                                "rowSpan": 1,
                                "columnSpan": 1,
                            },
                            "tableCellStyle": {
                                "backgroundColor": {"color": {"rgbColor": color}},
                            },
                            "fields": "backgroundColor",
                        }
                    })
                    # テキスト白
                    for content in eval_cell["content"]:
                        if "paragraph" in content:
                            s, e = content["startIndex"], content["endIndex"]
                            style_reqs.append({
                                "updateTextStyle": {
                                    "range": {"startIndex": s, "endIndex": e},
                                    "textStyle": {
                                        "bold": True,
                                        "foregroundColor": {"color": {"rgbColor": {
                                            "red": 1, "green": 1, "blue": 1
                                        }}},
                                    },
                                    "fields": "bold,foregroundColor",
                                }
                            })

    if style_reqs:
        service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": style_reqs}
        ).execute()

    print("Done!")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    print("=== Deleting old section ===")
    delete_current_section()
    print("\n=== Creating clean report ===")
    create_clean_report()
