"""Tests for factory.ops: historical snapshots from the git object database, and the runtime/historical split."""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from factory.ops import bundle as B  # noqa: E402
from factory.ops import collect as C  # noqa: E402
from factory.ops import runtime as R  # noqa: E402

FIX = REPO / "tests" / "fixtures" / "ops"


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


def write(repo, rel, text):
    p = Path(repo) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def commit(repo, msg):
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


ADR = "# ADR-0001: Pick X\n\n* **Status:** {status}\n* **Date:** 2026-01-02\n"


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    write(r, "docs/adr/ADR-0001-x.md", ADR.format(status="Proposed"))
    write(r, "docs/adr/ADR-0002-y.md", "# ADR-0002: Pick Y\n\n* **Status:** Accepted\n* **Date:** 2026-01-03\n")
    write(r, "research/topic.md", "# Topic\n\n> **As of:** 2026-10-19.\n")
    write(r, "docs/explorer/m.model.json", (FIX / "model.json").read_text())
    return r


def adr_tab(out, sha):
    m = json.loads((out / "snapshots" / sha / "manifest.json").read_text())
    return json.loads((out / "blobs" / f"{m['tabs']['adrs']['blob']}.json").read_text())


# (a) time travel -----------------------------------------------------------------------------------------

def test_time_travel_from_object_database(repo, tmp_path):
    s1 = commit(repo, "one")
    write(repo, "docs/adr/ADR-0001-x.md", ADR.format(status="Accepted"))
    s2 = commit(repo, "two")
    write(repo, "docs/adr/ADR-0003-z.md", "# ADR-0003: Z\n\n* **Status:** Accepted\n")
    commit(repo, "three")
    out = tmp_path / "out"
    # build only AFTER later commits exist: the earlier sha must still be reconstructable
    B.bundle(repo, s2, out)
    B.bundle(repo, s1, out)
    t1, t2 = adr_tab(out, s1), adr_tab(out, s2)
    assert [i["status"] for i in t1["items"]][0] == "Proposed"
    assert [i["status"] for i in t2["items"]][0] == "Accepted"
    assert len(t1["items"]) == len(t2["items"]) == 2  # the third ADR (commit three) is not in either


def test_worktree_mode_sees_uncommitted(repo, tmp_path):
    commit(repo, "one")
    write(repo, "docs/adr/ADR-0009-new.md", "# ADR-0009: New\n\n* **Status:** Draft\n")
    src = C.WorkTreeSource(repo)
    assert any(i["id"] == "ADR-0009" for i in C.adrs(src)["items"])
    assert not any(i["id"] == "ADR-0009" for i in C.adrs(C.GitSource(repo, "HEAD"))["items"])


# (b) dedup -----------------------------------------------------------------------------------------------

def test_blobs_deduplicate_unchanged_artifacts(repo, tmp_path):
    s1 = commit(repo, "one")
    write(repo, "docs/adr/ADR-0001-x.md", ADR.format(status="Accepted"))
    s2 = commit(repo, "two")
    out = tmp_path / "out"
    B.bundle(repo, s1, out)
    n1 = len(list((out / "blobs").glob("*.json")))
    B.bundle(repo, s2, out)
    m1 = json.loads((out / "snapshots" / s1 / "manifest.json").read_text())["tabs"]
    m2 = json.loads((out / "snapshots" / s2 / "manifest.json").read_text())["tabs"]
    assert m1["research"]["blob"] == m2["research"]["blob"]
    assert m1["architecture"]["blob"] == m2["architecture"]["blob"]
    assert m1["architecture"]["model_blobs"] == m2["architecture"]["model_blobs"]
    assert m1["adrs"]["blob"] != m2["adrs"]["blob"]
    added = len(list((out / "blobs").glob("*.json"))) - n1
    assert added < n1  # only the changed tabs (adrs, git, ...) add blobs


def test_architecture_model_blob_is_plain_model_json(repo, tmp_path):
    sha = commit(repo, "one")
    out = tmp_path / "out"
    B.bundle(repo, sha, out)
    m = json.loads((out / "snapshots" / sha / "manifest.json").read_text())
    (h,) = m["tabs"]["architecture"]["model_blobs"]
    assert json.loads((out / "blobs" / f"{h}.json").read_text()) == json.loads((FIX / "model.json").read_text())


