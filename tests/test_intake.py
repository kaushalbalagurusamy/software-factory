"""Intake gate: requirement ledger, sweep record, gate, delta mode."""
import csv
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from factory.intake.cli import main

FIX = Path(__file__).resolve().parent / "fixtures" / "intake" / "docs"
SLICE_FIX = Path(__file__).resolve().parent / "fixtures" / "slices" / "docs" / "slices" / "demo-login"
OK, FAIL, USAGE, GATE = 0, 1, 2, 3


@pytest.fixture
def proj(tmp_path, monkeypatch):
    shutil.copytree(FIX, tmp_path / "docs")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def paths(p):
    r = p / "docs" / "requirements"
    return r / "brief.md", r / "ledger.tsv", r / "register.json", r / "claims.json"


def run(*argv):
    return main([str(a) for a in argv])


def read_ledger(p):
    with open(p, newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def write_ledger(p, rows, cols=None):
    cols = cols or list(rows[0].keys())
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", lineterminator="\n")
        w.writeheader()
        w.writerows(rows)


def sha(s):
    return hashlib.sha256(s.strip().encode()).hexdigest()


def check(p, capsys=None):
    b, l, *_ = paths(p)
    code = run("check", "--source", b, "--ledger", l)
    if capsys is None:
        return code, ""
    cap = capsys.readouterr()
    return code, cap.out + cap.err


def record(p):
    b, l, r, c = paths(p)
    return run("record-sweep", "--register", r, "--ledger", l, "--source", b, "--claims", c)


def sweeps(p):
    return sorted((p / "docs" / "requirements" / "sweeps").glob("*.json"))


# ---------------------------------------------------------------- ledger check
def test_check_passes_on_fixture(proj):
    assert check(proj)[0] == OK


def test_dropped_source_line_is_detected(proj, capsys):
    b, l, *_ = paths(proj)
    rows = [r for r in read_ledger(l) if r["req_id"] != "R-004"]
    write_ledger(l, rows)
    code, out = check(proj, capsys)
    assert code == FAIL and "brief.md:4" in out and "not covered" in out


def test_dropped_optional_and_out_of_scope_lines_are_detected(proj, capsys):
    b, l, *_ = paths(proj)
    write_ledger(l, [r for r in read_ledger(l) if r["req_id"] not in ("R-005", "R-006")])
    code, out = check(proj, capsys)
    assert code == FAIL and "brief.md:5" in out and "brief.md:6" in out


def test_context_row_requires_a_reason(proj, capsys):
    b, l, *_ = paths(proj)
    rows = read_ledger(l)
    rows[0]["artifact_or_waits_on"] = ""
    write_ledger(l, rows)
    code, out = check(proj, capsys)
    assert code == FAIL and "context" in out and "reason" in out


def test_changed_source_line_is_detected_by_text_sha(proj, capsys):
    b, *_ = paths(proj)
    b.write_text(b.read_text().replace("fast unsalted hash", "slow salted hash"))
    code, out = check(proj, capsys)
    assert code == FAIL and "text_sha" in out and "brief.md:4" in out


def test_new_source_line_is_detected(proj, capsys):
    b, *_ = paths(proj)
    b.write_text(b.read_text() + "A brand new requirement.\n")
    code, out = check(proj, capsys)
    assert code == FAIL and "not covered" in out


def test_blocked_row_must_name_what_it_waits_on(proj, capsys):
    b, l, *_ = paths(proj)
    rows = read_ledger(l)
    rows[1]["status"] = "blocked"
    write_ledger(l, rows)
    assert check(proj, capsys)[0] == FAIL
    rows[1]["artifact_or_waits_on"] = "decision ADR-0007"
    write_ledger(l, rows)
    assert check(proj)[0] == OK


def test_satisfied_row_must_name_an_existing_artifact(proj, capsys):
    b, l, *_ = paths(proj)
    rows = read_ledger(l)
    rows[1]["status"] = "satisfied"
    write_ledger(l, rows)
    code, out = check(proj, capsys)
    assert code == FAIL and "satisfied" in out
    rows[1]["artifact_or_waits_on"] = "src/missing.py"
    write_ledger(l, rows)
    code, out = check(proj, capsys)
    assert code == FAIL and "src/missing.py" in out
    (proj / "src").mkdir()
    (proj / "src" / "login.py").write_text("x = 1\n")
    rows[1]["artifact_or_waits_on"] = "src/login.py"
    write_ledger(l, rows)
    assert check(proj)[0] == OK


def test_invalid_trust_and_status_values_fail(proj, capsys):
    b, l, *_ = paths(proj)
    rows = read_ledger(l)
    rows[1]["trust"] = "probably-fine"
    rows[2]["status"] = "done"
    write_ledger(l, rows)
    code, out = check(proj, capsys)
    assert code == FAIL and "trust" in out and "status" in out


def test_three_column_ledger_cannot_prove_coverage(proj, capsys):
    b, l, *_ = paths(proj)
    l.write_text("req_id\ttrust\tstatus\nR-003\ttrusted\tunserved\n")
    code, out = check(proj, capsys)
    assert code == FAIL and "source_ref" in out


def test_trusted_row_with_open_critical_status_fails(proj, capsys):
    b, l, *_ = paths(proj)
    rows = read_ledger(l)
    rows[5]["status"] = "blocked; open critical F-002"
    rows[5]["artifact_or_waits_on"] = "owner sign-off F-002"
    write_ledger(l, rows)
    code, out = check(proj, capsys)
    assert code == FAIL and "trusted" in out and "Critical" in out


# ---------------------------------------------------------------- record-sweep
def test_record_sweep_writes_record_and_ledger(proj):
    assert record(proj) == OK
    (rec,) = sweeps(proj)
    assert rec.stem == hashlib.sha256(paths(proj)[0].read_bytes()).hexdigest()
    rows = {r["req_id"]: r for r in read_ledger(paths(proj)[1])}
    assert rows["R-003"]["trust"] == "trusted"
    assert rows["R-004"]["trust"] == "conditioned(F-001)" and rows["R-004"]["finding_ids"] == "F-001"
    assert rows["R-004"]["disposition"] == "reframe"
    assert rows["R-007"]["trust"] == "rejected(F-002)"
    assert "open critical" in rows["R-007"]["status"].lower()
    assert rows["R-007"]["status"].startswith("blocked") and "F-002" in rows["R-007"]["artifact_or_waits_on"]
    # the omitted best practice was added as a row and the ledger still checks
    assert rows["BP-C-004"]["category"] == "best-practice:cryptography"
    assert check(proj)[0] == OK


def test_record_sweep_refuses_register_for_a_different_brief(proj, capsys):
    b, l, r, c = paths(proj)
    b.write_text(b.read_text().replace("fast unsalted hash", "something else"))
    # keep the ledger honest so only the hash mismatch is at issue
    rows = read_ledger(l)
    for row in rows:
        n = int(row["source_ref"].split(":")[1])
        row["text_sha"] = sha(b.read_text().split("\n")[n - 1])
    write_ledger(l, rows)
    assert record(proj) != OK
    assert "sha256" in capsys.readouterr().err and not sweeps(proj)


@pytest.mark.parametrize("mutate,needle", [
    (lambda d: d.pop("convergence"), "convergence"),
    (lambda d: d["findings"][0].__setitem__("id", "bad"), "pattern"),
    (lambda d: d["findings"][0].pop("severity"), "severity"),
    (lambda d: d["findings"][1].pop("owner_question"), "owner_question"),
    (lambda d: d["findings"][0]["severity"].__setitem__("tier", "huge"), "tier"),
    (lambda d: d["findings"][2].pop("dismissal_reason"), "dismissal_reason"),
    (lambda d: d["findings"][0].__setitem__("surprise", 1), "surprise"),
    (lambda d: d["brief"].__setitem__("sha256", "xyz"), "sha256"),
])
def test_register_validator_rejects_schema_violations(proj, capsys, mutate, needle):
    b, l, r, c = paths(proj)
    d = json.loads(r.read_text())
    mutate(d)
    r.write_text(json.dumps(d))
    assert record(proj) == FAIL
    assert needle in capsys.readouterr().err and not sweeps(proj)


# ---------------------------------------------------------------- gate
def gate(*extra):
    return run("gate", *extra)


def test_gate_fails_when_no_sweep_record(proj, capsys):
    b, l, *_ = paths(proj)
    assert gate("--source", b, "--ledger", l) == GATE
    assert "no sweep record" in capsys.readouterr().err


def test_gate_passes_after_sweep_with_dispositions(proj):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    assert gate("--source", b, "--ledger", l) == OK


def test_gate_fails_when_critical_has_no_disposition(proj, capsys):
    b, l, r, c = paths(proj)
    d = json.loads(r.read_text())
    f = d["findings"][1]
    f["status"] = "plausible"
    for k in ("disposition", "owner_question", "underlying_problem", "spec_section"):
        f.pop(k)
    f["would_settle"] = "read the site terms"
    r.write_text(json.dumps(d))
    assert record(proj) == OK
    assert gate("--source", b, "--ledger", l) == GATE
    assert "F-002" in capsys.readouterr().err


def test_gate_fails_when_high_has_no_disposition(proj, capsys):
    b, l, r, c = paths(proj)
    d = json.loads(r.read_text())
    f = d["findings"][0]
    f["status"] = "plausible"
    for k in ("disposition", "underlying_problem", "spec_section"):
        f.pop(k)
    f["would_settle"] = "measure"
    r.write_text(json.dumps(d))
    assert record(proj) == OK
    assert gate("--source", b, "--ledger", l) == GATE
    assert "F-001" in capsys.readouterr().err


def test_gate_fails_on_unrated_open_finding(proj, capsys):
    b, l, r, c = paths(proj)
    d = json.loads(r.read_text())
    f = d["findings"][0]
    f["status"] = "suspect"
    for k in ("severity", "disposition", "underlying_problem", "spec_section"):
        f.pop(k)
    r.write_text(json.dumps(d))
    assert record(proj) == OK
    assert gate("--source", b, "--ledger", l) == GATE
    assert "unrated" in capsys.readouterr().err


def test_gate_detects_ledger_trust_edited_past_the_sweep(proj, capsys):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    rows = read_ledger(l)
    for r in rows:
        if r["req_id"] == "R-007":
            r["trust"] = "trusted"
    write_ledger(l, rows)
    assert gate("--source", b, "--ledger", l) == GATE
    assert "R-007" in capsys.readouterr().err


def test_signoff_clears_open_critical_and_unblocks_slice(proj):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    assert run("signoff", "--source", b, "--ledger", l, "--finding", "F-002", "--by", "human:2026-10-19") == OK
    rows = {r["req_id"]: r for r in read_ledger(l)}
    assert "open" not in rows["R-007"]["status"].lower()
    assert rows["R-007"]["trust"] == "rejected(F-002)"
    assert gate("--source", b, "--ledger", l) == OK


def test_signoff_requires_known_finding_and_attribution(proj, capsys):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    assert run("signoff", "--source", b, "--ledger", l, "--finding", "F-099", "--by", "human:x") == USAGE
    assert run("signoff", "--source", b, "--ledger", l, "--finding", "F-002", "--by", "me") == USAGE


def make_slice(proj, ids):
    d = proj / "docs" / "slices" / "scrape"
    shutil.copytree(SLICE_FIX, d)
    text = (d / "proposal.md").read_text()
    lines = []
    for ln in text.split("\n"):
        if ln.startswith("id:"):
            ln = "id: scrape"
        if ln.startswith("source_requirement_ids"):
            ln = "source_requirement_ids: [" + ", ".join(ids) + "]"
        lines.append(ln)
    (d / "proposal.md").write_text("\n".join(lines))
    for lock in ("criteria.lock", "verification.json", "amendments.md"):
        (d / lock).unlink(missing_ok=True)
    return d


def test_gate_slice_blocked_by_open_critical_and_slices_checker_agrees(proj, capsys):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    s = make_slice(proj, ["R-007"])
    assert gate("--source", b, "--ledger", l, "--slice", s) == GATE
    assert "R-007" in capsys.readouterr().err
    out = subprocess.run([sys.executable, "-m", "factory.slices", "check", str(s), "--ledger", str(l)],
                         capture_output=True, text=True, cwd=proj, env={"PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    assert out.returncode == 1 and "open Critical" in out.stdout + out.stderr


def test_gate_slice_on_clean_rows_passes_and_slices_checker_agrees(proj):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    s = make_slice(proj, ["R-003"])
    assert gate("--source", b, "--ledger", l, "--slice", s) == OK
    out = subprocess.run([sys.executable, "-m", "factory.slices", "check", str(s), "--ledger", str(l)],
                         capture_output=True, text=True, cwd=proj, env={"PYTHONPATH": str(Path(__file__).resolve().parents[1])})
    assert out.returncode == 0, out.stdout + out.stderr


def test_gate_slice_with_unknown_requirement_fails(proj, capsys):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    s = make_slice(proj, ["R-999"])
    assert gate("--source", b, "--ledger", l, "--slice", s) == GATE
    assert "R-999" in capsys.readouterr().err


def test_signoff_unblocks_slice(proj):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    s = make_slice(proj, ["R-007"])
    run("signoff", "--source", b, "--ledger", l, "--finding", "F-002", "--by", "codex:ref-1")
    assert gate("--source", b, "--ledger", l, "--slice", s) == OK


# ---------------------------------------------------------------- delta mode
def git(p, *a):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=p, check=True, capture_output=True)


def change_source_keep_ledger_honest(proj, old, new):
    b, l, *_ = paths(proj)
    b.write_text(b.read_text().replace(old, new))
    rows = read_ledger(l)
    lines = b.read_text().split("\n")
    for row in rows:
        if row["source_ref"].startswith("brief.md:"):
            row["text_sha"] = sha(lines[int(row["source_ref"].split(":")[1]) - 1])
    write_ledger(l, rows)


def test_delta_without_change_passes(proj):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    git(proj, "init", "-q")
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "base")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=proj, capture_output=True, text=True).stdout.strip()
    assert gate("--source", b, "--ledger", l, "--since", base) == OK


