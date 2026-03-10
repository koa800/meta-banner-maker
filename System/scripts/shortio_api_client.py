#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT_DIR = Path("/Users/koa800/Desktop/cursor")
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from System import sheets_manager

DEFAULT_CREDENTIAL_PATH = Path("/Users/koa800/Desktop/cursor/System/credentials/shortio_api_key.json")
DEFAULT_DOMAIN_ID = 1304048
DEFAULT_TZ_OFFSET = 540
DEFAULT_SHEET_ID = "1KfpZKwSoezfrwy5FQiU4-tPbfw9bin8ydnFKw2BQDKg"
DEFAULT_ADS_SHEET = "広告（統合）"
DEFAULT_MASTER_SHEET = "01_全体台帳"
MASTER_SHEET_HEADERS = [
    "ファネル名",
    "集客媒体",
    "設置場所",
    "リンクタイトル",
    "リンクURL",
    "遷移先名",
    "遷移先リンク",
    "更新日",
    "状態",
]
VISIBLE_SHEET_HEADERS = [
    "ファネル名",
    "設置場所",
    "リンクタイトル",
    "リンクURL",
    "遷移先名",
    "遷移先リンク",
    "更新日",
    "状態",
]
DEFAULT_MEDIA_TAB_ORDER = [
    "共通",
    "Meta広告",
    "TikTok広告",
    "YouTube広告",
    "𝕏広告",
    "LINE広告",
    "Yahoo広告",
    "リスティング広告",
    "アフィリエイト広告",
    "オフライン広告",
    "YouTube",
    "𝕏",
    "Instagram",
    "Threads",
    "TikTok",
    "Facebook",
    "ブランド検索",
    "一般検索",
    "広報",
    "オフライン",
    "note",
    "セミナー①導線",
    "一般記事",
]
DEFAULT_FUNNEL_PRIORITY = [
    "センサーズ",
    "AI",
    "アドプロ",
    "スキルプラス",
    "ライトプラン",
    "書籍",
]
MEDIA_NORMALIZATION_RULES = [
    ("Meta広告", "Meta広告"),
    ("TikTok広告", "TikTok広告"),
    ("TT広告", "TikTok広告"),
    ("YouTube広告", "YouTube広告"),
    ("YT広告", "YouTube広告"),
    ("LINE広告", "LINE広告"),
    ("リスティング広告", "リスティング広告"),
    ("アフィリエイト広告", "アフィリエイト広告"),
    ("Yahoo!ディスプレイ広告", "Yahoo広告"),
    ("Yahoo!広告", "Yahoo広告"),
    ("Yahoo広告", "Yahoo広告"),
    ("X広告", "𝕏広告"),
    ("𝕏広告", "𝕏広告"),
    ("スキルプラス公式𝕏アカウント", "𝕏"),
    ("【プレスキット】X", "𝕏"),
    ("【プレスリリース】X", "𝕏"),
    ("X(", "𝕏"),
    ("X", "𝕏"),
    ("Instagram", "Instagram"),
    ("Threads", "Threads"),
    ("TikTok", "TikTok"),
    ("Facebook", "Facebook"),
    ("YouTube", "YouTube"),
    ("𝕏", "𝕏"),
    ("ブランド検索", "ブランド検索"),
    ("一般検索", "一般検索"),
    ("一般記事", "一般検索"),
    ("note", "広報"),
    ("公式HP", "広報"),
    ("プレスリリース", "広報"),
    ("プレスキット", "広報"),
    ("問い合わせ", "広報"),
    ("広報", "広報"),
    ("オフラインDM", "オフライン"),
    ("オフライン広告", "オフライン広告"),
    ("オフライン", "オフライン"),
    ("共通", "その他"),
    ("セミナー", "その他"),
    ("スキルプラス@企画専用", "その他"),
    ("アクションマップ", "その他"),
    ("SNS（オーガニック）", "その他"),
    ("UGC施策", "その他"),
    ("書籍", "その他"),
    ("SEO", "一般検索"),
    ("その他", "その他"),
]
LEGACY_URL_SHEETS = [
    "はじめに",
    "広告（みかみ導線）",
    "広告（スキルプラス導線）",
    "広告（ライトプラン導線）",
    "広告（書籍） ",
    "SNS",
    "SEO",
    "広報",
    "その他",
    "広告（統合）",
]
MASTER_COLUMN_WIDTHS = [160, 150, 240, 280, 360, 220, 360, 100, 110]
VISIBLE_COLUMN_WIDTHS = [150, 240, 280, 360, 220, 360, 100, 110]
HEADER_BG = {"red": 0.357, "green": 0.584, "blue": 0.976}
HEADER_FG = {"red": 1, "green": 1, "blue": 1}
ALT_ROW_BG = {"red": 0.91, "green": 0.941, "blue": 0.996}