# (c) idempotent --------------------------------------------------------------------------------------------

def test_bundle_is_idempotent(repo, tmp_path):
    sha = commit(repo, "one")
    out = tmp_path / "out"
    B.bundle(repo, sha, out)

    def state():
        return {str(p.relative_to(out)): p.read_bytes() for p in out.rglob("*") if p.is_file()}

    first = state()
    B.bundle(repo, sha, out)
    assert state() == first
    assert len(json.loads((out / "index.json").read_text())["commits"]) == 1


def test_backfill_builds_last_n(repo, tmp_path):
    for i in range(4):
        write(repo, "f.txt", str(i))
        commit(repo, f"c{i}")
    out = tmp_path / "out"
    B.bundle(repo, "HEAD", out, backfill=3)
    idx = json.loads((out / "index.json").read_text())["commits"]
    assert [c["subject"] for c in idx] == ["c3", "c2", "c1"]


# (d) missing artifacts -------------------------------------------------------------------------------------

def test_missing_artifacts_are_unavailable_with_reason(tmp_path):
    r = tmp_path / "bare"
    r.mkdir()
    git(r, "init", "-q", "-b", "main")
    write(r, "README.md", "hi")
    sha = commit(r, "only readme")
    out = tmp_path / "out"
    B.bundle(r, sha, out)
    m = json.loads((out / "snapshots" / sha / "manifest.json").read_text())["tabs"]
    for tab in ("architecture", "research", "experiments", "adrs", "prd_journeys", "evals", "bug_log", "dev_journey"):
        assert m[tab]["available"] is False and m[tab]["reason"], tab
    assert m["git"]["available"] is True
    assert "no slices" in m["prd_journeys"]["reason"]
    idx = json.loads((out / "index.json").read_text())["commits"][0]
    assert idx["tabs"]["adrs"] is False


def test_evals_membership_when_no_results(repo, tmp_path):
    write(repo, "evals/agents/GOLDEN.json", json.dumps(["TB01-G-001", "TB01-G-002", "TB01-D-001"]))
    sha = commit(repo, "one")
    tab = C.evals(C.GitSource(repo, sha))
    assert tab["available"] and tab["summary"]["results_committed"] is False
    assert tab["summary"]["membership"] == {"golden": 3, "diagnostic": 1}
    assert tab["summary"]["note"] == "no results committed"


def test_prd_journeys_one_page(repo):
    write(repo, "docs/slices/a/proposal.md", "---\npriority: P1\n---\n# Slice A\n\n## UX stories\n- As a user I can x\n- As a user I can y\n\n## Impact\nz\n")
    write(repo, "docs/slices/b/proposal.md", "# Slice B\n\n**Priority:** P0\n\n## UX stories\n1. As an owner I see z\n")
    sha = commit(repo, "slices")
    tab = C.prd_journeys(C.GitSource(repo, sha))
    assert [i["slice"] for i in tab["items"]] == ["b", "a"]
    assert tab["items"][1]["stories"] == ["As a user I can x", "As a user I can y"]
    assert tab["items"][0]["priority"] == "P0"


# (e) structural separation ---------------------------------------------------------------------------------

def test_manifest_never_references_runtime_and_runtime_is_unchanged(repo, tmp_path):
    s1 = commit(repo, "one")
    write(repo, "docs/adr/ADR-0001-x.md", ADR.format(status="Accepted"))
    s2 = commit(repo, "two")
    out = tmp_path / "out"
    R.write_runtime(None, out / "runtime.json")
    before = (out / "runtime.json").read_bytes()
    B.bundle(repo, s1, out)
    B.bundle(repo, s2, out)
    assert (out / "runtime.json").read_bytes() == before
    for p in list((out / "snapshots").rglob("manifest.json")) + [out / "index.json"]:
        text = p.read_text()
        assert "runtime" not in text.lower(), p
        assert json.loads(text).get("kind", "historical") == "historical"
    for blob in (out / "blobs").glob("*.json"):
        assert '"kind":"runtime"' not in blob.read_text()
    assert json.loads(before)["kind"] == "runtime" and json.loads(before)["not_tied_to_commit"] is True


