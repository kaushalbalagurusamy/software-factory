"""Shared loaders for the minesweeper tools. Standard library plus PyYAML and jsonschema."""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "engine" / "schemas"
LENSES = ROOT / "lenses"
CONFIG = ROOT / "config"
CACHE = ROOT / "sources" / "cache"
ADAPTERS = ROOT / "sources" / "adapters"


def load_yaml(path: Path):
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def split_front_matter(path: Path) -> tuple[dict, str]:
    """Return (front matter, body) for a Markdown file that opens with a --- YAML block."""
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: no front matter")
    end = text.find("\n---\n", 4)
    if end == -1:
        raise ValueError(f"{path}: unterminated front matter")
    return yaml.safe_load(text[4:end]) or {}, text[end + 5:]


def _registry() -> Registry:
    resources = []
    for p in SCHEMAS.glob("*.json"):
        doc = json.loads(p.read_text(encoding="utf-8"))
        res = Resource.from_contents(doc)
        resources.append((doc["$id"], res))
        resources.append((p.name, res))
    return Registry().with_resources(resources)


def validator(name: str) -> Draft202012Validator:
    """Validator for engine/schemas/<name>, with $refs between schemas resolved locally."""
    doc = json.loads((SCHEMAS / name).read_text(encoding="utf-8"))
    return Draft202012Validator(doc, registry=_registry(), format_checker=Draft202012Validator.FORMAT_CHECKER)


def lens_dirs() -> list[Path]:
    return sorted(p for p in LENSES.iterdir() if p.is_dir() and not p.name.startswith((".", "_")))


def load_lens(d: Path) -> dict:
    """Load one lens pack into a dict: manifest, body, traps, sources, cases."""
    manifest, body = split_front_matter(d / "lens.md")
    traps = load_yaml(d / "traps.yaml") if (d / "traps.yaml").exists() else None
    sources = load_yaml(d / "sources.yaml") if (d / "sources.yaml").exists() else None
    cases = {}
    if (d / "cases").is_dir():
        for p in sorted((d / "cases").glob("*.yaml")):
            cases[p.stem] = load_yaml(p)
    return {"dir": d, "manifest": manifest, "body": body, "traps": traps, "sources": sources, "cases": cases}


def applies(manifest: dict, brief_text: str) -> tuple[bool, str]:
    """Deterministic applies_when test. Returns (applies, why)."""
    aw = manifest.get("applies_when", {})
    if aw.get("always"):
        return True, "always"
    low = brief_text.lower()
    hits = [s for s in aw.get("signals", []) if s.lower() in low]
    return (bool(hits), "signals: " + ", ".join(hits[:5])) if hits else (False, "no signal matched")
