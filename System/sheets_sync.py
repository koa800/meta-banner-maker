"""
管理シート同期スクリプト（Master/sheets/ のデータを最新化する）

README.md の登録シート一覧からIDを読み取り、各シートのスナップショットを
ローカルにCSVキャッシュとして保存する。毎日1回 Orchestrator から呼び出す。

Usage:
    python3 System/sheets_sync.py              # 全シート同期
    python3 System/sheets_sync.py --dry-run    # 書き込みなしで確認
    python3 System/sheets_sync.py --id SHEET_ID  # 特定シートのみ
"""

import csv
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SHEETS_DIR = PROJECT_ROOT / "Master" / "sheets"
README_PATH = SHEETS_DIR / "README.md"

sys.path.insert(0, str(PROJECT_ROOT / "System"))
from sheets_manager import get_client, extract_spreadsheet_id


def parse_registered_sheets() -> list[dict]:
    """README.md の登録シート一覧テーブルからシートIDと名前を抽出"""
    if not README_PATH.exists():
        return []

    content = README_PATH.read_text(encoding="utf-8")
    sheets = []
    for line in content.splitlines():
        m = re.match(r"\|\s*`([A-Za-z0-9_-]+)`\s*\|(.+)", line)
        if m:
            sheet_id = m.group(1)
            rest = m.group(2).split("|")
            name = rest[0].strip() if len(rest) > 0 else ""
            sheets.append({"id": sheet_id, "name": name})
    return sheets


def sync_sheet(client, sheet_id: str, sheet_dir: Path, dry_run: bool = False) -> dict:
    """1つのスプレッドシートを同期し、メタ情報dictを返す"""
    try:
        spreadsheet = client.open_by_key(sheet_id)
    except Exception as e:
        return {"id": sheet_id, "error": str(e), "synced": False}

    result = {
        "id": sheet_id,
        "title": spreadsheet.title,
        "synced": True,
        "synced_at": datetime.now().isoformat(),
        "tabs": [],
    }

    if not dry_run:
        sheet_dir.mkdir(parents=True, exist_ok=True)

    for ws in spreadsheet.worksheets():
        tab_info = {
            "title": ws.title,
            "rows": ws.row_count,
            "cols": ws.col_count,
            "cached_rows": 0,
        }

        if not dry_run:
            try:
                values = ws.get_all_values()
                tab_info["cached_rows"] = len(values)

                safe_name = re.sub(r'[\\/:*?"<>|]', "_", ws.title)
                csv_path = sheet_dir / f"{safe_name}.csv"
                with open(csv_path, "w", encoding="utf-8", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerows(values)
            except Exception as e:
                tab_info["error"] = str(e)

        result["tabs"].append(tab_info)

    if not dry_run:
        meta_path = sheet_dir / "_meta.json"
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

    return result


def update_readme_sync_status(results: list[dict]):
    """README.md の同期列を最新タイムスタンプで更新"""
    if not README_PATH.exists():
        return

    content = README_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()
    new_lines = []

    for line in lines:
        m = re.match(r"(\|\s*`([A-Za-z0-9_-]+)`\s*\|.+\|)\s*([^|]*)\s*\|$", line)
        if m:
            sheet_id = m.group(2)
            matched = next((r for r in results if r["id"] == sheet_id), None)
            if matched and matched.get("synced"):
                ts = datetime.fromisoformat(matched["synced_at"]).strftime("%m/%d %H:%M")
                total_rows = sum(t.get("cached_rows", 0) for t in matched.get("tabs", []))
                sync_text = f"✅ {ts} ({total_rows}行)"
            elif matched:
                sync_text = f"❌ {matched.get('error', 'error')[:30]}"
            else:
                sync_text = "-"
            prefix = m.group(1)
            new_lines.append(f"{prefix} {sync_text} |")
        else:
            new_lines.append(line)

    README_PATH.write_text("\n".join(new_lines) + "\n", encoding="utf-8")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="管理シート同期")
    parser.add_argument("--dry-run", action="store_true", help="書き込みなしで確認")
    parser.add_argument("--id", type=str, help="特定シートIDのみ同期")
    args = parser.parse_args()

    sheets = parse_registered_sheets()
    if not sheets:
        print("登録シートが見つかりません")
        sys.exit(1)

    if args.id:
        sheets = [s for s in sheets if s["id"] == args.id]
        if not sheets:
            print(f"シートID {args.id} は登録されていません")
            sys.exit(1)

    print(f"同期対象: {len(sheets)}シート" + (" (dry-run)" if args.dry_run else ""))

    client = get_client()
    results = []

    for sheet in sheets:
        sheet_dir = SHEETS_DIR / sheet["id"]
        print(f"  同期中: {sheet['name']} ({sheet['id'][:12]}...)")
        result = sync_sheet(client, sheet["id"], sheet_dir, dry_run=args.dry_run)

        if result.get("synced"):
            tabs_summary = ", ".join(
                f"{t['title']}({t.get('cached_rows', '?')}行)"
                for t in result.get("tabs", [])
            )
            print(f"    ✅ {tabs_summary}")
        else:
            print(f"    ❌ {result.get('error', 'unknown error')}")

        results.append(result)

    if not args.dry_run:
        update_readme_sync_status(results)

    success_count = sum(1 for r in results if r.get("synced"))
    total = len(results)
    print(f"\n同期完了: {success_count}/{total}")

    if success_count < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