def load_api_key(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8"))
    api_key = data.get("api_key")
    if not api_key:
        raise SystemExit(f"api_key が見つかりません: {path}")
    return api_key


def request_json(url: str, api_key: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": api_key,
            "Accept": "application/json",
        },
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, context=ctx, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def print_json(data: dict) -> None:
    json.dump(data, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


def slug_from_short_url(short_url: str) -> str:
    parsed = urllib.parse.urlparse(short_url)
    return parsed.path.lstrip("/")


def domain_from_short_url(short_url: str) -> str:
    parsed = urllib.parse.urlparse(short_url)
    return parsed.netloc


def format_updated_date(iso_value: str) -> str:
    if not iso_value:
        return ""
    dt = datetime.fromisoformat(iso_value.replace("Z", "+00:00"))
    jst = timezone(timedelta(hours=9))
    return dt.astimezone(jst).strftime("%Y/%-m/%-d")


def list_links_page(
    domain_id: int,
    api_key: str,
    limit: int = 100,
    page_token: str = "",
) -> dict:
    params = {
        "domain_id": domain_id,
        "limit": limit,
    }
    if page_token:
        params["nextPageToken"] = page_token
    url = f"https://api.short.io/api/links?{urllib.parse.urlencode(params)}"
    return request_json(url, api_key)


def fetch_all_links(domain_id: int, api_key: str, page_limit: int = 100) -> list[dict]:
    links: list[dict] = []
    seen_ids: set[str] = set()
    page_token = ""
    while True:
        data = list_links_page(domain_id, api_key, limit=page_limit, page_token=page_token)
        chunk = data.get("links", [])
        if not chunk:
            break
        new_chunk = []
        for link in chunk:
            link_id = link.get("id") or link.get("idString")
            if link_id and link_id in seen_ids:
                continue
            if link_id:
                seen_ids.add(link_id)
            new_chunk.append(link)
        if not new_chunk:
            break
        links.extend(new_chunk)
        page_token = data.get("nextPageToken", "")
        if not page_token:
            break
    return links


def search_exact_link(domain_id: int, short_url: str, api_key: str) -> dict | None:
    slug = slug_from_short_url(short_url)
    params = {"limit": 10, "q": slug}
    url = (
        f"https://api.short.io/links/list/search/{domain_id}"
        f"?{urllib.parse.urlencode(params)}"
    )
    data = request_json(url, api_key)
    target = short_url.rstrip("/")
    for link in data.get("links", []):
        for candidate in (
            link.get("shortURL", ""),
            link.get("secureShortURL", ""),
        ):
            if candidate.rstrip("/") == target:
                return link
        if link.get("path") == slug:
            return link
    return None


def build_link_index(links: list[dict]) -> dict[str, dict]:
    index: dict[str, dict] = {}
    for link in links:
        for key in (link.get("shortURL", ""), link.get("secureShortURL", "")):
            if key:
                index[key.rstrip("/")] = link
        path = link.get("path")
        if path:
            index[path] = link
    return index


def expand_link(short_url: str, api_key: str) -> dict:
    domain = domain_from_short_url(short_url)
    path = slug_from_short_url(short_url)
    params = {
        "domain": domain,
        "path": path,
    }
    url = f"https://api.short.io/links/expand?{urllib.parse.urlencode(params)}"
    return request_json(url, api_key)


def cmd_folders(args: argparse.Namespace) -> None:
    api_key = load_api_key(Path(args.credentials))
    url = f"https://api.short.io/links/folders/{args.domain_id}"
    print_json(request_json(url, api_key))


def cmd_search(args: argparse.Namespace) -> None:
    api_key = load_api_key(Path(args.credentials))
    params = {
        "limit": args.limit,
        "q": args.query,
    }
    if args.folder_id:
        params["folderId"] = args.folder_id
    url = (
        f"https://api.short.io/links/list/search/{args.domain_id}"
        f"?{urllib.parse.urlencode(params)}"
    )
    print_json(request_json(url, api_key))


def cmd_link_stats(args: argparse.Namespace) -> None:
    api_key = load_api_key(Path(args.credentials))
    params = {
        "period": args.period,
        "tzOffset": args.tz_offset,
    }
    url = (
        f"https://statistics.short.io/statistics/link/{args.link_id}"
        f"?{urllib.parse.urlencode(params)}"
    )
    print_json(request_json(url, api_key))


def cmd_resolve(args: argparse.Namespace) -> None:
    api_key = load_api_key(Path(args.credentials))
    link = search_exact_link(args.domain_id, args.short_url, api_key)
    if not link:
        raise SystemExit(f"一致する short.io link が見つかりません: {args.short_url}")
    output = {
        "shortURL": link.get("shortURL"),
        "title": link.get("title"),
        "originalURL": link.get("originalURL"),
        "updatedAt": link.get("updatedAt"),
        "updatedDateJST": format_updated_date(link.get("updatedAt", "")),
        "folderId": link.get("FolderId"),
        "id": link.get("id"),
        "path": link.get("path"),
    }
    print_json(output)


def cmd_sync_ads_sheet(args: argparse.Namespace) -> None:
    api_key = load_api_key(Path(args.credentials))
    client = sheets_manager.get_client()
    ss = client.open_by_key(args.sheet_id)
    ws = ss.worksheet(args.sheet_name)
    values = ws.get_all_values()
    if not values:
        raise SystemExit("シートが空です")
    headers = values[0]
    header_index = {name: idx for idx, name in enumerate(headers)}
    required = ["URL", "遷移先", "更新日"]
    missing = [name for name in required if name not in header_index]
    if missing:
        raise SystemExit(f"必要な列がありません: {', '.join(missing)}")

    updates = []
    not_found = []
    checked = 0
    max_rows = args.limit_rows if args.limit_rows and args.limit_rows > 0 else None
    lookup_targets = []

    for row_num, row in enumerate(values[1:], start=2):
        if max_rows is not None and checked >= max_rows:
            break
        short_url = row[header_index["URL"]].strip() if len(row) > header_index["URL"] else ""
        if not short_url:
            continue
        checked += 1
        lookup_targets.append((row_num, short_url, row))

    results: dict[int, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        future_map = {
            executor.submit(expand_link, short_url, api_key): (row_num, short_url, row)
            for row_num, short_url, row in lookup_targets
        }
        for future in concurrent.futures.as_completed(future_map):
            row_num, short_url, row = future_map[future]
            try:
                link = future.result()
            except Exception:
                not_found.append({"row": row_num, "url": short_url})
                continue
            results[row_num] = {"link": link, "row": row, "url": short_url}

    for row_num, short_url, row in lookup_targets:
        item = results.get(row_num)
        if not item:
            continue
        link = item["link"]
        actual_dest = link.get("originalURL", "").strip()
        actual_updated = format_updated_date(link.get("updatedAt", ""))
        current_dest = row[header_index["遷移先"]].strip() if len(row) > header_index["遷移先"] else ""
        current_updated = row[header_index["更新日"]].strip() if len(row) > header_index["更新日"] else ""
        if actual_dest != current_dest or actual_updated != current_updated:
            updates.append(
                {
                    "row": row_num,
                    "url": short_url,
                    "before_dest": current_dest,
                    "after_dest": actual_dest,
                    "before_updated": current_updated,
                    "after_updated": actual_updated,
                }
            )

    result = {
        "sheet": args.sheet_name,
        "checked": checked,
        "updates": len(updates),
        "not_found": len(not_found),
        "write": args.write,
        "samples": updates[:5],
        "not_found_samples": not_found[:5],
    }

    if args.write and updates:
        batch_cells = []
        dest_col = header_index["遷移先"] + 1
        updated_col = header_index["更新日"] + 1
        for item in updates:
            batch_cells.append(
                {
                    "range": gspread_a1(item["row"], dest_col),
                    "values": [[item["after_dest"]]],
                }
            )
            batch_cells.append(
                {
                    "range": gspread_a1(item["row"], updated_col),
                    "values": [[item["after_updated"]]],
                }
            )
        ws.batch_update(batch_cells)

    print_json(result)


def gspread_a1(row: int, col: int) -> str:
    letters = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return f"{letters}{row}"


def ensure_worksheet(ss, title: str, rows: int = 100, cols: int = 20):
    try:
        return ss.worksheet(title)
    except Exception:
        return ss.add_worksheet(title=title, rows=rows, cols=cols)


def worksheet_id_map(ss) -> dict[str, int]:
    metadata = ss.fetch_sheet_metadata()
    result: dict[str, int] = {}
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        title = props.get("title")
        sheet_id = props.get("sheetId")
        if title is not None and sheet_id is not None:
            result[title] = sheet_id
    return result


def write_rows(ws, rows: list[list[str]]) -> None:
    row_count = max(len(rows) + 5, 100)
    col_count = max(max((len(row) for row in rows), default=1), len(MASTER_SHEET_HEADERS))
    if ws.row_count < row_count or ws.col_count < col_count:
        ws.resize(rows=max(ws.row_count, row_count), cols=max(ws.col_count, col_count))
    ws.clear()
    ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")


def apply_hyperlink_formulas(ws, rows: list[list[str]], url_columns: list[int]) -> None:
    if not rows:
        return
    updates = []
    last_row = len(rows) + 1
    for col_index in url_columns:
        col_values = []
        has_formula = False
        for row in rows:
            url = row[col_index].strip() if col_index < len(row) else ""
            if url.startswith("http"):
                safe_url = url.replace('"', '""')
                col_values.append([f'=HYPERLINK("{safe_url}","{safe_url}")'])
                has_formula = True
            else:
                col_values.append([url])
        if not has_formula:
            continue
        col_letter = gspread_a1(1, col_index + 1)[:-1]
        updates.append(
            {
                "range": f"{col_letter}2:{col_letter}{last_row}",
                "values": col_values,
            }
        )
    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")


def apply_sheet_format(ss, ws, headers: list[str], column_widths: list[int]) -> None:
    id_map = worksheet_id_map(ss)
    if ws.title not in id_map:
        return
    sheet_id = id_map[ws.title]
    metadata = ss.fetch_sheet_metadata()
    requests = []
    for sheet in metadata.get("sheets", []):
        props = sheet.get("properties", {})
        if props.get("sheetId") != sheet_id:
            continue
        for banded in sheet.get("bandedRanges", []):
            banded_id = banded.get("bandedRangeId")
            if banded_id is not None:
                requests.append({"deleteBanding": {"bandedRangeId": banded_id}})
        break
    requests.extend([
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(headers),
                },
                "cell": {
                    "userEnteredFormat": {
                        "backgroundColor": HEADER_BG,
                        "textFormat": {
                            "foregroundColor": HEADER_FG,
                            "bold": True,
                            "fontFamily": "Arial",
                            "fontSize": 10,
                        },
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "CLIP",
                    }
                },
                "fields": "userEnteredFormat(backgroundColor,textFormat,horizontalAlignment,verticalAlignment,wrapStrategy)",
            }
        },
        {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": ws.row_count,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(headers),
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "fontFamily": "Arial",
                            "fontSize": 10,
                            "bold": False,
                        },
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "CLIP",
                    }
                },
                "fields": "userEnteredFormat(textFormat,verticalAlignment,wrapStrategy)",
            }
        },
        {
            "setBasicFilter": {
                "filter": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": ws.row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(headers),
                    }
                }
            }
        },
        {
            "addBanding": {
                "bandedRange": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": ws.row_count,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(headers),
                    },
                    "rowProperties": {
                        "headerColor": HEADER_BG,
                        "firstBandColor": {"red": 1, "green": 1, "blue": 1},
                        "secondBandColor": ALT_ROW_BG,
                    },
                }
            }
        },
    ])
    for idx, width in enumerate(column_widths):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": idx,
                        "endIndex": idx + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )
    ss.batch_update({"requests": requests})


