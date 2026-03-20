#!/usr/bin/env python3
"""
【アドネス株式会社】共通除外マスタ を読む共通処理。

役割:
- 除外リスト のメールアドレス / 電話番号を判定する
- 無条件除外ルール の文字列条件を判定する
- 適用範囲 と 追加日 を見て、新しく発生したデータだけ除外する
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List

from gspread.exceptions import APIError

from sheets_manager import get_client

COMMON_EXCLUSION_MASTER_SHEET_ID = "1dSIXBovs-c8wVnBWsOqbe2wdqmJQ10bOIWhKJbC1MPw"
EXCLUSION_TAB_NAME = "除外リスト"
UNCONDITIONAL_RULE_TAB_NAME = "無条件除外ルール"

DATE_RE = re.compile(r"(\d{4})[/-](\d{1,2})[/-](\d{1,2})")
EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[A-Za-z]{2,}$")
RULE_CONTAINS_RE = re.compile(r"(.+?)\s*を含む")
RULE_EXACT_RE = re.compile(r"(.+?)\s*と一致")
RULE_PREFIX_RE = re.compile(r"(.+?)\s*で始まる")
READ_RETRY_SECONDS = (0, 5, 10, 20, 40)
TRANSIENT_SHEETS_STATUS_CODES = {429, 500, 502, 503, 504}
TRANSIENT_SHEETS_ERROR_MARKERS = (
    "quota exceeded",
    "resource_exhausted",
    "service is currently unavailable",
    "backend error",
    "internal error",
    "try again later",
)


def normalize_email(value: str) -> str:
    email = str(value or "").strip().lower()
    email = email.replace("＠", "@").replace("．", ".").replace("，", ",")
    email = email.replace("mailto:", "").strip("'").strip('"')
    return email if EMAIL_RE.match(email) else ""


def normalize_phone(value: str) -> str:
    phone = str(value or "").strip()
    if not phone:
        return ""
    phone = re.sub(r"[^\d+]", "", phone)
    if phone.startswith("+81"):
        phone = "0" + phone[3:]
    if phone and not phone.startswith("0") and len(phone) in (10, 11):
        phone = "0" + phone
    return re.sub(r"\D", "", phone)


def normalize_date(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    match = DATE_RE.search(text)
    if not match:
        return ""
    year, month, day = map(int, match.groups())
    return f"{year:04d}/{month:02d}/{day:02d}"


def normalize_text(value: str) -> str:
    return str(value or "").strip().lower()


def is_retryable_sheets_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code in TRANSIENT_SHEETS_STATUS_CODES:
        return True
    return any(marker in str(exc).lower() for marker in TRANSIENT_SHEETS_ERROR_MARKERS)


def run_sheets_read_with_retry(action, description: str):
    last_error = None
    for wait_seconds in READ_RETRY_SECONDS:
        if wait_seconds:
            time.sleep(wait_seconds)
        try:
            return action()
        except Exception as exc:
            last_error = exc
            if not is_retryable_sheets_error(exc) or wait_seconds == READ_RETRY_SECONDS[-1]:
                raise
    if last_error:
        raise last_error
    raise RuntimeError(f"{description} に失敗しました")


def scope_matches(rule_scope: str, target_scope: str) -> bool:
    normalized_rule = str(rule_scope or "").strip()
    if not normalized_rule or normalized_rule == "全体":
        return True
    target = str(target_scope or "").strip() or "全体"
    tokens = re.split(r"[,、/／\s]+", normalized_rule)
    tokens = [token for token in tokens if token]
    return "全体" in tokens or target in tokens


def date_is_after_or_equal(event_date: str, added_date: str) -> bool:
    normalized_added = normalize_date(added_date)
    if not normalized_added:
        return True
    normalized_event = normalize_date(event_date)
    if not normalized_event:
        normalized_event = datetime.now().strftime("%Y/%m/%d")
    return normalized_event >= normalized_added


@dataclass(frozen=True)
class ExclusionEntry:
    email: str
    phone: str
    reason: str
    scope: str
    added_date: str
    note: str


@dataclass(frozen=True)
class UnconditionalRule:
    target: str
    operator: str
    value: str
    scope: str
    note: str


@dataclass(frozen=True)
class ExclusionDecision:
    excluded: bool
    reason: str = ""


_CACHE: Dict[str, "CommonExclusionMaster"] = {}


class CommonExclusionMaster:
    def __init__(self, entries: List[ExclusionEntry], unconditional_rules: List[UnconditionalRule]):
        self.entries = entries
        self.unconditional_rules = unconditional_rules

    @classmethod
    def load(cls, account: str = "kohara", force_refresh: bool = False) -> "CommonExclusionMaster":
        cache_key = f"{account}"
        if not force_refresh and cache_key in _CACHE:
            return _CACHE[cache_key]

        gc = get_client(account)
        spreadsheet = run_sheets_read_with_retry(
            lambda: gc.open_by_key(COMMON_EXCLUSION_MASTER_SHEET_ID),
            "共通除外マスタ取得",
        )
        exclusion_ws = run_sheets_read_with_retry(
            lambda: spreadsheet.worksheet(EXCLUSION_TAB_NAME),
            f"{EXCLUSION_TAB_NAME} 取得",
        )
        unconditional_ws = run_sheets_read_with_retry(
            lambda: spreadsheet.worksheet(UNCONDITIONAL_RULE_TAB_NAME),
            f"{UNCONDITIONAL_RULE_TAB_NAME} 取得",
        )

        exclusion_rows = run_sheets_read_with_retry(lambda: exclusion_ws.get_all_values(), f"{EXCLUSION_TAB_NAME} 読み取り")
        unconditional_rows = run_sheets_read_with_retry(
            lambda: unconditional_ws.get_all_values(),
            f"{UNCONDITIONAL_RULE_TAB_NAME} 読み取り",
        )

        entries: List[ExclusionEntry] = []
        for row in exclusion_rows[1:]:
            padded = row + [""] * max(0, 7 - len(row))
            email = normalize_email(padded[0])
            phone = normalize_phone(padded[1])
            if not email and not phone:
                continue
            entries.append(
                ExclusionEntry(
                    email=email,
                    phone=phone,
                    reason=str(padded[3]).strip(),
                    scope=str(padded[4]).strip() or "全体",
                    added_date=normalize_date(padded[5]),
                    note=str(padded[6]).strip(),
                )
            )

        unconditional_rules: List[UnconditionalRule] = []
        for row in unconditional_rows[1:]:
            padded = row + [""] * max(0, 5 - len(row))
            target = str(padded[0]).strip()
            condition = str(padded[1]).strip()
            scope = str(padded[2]).strip() or "全体"
            state = str(padded[3]).strip()
            note = str(padded[4]).strip()
            if not target or state != "有効":
                continue
            operator = ""
            value = ""
            contains_match = RULE_CONTAINS_RE.fullmatch(condition)
            exact_match = RULE_EXACT_RE.fullmatch(condition)
            prefix_match = RULE_PREFIX_RE.fullmatch(condition)
            if contains_match:
                operator = "contains"
                value = normalize_text(contains_match.group(1))
            elif exact_match:
                operator = "equals"
                value = normalize_text(exact_match.group(1))
            elif prefix_match:
                operator = "starts_with"
                value = normalize_text(prefix_match.group(1))
            if not operator or not value:
                continue
            unconditional_rules.append(
                UnconditionalRule(
                    target=target,
                    operator=operator,
                    value=value,
                    scope=scope,
                    note=note,
                )
            )

        master = cls(entries=entries, unconditional_rules=unconditional_rules)
        _CACHE[cache_key] = master
        return master

    def _matches_unconditional(self, value: str, rule: UnconditionalRule) -> bool:
        normalized_value = normalize_text(value)
        if not normalized_value:
            return False
        if rule.operator == "contains":
            return rule.value in normalized_value
        if rule.operator == "equals":
            return normalized_value == rule.value
        if rule.operator == "starts_with":
            return normalized_value.startswith(rule.value)
        return False

    def decide(
        self,
        *,
        email: str = "",
        phone: str = "",
        name: str = "",
        scope: str = "全体",
        event_date: str = "",
    ) -> ExclusionDecision:
        normalized_email = normalize_email(email)
        normalized_phone = normalize_phone(phone)
        normalized_name = str(name or "").strip()

        for rule in self.unconditional_rules:
            if not scope_matches(rule.scope, scope):
                continue
            target_value = ""
            if rule.target == "メールアドレス":
                target_value = normalized_email
            elif rule.target == "電話番号":
                target_value = normalized_phone
            elif rule.target == "対象者名":
                target_value = normalized_name
            if self._matches_unconditional(target_value, rule):
                return ExclusionDecision(True, f"無条件除外ルール: {rule.target} {rule.value}")

        for entry in self.entries:
            if not scope_matches(entry.scope, scope):
                continue
            if not date_is_after_or_equal(event_date, entry.added_date):
                continue
            if entry.email and normalized_email and entry.email == normalized_email:
                return ExclusionDecision(True, f"除外リスト: {entry.reason or 'メールアドレス一致'}")
            if entry.phone and normalized_phone and entry.phone == normalized_phone:
                return ExclusionDecision(True, f"除外リスト: {entry.reason or '電話番号一致'}")

        return ExclusionDecision(False, "")

    def is_excluded(
        self,
        *,
        email: str = "",
        phone: str = "",
        name: str = "",
        scope: str = "全体",
        event_date: str = "",
    ) -> bool:
        return self.decide(
            email=email,
            phone=phone,
            name=name,
            scope=scope,
            event_date=event_date,
        ).excluded
