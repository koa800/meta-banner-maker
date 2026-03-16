#!/usr/bin/env python3
"""導線ツールの live readiness をまとめて確認する。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import warnings

import requests

try:
    from urllib3.exceptions import NotOpenSSLWarning
except Exception:  # pragma: no cover
    NotOpenSSLWarning = None

if NotOpenSSLWarning is not None:
    warnings.filterwarnings("ignore", category=NotOpenSSLWarning)

from lstep_auth import auth_probe as lstep_auth_probe
from mailchimp_journey_snapshot import build_session as build_mailchimp_session
from mailchimp_journey_snapshot import list_journeys


ROOT = Path(__file__).resolve().parents[2]
CDP_VERSION_URL = "http://127.0.0.1:9224/json/version"
SHORTIO_CREDS_PATH = ROOT / "System" / "credentials" / "shortio_api_key.json"
UTAGE_CREDS_PATH = ROOT / "System" / "credentials" / "utage.json"
LSTEP_CREDS_PATH = ROOT / "System" / "credentials" / "lstep.json"
MAILCHIMP_CREDS_PATH = ROOT / "System" / "credentials" / "mailchimp_login.json"
ZAPIER_CREDS_PATH = ROOT / "System" / "credentials" / "zapier.json"


def probe_cdp() -> dict[str, Any]:
    try:
        response = requests.get(CDP_VERSION_URL, timeout=3)
        response.raise_for_status()
        payload = response.json()
        return {
            "alive": True,
            "browser": payload.get("Browser"),
            "user_agent": payload.get("User-Agent"),
        }
    except Exception as exc:
        return {
            "alive": False,
            "error": str(exc),
        }


def probe_mailchimp_api() -> dict[str, Any]:
    try:
        session, base_url = build_mailchimp_session()
        journeys = list_journeys(session, base_url, count=3)
        return {
            "alive": True,
            "journey_count_sample": len(journeys),
            "sample_names": [item.get("journey_name") for item in journeys[:3]],
        }
    except Exception as exc:
        return {
            "alive": False,
            "error": str(exc),
        }


def probe_shortio_api() -> dict[str, Any]:
    if not SHORTIO_CREDS_PATH.exists():
        return {"alive": False, "error": "missing shortio_api_key.json"}
    try:
        creds = json.loads(SHORTIO_CREDS_PATH.read_text())
        api_key = creds.get("api_key") or creds.get("key")
        if not api_key:
            return {"alive": False, "error": "api_key missing"}
        response = requests.get(
            "https://api.short.io/api/domains",
            headers={"authorization": api_key},
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        return {
            "alive": True,
            "domain_count": len(payload),
            "sample_domains": [item.get("hostname") for item in payload[:3]],
        }
    except Exception as exc:
        return {
            "alive": False,
            "error": str(exc),
        }


def probe_credential_files() -> dict[str, Any]:
    return {
        "lstep_json": LSTEP_CREDS_PATH.exists(),
        "utage_json": UTAGE_CREDS_PATH.exists(),
        "mailchimp_login_json": MAILCHIMP_CREDS_PATH.exists(),
        "zapier_json": ZAPIER_CREDS_PATH.exists(),
        "shortio_api_key_json": SHORTIO_CREDS_PATH.exists(),
    }


def build_readiness() -> dict[str, Any]:
    cdp = probe_cdp()
    lstep = lstep_auth_probe(referer="https://manager.linestep.net/line/action")
    mailchimp = probe_mailchimp_api()
    shortio = probe_shortio_api()
    creds = probe_credential_files()

    return {
        "cdp": cdp,
        "credentials": creds,
        "lstep": {
            "auth_alive": lstep.get("auth_alive"),
            "working_source": lstep.get("working_source"),
            "account_name": ((lstep.get("authenticated_context") or {}).get("account_name")),
            "account_id": ((lstep.get("authenticated_context") or {}).get("account_id")),
            "cdp_alive": (lstep.get("cdp") or {}).get("alive"),
            "next_action": lstep.get("next_action"),
        },
        "utage": {
            "cdp_required": True,
            "cdp_alive": cdp.get("alive"),
            "credentials_present": creds["utage_json"],
            "ready_for_live": bool(cdp.get("alive") and creds["utage_json"]),
        },
        "mailchimp": {
            "api_alive": mailchimp.get("alive"),
            "credentials_present": creds["mailchimp_login_json"],
            "ready_for_api": bool(mailchimp.get("alive")),
            "sample_names": mailchimp.get("sample_names"),
        },
        "shortio": {
            "api_alive": shortio.get("alive"),
            "credentials_present": creds["shortio_api_key_json"],
            "ready_for_api": bool(shortio.get("alive")),
            "sample_domains": shortio.get("sample_domains"),
        },
        "zapier": {
            "cdp_required": True,
            "cdp_alive": cdp.get("alive"),
            "credentials_present": creds["zapier_json"],
            "ready_for_live": bool(cdp.get("alive") and creds["zapier_json"]),
        },
        "summary": {
            "live_browser_ready": bool(cdp.get("alive")),
            "api_ready_count": sum(
                1
                for item in (
                    bool(mailchimp.get("alive")),
                    bool(shortio.get("alive")),
                    bool(lstep.get("auth_alive")),
                )
                if item
            ),
        },
    }


def main() -> None:
    print(json.dumps(build_readiness(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
