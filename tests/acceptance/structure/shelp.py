"""Helpers for the independent acceptance tests of factory.structure."""
from pathlib import Path

from factory.structure.extract import extract


def write_tree(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        p = Path(root) / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return Path(root)


def scan(root: Path, files: dict) -> dict:
    return extract(str(write_tree(root, files)))


def edges_from(ex: dict, caller: str, text: str) -> list:
    out = [e for e in ex["edges"] if e["caller"] == caller and e["text"] == text]
    assert out, f"no edge {caller} -> {text}; edges: {[(e['caller'], e['text']) for e in ex['edges']]}"
    return out