def current_sheet_order(ss) -> list[str]:
    metadata = ss.fetch_sheet_metadata()
    sheets = metadata.get("sheets", [])
    sheets.sort(key=lambda item: item.get("properties", {}).get("index", 0))
    return [item.get("properties", {}).get("title", "") for item in sheets]


def set_sheet_visibility_and_order(ss, master_sheet: str, visible_titles: list[str]) -> None:
    id_map = worksheet_id_map(ss)
    current_order = current_sheet_order(ss)
    ordered_visible_titles = [title for title in current_order if title in visible_titles]
    ordered_visible_titles.extend(title for title in visible_titles if title not in ordered_visible_titles)
    requests = []
    desired_titles = [master_sheet] + ordered_visible_titles
    seen = set()
    index = 0
    for title in desired_titles:
        if title not in id_map or title in seen:
            continue
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": id_map[title],
                        "index": index,
                        "hidden": title == master_sheet,
                    },
                    "fields": "index,hidden",
                }
            }
        )
        seen.add(title)
        index += 1

    for title, sheet_id in id_map.items():
        if title in seen:
            continue
        should_hide = title in LEGACY_URL_SHEETS or title == master_sheet or title == DEFAULT_ADS_SHEET
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "hidden": should_hide,
                    },
                    "fields": "hidden",
                }
            }
        )

    if requests:
        ss.batch_update({"requests": requests})


