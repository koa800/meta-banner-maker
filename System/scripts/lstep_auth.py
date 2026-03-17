#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import browser_cookie3
import requests
from bs4 import BeautifulSoup
from requests.cookies import RequestsCookieJar, create_cookie

BASE_URL = "https://manager.linestep.net"
LOGIN_URL = f"{BASE_URL}/account/login"
DEFAULT_PROBE_URL = f"{BASE_URL}/api/actions?page=1"
DEFAULT_CDP_HTTP_URL = "http://127.0.0.1:9224"
DEFAULT_CDP_URL = "http://127.0.0.1:9224/json/version"


def normalize_text(value: str, limit: int = 160) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text[:limit]


def cookie_sources() -> list[dict[str, Any]]:
    home = Path.home()
    return [
        {
            "label": "chrome_cdp_live",
            "kind": "cdp",
            "cdp_url": DEFAULT_CDP_HTTP_URL,
        },
        {
            "label": "chrome_auto",
            "kind": "auto",
        },
        {
            "label": "chrome_default",
            "kind": "cookie_file",
            "path": home / "Library/Application Support/Google/Chrome/Default/Cookies",
        },
        {
            "label": "chrome_profile_9",
            "kind": "cookie_file",
            "path": home / "Library/Application Support/Google/Chrome/Profile 9/Cookies",
        },
        {
            "label": "chrome_debug_default",
            "kind": "cookie_file",
            "path": home / "Library/Application Support/Google/ChromeDebug/Default/Cookies",
        },
    ]


