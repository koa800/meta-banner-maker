#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OWNER = "koa800"
REPO = "share-pages"
REPO_URL = f"https://github.com/{OWNER}/{REPO}.git"
BASE_URL = f"https://{OWNER}.github.io/{REPO}"
CLONE_DIR = Path("/tmp/share-pages")
REGISTRY_PATH = Path("pages.json")
COMMIT_NAME = "koa800"
COMMIT_EMAIL = "koa800@users.noreply.github.com"


def run(cmd: list[str], *, cwd: Path | None = None, capture: bool = False) -> str:
    result = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(cmd)}\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result.stdout.strip() if capture else ""


def repo_exists() -> bool:
    result = subprocess.run(
        ["gh", "repo", "view", f"{OWNER}/{REPO}"],
        text=True,
        capture_output=True,
    )
    return result.returncode == 0


def ensure_repo() -> None:
    if repo_exists():
        return
    run(
        [
            "gh",
            "repo",
            "create",
            f"{OWNER}/{REPO}",
            "--public",
            "--description",
            "Shared static pages for Addness operations",
        ]
    )


def ensure_clone() -> None:
    if CLONE_DIR.exists() and not (CLONE_DIR / ".git").exists():
        shutil.rmtree(CLONE_DIR)

    if not CLONE_DIR.exists():
        run(["git", "clone", REPO_URL, str(CLONE_DIR)])

    has_commit = (
        subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=CLONE_DIR,
            text=True,
            capture_output=True,
        ).returncode
        == 0
    )

    if has_commit:
        run(["git", "checkout", "main"], cwd=CLONE_DIR)
        run(["git", "pull", "--ff-only", "origin", "main"], cwd=CLONE_DIR)
    else:
        run(["git", "checkout", "-B", "main"], cwd=CLONE_DIR)


def ensure_site_scaffold() -> None:
    (CLONE_DIR / ".nojekyll").write_text("", encoding="utf-8")
    readme = CLONE_DIR / "README.md"
    if not readme.exists():
        readme.write_text(
            "# share-pages\n\n公開用の静的ページ置き場です。\n",
            encoding="utf-8",
        )


def copy_source(source: Path, slug: str) -> None:
    destination = CLONE_DIR / slug
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)

    if source.is_file():
        shutil.copy2(source, destination / "index.html")
        return

    index_file = source / "index.html"
    if not index_file.exists():
        raise RuntimeError(f"directory source must contain index.html: {source}")

    for child in source.iterdir():
        target = destination / child.name
        if child.is_dir():
            shutil.copytree(child, target)
        else:
            shutil.copy2(child, target)


def load_registry() -> list[dict]:
    registry_file = CLONE_DIR / REGISTRY_PATH
    if not registry_file.exists():
        return []
    return json.loads(registry_file.read_text(encoding="utf-8"))


def save_registry(entries: list[dict]) -> None:
    registry_file = CLONE_DIR / REGISTRY_PATH
    ordered = sorted(entries, key=lambda item: item["updated_at"], reverse=True)
    registry_file.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def update_registry(slug: str, title: str, summary: str, source: Path) -> None:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    entries = load_registry()
    current = next((entry for entry in entries if entry["slug"] == slug), None)

    if current is None:
        entries.append(
            {
                "slug": slug,
                "title": title,
                "summary": summary,
                "published_at": now,
                "updated_at": now,
                "url": f"{BASE_URL}/{slug}/",
                "source_path": str(source),
            }
        )
    else:
        current["title"] = title
        current["summary"] = summary
        current["updated_at"] = now
        current["url"] = f"{BASE_URL}/{slug}/"
        current["source_path"] = str(source)

    save_registry(entries)


