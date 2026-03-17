#!/usr/bin/env python3
"""UTAGE の exploratory video rename を visible save button 前提で検証する。"""

from __future__ import annotations

import json
import time
from typing import Any

from chrome_raw_cdp import activate_target
from chrome_raw_cdp import create_target
from chrome_raw_cdp import eval_target
from chrome_raw_cdp import find_target
from chrome_raw_cdp import navigate_target
from utage_login_helper import ensure_login


LIST_URL = "https://school.addness.co.jp/media/video"
TARGET_NAME = "test2_20260315.mp4"
UPDATED_NAME = "ZZ_TEST_UTAGE_video_probe_UPDATED.mp4"


def _find_target_id() -> str:
    target = (
        find_target(url_contains="school.addness.co.jp/media/video")
        or find_target(url_contains="school.addness.co.jp/media")
        or find_target(title_contains="UTAGE")
    )
    if target is None:
        target = create_target(LIST_URL)
    target_id = str(target["id"])
    activate_target(target_id)
    return target_id


def _goto_list(target_id: str) -> None:
    navigate_target(target_id, LIST_URL)
    time.sleep(2.5)


def _count_rows(target_id: str, name: str) -> int:
    _goto_list(target_id)
    return int(
        eval_target(
            target_id,
            f"""(() => Array.from(document.querySelectorAll('tr'))
                .filter((row) => (row.innerText || '').includes({json.dumps(name, ensure_ascii=False)}))
                .length)()""",
        )
        or 0
    )


def _open_rename_modal(target_id: str, name: str) -> str:
    _goto_list(target_id)
    return str(
        eval_target(
            target_id,
            f"""(() => {{
  const row = Array.from(document.querySelectorAll('tr'))
    .find((tr) => (tr.innerText || '').includes({json.dumps(name, ensure_ascii=False)}));
  if (!row) return 'row-not-found';
  const btn = row.querySelector('button.btn-name');
  if (!btn) return 'button-not-found';
  btn.click();
  return 'ok';
}})()""",
        )
        or ""
    )


def _read_modal_value(target_id: str) -> str:
    time.sleep(1.0)
    return str(
        eval_target(
            target_id,
            """(() => {
  const form = Array.from(document.querySelectorAll('form'))
    .find((el) => (el.action || '').includes('/video/name/update'));
  if (!form) return '';
  const input = form.querySelector('input[name="name"]');
  return input ? (input.value || '') : '';
})()""",
        )
        or ""
    )


def _submit_via_save_button(target_id: str, next_name: str) -> str:
    return str(
        eval_target(
            target_id,
            f"""(() => {{
  const form = Array.from(document.querySelectorAll('form'))
    .find((el) => (el.action || '').includes('/video/name/update'));
  if (!form) return 'form-not-found';
  const input = form.querySelector('input[name="name"]');
  const save = form.querySelector('#button-name');
  if (!input || !save) return 'name-or-save-not-found';
  input.value = {json.dumps(next_name, ensure_ascii=False)};
  input.dispatchEvent(new Event('input', {{ bubbles: true }}));
  input.dispatchEvent(new Event('change', {{ bubbles: true }}));
  save.click();
  return 'submitted';
}})()""",
        )
        or ""
    )


def _row_exists(target_id: str, name: str) -> bool:
    _goto_list(target_id)
    return bool(
        eval_target(
            target_id,
            f"""(() => Array.from(document.querySelectorAll('tr'))
                .some((row) => (row.innerText || '').includes({json.dumps(name, ensure_ascii=False)})))()""",
        )
    )


def run_probe() -> dict[str, Any]:
    target_id = _find_target_id()
    before_count = _count_rows(target_id, TARGET_NAME)
    open_result = _open_rename_modal(target_id, TARGET_NAME)
    before_value = _read_modal_value(target_id)
    submit_result = _submit_via_save_button(target_id, UPDATED_NAME)
    time.sleep(2.5)
    after_new_count = _count_rows(target_id, UPDATED_NAME)
    after_old_count = _count_rows(target_id, TARGET_NAME)
    rollback_open = _open_rename_modal(target_id, UPDATED_NAME)
    rollback_value = _read_modal_value(target_id)
    rollback_submit = _submit_via_save_button(target_id, TARGET_NAME)
    time.sleep(2.5)
    rollback_old_exists = _row_exists(target_id, TARGET_NAME)
    rollback_new_exists = _row_exists(target_id, UPDATED_NAME)
    return {
        "mode": "visible-save-button",
        "before_count": before_count,
        "open_result": open_result,
        "before_value": before_value,
        "submit_result": submit_result,
        "after_new_count": after_new_count,
        "after_old_count": after_old_count,
        "changed_via_save_button": after_new_count == 1 and after_old_count == 0,
        "rollback_open": rollback_open,
        "rollback_value": rollback_value,
        "rollback_submit": rollback_submit,
        "rollback_old_exists": rollback_old_exists,
        "rollback_new_exists": rollback_new_exists,
    }


def main() -> None:
    if ensure_login(LIST_URL) != 0:
        raise SystemExit(1)
    result = run_probe()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
