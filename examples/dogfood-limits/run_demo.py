#!/usr/bin/env python3
"""Run the labelled-minimal-fixture demonstration (see README.md). Exits 0 only if every step behaves as stated."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
ENV = {**os.environ, "PYTHONPATH": str(REPO)}


def run(args, cwd=REPO, timeout=120):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, env=ENV, timeout=timeout)


def sf(*args, **kw):
    return run([sys.executable, "-m", "factory.cli", *args], **kw)


def step(n, text, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {n}. {text}" + (f"  [{detail}]" if detail else ""))
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "out"))
    out = Path(ap.parse_args().out)
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    ok = True

    r = sf("structure", "scan", str(HERE / "base"), "--summary")
    (out / "1-structure-base.json").write_text(r.stdout)
    s = json.loads(r.stdout)
    ok &= step(1, "structural scan of the base module (limits reported, no complete-graph claim)",
               r.returncode == 0 and s["counts"]["symbols"] == 2 and s["limits"]["complete_call_graph"] is False
               and s["limits"]["parse_failures"] == [])

    r = sf("contracts", "check-contracts", str(HERE / "contracts"))
    (out / "2-contract-review.txt").write_text(r.stdout + r.stderr)
    ok &= step(2, "contract review before code passes (consistent, not vacuous)", r.returncode == 0, f"exit {r.returncode}")

    def verify(variant, report, regress=None):
        a = ["contracts", "verify", str(HERE / "contracts"), "--root", str(HERE / variant), "--report", str(out / report)]
        if regress:
            a += ["--regress-dir", str(out / regress)]
        return sf(*a)

    r = verify("base", "3-verify-base.json")
    ok &= step(3, "base implementation: PROVED, gate passes", r.returncode == 0, f"exit {r.returncode}")

    r = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(HERE / "tests")],
            cwd=HERE / "head_bad", timeout=60)
    env_note = r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-200:]
    ok &= step(4, "the old unit test PASSES on the bad patch (it looks fine)", r.returncode == 0, env_note)

    work = out / "work"  # a working copy: the bad patch is verified here, then fixed in place
    work.mkdir()
    shutil.copy(HERE / "head_bad" / "limits.py", work / "limits.py")
    r = sf("contracts", "verify", str(HERE / "contracts"), "--root", str(work),
           "--report", str(out / "5-verify-head-bad.json"), "--regress-dir", str(out / "regressions"))
    rep = json.loads((out / "5-verify-head-bad.json").read_text())
    text = json.dumps(rep)
    ok &= step(5, "bad patch: COUNTEREXAMPLE, gate fails with exit 16 and a regression test is generated",
               r.returncode == 16 and "COUNTEREXAMPLE" in text and any((out / "regressions").glob("*.py")), f"exit {r.returncode}")

    r = sf("structure", "diff", str(HERE / "base"), str(HERE / "head_bad"))
    (out / "6-structure-diff.json").write_text(r.stdout)
    ok &= step(6, "structural diff lists the changed symbol", "clamp" in r.stdout and r.returncode in (0,), f"exit {r.returncode}")

    r = verify("head_good", "7-verify-head-good.json")
    ok &= step(7, "corrected patch: PROVED, gate passes", r.returncode == 0, f"exit {r.returncode}")
    reg = next((out / "regressions").glob("*.py"), None)
    if reg is not None:
        # the regression replays the file it was generated from (an absolute path, a known portability limit)
        before = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(reg)], cwd=work, timeout=60)
        shutil.copy(HERE / "head_good" / "limits.py", work / "limits.py")  # apply the fix in place
        after = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(reg)], cwd=work, timeout=60)
        ok &= step("7b", "the generated regression fails on the bad patch and passes once the fix is applied in place",
                   before.returncode != 0 and after.returncode == 0, f"before exit {before.returncode}, after exit {after.returncode}")

    model = out / "8-model.json"
    r = sf("structure", "model", str(HERE / "head_good"), "-o", str(model), "--name", "limits fixture")
    c = run([sys.executable, str(REPO / "skills/mermaid-nesting-dolls/scripts/nesting_dolls.py"), "check", str(model), "--repo", str(HERE / "head_good")])
    b = run([sys.executable, str(REPO / "skills/mermaid-nesting-dolls/scripts/nesting_dolls.py"), "build", str(model), "-o",
             str(out / "explorer.html"), "--repo", str(HERE / "head_good")])
    ok &= step(8, "refreshed clickable architecture artifact built from the structural scan (checker clean)",
               r.returncode == 0 and c.returncode == 0 and b.returncode == 0 and (out / "explorer.html").exists(),
               f"model {r.returncode}, check {c.returncode}, build {b.returncode}")
    print("\nALL STEPS AS EXPECTED" if ok else "\nSOMETHING DID NOT BEHAVE AS STATED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
