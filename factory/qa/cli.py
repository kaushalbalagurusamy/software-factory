"""python -m factory.qa: QA supervisor state, decisions, feedback and verification hand-off.

Exit codes: 0 ok, 1 error or audit failure, 2 usage error, 3 leak check rejected (or protected material
too large to check), 4 refused by the slices package.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

from .decide import decide_next
from .feedback import NoProtectedPaths, check_text, propose_regression, write_feedback
from .leak import LeakError
from .policy import PolicyError, load_policy
from .runs import record_run
from .stats import slice_dirs, tier_stats
from .store import AuditError, SliceStore, check_signature

OK, ERR, USAGE, LEAK, REFUSED = 0, 1, 2, 3, 4


class Usage(Exception):
    pass


def _store(a):
    if not a.slice:
        raise Usage("--slice is required")
    st = SliceStore(a.root, a.slice)
    return st


def _out(o):
    print(json.dumps(o, indent=2, sort_keys=True))


def cmd_init(a):
    _store(a).init(a.criteria, force=a.force)
    print(f"initialised {_store(a).dir}")
    return OK


def cmd_record(a):
    st, pol = _store(a), load_policy(a.root)
    err = Path(a.error_file).read_text(encoding="utf-8") if a.error_file else (a.error or "")
    line = record_run(st, pol, status=a.status, case=a.case, criterion=a.criterion, error=err, tier=a.tier,
                      duration_s=a.duration, tokens=a.tokens, cost_usd=a.cost, commit=a.commit,
                      rerun=a.rerun, verified=a.verified, environment=a.environment)
    _out({k: line[k] for k in ("seq", "outcome", "signature", "tier")})
    return OK


def cmd_next(a):
    st, pol = _store(a), load_policy(a.root)
    _out(decide_next(st, pol, apply=a.apply))
    return OK


def cmd_feedback(a):
    p = write_feedback(_store(a), criteria=a.criterion, observed=a.observed, expected=a.expected,
                       repro=a.repro, signature=a.signature, changed=a.changed, protect=a.protect,
                       allow_no_protect=a.allow_no_protect)
    print(p)
    return OK


def cmd_regression(a):
    print(propose_regression(_store(a), signature=a.signature, criterion=a.criterion,
                             input_class=a.input_class, expected=a.expected, recurred=a.recurred,
                             protect=a.protect, allow_no_protect=a.allow_no_protect))
    return OK


def cmd_verify_pass(a):
    st = _store(a)
    sdir = Path(a.slice_dir) if a.slice_dir else Path(a.root) / "docs" / "slices" / a.slice
    env_path = str(Path(__file__).resolve().parents[2])
    import os
    env = dict(os.environ, PYTHONPATH=env_path + os.pathsep + os.environ.get("PYTHONPATH", ""))
    r = subprocess.run([sys.executable, "-m", "factory.slices", "verify", str(sdir), a.task, "--role", "qa",
                        "--evidence", a.evidence, "--commit", a.commit],
                       capture_output=True, text=True, env=env, timeout=120)
    if r.returncode != 0:
        print(f"refused by slices package (exit {r.returncode}): {(r.stderr or r.stdout).strip()}", file=sys.stderr)
        return REFUSED
    if a.criteria:
        st.mark_verified(a.criteria)
    print(r.stdout.strip())
    return OK


def cmd_reviewer(a):
    st = _store(a)
    check_signature(a.signature)
    check_text(a.note, st.root, a.protect, a.allow_no_protect)  # the note is persisted into state.json
    st.set_reviewer_verdict(a.signature, a.verdict, a.note)
    return OK


def cmd_unblock(a):
    _store(a).set_status("active")
    return OK


def cmd_stats(a):
    dirs = [_store(a).dir] if a.slice else slice_dirs(a.root)
    _out(tier_stats(dirs))
    return OK


def cmd_audit(a):
    problems = _store(a).audit()
    for p in problems:
        print(p, file=sys.stderr)
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return ERR if problems else OK


def cmd_policy(a):
    _out(load_policy(a.root).as_dict())
    return OK


def cmd_promote_notes(a):
    from .notes import NotesError, promote
    root = a.notes_root or a.root
    slice_dir = a.notes_slice or a.slice
    if not slice_dir:
        raise Usage("--slice DIR is required")
    try:
        print(promote(root, slice_dir, a.protect, a.allow_no_protect))
    except LeakError:
        print("error: the notes text matches protected material; nothing was written", file=sys.stderr)
        return ERR
    except NotesError as e:
        print(f"error: {e}", file=sys.stderr)
        return ERR
    return OK


def build():
    ap = argparse.ArgumentParser(prog="python -m factory.qa", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--root", default=".")
    ap.add_argument("--slice")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def add(name, fn, *args):
        c = sub.add_parser(name)
        c.set_defaults(f=fn)
        return c
    c = add("init", cmd_init); c.add_argument("--criteria", nargs="+", required=True); c.add_argument("--force", action="store_true")
    c = add("record", cmd_record)
    c.add_argument("--status", required=True, choices=["pass", "fail"])
    c.add_argument("--case"); c.add_argument("--criterion"); c.add_argument("--error"); c.add_argument("--error-file")
    c.add_argument("--tier"); c.add_argument("--duration", type=float, default=0); c.add_argument("--tokens", type=int, default=0)
    c.add_argument("--cost", type=float, default=0.0); c.add_argument("--commit")
    c.add_argument("--rerun", action="store_true"); c.add_argument("--environment", action="store_true")
    c.add_argument("--verified", nargs="+")
    c = add("next", cmd_next); c.add_argument("--apply", action="store_true")
    c = add("feedback", cmd_feedback)
    c.add_argument("--criterion", action="append", required=True); c.add_argument("--observed", required=True)
    c.add_argument("--expected", required=True); c.add_argument("--repro", required=True)
    c.add_argument("--signature"); c.add_argument("--changed")
    c = add("regression-propose", cmd_regression)
    for k in ("signature", "criterion", "input-class", "expected", "recurred"):
        c.add_argument(f"--{k}", required=True)
    c = add("verify-pass", cmd_verify_pass); c.add_argument("task"); c.add_argument("--slice-dir")
    c.add_argument("--evidence", required=True); c.add_argument("--commit", required=True); c.add_argument("--criteria", nargs="+")
    c = add("reviewer-verdict", cmd_reviewer); c.add_argument("--signature", required=True)
    c.add_argument("--verdict", required=True, choices=["amended", "unresolved"]); c.add_argument("--note", required=True)
    c = add("promote-notes", cmd_promote_notes)
    c.add_argument("--slice", dest="notes_slice"); c.add_argument("--root", dest="notes_root")
    add("unblock", cmd_unblock); add("stats", cmd_stats); add("audit", cmd_audit); add("policy", cmd_policy)
    for n in ("feedback", "regression-propose", "reviewer-verdict", "promote-notes"):
        sp = sub.choices[n]
        sp.add_argument("--protect", action="append", default=[])
        sp.add_argument("--allow-no-protect", action="store_true")
    return ap


def main(argv=None) -> int:
    try:
        a = build().parse_args(argv)
    except SystemExit as e:
        return USAGE if e.code else OK
    try:
        return a.f(a)
    except (Usage, NoProtectedPaths, PolicyError, ValueError, FileExistsError) as e:
        print(f"usage error: {e}", file=sys.stderr)
        return USAGE
    except LeakError as e:
        print(f"leak check: {e}", file=sys.stderr)
        return LEAK
    except (AuditError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return ERR


if __name__ == "__main__":
    sys.exit(main())