def test_delta_requires_new_sweep_after_source_changes(proj, capsys):
    b, l, r, c = paths(proj)
    assert record(proj) == OK
    git(proj, "init", "-q")
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "base")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=proj, capture_output=True, text=True).stdout.strip()
    change_source_keep_ledger_honest(proj, "email and a password", "email, a password and a passkey")
    assert gate("--source", b, "--ledger", l, "--since", base) == GATE
    err = capsys.readouterr().err
    assert "no sweep record" in err and "changed" in err


def test_delta_new_record_must_cover_changed_lines(proj, capsys):
    b, l, r, c = paths(proj)
    assert record(proj) == OK
    git(proj, "init", "-q")
    git(proj, "add", "-A")
    git(proj, "commit", "-qm", "base")
    base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=proj, capture_output=True, text=True).stdout.strip()
    change_source_keep_ledger_honest(proj, "email and a password", "email, a password and a passkey")
    # re-sweep with registers pointing at the new hash, but claims that never mention line 3
    new_sha = hashlib.sha256(b.read_bytes()).hexdigest()
    reg = json.loads(r.read_text()); reg["brief"]["sha256"] = new_sha; r.write_text(json.dumps(reg))
    cl = json.loads(c.read_text()); cl["brief"]["sha256"] = new_sha
    cl["claims"] = [x for x in cl["claims"] if x["locator"] != "L3"]
    c.write_text(json.dumps(cl))
    assert record(proj) == OK
    assert gate("--source", b, "--ledger", l, "--since", base) == GATE
    assert "line 3" in capsys.readouterr().err
    cl["claims"].append({"id": "C-009", "kind": "requirement", "text": "sign in", "locator": "L3"})
    c.write_text(json.dumps(cl))
    assert record(proj) == OK
    assert gate("--source", b, "--ledger", l, "--since", base) == OK


def test_delta_with_bad_ref_is_a_usage_error(proj):
    b, l, *_ = paths(proj)
    assert record(proj) == OK
    git(proj, "init", "-q")
    assert gate("--source", b, "--ledger", l, "--since", "deadbeef") == USAGE
