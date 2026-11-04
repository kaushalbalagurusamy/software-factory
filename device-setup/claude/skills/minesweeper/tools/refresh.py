#!/usr/bin/env python3
"""Re-fetch stale sources into sources/cache/ and report what changed.

A source is stale when it has no cached copy or its copy is older than its freshness policy
(source.freshness_days, else policy.yaml freshness_days by kind, else the default). After each
fetch, every recorded quote is looked for in the new text: a quote that no longer appears is a
review item, because the rule may have changed under a verified trap.

Usage: python3 tools/refresh.py [--lens ID] [--source ID] [--force] [--dry-run] [--json]
Exit 0 when nothing needs review, 1 when a source changed, failed or lost a quote.
"""
from __future__ import annotations

import argparse
import importlib
import json
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ADAPTERS, CACHE, CONFIG, lens_dirs, load_yaml  # noqa: E402

sys.path.insert(0, str(ADAPTERS))


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def freshness(src: dict, policy: dict) -> int:
    f = policy.get("freshness_days", {})
    return int(src.get("freshness_days") or f.get(src.get("kind"), f.get("default", 180)))


def cached(lens: str, sid: str) -> tuple[Path, Path]:
    d = CACHE / lens
    return d / f"{sid}.txt", d / f"{sid}.meta.json"


def is_stale(lens: str, src: dict, policy: dict) -> bool:
    _, meta_p = cached(lens, src["id"])
    if not meta_p.exists():
        return True
    meta = json.loads(meta_p.read_text())
    if meta.get("url") != src["url"] and meta.get("source_url") != src["url"]:
        return True
    age = (date.today() - date.fromisoformat(meta["fetched"])).days
    return age >= freshness(src, policy)


def check_quotes(src: dict, text: str) -> list[str]:
    body = norm(text)
    return [q["locator"] for q in src.get("quotes", []) if norm(q["text"]) not in body]


def refresh(args) -> list[dict]:
    policy = load_yaml(CONFIG / "policy.yaml")
    rows = []
    for d in lens_dirs():
        if args.lens and d.name != args.lens or not (d / "sources.yaml").exists():
            continue
        for src in (load_yaml(d / "sources.yaml") or {}).get("sources", []):
            if args.source and src["id"] != args.source:
                continue
            row = {"lens": d.name, "source": src["id"], "url": src["url"]}
            if not (args.force or is_stale(d.name, src, policy)):
                row["state"] = "fresh"
                rows.append(row)
                continue
            if args.dry_run:
                row["state"] = "stale"
                rows.append(row)
                continue
            try:
                adapter = importlib.import_module(src["adapter"])
                res = adapter.fetch(src)
            except Exception as exc:
                res = {"text": None, "error": f"adapter crashed: {exc}"}
            if res.get("text") is None:
                row.update(state="failed", error=res.get("error"))
                rows.append(row)
                continue
            text_p, meta_p = cached(d.name, src["id"])
            text_p.parent.mkdir(parents=True, exist_ok=True)
            old = json.loads(meta_p.read_text()).get("sha256") if meta_p.exists() else None
            text_p.write_text(res["text"], encoding="utf-8")
            meta = {k: res[k] for k in ("url", "status", "fetched", "sha256")}
            meta["source_url"] = src["url"]
            meta_p.write_text(json.dumps(meta, indent=2))
            row["state"] = "new" if old is None else ("changed" if old != res["sha256"] else "unchanged")
            missing = check_quotes(src, res["text"])
            if missing:
                row["quotes_missing"] = missing
            rows.append(row)
    return rows


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--lens")
    ap.add_argument("--source")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = refresh(args)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        for r in rows:
            extra = r.get("error") or (f"quotes missing: {', '.join(r['quotes_missing'])}" if r.get("quotes_missing") else "")
            print(f"{r['state']:9} {r['lens']}/{r['source']}  {extra}")
    counts = {}
    for r in rows:
        counts[r["state"]] = counts.get(r["state"], 0) + 1
    print("refresh: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())), file=sys.stderr)
    review = [r for r in rows if r["state"] in ("changed", "failed") or r.get("quotes_missing")]
    return 1 if review else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