def delete_obsolete_sheets(ss, keep_titles: set[str]) -> list[str]:
    id_map = worksheet_id_map(ss)
    delete_targets = [title for title in id_map if title not in keep_titles]
    requests = [
        {"deleteSheet": {"sheetId": id_map[title]}}
        for title in delete_targets
    ]
    if requests:
        ss.batch_update({"requests": requests})
    return delete_targets


def normalize_media_name(media_value: str, link_title: str, funnel_name: str = "") -> str:
    if funnel_name.strip() == "共通導線":
        return "共通"
    candidates = []
    title_head = link_title.split("_", 1)[0].strip() if link_title else ""
    if title_head:
        candidates.append(title_head)
    cleaned_media = media_value.replace("\n", " ").strip()
    if cleaned_media:
        candidates.append(cleaned_media)

    for candidate in candidates:
        for pattern, normalized in MEDIA_NORMALIZATION_RULES:
            if pattern in candidate:
                return normalized

    return cleaned_media or title_head or "その他"


def normalize_master_rows(headers: list[str], rows: list[list[str]]) -> list[list[str]]:
    old_map = {name: idx for idx, name in enumerate(headers)}

    if headers[: len(MASTER_SHEET_HEADERS)] == MASTER_SHEET_HEADERS:
        result = []
        for row in rows:
            padded = row + [""] * (len(headers) - len(row))
            if padded[8].strip() == "未作成":
                continue
            funnel_name = padded[0].strip()
            media_name = normalize_media_name(padded[1].strip(), padded[3].strip(), funnel_name)
            padded[1] = media_name
            result.append(padded[: len(MASTER_SHEET_HEADERS)])
        return result

    legacy_required = [
        "集客媒体",
        "設置場所",
        "リンクタイトル",
        "更新日",
        "状態",
    ]
    missing = [name for name in legacy_required if name not in old_map]
    if missing:
        raise SystemExit(f"01_全体台帳 のヘッダーが想定と異なります: {', '.join(missing)}")

    funnel_key = "ファネル分類" if "ファネル分類" in old_map else "ファネル"
    url_key = "URL" if "URL" in old_map else "リンクURL"
    destination_key = "遷移先" if "遷移先" in old_map else "遷移先リンク"

    normalized = []
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        if padded[old_map["状態"]].strip() == "未作成":
            continue
        link_title = padded[old_map["リンクタイトル"]].strip()
        funnel_name = padded[old_map[funnel_key]].strip()
        media_name = normalize_media_name(
            padded[old_map["集客媒体"]].strip(),
            link_title,
            funnel_name,
        )
        normalized.append(
            [
                funnel_name,
                media_name,
                padded[old_map["設置場所"]].strip(),
                link_title,
                padded[old_map[url_key]].strip(),
                padded[old_map["遷移先名"]].strip(),
                padded[old_map[destination_key]].strip(),
                padded[old_map["更新日"]].strip(),
                padded[old_map["状態"]].strip(),
            ]
        )
    return normalized


