#!/usr/bin/env python3
"""
Looker Studio 媒体ファネルCSVエクスポーター (v2)

UI操作で1日ずつ日付フィルターを設定し、CSVをダウンロードする。
URLパラメータが効かないため、Angular Material の mat-calendar を直接操作する。

使い方:
  python3 looker_media_export.py login              # 初回: Googleログイン
  python3 looker_media_export.py run                 # 全期間を実行
  python3 looker_media_export.py run 2025-07-27      # 指定日から開始
  python3 looker_media_export.py test 2025-08-01     # 1日分だけテスト
"""

import os
import sys
import time
import re
from datetime import date, timedelta
from playwright.sync_api import sync_playwright

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPORT_URL = "https://lookerstudio.google.com/reporting/f3d08756-9297-4d34-b6ea-ea22780eb4d2/page/p_dsqvinv6zd"
PROFILE_DIR = os.path.join(SCRIPT_DIR, "looker_browser_profile")
DOWNLOAD_DIR = os.path.expanduser("~/Desktop/Looker Studio CSV")
DEBUG_DIR = os.path.join(SCRIPT_DIR, "looker_debug")

DEFAULT_START = date(2025, 7, 1)
DEFAULT_END = date(2026, 2, 19)
MAX_RETRIES = 3


def ensure_dirs():
    os.makedirs(PROFILE_DIR, exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    os.makedirs(DEBUG_DIR, exist_ok=True)


def csv_path_for(target_date):
    return os.path.join(DOWNLOAD_DIR, f"looker_media_funnel_{target_date.isoformat()}.csv")


def date_aria(d):
    """aria-label文字列を生成: '2025年7月1日'"""
    return f"{d.year}年{d.month}月{d.day}日"


def month_diff(from_year, from_month, to_year, to_month):
    return (to_year - from_year) * 12 + (to_month - from_month)


def parse_month_label(text):
    """'2025年7月' → (2025, 7)"""
    m = re.match(r"(\d{4})年(\d{1,2})月", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, None


def get_calendar_month(page, cal_sel):
    """カレンダーの現在表示月を (year, month) で返す"""
    text = page.evaluate(f"""() => {{
        const btn = document.querySelector('{cal_sel} button[aria-label="Choose month and year"]');
        return btn ? btn.textContent.trim() : '';
    }}""")
    return parse_month_label(text)


def navigate_calendar_to(page, cal_sel, target_year, target_month):
    """カレンダーをtarget月まで移動する"""
    cur_y, cur_m = get_calendar_month(page, cal_sel)
    if cur_y is None:
        raise RuntimeError(f"カレンダー月取得失敗: {cal_sel}")

    diff = month_diff(cur_y, cur_m, target_year, target_month)
    if diff == 0:
        return

    aria = "Next month" if diff > 0 else "Previous month"
    for _ in range(abs(diff)):
        page.locator(f'{cal_sel} button[aria-label="{aria}"]').first.click()
        time.sleep(0.4)
    time.sleep(0.5)


def click_day(page, cal_sel, target_date):
    """カレンダーで指定日をクリック"""
    aria = date_aria(target_date)
    cell = page.locator(f'{cal_sel} button[aria-label="{aria}"]').first
    cell.click()
    time.sleep(0.5)


def ensure_absolute_mode(page):
    """日付ピッカーが「絶対指定」モードになっていなければ切り替える"""
    is_absolute = page.evaluate("""() => {
        const d = document.querySelector('ng2-date-picker-dialog');
        if (!d) return false;
        for (const b of d.querySelectorAll('button')) {
            if (b.textContent.trim().startsWith('絶対指定')) return true;
        }
        return false;
    }""")

    if is_absolute:
        return

    page.evaluate("""() => {
        const d = document.querySelector('ng2-date-picker-dialog');
        for (const b of d.querySelectorAll('button')) {
            const t = b.textContent.trim();
            if (t.includes('詳細設定') || t.includes('今日') || t.includes('カスタム')
                || t.includes('過去') || t.includes('今週') || t.includes('今月')) {
                b.click(); return;
            }
        }
    }""")
    time.sleep(2)

    for mi in page.get_by_role("menuitem").all():
        if (mi.text_content() or "").strip() == "絶対指定":
            mi.click()
            break
    time.sleep(3)


def set_date_filter(page, target_date):
    """日付フィルターを target_date (開始=終了) に設定して適用"""

    page.locator("button.ng2-date-picker-button").first.click()
    time.sleep(3)

    ensure_absolute_mode(page)

    start_cal = ".start-date-picker"
    end_cal = ".end-date-picker"

    navigate_calendar_to(page, start_cal, target_date.year, target_date.month)
    click_day(page, start_cal, target_date)

    navigate_calendar_to(page, end_cal, target_date.year, target_date.month)
    click_day(page, end_cal, target_date)

    page.locator("button.apply-button").first.click()
    time.sleep(10)


def export_csv(page):
    """テーブルからCSVをエクスポートしてダウンロードオブジェクトを返す"""

    table = page.locator("lego-table").first
    table.wait_for(state="visible", timeout=30000)
    table.hover()
    time.sleep(2)

    menu_btn = page.locator('button[aria-label="グラフのメニューを表示"]').first
    menu_btn.wait_for(state="visible", timeout=10000)
    menu_btn.click()
    time.sleep(1.5)

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('[role="menuitem"]')) {
            if (el.textContent.includes('グラフをエクスポート')) { el.click(); return; }
        }
    }""")
    time.sleep(1.5)

    page.evaluate("""() => {
        for (const el of document.querySelectorAll('[role="menuitem"]')) {
            if (el.textContent.includes('データのエクスポート')) { el.click(); return; }
        }
    }""")
    time.sleep(2)

    with page.expect_download(timeout=60000) as dl_info:
        page.evaluate("""() => {
            for (const b of document.querySelectorAll('button')) {
                if (b.textContent.trim() === 'エクスポート') { b.click(); return; }
            }
        }""")

    return dl_info.value


def close_any_dialog(page):
    """開いたままのダイアログやメニューを閉じる"""
    page.keyboard.press("Escape")
    time.sleep(1)
    page.keyboard.press("Escape")
    time.sleep(0.5)


def process_one_day(page, target_date):
    """1日分: 日付設定 → CSVエクスポート → 保存"""
    set_date_filter(page, target_date)
    download = export_csv(page)
    dest = csv_path_for(target_date)
    download.save_as(dest)
    return dest


# ── CLI コマンド ──────────────────────────────────────────────

def cmd_login():
    ensure_dirs()
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            viewport={"width": 1400, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(REPORT_URL, timeout=120_000)
        print("ブラウザでGoogleアカウントにログインしてください。")
        print("ログイン後、レポートが表示されたらEnterを押してください。")
        input(">>> Enterで終了 ")
        ctx.close()
        print("ログイン状態を保存しました。")


def cmd_test(target_date_str):
    ensure_dirs()
    target = date.fromisoformat(target_date_str)
    print(f"テスト: {target}")

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(REPORT_URL, timeout=90000, wait_until="commit")
        time.sleep(20)

        if "accounts.google.com" in page.url:
            print("認証切れ。login コマンドで再ログインしてください。")
            ctx.close()
            return

        try:
            path = process_one_day(page, target)
            fsize = os.path.getsize(path)
            print(f"成功: {path} ({fsize:,} bytes)")
        except Exception as e:
            print(f"失敗: {e}")
            try:
                page.screenshot(path=os.path.join(DEBUG_DIR, f"test_error_{target}.png"))
            except Exception:
                pass
        finally:
            ctx.close()


def cmd_run(start_from=None):
    ensure_dirs()
    start = date.fromisoformat(start_from) if start_from else DEFAULT_START
    end = DEFAULT_END
    total = (end - start).days + 1

    already = sum(
        1 for d in range(total) if os.path.exists(csv_path_for(start + timedelta(days=d)))
    )
    remaining = total - already
    print(f"=== 媒体ファネルCSVエクスポート ===")
    print(f"  期間: {start} 〜 {end} ({total}日)")
    print(f"  済: {already} / 残: {remaining}")
    print(f"  保存先: {DOWNLOAD_DIR}\n")

    if remaining == 0:
        print("全日分ダウンロード済みです。")
        return

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=PROFILE_DIR,
            headless=False,
            accept_downloads=True,
            viewport={"width": 1920, "height": 1080},
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto(REPORT_URL, timeout=90000, wait_until="commit")
        time.sleep(20)

        if "accounts.google.com" in page.url:
            print("認証切れ。login コマンドで再ログインしてください。")
            ctx.close()
            return

        success, fail, skip = 0, 0, 0
        current = start

        while current <= end:
            n = (current - start).days + 1

            if os.path.exists(csv_path_for(current)):
                skip += 1
                current += timedelta(days=1)
                continue

            label = f"[{current}] ({n}/{total})"
            ok = False

            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    suffix = f" (retry {attempt})" if attempt > 1 else ""
                    print(f"{label} ダウンロード中...{suffix}")
                    path = process_one_day(page, current)
                    fsize = os.path.getsize(path)
                    print(f"{label} 完了 ({fsize:,} bytes)")
                    success += 1
                    ok = True
                    break
                except Exception as e:
                    print(f"{label} エラー: {e}")
                    try:
                        ss = os.path.join(DEBUG_DIR, f"error_{current}_{attempt}.png")
                        if not page.is_closed():
                            page.screenshot(path=ss)
                    except Exception:
                        pass
                    if attempt < MAX_RETRIES:
                        try:
                            close_any_dialog(page)
                        except Exception:
                            pass
                        try:
                            page.goto(REPORT_URL, timeout=90000, wait_until="commit")
                            time.sleep(15)
                        except Exception:
                            pass
                        time.sleep(3)

            if not ok:
                fail += 1
                print(f"{label} {MAX_RETRIES}回失敗 → スキップ")

            current += timedelta(days=1)
            time.sleep(2)

        ctx.close()

    print(f"\n=== 完了 ===")
    print(f"  成功: {success} / スキップ(済): {skip} / 失敗: {fail}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "login":
        cmd_login()
    elif cmd == "run":
        cmd_run(sys.argv[2] if len(sys.argv) > 2 else None)
    elif cmd == "test":
        if len(sys.argv) < 3:
            print("日付を指定してください（例: 2025-08-01）")
            sys.exit(1)
        cmd_test(sys.argv[2])
    else:
        print(f"不明なコマンド: {cmd}")
        print(__doc__)
        sys.exit(1)