def render_homepage() -> None:
    entries = load_registry()
    cards = []
    for entry in entries:
        cards.append(
            f"""
            <article class="card">
              <p class="meta">slug: <code>{html.escape(entry['slug'])}</code></p>
              <h2>{html.escape(entry['title'])}</h2>
              <p class="summary">{html.escape(entry['summary'] or '説明は未設定です。')}</p>
              <div class="footer">
                <span>最終更新: {html.escape(entry['updated_at'].replace('T', ' '))}</span>
                <a href="{html.escape(entry['url'])}">ページを開く</a>
              </div>
            </article>
            """
        )

    card_html = "\n".join(cards) if cards else "<p class=\"empty\">公開ページはまだありません。</p>"

    homepage = f"""<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>共有ページ一覧</title>
  <style>
    :root {{
      --bg: #f4f7f1;
      --card: rgba(255,255,255,.9);
      --line: #d7ded1;
      --text: #18211b;
      --muted: #617061;
      --accent: #1f6a4a;
      --shadow: 0 20px 48px rgba(18, 31, 22, .08);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 20px 14px 48px;
      background:
        radial-gradient(circle at top left, rgba(31, 106, 74, .08), transparent 34%),
        linear-gradient(180deg, #fbfcf9 0%, var(--bg) 100%);
      color: var(--text);
      font: 15px/1.7 -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", sans-serif;
    }}
    .wrap {{
      max-width: 1100px;
      margin: 0 auto;
    }}
    .hero {{
      padding: 28px 22px;
      border: 1px solid var(--line);
      border-radius: 30px;
      background: linear-gradient(180deg, rgba(255,255,255,.98), rgba(250,252,248,.96));
      box-shadow: var(--shadow);
      margin-bottom: 18px;
    }}
    .eyebrow {{
      margin: 0 0 12px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: .08em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: clamp(32px, 8vw, 52px);
      line-height: 1.04;
      letter-spacing: -.04em;
    }}
    .lead {{
      margin: 0;
      max-width: 760px;
      color: var(--muted);
      font-size: 16px;
    }}
    .grid {{
      display: grid;
      gap: 14px;
      grid-template-columns: 1fr;
    }}
    .card {{
      padding: 20px 18px;
      border: 1px solid var(--line);
      border-radius: 26px;
      background: var(--card);
      box-shadow: var(--shadow);
    }}
    .card h2 {{
      margin: 0 0 10px;
      font-size: 22px;
      line-height: 1.2;
      letter-spacing: -.03em;
    }}
    .meta {{
      margin: 0 0 12px;
      color: var(--muted);
      font-size: 13px;
    }}
    .summary {{
      margin: 0;
      color: var(--text);
    }}
    .footer {{
      margin-top: 18px;
      display: flex;
      flex-direction: column;
      gap: 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    a {{
      color: var(--accent);
      font-weight: 700;
      text-decoration: none;
    }}
    code {{
      padding: 2px 6px;
      border-radius: 999px;
      background: rgba(31, 106, 74, .08);
      color: var(--accent);
    }}
    .empty {{
      padding: 24px 18px;
      border: 1px dashed var(--line);
      border-radius: 24px;
      background: rgba(255,255,255,.72);
      color: var(--muted);
    }}
    @media (min-width: 720px) {{
      body {{ padding: 28px 22px 64px; font-size: 16px; }}
      .hero {{ padding: 34px 30px; }}
      .grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .footer {{ flex-direction: row; justify-content: space-between; align-items: center; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <p class="eyebrow">Public Pages</p>
      <h1>共有ページ一覧</h1>
      <p class="lead">LP、修正ガイド、確認メモなどを、そのままURLで共有するための公開ページ置き場です。公開元は cursor 側のソースHTMLで管理し、ここは配信用の箱として使います。</p>
    </section>
    <section class="grid">
      {card_html}
    </section>
  </div>
</body>
</html>
"""
    (CLONE_DIR / "index.html").write_text(homepage, encoding="utf-8")


def commit_and_push(slug: str) -> None:
    status = run(["git", "status", "--short"], cwd=CLONE_DIR, capture=True)
    if not status:
        return
    run(["git", "add", "."], cwd=CLONE_DIR)
    run(
        [
            "git",
            "-c",
            f"user.name={COMMIT_NAME}",
            "-c",
            f"user.email={COMMIT_EMAIL}",
            "commit",
            "-m",
            f"公開ページ更新: {slug}",
        ],
        cwd=CLONE_DIR,
    )
    run(["git", "push", "-u", "origin", "main"], cwd=CLONE_DIR)


def ensure_pages_enabled() -> str:
    existing = subprocess.run(
        ["gh", "api", f"repos/{OWNER}/{REPO}/pages", "--jq", ".html_url"],
        text=True,
        capture_output=True,
    )
    if existing.returncode == 0:
        return existing.stdout.strip()

    created = subprocess.run(
        [
            "gh",
            "api",
            "-X",
            "POST",
            f"repos/{OWNER}/{REPO}/pages",
            "-F",
            "source[branch]=main",
            "-F",
            "source[path]=/",
            "--jq",
            ".html_url",
        ],
        text=True,
        capture_output=True,
    )
    if created.returncode == 0:
        return created.stdout.strip()
    if "already exists" in (created.stderr or ""):
        return BASE_URL
    raise RuntimeError(
        f"failed to enable GitHub Pages\nstdout:\n{created.stdout}\nstderr:\n{created.stderr}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="静的HTMLをGitHub Pagesへ公開する")
    parser.add_argument("--source", required=True, help="公開元のHTMLファイルまたはindex.htmlを含むディレクトリ")
    parser.add_argument("--slug", required=True, help="公開URLに使うslug")
    parser.add_argument("--title", required=True, help="一覧に表示するタイトル")
    parser.add_argument("--summary", default="", help="一覧に表示する短い説明")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    if not source.exists():
        raise RuntimeError(f"source not found: {source}")

    ensure_repo()
    ensure_clone()
    ensure_site_scaffold()
    copy_source(source, args.slug)
    update_registry(args.slug, args.title, args.summary, source)
    render_homepage()
    commit_and_push(args.slug)
    pages_url = ensure_pages_enabled().rstrip("/")

    print(f"一覧URL: {pages_url}/")
    print(f"公開URL: {BASE_URL}/{args.slug}/")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
