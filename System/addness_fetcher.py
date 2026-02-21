#!/usr/bin/env python3
"""
Addness ゴール・タスク取得スクリプト

- Googleアカウントでログイン（セッション保存・再利用）
- 指定ゴールURLからツリー構造を全取得
- 誰が / 何の目的で / 何を / いつまでに を構造化JSON保存
"""

import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("addness_fetcher")

# ---- パス設定 ----
SCRIPT_DIR = Path(__file__).parent
CONFIG_PATH = SCRIPT_DIR / "addness_config.json"
SESSION_PATH = SCRIPT_DIR / "addness_session.json"

# ---- デフォルト設定 ----
DEFAULT_CONFIG = {
    "start_url": "https://www.addness.com/goals/45e3a49b-4818-429d-936e-913d41b5d833",
    "output_dir": str(SCRIPT_DIR / "addness_data"),
    "headless": True,
    "timeout_ms": 30000,
    "wait_after_load_ms": 3000,
}


def load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        return {**DEFAULT_CONFIG, **cfg}
    return DEFAULT_CONFIG


def save_config(cfg: dict):
    save = {k: v for k, v in cfg.items() if k in DEFAULT_CONFIG}
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(save, f, ensure_ascii=False, indent=2)


def is_authenticated(page) -> bool:
    """ログイン済みか確認（sign-in/sign-upでなければOK）"""
    url = page.url
    return "sign-in" not in url and "sign-up" not in url and "addness.com" in url


def login_manually(playwright, start_url: str):
    """
    本物のChromeブラウザを開いて手動ログイン後、セッションを保存する。
    Google OAuth はChromiumだとbotと判定されるため channel="chrome" を使用。
    """
    print("=" * 60)
    print("【初回ログイン / セッション更新】")
    print("Chromeブラウザが開きます。Googleアカウントでログインしてください。")
    print("※ 会社アカウント(addness.co.jp)でログインしてください。")
    print("ログイン完了後、自動的にセッションを保存します。")
    print("=" * 60)

    # Google OAuth bot検知を回避するため本物のChromeを使用
    # 専用の一時プロファイルを使い、実行中のChromeと競合しない
    chrome_profile_dir = SCRIPT_DIR / "addness_chrome_profile"
    chrome_profile_dir.mkdir(exist_ok=True)

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(chrome_profile_dir),
        channel="chrome",
        headless=False,
        viewport={"width": 1280, "height": 800},
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
        ],
        # Googleがbot判定する --enable-automation を除外
        ignore_default_args=["--enable-automation"],
    )
    page = context.new_page()
    # navigator.webdriver を隠す（Googleのbot検知対策）
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    page.goto(start_url)

    print("\nログイン待機中... ブラウザでGoogleログイン後、Addnessが開くまでお待ちください。（最大5分）")
    try:
        # /goals/ に到達するまで最大5分待つ（Googleログイン時間を含む）
        page.wait_for_url("**/goals/**", timeout=300_000)
        time.sleep(3)  # データ読み込み待ち
        print("ログイン確認済み。セッションを保存します...")
        context.storage_state(path=str(SESSION_PATH))
        print(f"セッション保存: {SESSION_PATH}")
    except PlaywrightTimeoutError:
        logger.error("Addnessログインタイムアウト", extra={"error": {"type": "PlaywrightTimeoutError", "message": "5分以内にログイン未完了"}})
        print("タイムアウト（5分）: ログインが完了しませんでした。再度実行してください。")
        context.close()
        sys.exit(1)
    except Exception as e:
        logger.error("Addnessログインエラー", extra={"error": {"type": type(e).__name__, "message": str(e)}})
        print(f"ブラウザエラー: {e}")
        print("ブラウザを閉じずにログインを完了してください。再度実行してください。")
        try:
            context.close()
        except Exception:
            pass
        sys.exit(1)

    context.close()