def load_cdp_cookie_jar(cdp_url: str) -> RequestsCookieJar:
    node_script = r"""
const http = require('http');
const cdpUrl = process.argv[1];
async function fetchVersion(url) {
  return await new Promise((resolve, reject) => {
    http.get(url.replace(/\/$/, '') + '/json/version', (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => resolve(JSON.parse(data)));
    }).on('error', reject);
  });
}
(async () => {
  const version = await fetchVersion(cdpUrl);
  const ws = new WebSocket(version.webSocketDebuggerUrl);
  ws.onopen = () => ws.send(JSON.stringify({id: 1, method: 'Storage.getCookies'}));
  ws.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    if (payload.id !== 1) return;
    process.stdout.write(JSON.stringify(payload.result.cookies || []));
    ws.close();
  };
  ws.onerror = (event) => {
    const message = event && event.message ? event.message : 'CDP websocket error';
    console.error(message);
    process.exit(1);
  };
  ws.onclose = () => process.exit(0);
})().catch((error) => {
  console.error(String(error && error.message ? error.message : error));
  process.exit(1);
});
"""
    try:
        result = subprocess.run(
            ["node", "-e", node_script, cdp_url],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        raw_cookies = json.loads(result.stdout or "[]")
    except Exception as exc:
        raise RuntimeError(f"CDP cookie 取得に失敗しました: {exc}") from exc

    jar = RequestsCookieJar()
    for item in raw_cookies:
        domain = str(item.get("domain") or "")
        if "manager.linestep.net" not in domain:
            continue
        cookie = create_cookie(
            name=str(item.get("name") or ""),
            value=str(item.get("value") or ""),
            domain=domain,
            path=str(item.get("path") or "/"),
            secure=bool(item.get("secure")),
            expires=item.get("expires"),
        )
        jar.set_cookie(cookie)

    if not jar:
        raise RuntimeError("CDP cookie 取得結果が空でした")
    return jar


def load_cookie_jar(source: dict[str, Any]):
    if source.get("kind") == "cdp":
        return load_cdp_cookie_jar(str(source.get("cdp_url") or DEFAULT_CDP_HTTP_URL))
    if source.get("kind") == "auto":
        return browser_cookie3.chrome(domain_name="manager.linestep.net")
    path = source.get("path")
    if not isinstance(path, Path) or not path.exists():
        return None
    return browser_cookie3.chrome(cookie_file=str(path), domain_name="manager.linestep.net")


def build_session(referer: str, source: dict[str, Any]) -> requests.Session:
    jar = load_cookie_jar(source)
    if jar is None:
        raise RuntimeError(f"cookie source unavailable: {source.get('label')}")
    s = requests.Session()
    s.cookies = jar
    s.headers.update(
        {
            "X-Requested-With": "XMLHttpRequest",
            "Referer": referer,
            "User-Agent": "Mozilla/5.0",
        }
    )
    return s


def fetch_authenticated_context(s: requests.Session, page_url: str) -> dict[str, Any] | None:
    try:
        resp = s.get(page_url, timeout=60)
        resp.raise_for_status()
    except Exception:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    app = soup.select_one("liny-app")
    if not app:
        return None

    session_raw = app.get("v-bind:session")
    if not session_raw:
        return None

    try:
        session_data = json.loads(html.unescape(session_raw))
    except Exception:
        return None

    user = session_data.get("user") or {}
    account = session_data.get("account") or {}
    return {
        "user_id": user.get("id"),
        "user_name": user.get("name"),
        "account_id": account.get("id"),
        "account_name": account.get("name"),
        "page_url": page_url,
    }


def probe_source(source: dict[str, Any], referer: str, probe_url: str = DEFAULT_PROBE_URL) -> dict[str, Any]:
    result: dict[str, Any] = {
        "label": source.get("label"),
        "kind": source.get("kind"),
    }
    path = source.get("path")
    if isinstance(path, Path):
        result["cookie_file_exists"] = path.exists()
    try:
        s = build_session(referer=referer, source=source)
    except Exception as exc:
        result["error"] = str(exc)
        result["auth_alive"] = False
        return result

    try:
        api = s.get(probe_url, timeout=60, allow_redirects=False)
        result["api_status"] = api.status_code
        result["api_content_type"] = api.headers.get("content-type", "")
        result["api_location"] = api.headers.get("location")
        result["api_body_prefix"] = normalize_text(api.text)
        result["cookie_names"] = sorted({cookie.name for cookie in s.cookies if "linestep" in cookie.domain})
        is_json = "json" in (api.headers.get("content-type", "") or "").lower()
        json_ok = False
        if api.status_code == 200 and is_json:
            try:
                payload = api.json()
                json_ok = isinstance(payload, dict) and (
                    "data" in payload or "current_page" in payload or "last_page" in payload
                    or "notifications" in payload
                )
            except Exception:
                json_ok = False
        result["auth_alive"] = json_ok
        if json_ok:
            context = fetch_authenticated_context(s, referer)
            if context:
                result["authenticated_context"] = context
    except Exception as exc:
        result["error"] = str(exc)
        result["auth_alive"] = False
    return result


def parse_login_page() -> dict[str, Any]:
    resp = requests.get(LOGIN_URL, timeout=60)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    out: dict[str, Any] = {
        "login_url": LOGIN_URL,
        "status": resp.status_code,
        "trace_id": (soup.select_one('meta[name="lm-trace-id"]') or {}).get("content"),
        "csrf_token_present": bool((soup.select_one('meta[name="csrf-token"]') or {}).get("content")),
        "recaptcha_site_key_present": bool((soup.select_one('meta[name="recaptcha-site-key"]') or {}).get("content")),
    }

    app = soup.select_one("liny-app")
    if app:
        server_data_raw = app.get("v-bind:server-data")
        session_raw = app.get("v-bind:session")
        if server_data_raw:
            try:
                server_data = json.loads(html.unescape(server_data_raw))
                out["server_data"] = {
                    "serviceCode": server_data.get("serviceCode"),
                    "chatPlusId": server_data.get("chatPlusId"),
                    "manualRootWithSlash": server_data.get("manualRootWithSlash"),
                    "recaptcha": server_data.get("recaptcha"),
                }
            except Exception as exc:
                out["server_data_error"] = str(exc)
        if session_raw:
            try:
                session_data = json.loads(html.unescape(session_raw))
                user = session_data.get("user") or {}
                account = session_data.get("account") or {}
                out["session_summary"] = {
                    "user_id": user.get("id"),
                    "user_name": user.get("name"),
                    "account_id": account.get("id"),
                    "account_name": account.get("name"),
                }
            except Exception as exc:
                out["session_parse_error"] = str(exc)

    login_bundle_url = None
    main_bundle_url = None
    for script in soup.find_all("script", src=True):
        src = script.get("src") or ""
        if "login-" in src and src.endswith(".js"):
            login_bundle_url = src
            break
        if "/build/assets/main-" in src and src.endswith(".js"):
            main_bundle_url = src
    if not login_bundle_url and main_bundle_url:
        try:
            main_bundle = requests.get(main_bundle_url, timeout=60).text
            match = re.search(r'assets/(login-[A-Za-z0-9_-]+\.js)', main_bundle)
            if match:
                login_bundle_url = f"{BASE_URL}/build/{match.group(0)}"
        except Exception as exc:
            out["main_bundle_error"] = str(exc)
    if login_bundle_url:
        if login_bundle_url.startswith("/"):
            login_bundle_url = f"{BASE_URL}{login_bundle_url}"
        out["login_bundle_url"] = login_bundle_url
        try:
            bundle = requests.get(login_bundle_url, timeout=60).text
            out["form"] = {
                "action": "/account/login" if 'action:"/account/login"' in bundle else None,
                "method": "post" if 'method:"post"' in bundle else None,
                "fields": [field for field in ("_token", "name", "password") if f'name:"{field}"' in bundle],
            }
            marker = "const L=S(()=>"
            idx = bundle.find(marker)
            if idx != -1:
                out["submit_guard"] = bundle[idx : idx + 80]
        except Exception as exc:
            out["login_bundle_error"] = str(exc)

    return out


def probe_cdp(cdp_url: str = DEFAULT_CDP_URL) -> dict[str, Any]:
    try:
        response = requests.get(cdp_url, timeout=3)
        response.raise_for_status()
        payload = response.json()
        return {
            "alive": True,
            "webSocketDebuggerUrl": payload.get("webSocketDebuggerUrl"),
            "browser": payload.get("Browser"),
            "userAgent": payload.get("User-Agent"),
        }
    except Exception as exc:
        return {
            "alive": False,
            "error": str(exc),
        }


def build_recovery_priority(auth_alive: bool, cdp: dict[str, Any], login_page: dict[str, Any]) -> list[dict[str, Any]]:
    recaptcha = ((login_page.get("server_data") or {}).get("recaptcha") or {}).get("enabled")
    items: list[dict[str, Any]] = []
    if auth_alive:
        items.append(
            {
                "priority": 1,
                "label": "cookie 直利用",
                "why": "browser を開かずに API helper をそのまま再開できる",
                "command": "python3 System/scripts/lstep_auth.py",
            }
        )
    items.append(
        {
            "priority": len(items) + 1,
            "label": "CDP 既存セッション再利用",
            "why": "最も再現性が高く、reCAPTCHA を踏まずに復旧できる可能性がある",
            "command": "python3 System/scripts/lstep_login_helper.py --target https://manager.linestep.net/line/action",
            "precondition": "127.0.0.1:9224 が alive",
            "available_now": bool(cdp.get("alive")),
        }
    )
    items.append(
        {
            "priority": len(items) + 1,
            "label": "CDP + 自動入力 + checkbox 試行",
            "why": "未ログインでも ID/PW 入力と reCAPTCHA checkbox までは自動で寄せられる",
            "command": "python3 System/scripts/lstep_login_helper.py --target https://manager.linestep.net/line/action",
            "precondition": "127.0.0.1:9224 が alive",
            "available_now": bool(cdp.get("alive")),
        }
    )
    items.append(
        {
            "priority": len(items) + 1,
            "label": "手動 browser login",
            "why": "reCAPTCHA image challenge や CDP 不在でも最後に必ず復旧できる",
            "command": "Lステップに browser でログイン後、python3 System/scripts/lstep_auth.py を再実行",
            "precondition": "reCAPTCHA enabled=true" if recaptcha else "manual only",
            "available_now": True,
        }
    )
    return items


def auth_probe(referer: str, probe_url: str = DEFAULT_PROBE_URL) -> dict[str, Any]:
    source_results = [probe_source(source, referer=referer, probe_url=probe_url) for source in cookie_sources()]
    working = next((item for item in source_results if item.get("auth_alive")), None)
    login_page = parse_login_page()
    cdp = probe_cdp()
    return {
        "base_url": BASE_URL,
        "referer": referer,
        "probe_url": probe_url,
        "auth_alive": bool(working),
        "working_source": working.get("label") if working else None,
        "authenticated_context": working.get("authenticated_context") if working else None,
        "cdp": cdp,
        "sources": source_results,
        "login_page": login_page,
        "recovery_priority": build_recovery_priority(bool(working), cdp, login_page),
        "next_action": (
            "cookie source が全滅で、login page は reCAPTCHA enabled=true。"
            " current session の再取得には browser login が必要。"
        ),
    }


def build_authenticated_session(
    referer: str,
    probe_url: str = DEFAULT_PROBE_URL,
    expected_account_name: str | None = None,
) -> requests.Session:
    seen_contexts: list[str] = []
    for source in cookie_sources():
        result = probe_source(source, referer=referer, probe_url=probe_url)
        if result.get("auth_alive"):
            s = build_session(referer=referer, source=source)
            if expected_account_name:
                context = result.get("authenticated_context") or fetch_authenticated_context(s, referer)
                current_name = (context or {}).get("account_name")
                if current_name:
                    seen_contexts.append(str(current_name))
                if current_name != expected_account_name:
                    continue
            return s
    if expected_account_name and seen_contexts:
        raise RuntimeError(
            "Lステップ認証は生きていますが、対象 account 文脈が違います。"
            f" expected={expected_account_name} current={', '.join(sorted(set(seen_contexts)))}"
        )
    probe = parse_login_page()
    recaptcha = ((probe.get("server_data") or {}).get("recaptcha") or {}).get("enabled")
    message = (
        "Lステップ認証が切れています。"
        " `python3 System/scripts/lstep_auth.py` で状態を確認してください。"
    )
    if recaptcha:
        message += " current login は reCAPTCHA enabled=true のため、browser での再ログインが必要です。"
    raise RuntimeError(message)


def main() -> None:
    parser = argparse.ArgumentParser(description="LSTEP auth probe")
    parser.add_argument("--referer", default=f"{BASE_URL}/line/action", help="Probe referer")
    parser.add_argument("--probe-url", default=DEFAULT_PROBE_URL, help="Probe API URL")
    args = parser.parse_args()
    print(json.dumps(auth_probe(referer=args.referer, probe_url=args.probe_url), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
