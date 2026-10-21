#!/usr/bin/env python3
"""Add the installed Antigravity IDE URL scheme to shared editor-link assets."""
from pathlib import Path
import re
import sys


def apply(root):
    root = Path(root)
    primary = root / 'skills/mermaid-nesting-dolls/assets/editor-links.js'
    text = primary.read_text()
    if '"antigravity-ide"' not in text:
        assert '"windsurf",' in text, 'Editor list changed; review integration before installing'
        text = text.replace('"windsurf",', '"windsurf", "antigravity-ide",', 1)
    pattern = r'/\* editor-links:begin \*/.*?/\* editor-links:end \*/'
    block = re.search(pattern, text, re.S).group()
    for rel in ('skills/mermaid-nesting-dolls/assets/editor-links.js',
                'skills/mermaid-nesting-dolls/assets/template.html',
                'skills/lsf/assets/editor-links.js', 'skills/lsf/assets/dashboard.html',
                'ops/shell/index.html'):
        p = root / rel
        updated, count = re.subn(pattern, lambda _: block, p.read_text(), flags=re.S)
        assert count == 1, 'Missing or ambiguous editor-links block: ' + rel
        if updated != p.read_text():
            p.write_text(updated)
    for rel in ('skills/lsf/scripts/lsf.py', 'skills/mermaid-nesting-dolls/scripts/nesting_dolls.py'):
        p = root / rel
        text = p.read_text()
        match = re.search(r'^EDITORS\s*=.*$', text, re.M)
        assert match, 'Missing editor choices: ' + rel
        line = match.group()
        if '"antigravity-ide"' not in line:
            assert '"windsurf",' in line, 'Editor choices changed: ' + rel
            p.write_text(text[:match.start()] + line.replace('"windsurf",', '"windsurf", "antigravity-ide",', 1) + text[match.end():])


if __name__ == '__main__':
    apply(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[1])
