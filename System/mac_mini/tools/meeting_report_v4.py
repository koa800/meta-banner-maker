"""経営会議資料 v4: 端的・視覚的・1秒で伝わる（修正版）

v3からの変更点:
- 過去7日間KPIを「3月目標と現状」テーブル内に統合（参考元準拠）
- 過去7日間の独立テーブル廃止（スクショが主役、数値テキスト不要）
- テーブルヘッダーを中央揃え
- プロジェクト進捗の色を控えめなパステル調に（主張しすぎない）
"""

from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

CREDENTIALS_DIR = Path(__file__).resolve().parent.parent.parent / "credentials"
TOKEN_PATH = CREDENTIALS_DIR / "token.json"
DOC_ID = "18D5fgk5G2xjgmpM7fORQuwcnD6oemZrNzPeDWNozO7s"


def get_service():
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), [
        "https://www.googleapis.com/auth/documents",
    ])
    return build("docs", "v1", credentials=creds)


def delete_current_section():
    """既存セクションを削除（テーブル個別削除→テキスト削除）"""
    service = get_service()

    for _ in range(10):
        doc = service.documents().get(documentId=DOC_ID).execute()
        body = doc["body"]["content"]

        sb_start = None
        for el in body:
            if "sectionBreak" in el and el.get("startIndex", 0) > 1:
                sb_start = el["startIndex"]
                break
        if sb_start is None:
            print("No section break found")
            return

        last_table = None
        for el in body:
            if el.get("startIndex", 0) >= sb_start:
                break
            if "table" in el:
                last_table = el

        if last_table is None:
            break

        ts, te = last_table["startIndex"], last_table["endIndex"]
        print(f"  Deleting table {ts}-{te}")
        service.documents().batchUpdate(
            documentId=DOC_ID,
            body={"requests": [{"deleteContentRange": {"range": {"startIndex": ts, "endIndex": te}}}]}
        ).execute()

    # 残りテキスト削除
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]
    sb_start = None
    for el in body:
        if "sectionBreak" in el and el.get("startIndex", 0) > 1:
            sb_start = el["startIndex"]
            break

    if sb_start and sb_start > 2:
        end = sb_start - 1
        print(f"  Deleting text 1-{end}")
        service.documents().batchUpdate(
            documentId=DOC_ID,
            body={"requests": [{"deleteContentRange": {"range": {"startIndex": 1, "endIndex": end}}}]}
        ).execute()
    print("Section deleted.")


