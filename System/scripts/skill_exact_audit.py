#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from pathlib import Path
import sys

SKILL_REQUIRED = [
    '## 役割',
    '## ゴール',
    '## 必要変数',
    '## 実装前の最小チェック',
    '## Workflow',
    '## exact 手順',
    '## 保存前の最小チェック',
    '## 保存後の最小チェック',
    '## ここで止めて確認する条件',
    '## 完成条件',
]

WORKFLOW_REQUIRED = [
    '## 保存前の最小チェック',
    '## 保存後の最小チェック',
    '## ここで止めて確認する条件',
    '## 完成条件',
]


def audit(root: Path) -> int:
    problems = []
    for skill in sorted(root.glob('*/SKILL.md')):
        text = skill.read_text()
        missing = [h for h in SKILL_REQUIRED if h not in text]
        if missing:
            problems.append((skill, missing))
        wf = skill.parent / 'references' / 'workflow.md'
        if wf.exists():
            wf_text = wf.read_text()
            wf_missing = [h for h in WORKFLOW_REQUIRED if h not in wf_text]
            if wf_missing:
                problems.append((wf, wf_missing))
    if not problems:
        print('OK: exact audit passed')
        return 0
    print('NG: exact audit failed')
    for path, missing in problems:
        print(f'\n{path}')
        for item in missing:
            print(f'  MISSING {item}')
    return 1


if __name__ == '__main__':
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('/Users/koa800/Desktop/cursor/Skills/2_導線')
    raise SystemExit(audit(root))
