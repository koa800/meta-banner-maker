#!/usr/bin/env python3
"""決済データ用の商品マスタ構造をマスタデータへ反映する。"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional

import gspread

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sheets_manager import get_client  # noqa: E402


MASTER_SHEET_ID = "1kxUbLqhnzLC1Pg0ASVgU135bnx4Rsv_jP0pqGC0R69w"
MASTER_PRODUCT_TAB = "商品マスタ"
PRODUCT_REVIEW_TAB = "商品区分たたき台"
PAYMENT_MAPPING_TAB = "決済商品変換マスタ"

REFERENCE_SHEET_ID = "1Y6akVont1zmqoVgLS527tbjMButHUS6ej5zHdY8XhA0"
REFERENCE_TAB = "シート1"

PAYMENT_COLLECTION_SHEET_ID = "1FfGM0HpofM8yayhJniArXp_vQ6-4JRvlp6rxDt-eHTI"
PAYMENT_COLLECTION_TAB = "決済データ"

BUSINESS_SKILLPLUS = "スキルプラス事業"
BUSINESS_ADDNESS = "Addness事業"
BUSINESS_AI_TRAINING = "AI研修事業"
BUSINESS_DEZA_JV = "デザジュクJV"

TARGET_NON_MEMBER = "非会員向け"
TARGET_MEMBER = "会員向け"
TARGET_BOTH = "両方向け"

ATTR_INDIVIDUAL = "個人"
ATTR_CORPORATE = "法人"
ATTR_BOTH = "両方"

PRODUCT_MASTER_HEADERS = [
    "商品ID",
    "商品管理コード",
    "商品名",
    "事業区分",
    "対象顧客",
    "顧客属性区分",
    "価格",
    "購入形態",
    "初期費用",
    "商品種類",
]

PRODUCT_REVIEW_HEADERS = [
    "商品ID",
    "商品管理コード",
    "商品名",
    "事業区分",
    "対象顧客",
    "顧客属性区分",
    "メモ",
]

PAYMENT_MAPPING_HEADERS = [
    "決済ソース",
    "生商品名",
    "参照件数",
    "参照金額",
    "正式商品名",
    "商品ID",
    "商品管理コード",
    "事業区分",
    "対象顧客",
    "顧客属性区分",
    "判定区分",
    "補助条件",
    "判定根拠",
    "備考",
]

PRODUCT_MASTER_WIDTHS = [100, 130, 320, 130, 120, 120, 110, 120, 100, 100]
PRODUCT_REVIEW_WIDTHS = [100, 130, 320, 130, 120, 120, 260]
PAYMENT_MAPPING_WIDTHS = [120, 360, 90, 130, 260, 100, 140, 130, 120, 120, 110, 220, 220, 240]

ID_PATTERN = re.compile(r"^PRD-(\d{4,})$")


@dataclass(frozen=True)
class ProductRule:
    business: str = ""
    target: str = ""
    customer_attr: str = ""
    note: str = ""


@dataclass(frozen=True)
class ProductMeta:
    product_id: str
    management_code: str
    business: str
    target: str
    customer_attr: str


@dataclass
class PaymentAggregate:
    source: str
    raw_name: str
    count: int = 0
    amount: int = 0


PRODUCT_RULES: dict[str, ProductRule] = {
    "SNSマーケ完全攻略ダイナマイト合宿": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "AIXコンサルタント3日間完全攻略合宿": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "デザイン限界突破3日間合宿": ProductRule(BUSINESS_DEZA_JV, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "みかみ秘密の部屋": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "AIみかみ秘密の部屋": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "コンドウハルキ秘密の部屋": ProductRule(BUSINESS_DEZA_JV, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "月商1.9億を支えるテンプレ大全": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "最速1分でバズ投稿を量産できる禁断のAIテンプレパック": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "パラダイムシフト": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "iステップ": ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL),
    "スレップ": ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL),
    "動画広告分析Pro　1媒体": ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL),
    "動画広告分析Pro　3媒体": ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL),
    "生成AIキャンプ": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "生成AIキャンプアフターサポート": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラスフリープラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラスススタートダッシュプラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラススタンダードプラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラスエリートプラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラスプライムプラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラスデザインプラン／デザジュク": ProductRule(BUSINESS_DEZA_JV, TARGET_NON_MEMBER, ATTR_INDIVIDUAL, "デザジュク系のため要確認"),
    "スキルプラスフルサポートプラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラス月額プラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "アドネス大合宿_STD生用": ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL),
    "代理店ビギナー": ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL),
    "代理店レギュラー": ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL),
    "代理店プレミアム": ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL),
    "Visiontodo Basic (1-10名)": ProductRule(BUSINESS_ADDNESS, TARGET_NON_MEMBER, ATTR_CORPORATE),
    "Visiontodo Basic (11-50名)": ProductRule(BUSINESS_ADDNESS, TARGET_NON_MEMBER, ATTR_CORPORATE),
    "Visiontodo Basic (51-100名)": ProductRule(BUSINESS_ADDNESS, TARGET_NON_MEMBER, ATTR_CORPORATE),
    "Visiontodo Basic (101-200名)": ProductRule(BUSINESS_ADDNESS, TARGET_NON_MEMBER, ATTR_CORPORATE),
    "Visiontodo Basic (201名-)": ProductRule(BUSINESS_ADDNESS, TARGET_NON_MEMBER, ATTR_CORPORATE),
    "スキルプラスfor Biz　研修": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_CORPORATE),
    "アドネス×USEN光01 光回線限定プラン": ProductRule(BUSINESS_ADDNESS, TARGET_NON_MEMBER, "", "要確認"),
    "AIエージェント": ProductRule(BUSINESS_AI_TRAINING, TARGET_NON_MEMBER, ATTR_CORPORATE),
    "（仮）AIエージェントプラスサービスの概念実証（PoC）": ProductRule(
        BUSINESS_AI_TRAINING,
        TARGET_NON_MEMBER,
        ATTR_CORPORATE,
        "AIエージェント系PoCとして仮置き",
    ),
    "新スキルプラスフルサポートプラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラス ライトプラン（月額）": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラス オールインワンプラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "スキルプラス ライトプラン（年間）": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "（仮）新生スキルプラスエグゼクティブ？？": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, "", "要確認"),
    "生成AIプロンプトマルチパック": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL, "仮置き"),
    "アドネスサポートパック": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "みかみの秘密の部屋_月額プラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL, "仮置き"),
    "みかみの秘密の部屋_年額プラン": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL, "仮置き"),
    "生成AIコース アクションマップ": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "SNSマーケティングコース アクションマップ": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "広告マーケティングコース アクションマップ": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "動画編集コース アクションマップ": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "マインドセットコース　アクションマップ": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
    "AICAN(アイキャン)": ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL),
}

REVIEW_EXTRA_ROWS = [
    ProductRule(BUSINESS_SKILLPLUS, TARGET_NON_MEMBER, ATTR_INDIVIDUAL, "AIコンテンツ自動量産Live参加費用 等の集約名"),
    ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL, "VIPチケット / 一般チケット / 両方参加 の集約名"),
    ProductRule(BUSINESS_SKILLPLUS, TARGET_MEMBER, ATTR_INDIVIDUAL, "個別イベント商品として管理"),
]

REVIEW_EXTRA_NAMES = [
    "Live参加費",
    "スキルプラスイベント",
    "みかみとお茶会",
]

REVIEW_EXCLUDED_PRODUCTS = {
    "受託_業務委託契約",
}

SOURCE_EXCLUDED_PRODUCTS = {
    "",
    "受託_業務委託契約",
    "新商品・サービスが増えたら最新の商品の下に追加！！",
}

BUSINESS_CODE = {
    BUSINESS_SKILLPLUS: "SP",
    BUSINESS_ADDNESS: "AD",
    BUSINESS_AI_TRAINING: "AI",
    BUSINESS_DEZA_JV: "JV",
}

TARGET_CODE = {
    TARGET_NON_MEMBER: "N",
    TARGET_MEMBER: "M",
    TARGET_BOTH: "B",
}

ATTR_CODE = {
    ATTR_INDIVIDUAL: "C",
    ATTR_CORPORATE: "B",
    ATTR_BOTH: "X",
}


def ensure_worksheet(spreadsheet: gspread.Spreadsheet, title: str, rows: int, cols: int) -> gspread.Worksheet:
    try:
        ws = spreadsheet.worksheet(title)
        if ws.row_count < rows or ws.col_count < cols:
            ws.resize(rows=max(ws.row_count, rows), cols=max(ws.col_count, cols))
        return ws
    except gspread.WorksheetNotFound:
        return spreadsheet.add_worksheet(title=title, rows=rows, cols=cols)


def parse_amount(value: str) -> int:
    text = (value or "").strip()
    if not text:
        return 0
    normalized = (
        text.replace("¥", "")
        .replace(",", "")
        .replace("，", "")
        .replace("−", "-")
        .replace("—", "-")
        .replace("ー", "-")
        .replace(" ", "")
    )
    match = re.search(r"-?\d+", normalized)
    return int(match.group()) if match else 0


def normalize_display_amount(value: int) -> str:
    return f"¥{value:,}"


def source_sale_is_success(src: str, event: str, status: str) -> bool:
    if src == "UnivaPay":
        return event == "売上" and status == "成功"
    if src == "MOSH":
        return status == "支払い済み"
    if src == "INVOY":
        return status == "入金済"
    if src == "日本プラム":
        return status == "最終承認"
    if src in {"きらぼし銀行", "CBS", "京都信販", "CREDIX"}:
        return True
    return False


def normalize_candidate_name(raw_name: str) -> str:
    text = (raw_name or "").strip()
    if not text or text == "(空欄)":
        return text

    text = re.sub(r"^【[^】]+】", "", text).strip()
    text = re.sub(r"^【[^】]+】", "", text).strip()
    text = re.sub(r"\s*~[^~]*~\s*$", "", text).strip()
    text = text.replace("（全額返金保証付）", "")
    text = text.replace("（全額返金保証）", "")
    text = text.replace("~購入後1週間以内に限り【全額返金保証付き】~", "")
    text = text.replace("　", " ").strip()
    return text


def infer_business_from_legacy(code: str, name: str, current: str) -> str:
    if current:
        return current

    normalized = (name or "").replace("　", " ").strip()
    if "スキルプラスfor Biz" in normalized:
        return BUSINESS_SKILLPLUS
    if "AIエージェント" in normalized or "概念実証" in normalized or "PoC" in normalized:
        return BUSINESS_AI_TRAINING
    if code.startswith("IN-SYS-"):
        return BUSINESS_ADDNESS
    if code.startswith("IN-SKL-"):
        return BUSINESS_SKILLPLUS

    skillplus_markers = (
        "AIX",
        "SNSマーケ",
        "みかみ",
        "AICAN",
        "アクションマップ",
        "アドネスサポートパック",
        "生成AI",
        "テンプレ",
    )
    if any(marker in normalized for marker in skillplus_markers):
        return BUSINESS_SKILLPLUS
    return ""


def load_product_master_rows(ws: gspread.Worksheet) -> tuple[list[str], list[list[str]]]:
    values = ws.get_all_values()
    if not values:
        return PRODUCT_MASTER_HEADERS[:], []
    headers = values[0]
    rows = values[1:]
    return headers, rows


def load_source_product_rows(ws: gspread.Worksheet) -> list[dict[str, str]]:
    headers, rows = load_product_master_rows(ws)
    if not headers:
        return []

    index = {header: idx for idx, header in enumerate(headers)}

    def pick(row: list[str], header: str) -> str:
        idx = index.get(header)
        if idx is None or idx >= len(row):
            return ""
        return row[idx].strip()

    source_rows: list[dict[str, str]] = []
    for row in rows:
        product_name = pick(row, "商品名")
        if product_name in SOURCE_EXCLUDED_PRODUCTS or not product_name:
            continue
        source_rows.append(
            {
                "商品ID": pick(row, "商品ID"),
                "商品名": product_name,
                "事業区分": pick(row, "事業区分"),
                "対象顧客": pick(row, "対象顧客"),
                "顧客属性区分": pick(row, "顧客属性区分"),
                "価格": pick(row, "価格"),
                "購入形態": pick(row, "購入形態"),
                "初期費用": pick(row, "初期費用"),
                "商品種類": pick(row, "商品種類"),
            }
        )
    return source_rows


def legacy_target_from_record(record: dict[str, str]) -> str:
    legacy = (record.get("旧対象顧客") or "").strip()
    if legacy:
        return legacy

    current_target = (record.get("対象顧客") or "").strip()
    if current_target in {TARGET_NON_MEMBER, TARGET_MEMBER, TARGET_BOTH}:
        return ""
    return current_target


def infer_target_from_legacy(legacy_target: str) -> str:
    text = (legacy_target or "").strip()
    if not text:
        return ""
    if "スキルプラス生" in text or "サブスク会員" in text or "_STD" in text:
        return TARGET_MEMBER
    if "非会員" in text:
        return TARGET_NON_MEMBER
    if "事業者" in text:
        return TARGET_NON_MEMBER
    return ""


def infer_customer_attr_from_legacy(legacy_target: str) -> str:
    text = (legacy_target or "").strip()
    if not text:
        return ""
    if "事業者" in text and "個人" in text:
        return ATTR_BOTH
    if "事業者" in text:
        return ATTR_CORPORATE
    if "個人" in text:
        return ATTR_INDIVIDUAL
    if "非会員" in text or "スキルプラス生" in text or "サブスク会員" in text or "_STD" in text:
        return ATTR_INDIVIDUAL
    return ""


def classify_product(name: str, record: dict[str, str]) -> ProductRule:
    explicit = PRODUCT_RULES.get(name)
    if explicit:
        return explicit

    business = (record.get("事業区分") or "").strip()
    target = (record.get("対象顧客") or "").strip()
    customer_attr = (record.get("顧客属性区分") or "").strip()
    note = "要確認" if not (business and target and customer_attr) else ""
    return ProductRule(business, target, customer_attr, note)


def parse_existing_product_id(value: str) -> Optional[int]:
    match = ID_PATTERN.match((value or "").strip())
    if not match:
        return None
    return int(match.group(1))


def build_product_id(number: int) -> str:
    return f"PRD-{number:04d}"


def build_management_code(product_id: str, business: str, target: str, customer_attr: str) -> str:
    if not product_id or not business or not target or not customer_attr:
        return ""
    numeric = product_id.split("-")[-1]
    business_code = BUSINESS_CODE.get(business)
    target_code = TARGET_CODE.get(target)
    attr_code = ATTR_CODE.get(customer_attr)
    if not business_code or not target_code or not attr_code:
        return ""
    return f"{business_code}-{target_code}-{attr_code}-{numeric}"


def sync_product_master_structure(
    ws: gspread.Worksheet,
    source_rows: list[dict[str, str]],
) -> tuple[dict[str, ProductMeta], list[list[str]], dict[str, str]]:
    headers, rows = load_product_master_rows(ws)
    existing_id_map: dict[str, str] = {}
    for row in rows:
        padded = row + [""] * (len(headers) - len(row))
        record = {headers[idx]: padded[idx] for idx in range(len(headers))}
        existing_name = (record.get("商品名") or "").strip()
        existing_id = record.get("商品ID", "").strip()
        if existing_name and parse_existing_product_id(existing_id):
            existing_id_map[existing_name] = record.get("商品ID", "").strip()

    matched_existing_ids = [
        parse_existing_product_id(existing_id_map[row.get("商品名", "").strip()] or "")
        for row in source_rows
        if row.get("商品名", "").strip() in existing_id_map
    ]
    matched_existing_ids = [value for value in matched_existing_ids if value is not None]
    next_id = max(matched_existing_ids) + 1 if matched_existing_ids else 1
    normalized_rows: list[list[str]] = []
    product_index: dict[str, ProductMeta] = {}
    review_notes: dict[str, str] = {}

    for record in source_rows:
        name = record.get("商品名", "").strip()
        if not name:
            continue

        rule = classify_product(name, record)
        product_id = (record.get("商品ID") or "").strip() or existing_id_map.get(name, "")
        if not parse_existing_product_id(product_id):
            product_id = build_product_id(next_id)
            next_id += 1

        management_code = build_management_code(product_id, rule.business, rule.target, rule.customer_attr)
        record["商品ID"] = product_id
        record["商品管理コード"] = management_code
        record["事業区分"] = rule.business
        record["対象顧客"] = rule.target
        record["顧客属性区分"] = rule.customer_attr

        normalized_rows.append([record.get(header, "") for header in PRODUCT_MASTER_HEADERS])
        product_index[name] = ProductMeta(
            product_id=product_id,
            management_code=management_code,
            business=rule.business,
            target=rule.target,
            customer_attr=rule.customer_attr,
        )
        review_notes[name] = rule.note

    payload = [PRODUCT_MASTER_HEADERS] + normalized_rows
    ws.clear()
    ws.resize(rows=max(len(payload) + 20, 200), cols=len(PRODUCT_MASTER_HEADERS))
    ws.update(range_name="A1", values=payload, value_input_option="USER_ENTERED")
    apply_basic_formatting(ws, PRODUCT_MASTER_WIDTHS)
    return product_index, normalized_rows, review_notes


def build_review_rows(master_rows: list[list[str]], product_headers: list[str], review_notes: dict[str, str]) -> list[list[str]]:
    idx = {header: i for i, header in enumerate(product_headers)}
    rows: list[list[str]] = [PRODUCT_REVIEW_HEADERS]

    for row in master_rows:
        name = row[idx["商品名"]].strip()
        if name in REVIEW_EXCLUDED_PRODUCTS:
            continue
        rows.append(
            [
                row[idx["商品ID"]],
                row[idx["商品管理コード"]],
                name,
                row[idx["事業区分"]],
                row[idx["対象顧客"]],
                row[idx["顧客属性区分"]],
                review_notes.get(name, ""),
            ]
        )

    rows.append([""] * len(PRODUCT_REVIEW_HEADERS))
    for name, rule in zip(REVIEW_EXTRA_NAMES, REVIEW_EXTRA_ROWS):
        rows.append(
            [
                "",
                "",
                name,
                rule.business,
                rule.target,
                rule.customer_attr,
                rule.note,
            ]
        )
    return rows


def write_review_rows(ws: gspread.Worksheet, rows: list[list[str]]) -> None:
    ws.clear()
    ws.resize(rows=max(len(rows) + 30, 120), cols=len(PRODUCT_REVIEW_HEADERS))
    ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")
    apply_basic_formatting(ws, PRODUCT_REVIEW_WIDTHS)


def load_reference_mapping(ws: gspread.Worksheet) -> dict[str, str]:
    rows = ws.get_all_values()
    mapping: dict[str, str] = {}
    for row in rows[1:]:
        if len(row) < 3:
            continue
        raw_name = (row[0] or "").strip()
        mapped_name = (row[2] or "").strip()
        if raw_name and mapped_name and raw_name not in mapping:
            mapping[raw_name] = mapped_name
    return mapping


def aggregate_live_payment_products(ws: gspread.Worksheet) -> list[PaymentAggregate]:
    rows = ws.get_all_values()
    if not rows:
        return []

    headers = rows[0]
    idx = {header: i for i, header in enumerate(headers)}
    aggregates: dict[tuple[str, str], PaymentAggregate] = {}

    for row in rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        source = padded[idx["参照システム"]].strip()
        event = padded[idx["イベント"]].strip()
        status = padded[idx["課金ステータス"]].strip()
        if not source_sale_is_success(source, event, status):
            continue

        raw_name = padded[idx["商品名"]].strip() or "(空欄)"
        key = (source, raw_name)
        aggregate = aggregates.setdefault(key, PaymentAggregate(source=source, raw_name=raw_name))
        aggregate.count += 1
        aggregate.amount += parse_amount(padded[idx["イベント金額"]])

    return sorted(
        aggregates.values(),
        key=lambda item: (-item.amount, -item.count, item.source, item.raw_name),
    )


def build_mapping_rows(
    aggregates: Iterable[PaymentAggregate],
    product_index: dict[str, ProductMeta],
    reference_mapping: dict[str, str],
) -> list[list[str]]:
    rows: list[list[str]] = [PAYMENT_MAPPING_HEADERS]
    exact_product_names = set(product_index.keys())

    for aggregate in aggregates:
        raw_name = aggregate.raw_name
        candidate_name = ""
        product_meta: Optional[ProductMeta] = None
        status = "要確認"
        extra_condition = ""
        reason_parts: list[str] = []
        note = ""

        if raw_name == "(空欄)":
            status = "不明"
            extra_condition = "イベント金額・課金タイプ・メール照合で個別判定"
            note = "空欄商品のため自動確定しない"
        else:
            if raw_name in exact_product_names:
                candidate_name = raw_name
                reason_parts.append("商品マスタ完全一致")
            elif raw_name in reference_mapping:
                candidate_name = reference_mapping[raw_name]
                reason_parts.append("不明商品名照合テーブル")
            else:
                normalized = normalize_candidate_name(raw_name)
                if normalized in exact_product_names:
                    candidate_name = normalized
                    reason_parts.append("装飾除去で一致")

            if candidate_name:
                product_meta = product_index.get(candidate_name)
                if product_meta is None:
                    status = "商品マスタ未登録"
                    note = "正式商品名候補はあるが商品マスタ未登録"
                else:
                    status = "変換済み"
                    if product_meta.management_code:
                        reason_parts.append(product_meta.management_code)
            else:
                status = "要確認"
                note = "正式商品名候補を未確定"

        rows.append(
            [
                aggregate.source,
                raw_name,
                str(aggregate.count),
                normalize_display_amount(aggregate.amount),
                candidate_name,
                product_meta.product_id if product_meta else "",
                product_meta.management_code if product_meta else "",
                product_meta.business if product_meta else "",
                product_meta.target if product_meta else "",
                product_meta.customer_attr if product_meta else "",
                status,
                extra_condition,
                " / ".join(reason_parts),
                note,
            ]
        )

    return rows


def apply_basic_formatting(ws: gspread.Worksheet, widths: list[int]) -> None:
    ws.freeze(rows=1)
    ws.set_basic_filter()
    end_col = max(len(widths), ws.col_count)
    ws.format(
        f"A1:{gspread.utils.rowcol_to_a1(1, end_col)}",
        {
            "backgroundColor": {"red": 0.247, "green": 0.42, "blue": 0.878},
            "textFormat": {
                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                "bold": True,
                "fontSize": 10,
            },
            "horizontalAlignment": "CENTER",
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "CLIP",
        },
    )
    ws.format(
        f"A2:{gspread.utils.rowcol_to_a1(max(ws.row_count, 2), end_col)}",
        {
            "textFormat": {"fontSize": 10},
            "verticalAlignment": "MIDDLE",
            "wrapStrategy": "CLIP",
        },
    )

    requests = []
    for idx, width in enumerate(widths):
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "COLUMNS",
                        "startIndex": idx,
                        "endIndex": idx + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )
    requests.extend(
        [
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "ROWS",
                        "startIndex": 0,
                        "endIndex": 1,
                    },
                    "properties": {"pixelSize": 34},
                    "fields": "pixelSize",
                }
            },
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": ws.id,
                        "dimension": "ROWS",
                        "startIndex": 1,
                        "endIndex": max(ws.row_count, 2),
                    },
                    "properties": {"pixelSize": 24},
                    "fields": "pixelSize",
                }
            },
        ]
    )
    ws.spreadsheet.batch_update({"requests": requests})


def write_mapping_rows(ws: gspread.Worksheet, rows: list[list[str]]) -> None:
    ws.clear()
    ws.resize(rows=max(len(rows) + 50, 500), cols=len(PAYMENT_MAPPING_HEADERS))
    ws.update(range_name="A1", values=rows, value_input_option="USER_ENTERED")
    apply_basic_formatting(ws, PAYMENT_MAPPING_WIDTHS)


def main() -> None:
    gc = get_client()

    master_ss = gc.open_by_key(MASTER_SHEET_ID)
    product_ws = master_ss.worksheet(MASTER_PRODUCT_TAB)
    review_ws = ensure_worksheet(master_ss, PRODUCT_REVIEW_TAB, 120, len(PRODUCT_REVIEW_HEADERS))
    mapping_ws = ensure_worksheet(master_ss, PAYMENT_MAPPING_TAB, 500, len(PAYMENT_MAPPING_HEADERS))

    reference_ss = gc.open_by_key(REFERENCE_SHEET_ID)
    reference_ws = reference_ss.worksheet(REFERENCE_TAB)

    payment_ss = gc.open_by_key(PAYMENT_COLLECTION_SHEET_ID)
    payment_ws = payment_ss.worksheet(PAYMENT_COLLECTION_TAB)

    source_rows = load_source_product_rows(product_ws)
    product_index, normalized_rows, review_notes = sync_product_master_structure(product_ws, source_rows)
    review_rows = build_review_rows(normalized_rows, PRODUCT_MASTER_HEADERS, review_notes)
    write_review_rows(review_ws, review_rows)

    reference_mapping = load_reference_mapping(reference_ws)
    aggregates = aggregate_live_payment_products(payment_ws)
    mapping_rows = build_mapping_rows(aggregates, product_index, reference_mapping)
    write_mapping_rows(mapping_ws, mapping_rows)

    print(f"商品マスタ更新: {len(product_index):,} 商品")
    print(f"商品区分たたき台更新: {len(review_rows) - 1:,} 行")
    print(f"決済商品変換マスタ更新: {len(mapping_rows) - 1:,} 行")


if __name__ == "__main__":
    main()
