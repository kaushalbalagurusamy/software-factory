#!/usr/bin/env python3
"""Local BM25 search over the source cache and the trap catalogue. No embeddings (owner decision:
lexical first; embeddings only if evaluation shows BM25 missing traps that they would find).

  python3 tools/search.py "exactly once delivery retries"           # cached source passages
  python3 tools/search.py --traps "log completions to fine-tune"      # trap catalogue
  python3 tools/search.py --lens licensing "network interaction" -k 5

Prints JSON lines: score, where it came from, and the passage or trap summary.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import CACHE, lens_dirs, load_yaml  # noqa: E402

TOKEN = re.compile(r"[a-z0-9]+(?:[-'][a-z0-9]+)*")
STOP = set("a an and are as at be by for from has have in is it its of on or that the this to was were will with not no".split())


def tokens(text: str) -> list[str]:
    return [t for t in TOKEN.findall(text.lower()) if t not in STOP]


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.docs, self.k1, self.b = docs, k1, b
        self.n = len(docs)
        self.avg = sum(map(len, docs)) / self.n if self.n else 0
        df = Counter(t for d in docs for t in set(d))
        self.idf = {t: math.log(1 + (self.n - f + 0.5) / (f + 0.5)) for t, f in df.items()}
        self.tf = [Counter(d) for d in docs]

    def score(self, q: list[str], i: int) -> float:
        tf, dl, s = self.tf[i], len(self.docs[i]), 0.0
        for t in q:
            if t in tf:
                f = tf[t]
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avg))
        return s

    def top(self, q: list[str], k: int) -> list[tuple[int, float]]:
        scored = [(i, self.score(q, i)) for i in range(self.n)]
        return sorted((x for x in scored if x[1] > 0), key=lambda x: -x[1])[:k]


def passages(text: str, size: int = 900) -> list[str]:
    out, buf = [], ""
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) > size and buf:
            out.append(buf)
            buf = ""
        buf = (buf + "\n\n" + para).strip()
        while len(buf) > 2 * size:
            out.append(buf[:size])
            buf = buf[size:]
    if buf:
        out.append(buf)
    return out


def corpus_sources(lens: str | None):
    items = []
    for d in sorted(CACHE.iterdir()) if CACHE.exists() else []:
        if not d.is_dir() or (lens and d.name != lens):
            continue
        for p in sorted(d.glob("*.txt")):
            meta_p = p.with_suffix(".meta.json")
            meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
            for i, chunk in enumerate(passages(p.read_text(encoding="utf-8"))):
                items.append(({"lens": d.name, "source": p.stem, "url": meta.get("source_url"), "fetched": meta.get("fetched"), "passage": i, "text": chunk}, chunk))
    return items


def corpus_traps(lens: str | None):
    items = []
    for d in lens_dirs():
        if lens and d.name != lens or not (d / "traps.yaml").exists():
            continue
        for t in (load_yaml(d / "traps.yaml") or {}).get("traps", []):
            text = " ".join([t.get("title", ""), " ".join(t.get("cues", [])), t.get("principle", ""), " ".join(t.get("aliases", []))])
            items.append(({"lens": d.name, "trap": t["id"], "status": t.get("status"), "title": t.get("title"), "cues": t.get("cues")}, text))
    return items


def search(query: str, traps: bool = False, lens: str | None = None, k: int = 8) -> list[dict]:
    items = corpus_traps(lens) if traps else corpus_sources(lens)
    if not items:
        return []
    idx = BM25([tokens(text) for _, text in items])
    return [{"score": round(s, 3), **items[i][0]} for i, s in idx.top(tokens(query), k)]


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--traps", action="store_true")
    ap.add_argument("--lens")
    ap.add_argument("-k", type=int, default=8)
    a = ap.parse_args(argv)
    hits = search(a.query, a.traps, a.lens, a.k)
    if not hits:
        print("no hits" + ("" if a.traps else " (is the cache empty? run tools/refresh.py)"), file=sys.stderr)
        return 1
    for h in hits:
        print(json.dumps(h, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