# (f) runtime ------------------------------------------------------------------------------------------------

def test_runtime_empty_config_measures_nothing(tmp_path):
    d = R.write_runtime(tmp_path / "missing.json", tmp_path / "rt.json")
    assert d["as_of"]
    for name, f in d["figures"].items():
        assert f["measured"] is False and f["reason"] and f["label"] == "unavailable", name
        assert "value" not in f
    assert d["langfuse"]["applicable"] is False and "not applicable" in d["langfuse"]["reason"]


def test_runtime_empty_json_object_config(tmp_path):
    cfg = tmp_path / "ops" / "config.json"
    cfg.parent.mkdir()
    cfg.write_text("{}")
    d = R.collect_runtime(cfg)
    assert all(not f["measured"] for f in d["figures"].values())


def test_runtime_measures_live_health_and_versions(tmp_path):
    # a plain stand-in for the monitored app (the dashboard server only serves its own allowlisted artifacts)
    import functools
    import threading
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(tmp_path))
    handler.log_message = lambda *a, **k: None
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    (tmp_path / "health").write_text("ok")
    (tmp_path / "v.json").write_text(json.dumps({"commit": "abc123"}))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        (tmp_path / "exp.txt").write_text("abc123\n")
        (tmp_path / "tests.json").write_text(json.dumps({"passed": 5, "failed": 0}))
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({
            "health_url": f"http://127.0.0.1:{port}/health",
            "deployed_version": {"url": f"http://127.0.0.1:{port}/v.json", "json_path": "commit"},
            "expected_version": {"file": "exp.txt"},
            "test_summary_file": "tests.json"}))
        d = R.collect_runtime(cfg)
    finally:
        srv.shutdown()
    f = d["figures"]
    assert f["app_health"]["measured"] and f["app_health"]["label"] == "live" and f["app_health"]["value"]["http_status"] == 200
    assert f["deployed_version"]["value"] == "abc123" and f["deployed_version"]["label"] == "live"
    assert f["expected_version"]["label"] == "static"
    assert f["version_match"]["measured"] and f["version_match"]["value"] is True
    assert f["last_test_summary"]["value"] == {"passed": 5, "failed": 0}
    assert not f["ci_latest_run"]["measured"]


def test_runtime_unreachable_health_is_not_a_number(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"health_url": "http://127.0.0.1:9/health"}))
    f = R.collect_runtime(cfg)["figures"]["app_health"]
    assert f["measured"] is False and "could not reach" in f["reason"]


def test_runtime_never_leaks_url_secrets(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"health_url": "http://user:SECRETPW@127.0.0.1:9/h?token=SECRETTOK"}))
    text = json.dumps(R.collect_runtime(cfg))
    assert "SECRETPW" not in text and "SECRETTOK" not in text


def test_langfuse_applicable_only_when_declared(tmp_path):
    cfg = tmp_path / "c.json"
    cfg.write_text(json.dumps({"langfuse": {"llm_features": True, "host": "https://lf.example"}}))
    lf = R.collect_runtime(cfg)["langfuse"]
    assert lf["applicable"] and lf["configured"]["measured"] and lf["traces"]["measured"] is False


def test_server_is_read_only_and_serves_shell(tmp_path):
    import threading
    import urllib.error
    import urllib.request
    (tmp_path / "shell").mkdir()
    (tmp_path / "shell" / "index.html").write_text("<html>shell</html>")
    srv = R.make_server(tmp_path, "127.0.0.1", 0)
    assert srv.server_address[0] == "127.0.0.1"
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        assert b"shell" in urllib.request.urlopen(base + "/").read()
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(urllib.request.Request(base + "/shell/index.html", data=b"x", method="POST"))
        assert e.value.code in (501, 405)
        (tmp_path / "empty").mkdir()
        (tmp_path / "empty" / "secret.txt").write_text("x")
        with pytest.raises(urllib.error.HTTPError) as e:
            urllib.request.urlopen(base + "/empty/")
        assert e.value.code == 404  # no directory listing
    finally:
        srv.shutdown()