def visible_row_sort_key(row: list[str]) -> tuple:
    priority_map = {name: idx for idx, name in enumerate(DEFAULT_FUNNEL_PRIORITY)}
    funnel_name = row[0].strip()
    return (
        priority_map.get(funnel_name, 999),
        funnel_name,
        row[1].strip(),
        row[2].strip(),
    )


def cmd_rebuild_sheet_views(args: argparse.Namespace) -> None:
    client = sheets_manager.get_client()
    ss = client.open_by_key(args.sheet_id)
    master_ws = ss.worksheet(args.master_sheet)
    values = master_ws.get_all_values()
    if not values:
        raise SystemExit("マスターシートが空です")

    headers = values[0]
    normalized_rows = normalize_master_rows(headers, values[1:])
    write_rows(master_ws, [MASTER_SHEET_HEADERS] + normalized_rows)

    media_idx = MASTER_SHEET_HEADERS.index("集客媒体")
    grouped: dict[str, list[list[str]]] = {}
    for row in normalized_rows:
        media_name = row[media_idx].strip()
        if not media_name:
            continue
        visible_row = [row[0], row[2], row[3], row[4], row[5], row[6], row[7], row[8]]
        grouped.setdefault(media_name, []).append(visible_row)

    ordered_titles = [title for title in DEFAULT_MEDIA_TAB_ORDER if title in grouped]
    ordered_titles.extend(sorted(title for title in grouped if title not in ordered_titles))

    created_or_updated = []
    for title in ordered_titles:
        grouped[title].sort(key=visible_row_sort_key)
        ws = ensure_worksheet(
            ss,
            title,
            rows=max(len(grouped[title]) + 10, 100),
            cols=len(VISIBLE_SHEET_HEADERS),
        )
        write_rows(ws, [VISIBLE_SHEET_HEADERS] + grouped[title])
        apply_hyperlink_formulas(ws, grouped[title], [3, 5])
        apply_sheet_format(ss, ws, VISIBLE_SHEET_HEADERS, VISIBLE_COLUMN_WIDTHS)
        created_or_updated.append({"title": title, "rows": len(grouped[title])})

    apply_sheet_format(ss, master_ws, MASTER_SHEET_HEADERS, MASTER_COLUMN_WIDTHS)
    apply_hyperlink_formulas(master_ws, normalized_rows, [4, 6])
    set_sheet_visibility_and_order(ss, args.master_sheet, ordered_titles)
    deleted_titles = []
    if args.delete_obsolete:
        keep_titles = {args.master_sheet, *ordered_titles}
        deleted_titles = delete_obsolete_sheets(ss, keep_titles)

    print_json(
        {
            "sheet_id": args.sheet_id,
            "master_sheet": args.master_sheet,
            "visible_media_tabs": ordered_titles,
            "updated_tabs": created_or_updated,
            "deleted_tabs": deleted_titles,
        }
    )