def create_report():
    """資料を作成"""
    service = get_service()

    # ===== STEP 1: テキスト挿入 =====
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
    fmt = []

    # タイトル: 太字+下線+20pt+中央
    title = "2026/3/6　アドネス経営会議"
    pos = full_text.find(title)
    s, e = 1 + pos, 1 + pos + len(title)
    fmt.extend([
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

    # セクション見出し: 太字+14pt
    for header in ["【総評】", "＜NEWS！＞", "【3月目標と現状】",
                    "【プロジェクト進捗】",
                    "【ボトルネックと改善アクション】", "【その他・共有事項】"]:
        pos = full_text.find(header)
        if pos >= 0:
            s, e = 1 + pos, 1 + pos + len(header)
            fmt.append({"updateTextStyle": {
                "range": {"startIndex": s, "endIndex": e},
                "textStyle": {"bold": True, "fontSize": {"magnitude": 14, "unit": "PT"}},
                "fields": "bold,fontSize",
            }})

    # 評価 "2/5" 太字+13pt
    pos = full_text.find("2/5")
    if pos >= 0:
        s, e = 1 + pos, 1 + pos + 3
        fmt.append({"updateTextStyle": {
            "range": {"startIndex": s, "endIndex": e},
            "textStyle": {"bold": True, "fontSize": {"magnitude": 13, "unit": "PT"}},
            "fields": "bold,fontSize",
        }})

    service.documents().batchUpdate(documentId=DOC_ID, body={"requests": fmt}).execute()

    # ===== STEP 3: テーブル挿入 =====
    print("Step 3: Inserting tables...")
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]

    def find_section_end():
        for el in body:
            if "sectionBreak" in el and el.get("startIndex", 0) > 1:
                return el["startIndex"]
        return 99999

    def find_next_para_index(search_text):
        se = find_section_end()
        for i, el in enumerate(body):
            if el.get("startIndex", 0) >= se:
                break
            if "paragraph" in el:
                for e in el["paragraph"]["elements"]:
                    if "textRun" in e and search_text in e["textRun"]["content"]:
                        if i + 1 < len(body):
                            return body[i + 1]["startIndex"]
        return None

    # テーブル定義（後ろから挿入）
    table_defs = [
        ("project", "【プロジェクト進捗】", 4, 3),
        ("monthly", "【3月目標と現状】", 5, 2),  # 5行: 目標/月次進捗/12週/7日間/着地予想
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

    se = find_section_end()
    tables = []
    for el in body:
        if el.get("startIndex", 0) >= se:
            break
        if "table" in el:
            tables.append(el)

    print(f"  Found {len(tables)} tables")

    def cell_idx(t, r, c):
        return t["table"]["tableRows"][r]["tableCells"][c]["content"][0]["paragraph"]["elements"][0]["startIndex"]

    all_reqs = []

    if len(tables) >= 1:
        # 月目標テーブル: 5行×2列（目標/月次進捗/12週/7日間/着地予想）
        t = tables[0]
        cells = [
            (0, 0, "3月の目標"),
            (0, 1, "①着金売上：4億円（1億/週）\n②集客数：4万人（1万/週）"),
            (1, 0, "3月の進捗\n(3/1〜3/4)"),
            (1, 1, "[月次KPIスクショ]\n\n目標に対して、着金売上△ ROAS△"),
            (2, 0, "過去12週推移"),
            (2, 1, "[12週グラフスクショ]\n\n集客数は回復傾向。予約数は減少トレンド。"),
            (3, 0, "過去7日間\n(2/27〜3/5)"),
            (3, 1, "[7日間KPIスクショ]\n\n集客数+21.9%。着金売上+4.8%。"),
            (4, 0, "3月着地予想"),
            (4, 1, "着金売上：約5,270万円\n集客数：約25,900人\n※月初4日の日割り。着金ラグで上振れ余地あり"),
        ]
        for r, c, text in cells:
            all_reqs.append({"insertText": {
                "location": {"index": cell_idx(t, r, c)}, "text": text}})

    if len(tables) >= 2:
        # プロジェクト進捗テーブル: 4行×3列
        t = tables[1]
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

    all_reqs.sort(key=lambda r: r["insertText"]["location"]["index"], reverse=True)
    if all_reqs:
        service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": all_reqs}
        ).execute()

    # ===== STEP 5: ボトルネック箇条書き =====
    print("Step 5: Adding bottleneck...")
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]
    se = find_section_end()

    bn_idx = None
    for i, el in enumerate(body):
        if el.get("startIndex", 0) >= se:
            break
        if "paragraph" in el:
            for e in el["paragraph"]["elements"]:
                if "textRun" in e and "【ボトルネックと改善アクション】" in e["textRun"]["content"]:
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
            body={"requests": [{"insertText": {"location": {"index": bn_idx}, "text": bn_text}}]}
        ).execute()

    # ===== STEP 6: テーブルスタイル =====
    print("Step 6: Styling tables...")
    doc = service.documents().get(documentId=DOC_ID).execute()
    body = doc["body"]["content"]
    se = find_section_end()

    tables = []
    for el in body:
        if el.get("startIndex", 0) >= se:
            break
        if "table" in el:
            tables.append(el)

    style_reqs = []

    for t_idx, t in enumerate(tables):
        # ヘッダー行: 太字 + 中央揃え
        first_row = t["table"]["tableRows"][0]
        for cell in first_row["tableCells"]:
            for content in cell["content"]:
                if "paragraph" in content:
                    s, e = content["startIndex"], content["endIndex"]
                    style_reqs.append({"updateTextStyle": {
                        "range": {"startIndex": s, "endIndex": e},
                        "textStyle": {"bold": True},
                        "fields": "bold",
                    }})
                    style_reqs.append({"updateParagraphStyle": {
                        "range": {"startIndex": s, "endIndex": e},
                        "paragraphStyle": {"alignment": "CENTER"},
                        "fields": "alignment",
                    }})

        # 月目標テーブル: 左列太字
        if t_idx == 0:
            for row in t["table"]["tableRows"]:
                cell = row["tableCells"][0]
                for content in cell["content"]:
                    if "paragraph" in content:
                        s, e = content["startIndex"], content["endIndex"]
                        style_reqs.append({"updateTextStyle": {
                            "range": {"startIndex": s, "endIndex": e},
                            "textStyle": {"bold": True},
                            "fields": "bold",
                        }})

        # プロジェクトテーブル: 評価列の控えめな色分け
        if t_idx == 1:
            # パステル調の控えめな色（背景が薄く、テキストは黒のまま）
            color_map = {
                "悪い": {"red": 0.96, "green": 0.80, "blue": 0.80},         # 薄い赤
                "やや悪い": {"red": 0.98, "green": 0.88, "blue": 0.75},     # 薄いオレンジ
                "やや良い": {"red": 0.85, "green": 0.94, "blue": 0.80},     # 薄い黄緑
                "良い": {"red": 0.78, "green": 0.92, "blue": 0.78},         # 薄い緑
            }
            for row_idx, row in enumerate(t["table"]["tableRows"]):
                if row_idx == 0:
                    continue
                eval_cell = row["tableCells"][1]
                eval_text = ""
                for content in eval_cell["content"]:
                    if "paragraph" in content:
                        for el in content["paragraph"]["elements"]:
                            if "textRun" in el:
                                eval_text += el["textRun"]["content"].strip()

                color = color_map.get(eval_text)
                if color:
                    style_reqs.append({"updateTableCellStyle": {
                        "tableRange": {
                            "tableCellLocation": {
                                "tableStartLocation": {"index": t["startIndex"]},
                                "rowIndex": row_idx,
                                "columnIndex": 1,
                            },
                            "rowSpan": 1, "columnSpan": 1,
                        },
                        "tableCellStyle": {"backgroundColor": {"color": {"rgbColor": color}}},
                        "fields": "backgroundColor",
                    }})

                # 評価テキストを中央揃え
                for content in eval_cell["content"]:
                    if "paragraph" in content:
                        s, e = content["startIndex"], content["endIndex"]
                        style_reqs.append({"updateParagraphStyle": {
                            "range": {"startIndex": s, "endIndex": e},
                            "paragraphStyle": {"alignment": "CENTER"},
                            "fields": "alignment",
                        }})

    if style_reqs:
        service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": style_reqs}
        ).execute()

    print("Done!")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    print("=== Deleting old section ===")
    delete_current_section()
    print("\n=== Creating report ===")
    create_report()