# (g) dev journey ---------------------------------------------------------------------------------------------

def test_dev_journey_counts_match_fixture(repo):
    write(repo, "docs/slices/s1/tasks.md", "- [x] a\n- [x] b\n- [ ] c\n- [ ] d\n- [ ] e\n")
    write(repo, "docs/slices/s1/verification.json", json.dumps({"criteria": [
        {"id": "A1", "verified": True}, {"id": "A2", "verified": False}, {"id": "A3", "status": "passed"}]}))
    write(repo, "docs/slices/s1/amendments.md", "# Amendments\n\n## 2026-10-19 add case\ntext\n\n## 2026-10-20 tighten\n")
    write(repo, "docs/slices/s2/tasks.md", "- [x] only\n")
    write(repo, "ops/events.jsonl", json.dumps({"at": "t", "stage": "6", "slice": "s1", "sha": "x", "verdict": "pass", "note": ""}) + "\n")
    sha = commit(repo, "slices")
    tab = C.dev_journey(C.GitSource(repo, sha))
    s1, s2 = tab["items"]
    assert s1["tasks"] == {"done": 2, "open": 3, "total": 5}
    assert s1["verification"] == {"verified": 2, "total": 3}
    assert s1["amendments"]["titles"] == ["2026-10-19 add case", "2026-10-20 tighten"] and s1["amendments"]["count"] == 2
    assert s2["tasks"]["total"] == 1 and s2["verification"]["available"] is False and s2["amendments"]["available"] is False
    assert len(tab["events"]) == 1 and tab["events"][0]["stage"] == "6"


def test_index_carries_latest_stage_event(repo, tmp_path):
    write(repo, "ops/events.jsonl", json.dumps({"at": "t1", "stage": "5", "slice": "s", "sha": "x", "verdict": "pass", "note": ""}) + "\n"
          + json.dumps({"at": "t2", "stage": "6", "slice": "s", "sha": "x", "verdict": "fail", "note": "n"}) + "\n")
    sha = commit(repo, "ev")
    out = tmp_path / "out"
    B.bundle(repo, sha, out)
    assert json.loads((out / "index.json").read_text())["commits"][0]["latest_stage_event"]["stage"] == "6"


# (h) stage events ----------------------------------------------------------------------------------------------

def test_stage_event_appends_valid_json_and_never_rewrites(repo):
    commit(repo, "one")
    script = REPO / "scripts" / "ops-stage-event.sh"
    ev = repo / "ops" / "events.jsonl"
    subprocess.run([str(script), "5", "j", "pass", "first note, with \"quotes\""], cwd=repo, check=True)
    first = ev.read_bytes()
    subprocess.run([str(script), "6", "j", "fail"], cwd=repo, check=True)
    after = ev.read_bytes()
    assert after.startswith(first)
    rows = [json.loads(l) for l in after.decode().splitlines()]
    assert [r["stage"] for r in rows] == ["5", "6"]
    assert set(rows[0]) == {"at", "stage", "slice", "sha", "verdict", "note"}
    assert rows[0]["sha"] == git(repo, "rev-parse", "HEAD") and rows[0]["note"] == 'first note, with "quotes"'
    assert subprocess.run([str(script), "x"], cwd=repo, capture_output=True).returncode == 2


# (i) dolls viewer ----------------------------------------------------------------------------------------------

def test_dolls_viewer_builds_and_has_model_loader():
    sys.path.insert(0, str(REPO / "skills" / "mermaid-nesting-dolls" / "scripts"))
    sys.dont_write_bytecode = True  # a committed-looking __pycache__ in skills/ fails the skills sync check
    import nesting_dolls as nd
    model = json.loads((REPO / "docs" / "explorer" / "software-factory.model.json").read_text())
    html = nd.build(model)
    assert 'new URLSearchParams(location.search).get("model")' in html
    assert '"software-factory"' in html or model["meta"]["title"] in html
    assert html.count('id="nd-model"') == 1