def cmd_audit_sheet(args: argparse.Namespace) -> None:
    client = sheets_manager.get_client()
    ss = client.open_by_key(args.sheet_id)
    ws = ss.worksheet(args.master_sheet)
    values = ws.get_all_values()
    if not values:
        raise SystemExit("マスターシートが空です")

    rows = normalize_master_rows(values[0], values[1:])
    suspicious_titles = []
    missing_urls = []
    missing_destinations = []

    for row_num, row in enumerate(rows, start=2):
        title = row[3].strip()
        link_url = row[4].strip()
        destination = row[6].strip()
        state = row[8].strip()
        if state != "未作成" and len(title) <= 1:
            suspicious_titles.append(
                {
                    "row": row_num,
                    "media": row[1],
                    "funnel": row[0],
                    "title": title,
                    "link_url": link_url,
                }
            )
        if state != "未作成" and not link_url:
            missing_urls.append(
                {
                    "row": row_num,
                    "media": row[1],
                    "funnel": row[0],
                    "title": title,
                    "state": state,
                }
            )
        if state == "正常" and not destination:
            missing_destinations.append(
                {
                    "row": row_num,
                    "media": row[1],
                    "funnel": row[0],
                    "title": title,
                }
            )

    print_json(
        {
            "sheet_id": args.sheet_id,
            "master_sheet": args.master_sheet,
            "counts": {
                "suspicious_titles": len(suspicious_titles),
                "missing_urls": len(missing_urls),
                "missing_destinations_in_normal_rows": len(missing_destinations),
            },
            "samples": {
                "suspicious_titles": suspicious_titles[:10],
                "missing_urls": missing_urls[:10],
                "missing_destinations_in_normal_rows": missing_destinations[:10],
            },
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="short.io の official API を叩く最小 client。Addness の current domain 1304048 を既定値で持つ。"
    )
    parser.add_argument(
        "--credentials",
        default=str(DEFAULT_CREDENTIAL_PATH),
        help="short.io secret API key JSON のパス",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    folders = subparsers.add_parser("folders", help="フォルダ一覧を取得する")
    folders.add_argument("--domain-id", type=int, default=DEFAULT_DOMAIN_ID)
    folders.set_defaults(func=cmd_folders)

    search = subparsers.add_parser("search", help="リンク一覧を検索する")
    search.add_argument("--domain-id", type=int, default=DEFAULT_DOMAIN_ID)
    search.add_argument("--query", default="", help="q パラメータ")
    search.add_argument("--limit", type=int, default=30)
    search.add_argument("--folder-id", help="folderId で絞る")
    search.set_defaults(func=cmd_search)

    link_stats = subparsers.add_parser("link-stats", help="リンク単位の統計を取得する")
    link_stats.add_argument("link_id", help="lnk_... の link id")
    link_stats.add_argument("--period", default="last30", help="last30 / total など")
    link_stats.add_argument("--tz-offset", type=int, default=DEFAULT_TZ_OFFSET)
    link_stats.set_defaults(func=cmd_link_stats)

    resolve = subparsers.add_parser("resolve", help="shortURL から exact な実体を引く")
    resolve.add_argument("short_url", help="https://skill.addness.co.jp/... の短縮URL")
    resolve.add_argument("--domain-id", type=int, default=DEFAULT_DOMAIN_ID)
    resolve.set_defaults(func=cmd_resolve)

    sync_ads_sheet = subparsers.add_parser("sync-ads-sheet", help="広告（統合）の遷移先と更新日を short.io 実体で同期する")
    sync_ads_sheet.add_argument("--domain-id", type=int, default=DEFAULT_DOMAIN_ID)
    sync_ads_sheet.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    sync_ads_sheet.add_argument("--sheet-name", default=DEFAULT_ADS_SHEET)
    sync_ads_sheet.add_argument("--limit-rows", type=int, default=0, help="検証用に先頭N件だけ見る")
    sync_ads_sheet.add_argument("--max-workers", type=int, default=8)
    sync_ads_sheet.add_argument("--write", action="store_true", help="dry-run ではなくシートへ反映する")
    sync_ads_sheet.set_defaults(func=cmd_sync_ads_sheet)

    rebuild_sheet_views = subparsers.add_parser(
        "rebuild-sheet-views",
        help="01_全体台帳 から集客媒体タブを再構築する",
    )
    rebuild_sheet_views.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    rebuild_sheet_views.add_argument("--master-sheet", default=DEFAULT_MASTER_SHEET)
    rebuild_sheet_views.add_argument("--delete-obsolete", action="store_true", help="旧タブを削除する")
    rebuild_sheet_views.set_defaults(func=cmd_rebuild_sheet_views)

    audit_sheet = subparsers.add_parser("audit-sheet", help="01_全体台帳 の品質を監査する")
    audit_sheet.add_argument("--sheet-id", default=DEFAULT_SHEET_ID)
    audit_sheet.add_argument("--master-sheet", default=DEFAULT_MASTER_SHEET)
    audit_sheet.set_defaults(func=cmd_audit_sheet)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