def intercept_api_responses(page) -> dict:
    """
    ページが行うAPIリクエストをインターセプトしてデータを収集
    """
    api_data: dict[str, dict] = {}

    def handle_response(response):
        try:
            url = response.url
            # JSON APIレスポンスのみキャプチャ
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200:
                # URLからキーを作成
                key = url.split("addness.com")[-1].split("?")[0]
                if key and len(key) > 1:
                    body = response.json()
                    api_data[key] = body
        except Exception:
            pass

    page.on("response", handle_response)
    return api_data


def extract_next_data(page) -> Optional[dict]:
    """Next.js の __NEXT_DATA__ からデータを取得"""
    try:
        data = page.evaluate("""
            () => {
                const el = document.getElementById('__NEXT_DATA__');
                if (el) return JSON.parse(el.textContent);
                return null;
            }
        """)
        return data
    except Exception:
        return None


def extract_dom_tasks(page) -> list:
    """
    DOMからタスク/ゴール情報を抽出
    Addnessのクラス構造に基づくセレクタを試みる
    """
    try:
        return page.evaluate("""
            () => {
                const results = [];
                const seen = new Set();

                // よく使われるタスク系セレクタを網羅的に試す
                const selectors = [
                    '[class*="task"]',
                    '[class*="goal"]',
                    '[class*="todo"]',
                    '[class*="item"]',
                    '[data-testid]',
                    'li',
                ];

                for (const sel of selectors) {
                    document.querySelectorAll(sel).forEach(el => {
                        const text = (el.innerText || '').trim();
                        if (text.length > 5 && text.length < 2000 && !seen.has(text)) {
                            seen.add(text);
                            const rect = el.getBoundingClientRect();
                            // 表示されている要素のみ
                            if (rect.width > 0 && rect.height > 0) {
                                results.push({
                                    selector: sel,
                                    tag: el.tagName,
                                    className: el.className,
                                    text: text,
                                    dataAttrs: Object.fromEntries(
                                        Array.from(el.attributes)
                                            .filter(a => a.name.startsWith('data-'))
                                            .map(a => [a.name, a.value])
                                    ),
                                    depth: (() => {
                                        let d = 0, p = el.parentElement;
                                        while (p) { d++; p = p.parentElement; }
                                        return d;
                                    })(),
                                });
                            }
                        }
                    });
                }
                return results;
            }
        """)
    except Exception:
        return []


def extract_react_state(page) -> Optional[dict]:
    """React Fiber から状態データを抽出（可能な場合）"""
    try:
        return page.evaluate("""
            () => {
                // React root を探す
                const root = document.getElementById('__next') || document.getElementById('root');
                if (!root) return null;

                // React Fiber key を探す
                const fiberKey = Object.keys(root).find(
                    k => k.startsWith('__reactFiber') || k.startsWith('__reactInternalInstance')
                );
                if (!fiberKey) return null;

                // Fiber ツリーを簡易シリアライズ（循環参照を避けて）
                function extractProps(fiber, depth = 0) {
                    if (!fiber || depth > 10) return null;
                    const result = {};
                    if (fiber.memoizedProps) {
                        try {
                            result.props = JSON.parse(JSON.stringify(fiber.memoizedProps));
                        } catch { result.props = String(fiber.memoizedProps); }
                    }
                    if (fiber.memoizedState && fiber.memoizedState.queue) {
                        try {
                            result.state = JSON.parse(JSON.stringify(fiber.memoizedState.queue));
                        } catch {}
                    }
                    if (fiber.child) result.child = extractProps(fiber.child, depth + 1);
                    if (fiber.sibling) result.sibling = extractProps(fiber.sibling, depth + 1);
                    return result;
                }

                try {
                    return extractProps(root[fiberKey], 0);
                } catch {
                    return null;
                }
            }
        """)
    except Exception:
        return None