def test_dolls_check_still_passes_on_a_valid_model(tmp_path):
    (tmp_path / "f.txt").write_text("hello world\n")
    m = {"root": "a", "nodes": {"a": {"title": "A", "summary": "s", "children": [], "files": [{"path": "f.txt", "lines": "1", "contains": "hello"}]}}}
    (tmp_path / "m.json").write_text(json.dumps(m))
    p = subprocess.run([sys.executable, str(REPO / "skills/mermaid-nesting-dolls/scripts/nesting_dolls.py"), "check",
                        str(tmp_path / "m.json"), "--repo", str(tmp_path)], capture_output=True, text=True)
    assert p.returncode == 0, p.stdout + p.stderr


def test_explorer_model_check_adds_no_error_from_the_viewer_change():
    """The docs/explorer model has file-reference drift errors that predate this slice (other slices own them).
    The viewer change must not change what check reports: compare against the template at HEAD~ is not possible
    here, so assert check itself runs to completion and reports only file-reference errors."""
    p = subprocess.run([sys.executable, str(REPO / "skills/mermaid-nesting-dolls/scripts/nesting_dolls.py"), "check",
                        "docs/explorer/software-factory.model.json", "--repo", str(REPO)], capture_output=True, text=True, cwd=REPO)
    errs = [l for l in p.stdout.splitlines() if l.startswith("ERROR:")]
    assert re.search(r"\d+ nodes, \d+ diagrams, \d+ errors", p.stdout)
    assert all(re.search(r"file not found|does not contain|outside file|bad line range", e) for e in errs), errs


def test_bundle_writes_loaderless_viewer(repo, tmp_path):
    sha = commit(repo, "one")
    out = tmp_path / "out"
    B.bundle(repo, sha, out)
    html = (out / "viewer.html").read_text()
    assert '<script type="application/json" id="nd-model"></script>' in html
    assert 'get("model")' in html
    assert (out / "shell" / "index.html").exists()


# shell smoke (no browser) ----------------------------------------------------------------------------------------

def test_shell_is_self_contained_and_uses_only_ops_relative_paths():
    html = (REPO / "ops" / "shell" / "index.html").read_text()
    assert not re.search(r"(?:src|href)=[\"']?(?:https?:)?//", html)
    assert not re.search(r"""(?:fetch|import)\(\s*["']https?:""", html)
    assert "<script src" not in html and "<link" not in html
    fetched = re.findall(r'getJSON\("([^"]+)"\)', html) + re.findall(r'getJSON\("(\.\./[a-z/]+)', html)
    assert fetched and all(f.startswith("../") for f in fetched), fetched
    for needle in ("prefers-color-scheme", 'name="viewport"', "#/", "aria-current", "Snapshot at ", "not tied to a commit",
                   "not measured", "../viewer.html?model=", "../index.json", "../runtime.json"):
        assert needle in html, needle
    for tab in ("Overview", "Ops", "Architecture", "Research", "Experiments", "ADRs", "PRD journeys", "Langfuse",
                "Evals &amp; bugs".replace("&amp;", "&"), "Dev journey", "Git history"):
        assert tab in html, tab


def test_shell_script_parses_with_node():
    import shutil
    node = shutil.which("node")
    assert node, "node is required to syntax-check the shell script"
    html = (REPO / "ops" / "shell" / "index.html").read_text()
    js = re.search(r"<script>(.*)</script>", html, re.S).group(1)
    p = subprocess.run([node, "--check", "-"], input=js, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_dolls_template_script_parses_with_node():
    import shutil
    node = shutil.which("node")
    assert node, "node is required to syntax-check the viewer script"
    tpl = (REPO / "skills/mermaid-nesting-dolls/assets/template.html").read_text()
    js = re.findall(r"<script>(.*?)</script>", tpl, re.S)[-1]
    p = subprocess.run([node, "--check", "-"], input=js, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_shell_constrains_the_commit_selector_for_narrow_screens():
    """The selector was sized to its longest option and made the page 781 px wide at 390 px (seen in a real browser)."""
    html = (REPO / "ops" / "shell" / "index.html").read_text(encoding="utf-8")
    assert "#sel{width:100%" in html and "header>div{min-width:0" in html
