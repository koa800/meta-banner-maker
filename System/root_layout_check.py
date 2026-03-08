#!/usr/bin/env python3
"""cursor root 直下の構成逸脱を検知する。"""

from pathlib import Path
import sys


ROOT_DIR = Path(__file__).resolve().parent.parent
ALLOWED_DIRS = {
    ".claude",
    ".cursor",
    ".git",
    ".vscode",
    "Master",
    "Project",
    "Skills",
    "System",
}
ALLOWED_FILES = {
    ".DS_Store",
    ".gitignore",
    ".gitmodules",
    "AGENTS.md",
    "CLAUDE.md",
    "pyproject.toml",
}


def collect_unexpected_entries() -> tuple[list[str], list[str]]:
    unexpected_dirs: list[str] = []
    unexpected_files: list[str] = []

    for entry in sorted(ROOT_DIR.iterdir(), key=lambda path: path.name):
        name = entry.name
        if entry.is_dir():
            if name not in ALLOWED_DIRS:
                unexpected_dirs.append(name)
        elif entry.is_file():
            if name not in ALLOWED_FILES:
                unexpected_files.append(name)

    return unexpected_dirs, unexpected_files


def main() -> int:
    unexpected_dirs, unexpected_files = collect_unexpected_entries()

    print(f"Root: {ROOT_DIR}")
    print(f"Allowed dirs: {', '.join(sorted(ALLOWED_DIRS))}")
    print(f"Allowed files: {', '.join(sorted(ALLOWED_FILES))}")

    if not unexpected_dirs and not unexpected_files:
        print("OK: root 直下の構成に逸脱はありません。")
        return 0

    print("NG: root 直下に許可されていない項目があります。")
    if unexpected_dirs:
        print("Unexpected dirs:")
        for name in unexpected_dirs:
            print(f"  - {name}")
    if unexpected_files:
        print("Unexpected files:")
        for name in unexpected_files:
            print(f"  - {name}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
