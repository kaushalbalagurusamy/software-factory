"""Stable failure signatures: hash of (case or criterion id, normalized error text)."""
import hashlib
import re

_RULES = [
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"), "<TS>"),
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
    (re.compile(r"\b0x[0-9a-fA-F]+\b"), "<ADDR>"),
    (re.compile(r"\b[A-Za-z]:\\[^\s:'\",)]+"), "<PATH>"),
    (re.compile(r"(?<![\w<])(?:~|\.{1,2})?/[^\s:'\",)]+"), "<PATH>"),
    (re.compile(r"\b[\w.\-@+]+(?:/[\w.\-@+]+)+\.\w+\b"), "<PATH>"),
    (re.compile(r"\b[0-9a-fA-F]{7,}\b"), "<HEX>"),
    (re.compile(r"\d+(?:\.\d+)?"), "<N>"),
]


def normalize_error(text: str) -> str:
    """Mask timestamps, ids, addresses, paths and numbers; collapse whitespace."""
    out = text
    for rx, repl in _RULES:
        out = rx.sub(repl, out)
    return re.sub(r"\s+", " ", out).strip()


def signature(case_or_criterion: str, error: str) -> str:
    key = f"{case_or_criterion}\x00{normalize_error(error)}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
