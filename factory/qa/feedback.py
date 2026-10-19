"""Contract-level feedback (no test source) and append-only regression proposals."""
from pathlib import Path

import yaml

from .leak import LeakError, assert_no_leak, expand


class NoProtectedPaths(Exception):
    pass


def protected_paths(root, extra=()) -> list:
    """paths.eval and paths.held_out from .factory/profile.yaml, plus explicit --protect arguments."""
    out = list(extra)
    prof = Path(root) / ".factory" / "profile.yaml"
    if prof.is_file():
        paths = (yaml.safe_load(prof.read_text(encoding="utf-8")) or {}).get("paths") or {}
        out += list(paths.get("eval") or []) + list(paths.get("held_out") or [])
    return out


def _check(text, root, extra, allow_none):
    prot = protected_paths(root, extra)
    if not prot:
        if allow_none:
            return
        raise NoProtectedPaths("no protected paths: add paths.eval to .factory/profile.yaml or pass --protect "
                               "(--allow-no-protect to skip the leak check deliberately)")
    assert_no_leak(text, prot, root=root)
    if not expand(prot, root) and not allow_none:
        raise NoProtectedPaths("protected paths match no files; refusing to treat that as a clean leak check")


def write_feedback(store, *, criteria, observed, expected, repro, signature=None, changed=None,
                   protect=(), allow_no_protect=False) -> Path:
    f = store.facts()
    sig = signature or f["current_sig"]
    attempt = len(f["fails_by_sig"].get(sig, [])) if sig else f["counted"]
    if changed is None:
        changed = ("first failure for this signature; nothing to compare" if attempt <= 1
                   else "no change reported since the previous attempt")
    n = store.state["feedback_count"] + 1
    text = (f"# QA feedback {n} for slice {store.id}\n\n"
            f"Attempt {attempt} failed" + (f" (signature `{sig}`)" if sig else "") + ".\n\n"
            f"## Criteria\n" + "".join(f"- {c}\n" for c in criteria) +
            f"\n## Observed\n{observed.strip()}\n\n## Expected\n{expected.strip()}\n\n"
            f"## Reproduce (product level)\n```\n{repro.strip()}\n```\n\n"
            f"## Changed since the last attempt\n{changed.strip()}\n")
    _check(text, store.root, protect, allow_no_protect)  # before anything is written
    store.next_feedback_number()
    out = store.dir / "qa-feedback" / f"{n}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return out


def propose_regression(store, *, signature, criterion, input_class, expected, recurred, protect=(),
                       allow_no_protect=False) -> Path:
    """Append a proposal for the eval author. Never touches eval files."""
    from .store import now
    section = (f"## Proposal at {now()}\n- Criterion: {criterion}\n- Input class: {input_class}\n"
               f"- Expected behaviour: {expected}\n- Where the failure recurred: {recurred}\n\n")
    _check(section, store.root, protect, allow_no_protect)
    out = store.dir / "regression-proposals" / f"{signature}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    new = not out.exists()
    with open(out, "a", encoding="utf-8") as fh:
        if new:
            fh.write(f"# Regression proposals for signature {signature}\n\n"
                     "Append-only. For the eval author to review and add; QA does not edit eval files.\n\n")
        fh.write(section)
    store.note_proposal(signature, str(out.relative_to(store.root)))
    return out