def extract_page_text_structure(page) -> dict:
    """ページ全体のテキスト構造を取得"""
    try:
        return page.evaluate("""
            () => {
                // 見出し・ラベル・テキストを階層付きで取得
                const headings = [];
                document.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]').forEach(el => {
                    headings.push({
                        level: el.tagName || el.getAttribute('aria-level'),
                        text: (el.innerText || '').trim(),
                    });
                });

                // ページ全体テキスト
                const bodyText = (document.body.innerText || '').trim();

                // メインコンテンツエリアを特定
                const main = document.querySelector('main, [role="main"], #main, .main');
                const mainText = main ? (main.innerText || '').trim() : '';

                return { headings, bodyText, mainText };
            }
        """)
    except Exception:
        return {}


def take_screenshot(page, output_dir: Path, label: str) -> str:
    """スクリーンショットを保存"""
    path = output_dir / f"screenshot_{label}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


def fetch_goal_tree(config: dict) -> dict:
    """
    メインの取得処理:
    ログイン → 対象ページ移動 → データ抽出
    """
    start_url: str = config["start_url"]
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    timeout = config["timeout_ms"]
    wait_ms = config["wait_after_load_ms"]

    with sync_playwright() as p:
        # セッションファイルが存在する場合は再利用
        if SESSION_PATH.exists():
            print(f"セッションを読み込み中: {SESSION_PATH}")
            context = p.chromium.launch(headless=config["headless"]).new_context(
                storage_state=str(SESSION_PATH)
            )
        else:
            print("セッションファイルなし → 手動ログインを起動")
            login_manually(p, start_url)
            context = p.chromium.launch(headless=config["headless"]).new_context(
                storage_state=str(SESSION_PATH)
            )

        # ブラウザを再起動（launch を context 外で管理するため再構成）
        context.close()

        browser = p.chromium.launch(headless=config["headless"])
        context = browser.new_context(
            storage_state=str(SESSION_PATH) if SESSION_PATH.exists() else None,
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        # APIレスポンスをインターセプト
        api_data = intercept_api_responses(page)

        def visit_page(url: str, extra_wait: int = 0):
            """1ページを開いてAPIを収集する共通処理"""
            print(f"  → {url}")
            page.goto(url, wait_until="networkidle", timeout=timeout)
            page.wait_for_timeout(wait_ms + extra_wait)
            # サイドバーのスクロールで遅延読み込みをトリガー
            try:
                page.evaluate("""() => {
                    const sidebar = document.querySelector('nav, aside, [class*="sidebar"], [class*="Sidebar"], [class*="tree"], [class*="Tree"]');
                    if (sidebar) sidebar.scrollTop = 9999;
                }""")
                page.wait_for_timeout(2000)
            except Exception:
                pass

        # 1ページ目: todo/execution（組織全体のツリーが読み込まれる）
        print(f"ページを開いています: {start_url}")
        page.goto(start_url, wait_until="networkidle", timeout=timeout)

        # 認証チェック
        if not is_authenticated(page):
            print("セッション期限切れ → 再ログインが必要です")
            context.close()
            browser.close()
            SESSION_PATH.unlink(missing_ok=True)
            login_manually(p, start_url)
            browser = p.chromium.launch(headless=config["headless"])
            context = browser.new_context(
                storage_state=str(SESSION_PATH),
                viewport={"width": 1440, "height": 900},
            )
            page = context.new_page()
            api_data = intercept_api_responses(page)
            page.goto(start_url, wait_until="networkidle", timeout=timeout)

        print(f"現在のURL: {page.url}")
        print(f"データ読み込み待機中 ({wait_ms}ms)...")
        page.wait_for_timeout(wait_ms)

        # 2ページ目: 最上位ゴールページを開いてサイドバーのAPIを収集
        # サイドバーには全組織ゴールが表示されるため長めに待機
        print("最上位ゴールページを開いてサイドバーAPIを収集中...")
        ROOT_GOAL_ID = "45e3a49b-4818-429d-936e-913d41b5d833"
        ORG_ID = "79e5df38-ffbb-4a95-9d41-f5968427c653"
        # 甲原海人の担当ゴールID（固定）
        KOHARA_GOAL_ID = "69bbece5-9ff7-4f96-b7f8-0227d0560f9c"
        try:
            visit_page(f"https://www.addness.com/goals/{ROOT_GOAL_ID}", extra_wait=5000)
        except Exception as e:
            print(f"  スキップ: {e}")

        # サイドバーのAPIエンドポイント候補を追加で試す
        print("サイドバー用APIエンドポイントを探索中...")
        sidebar_candidates = [
            "/api/v1/team/objectives/tree",
            f"/api/v1/team/objectives/{ROOT_GOAL_ID}/sidebar",
            f"/api/v1/team/objectives/{ROOT_GOAL_ID}/full_tree",
            f"/api/v1/team/daily_focus_objectives/tree?depth=10",
            f"/api/v1/team/daily_focus_objectives/tree?all=true",
            "/api/v1/team/sidebar/tree",
            "/api/v1/team/navigation/tree",
        ]
        for ep in sidebar_candidates:
            try:
                resp = page.request.get(
                    f"https://www.addness.com{ep}",
                    headers={"Accept": "application/json"},
                )
                if resp.ok and "json" in resp.headers.get("content-type", ""):
                    body = resp.json()
                    items = body.get("data", body) if isinstance(body, dict) else body
                    count = len(items) if isinstance(items, list) else "dict"
                    print(f"  ✅ {ep}  [{count}件]")
                    api_data[ep] = body
            except Exception:
                pass

        # Playwrightのブラウザコンテキスト経由でAPIを直接呼び出す
        # （page.request は正しい認証ヘッダーを自動付与する）
        print("組織全体のゴールをAPIで取得中...")
        base = "https://www.addness.com"
        api_candidates = [
            f"/api/v1/team/objectives/{ROOT_GOAL_ID}/children",
            f"/api/v1/team/objectives?parentObjectiveId={ROOT_GOAL_ID}&limit=100",
            f"/api/v1/team/organizations/{ORG_ID}/objectives?limit=200",
            f"/api/v1/team/objectives/{ROOT_GOAL_ID}/subtree",
        ]
        for ep in api_candidates:
            try:
                resp = page.request.get(
                    base + ep,
                    headers={"Accept": "application/json"},
                )
                if resp.ok and "json" in resp.headers.get("content-type", ""):
                    body = resp.json()
                    items = body.get("data", body) if isinstance(body, dict) else body
                    count = len(items) if isinstance(items, list) else "dict"
                    print(f"  ✅ {ep}  [{count}件]")
                    api_data[ep] = body
                else:
                    print(f"  ✗ {ep}  [{resp.status}]")
            except Exception as e:
                print(f"  ✗ {ep}  [{e}]")

        # サイドバーのDOMを直接抽出（全ゴールタイトルを取得）
        print("サイドバーからゴールリストを直接抽出中...")
        sidebar_items = page.evaluate("""() => {
            const results = [];
            const seen = new Set();

            // サイドバーの全テキストノードを収集（ゴール名らしいもの）
            // Addnessのサイドバーは左パネルにある
            const allElements = document.querySelectorAll(
                'a[href*="/goals/"], li, [role="treeitem"], [class*="objective"], [class*="Objective"], [class*="goal"], [class*="Goal"]'
            );

            allElements.forEach(el => {
                const text = (el.innerText || el.textContent || '').trim().split('\\n')[0].trim();
                const href = el.href || el.getAttribute('href') || '';
                if (text && text.length > 3 && text.length < 100 && !seen.has(text)) {
                    const goalIdMatch = href.match(/goals\\/([a-f0-9-]{36})/);
                    seen.add(text);
                    results.push({
                        title: text,
                        goalId: goalIdMatch ? goalIdMatch[1] : null,
                        href: href,
                    });
                }
            });
            return results;
        }""")

        if sidebar_items:
            print(f"  サイドバー要素: {len(sidebar_items)} 件")
            api_data["/sidebar/goals"] = {"items": sidebar_items}
            for item in sidebar_items[:10]:
                print(f"    - {item['title'][:50]}")

        # === サイドバーを展開してより多くのゴールを取得 ===
        print("サイドバーを展開中...")
        for _ in range(5):
            try:
                expanded = page.evaluate("""() => {
                    let n = 0;
                    document.querySelectorAll(
                        'button[aria-expanded="false"], [data-expanded="false"], ' +
                        '[class*="expand"]:not([aria-expanded="true"]), ' +
                        '[class*="chevron"], [class*="arrow"], [class*="caret"]'
                    ).forEach(el => {
                        try { el.click(); n++; } catch(e) {}
                    });
                    return n;
                }""")
                if expanded == 0:
                    break
                page.wait_for_timeout(800)
            except Exception:
                break

        # 展開後の全ゴールリンクを取得
        all_goal_links = page.evaluate("""() => {
            const seen = new Set();
            const results = [];
            document.querySelectorAll('a[href*="/goals/"]').forEach(a => {
                const m = (a.href || '').match(/goals\\/([a-f0-9-]{36})/);
                if (!m) return;
                const goalId = m[1];
                if (seen.has(goalId)) return;
                seen.add(goalId);
                const text = (a.innerText || a.textContent || '').trim().split('\\n')[0].trim();
                if (text && text.length > 2) results.push({ title: text, goalId, href: a.href });
            });
            return results;
        }""")
        if all_goal_links:
            api_data["/sidebar/all_links"] = {"items": all_goal_links}
            print(f"  展開後ゴールリンク: {len(all_goal_links)} 件")

        # === 各ゴールページを巡回してAPIをキャプチャ ===
        # サイドバーで発見した全ゴールIDを対象にする
        visited_ids = {ROOT_GOAL_ID}
        all_discovered_ids = [
            item["goalId"] for item in all_goal_links
            if item.get("goalId") and item["goalId"] not in visited_ids
        ]
        # フォールバック: 展開前のリストも使う
        if not all_discovered_ids:
            all_discovered_ids = [
                item["goalId"] for item in sidebar_items
                if item.get("goalId") and item["goalId"] not in visited_ids
            ]

        # サイドバーゴール（各メンバー担当ゴール）のpreviewをAPIで直接取得
        # サイドバー展開後 = all_discovered_ids が確定した後に実行
        print("サイドバーゴールのpreviewをAPIで直接取得中...")
        counts_key = f"/api/v1/team/objectives/{ROOT_GOAL_ID}/unresolved_comments_counts"
        counts_data = api_data.get(counts_key, {}).get("data", [])
        counts_ids = [item.get("id") for item in counts_data if item.get("id")]
        sidebar_direct_ids = list(dict.fromkeys(all_discovered_ids[:40] + counts_ids))
        for obj_id in sidebar_direct_ids:
            ep = f"/api/v1/team/objectives/{obj_id}/preview"
            if ep in api_data:
                continue
            try:
                resp = page.request.get(
                    base + ep,
                    headers={"Accept": "application/json"},
                )
                if resp.ok and "json" in resp.headers.get("content-type", ""):
                    api_data[ep] = resp.json()
                    d = api_data[ep].get("data", api_data[ep])
                    title = d.get("title", "")[:35] if isinstance(d, dict) else ""
                    n_ch = len(d.get("children", [])) if isinstance(d, dict) else 0
                    print(f"  ✅ {title} ({n_ch}children)")
            except Exception:
                pass
        print(f"  preview取得: {len([k for k in api_data if '/preview' in k and '/objectives/' in k])} 件")

        # === 甲原海人担当ゴール優先取得（直接ページ訪問）===
        # page.request.get() は認証の関係で機能しないため、ページ訪問でinterceptorにキャプチャさせる
        print(f"\n甲原海人担当ゴール優先取得中 ({KOHARA_GOAL_ID[:8]})...")
        kohara_visited = set()
        kohara_visited.add(KOHARA_GOAL_ID)

        def visit_goal_for_preview(goal_id: str, label: str = "") -> list:
            """ゴールページを訪問しpreviewをキャプチャ。子ゴールIDリストを返す"""
            preview_key = f"/api/v1/team/objectives/{goal_id}/preview"
            try:
                page.goto(
                    f"https://www.addness.com/goals/{goal_id}",
                    wait_until="networkidle",
                    timeout=timeout,
                )
                page.wait_for_timeout(2000)
                preview = api_data.get(preview_key, {})
                d = preview.get("data", preview) if isinstance(preview, dict) else {}
                children = d.get("children", []) if isinstance(d, dict) else []
                title = d.get("title", goal_id[:8]) if isinstance(d, dict) else goal_id[:8]
                print(f"  {label}✅ {title[:40]} ({len(children)}子)")
                return [c.get("id") for c in children if isinstance(c, dict) and c.get("id")]
            except Exception as e:
                print(f"  {label}エラー ({goal_id[:8]}): {e}")
                return []

        # 甲原海人のゴールページを訪問してpreviewをキャプチャ → 26人の子ゴールIDを取得
        child_ids = visit_goal_for_preview(KOHARA_GOAL_ID, "甲原: ")
        print(f"  甲原海人の子ゴール: {len(child_ids)}件")

        # 子ゴールをすべて訪問してpreviewをキャプチャ
        for i, cid in enumerate(child_ids):
            if cid in kohara_visited:
                continue
            kohara_visited.add(cid)
            gc_ids = visit_goal_for_preview(cid, f"[{i+1}/{len(child_ids)}] ")
            # 孫ゴール（3階層目）の descriptions が必要な場合は訪問
            for j, gcid in enumerate(gc_ids):
                if gcid in kohara_visited:
                    continue
                kohara_visited.add(gcid)
                visit_goal_for_preview(gcid, f"  孫[{j+1}/{len(gc_ids)}] ")

        kohara_total = len([k for k in api_data if "/preview" in k and "/objectives/" in k])
        print(f"  甲原海人サブツリー取得完了 (preview合計: {kohara_total}件)")

        print(f"\n各ゴールページを巡回中 ({min(len(all_discovered_ids), 40)}件)...")
        per_goal_links = {}

        for idx, goal_id in enumerate(all_discovered_ids[:40]):
            goal_url = f"https://www.addness.com/goals/{goal_id}"
            print(f"  [{idx+1}/{min(len(all_discovered_ids), 40)}] {goal_id[:8]}...")

            before_keys = set(api_data.keys())
            try:
                page.goto(goal_url, wait_until="networkidle", timeout=timeout)
                page.wait_for_timeout(1500)

                new_keys = set(api_data.keys()) - before_keys
                interesting = [k for k in new_keys if any(t in k for t in ["tree", "children", "objective", "goal"])]
                if interesting:
                    print(f"    新規API: {interesting[:3]}")

                # preview を ブラウザ内 fetch() で取得（認証ヘッダーが自動付与される）
                preview_ep = f"/api/v1/team/objectives/{goal_id}/preview"
                if preview_ep not in api_data:
                    try:
                        preview_body = page.evaluate(f"""async () => {{
                            const r = await fetch('{preview_ep}', {{
                                headers: {{ 'Accept': 'application/json' }}
                            }});
                            if (!r.ok) return null;
                            return await r.json();
                        }}""")
                        if preview_body and isinstance(preview_body, dict):
                            api_data[preview_ep] = preview_body
                            d = preview_body.get("data", preview_body)
                            title = d.get("title", "") if isinstance(d, dict) else ""
                            children_count = len(d.get("children", [])) if isinstance(d, dict) else 0
                            print(f"    ✅ preview [{children_count}children] {title[:25]}")
                    except Exception as e:
                        pass

                # このページのメインコンテンツ内のゴールリンクを取得（サイドバー除く）
                main_links = page.evaluate("""() => {
                    const seen = new Set();
                    const results = [];
                    // メインコンテンツ優先、なければ全ページ
                    const container = document.querySelector(
                        'main, [role="main"], [class*="content"], [class*="Content"], ' +
                        '[class*="main"], [class*="Main"]'
                    ) || document.body;
                    container.querySelectorAll('a[href*="/goals/"]').forEach(a => {
                        const m = (a.href || '').match(/goals\\/([a-f0-9-]{36})/);
                        if (!m) return;
                        const id = m[1];
                        if (seen.has(id)) return;
                        seen.add(id);
                        const text = (a.innerText || a.textContent || '').trim().split('\\n')[0].trim();
                        if (text && text.length > 2) results.push({ title: text, goalId: id });
                    });
                    return results;
                }""")
                if main_links:
                    per_goal_links[goal_id] = main_links
                    print(f"    DOM: {len(main_links)}件のリンク")

            except Exception as e:
                print(f"    エラー: {e}")

        if per_goal_links:
            api_data["/goal_pages/children_links"] = per_goal_links
            print(f"\nゴールページ巡回完了: {len(per_goal_links)}ページ")

        # === 既存previewのchildren IDをページ訪問でpreviewを追加取得 ===
        # ページを訪問するとブラウザが自動で /preview を呼ぶため interceptor が確実にキャプチャできる
        print("\n担当ゴールの子ゴールページを訪問してpreview取得中...")

        # 全previewのchildren IDを収集（まだ自身のpreviewがないもの）
        # サイドバーゴールの direct children を優先してpreviewを取得する
        already_visited = set(visited_ids)
        already_visited.add(ROOT_GOAL_ID)
        for gid in all_discovered_ids[:40]:
            already_visited.add(gid)

        def collect_child_ids_from_preview(key: str) -> list:
            val = api_data.get(key, {})
            d = val.get("data", val) if isinstance(val, dict) else val
            ids = []
            if isinstance(d, dict):
                for c in d.get("children", []):
                    cid = c.get("id") if isinstance(c, dict) else None
                    title = c.get("title", "") if isinstance(c, dict) else ""
                    if (
                        cid
                        and title
                        and cid not in already_visited
                        and f"/api/v1/team/objectives/{cid}/preview" not in api_data
                    ):
                        ids.append(cid)
                        already_visited.add(cid)
            return ids

        # サイドバーゴール（各メンバーの担当ゴール）の子を優先
        priority_ids = []
        other_ids = []
        sidebar_goal_ids = {
            item["goalId"]
            for item in api_data.get("/sidebar/all_links", {}).get("items", [])
            if item.get("goalId")
        }
        for key in api_data:
            if "/preview" not in key or "/objectives/" not in key:
                continue
            # keyからgoal IDを抽出
            parts = key.rstrip("/").split("/")
            gid = next((p for p in parts if len(p) == 36 and p.count("-") == 4), None)
            child_ids = collect_child_ids_from_preview(key)
            if gid and gid in sidebar_goal_ids:
                priority_ids.extend(child_ids)  # サイドバーゴールの子を優先
            else:
                other_ids.extend(child_ids)

        extra_ids_to_visit = list(dict.fromkeys(priority_ids + other_ids))[:60]
        print(f"  追加訪問対象: {len(extra_ids_to_visit)}件")

        for idx, goal_id in enumerate(extra_ids_to_visit):
            goal_url = f"https://www.addness.com/goals/{goal_id}"
            print(f"  [extra {idx+1}/{len(extra_ids_to_visit)}] {goal_id[:8]}...")
            before_keys = set(api_data.keys())
            try:
                page.goto(goal_url, wait_until="networkidle", timeout=timeout)
                page.wait_for_timeout(1200)
                new_keys = set(api_data.keys()) - before_keys
                preview_keys = [k for k in new_keys if k.endswith("/preview") and "/objectives/" in k]
                if preview_keys:
                    for pk in preview_keys:
                        d = api_data[pk].get("data", api_data[pk])
                        title = d.get("title", "")[:35] if isinstance(d, dict) else ""
                        n_ch = len(d.get("children", [])) if isinstance(d, dict) else 0
                        print(f"    ✅ {title} ({n_ch}children)")
                # メインコンテンツのDOMリンクも収集
                main_links = page.evaluate("""() => {
                    const seen = new Set();
                    const results = [];
                    const container = document.querySelector(
                        'main, [role="main"], [class*="content"], [class*="Content"], ' +
                        '[class*="main"], [class*="Main"]'
                    ) || document.body;
                    container.querySelectorAll('a[href*="/goals/"]').forEach(a => {
                        const m = (a.href || '').match(/goals\\/([a-f0-9-]{36})/);
                        if (!m) return;
                        const id = m[1];
                        if (seen.has(id)) return;
                        seen.add(id);
                        const text = (a.innerText || a.textContent || '').trim().split('\\n')[0].trim();
                        if (text && text.length > 2) results.push({ title: text, goalId: id });
                    });
                    return results;
                }""")
                if main_links:
                    per_goal_links[goal_id] = main_links
            except Exception as e:
                print(f"    エラー: {e}")

        total_previews = len([k for k in api_data if "/preview" in k and "/objectives/" in k])
        print(f"  preview合計: {total_previews}件")

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        # スクリーンショット保存
        screenshot_path = take_screenshot(page, output_dir, ts)
        print(f"スクリーンショット: {screenshot_path}")

        # 各種データ抽出
        print("データ抽出中...")
        next_data = extract_next_data(page)
        dom_tasks = extract_dom_tasks(page)
        page_text = extract_page_text_structure(page)

        result = {
            "fetched_at": datetime.now().isoformat(),
            "source_url": start_url,
            "start_url": start_url,
            "api_responses": api_data,
            "next_data": next_data,
            "dom_tasks": dom_tasks,
            "page_text": page_text,
        }

        context.close()
        browser.close()
        return result


def save_result(result: dict, output_dir: Path):
    """結果をJSONファイルに保存"""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"addness_{ts}.json"
    latest_path = output_dir / "latest.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    with open(latest_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2, default=str)

    print(f"保存: {output_path}")
    print(f"最新: {latest_path}")
    return output_path


def summarize_result(result: dict):
    """取得結果のサマリーを表示"""
    print("\n" + "=" * 60)
    print("【取得結果サマリー】")
    print(f"取得時刻: {result['fetched_at']}")
    print(f"URL: {result['source_url']}")
    print(f"APIレスポンス数: {len(result.get('api_responses', {}))}")
    print(f"DOM要素数: {len(result.get('dom_tasks', []))}")

    if result.get("api_responses"):
        print("\nキャプチャしたAPIエンドポイント:")
        for ep in list(result["api_responses"].keys())[:20]:
            print(f"  - {ep}")

    if result.get("page_text", {}).get("headings"):
        print("\nページ見出し:")
        for h in result["page_text"]["headings"][:10]:
            print(f"  [{h['level']}] {h['text']}")

    print("=" * 60)


def main():
    print(f"[{datetime.now().isoformat()}] Addness Fetcher 開始")

    config = load_config()

    # 設定ファイルが存在しない場合は保存
    if not CONFIG_PATH.exists():
        save_config(config)
        print(f"設定ファイルを作成しました: {CONFIG_PATH}")

    output_dir = Path(config["output_dir"])

    try:
        result = fetch_goal_tree(config)
        output_path = save_result(result, output_dir)
        summarize_result(result)
        print(f"\n完了: {output_path}")

    except PlaywrightTimeoutError as e:
        logger.error("Addness取得タイムアウト", extra={
            "error": {"type": "PlaywrightTimeoutError", "message": str(e)},
        })
        print(f"タイムアウトエラー: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception("Addness取得エラー", extra={
            "error": {"type": type(e).__name__, "message": str(e)},
        })
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    print(f"[{datetime.now().isoformat()}] 完了")


if __name__ == "__main__":
    main()
