"""SFN-03 unit tests: dashboard content sources (PRD onepager, experiments, bugs, hitl, langfuse)."""
import json
import subprocess
from pathlib import Path

import pytest

from factory.hitl import store as H
from factory.intake import experiments as X
from factory.ops import collect as C
from factory.ops import runtime as R
from factory.ops.cli import main as ops_main


def git(r, *a):
    subprocess.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    return tmp_path


def put(r, rel, text):
    p = r / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def src(r):
    git(r, "add", "-A")
    git(r, "commit", "-qm", "c", "--allow-empty")
    return C.GitSource(r, "HEAD")


def test_onepager_journeys_flags_and_order(repo):
    put(repo, "docs/slices/a/proposal.md", "# A\n")
    put(repo, "docs/prd/onepager.md", "# Core\n\n## Journey: First\nSlices: a, zz\n- one\n- two\n\n## Journey: Second\n- only\n")
    d = C.prd_journeys(src(repo))
    j = [i for i in d["items"] if i.get("kind") == "journey"]
    assert [x["name"] for x in j] == ["First", "Second"]
    assert j[0]["steps"] == ["one", "two"] and j[0]["slices"] == [{"id": "a", "exists": True}, {"id": "zz", "exists": False}]
    assert any("unknown slice zz" in f for f in j[0]["flags"])
    assert any("Slices" in f for f in j[1]["flags"])
    assert "warning" not in d


def test_onepager_long_page_warns_and_keeps_everything(repo):
    body = "# Core\n\n## Journey: J\nSlices: x\n- s\n" + "\n" * 85
    put(repo, "docs/prd/onepager.md", body)
    d = C.prd_journeys(src(repo))
    assert d["warning"] == "longer than one page" and d["items"][0]["name"] == "J"


def test_slice_file_is_not_a_slice_dir(repo):
    put(repo, "docs/slices/plain", "a file\n")
    put(repo, "docs/prd/onepager.md", "# C\n## Journey: J\nSlices: plain\n- s\n")
    j = C.prd_journeys(src(repo))["items"][0]
    assert j["slices"][0]["exists"] is False


def test_prd_unavailable_names_all_sources(repo):
    put(repo, "README.md", "x")
    d = C.prd_journeys(src(repo))
    assert not d["available"] and "onepager.md" in d["reason"] and "docs/prds/*.md" in d["reason"]


def test_prd_files_listed(repo):
    put(repo, "docs/prds/P.md", "# P title\n\n| | |\n|---|---|\n| **Delivers** | things |\n")
    it = C.prd_journeys(src(repo))["items"][0]
    assert it["kind"] == "prd" and it["title"] == "P title" and it["delivers"] == "things"


def test_experiments_both_kinds_and_error(repo):
    put(repo, "experiments/a/results.json", "{}")
    put(repo, "experiments/b/resolved.json", json.dumps({"question": "q", "resolved_by": "r", "sources": ["s"], "as_of": "2026-01-01"}))
    put(repo, "experiments/c/resolved.json", "{nope")
    d = C.experiments(src(repo))
    kinds = {i["name"]: i["kind"] for i in d["items"]}
    assert kinds == {"a": "experiment", "b": "resolved", "c": "resolved"}
    assert "error" in next(i for i in d["items"] if i["name"] == "c")


def test_experiments_unavailable_reason(repo):
    put(repo, "x", "1")
    r = C.experiments(src(repo))["reason"]
    assert "results.json" in r and "resolved.json" in r


def test_resolved_check(tmp_path):
    d = tmp_path / "e1"
    d.mkdir()
    ok = {"question": "q", "resolved_by": "research", "sources": ["u"], "as_of": "2026-01-01"}
    (d / "resolved.json").write_text(json.dumps(ok))
    assert X.check_dir(d) == []
    for k in ok:
        bad = {x: v for x, v in ok.items() if x != k}
        (d / "resolved.json").write_text(json.dumps(bad))
        errs = X.check_dir(d)
        assert errs and "e1" in errs[0] and k in " ".join(errs)
    (d / "resolved.json").write_text(json.dumps({**ok, "sources": []}))
    assert X.check_dir(d)
    (d / "resolved.json").write_text(json.dumps({**ok, "as_of": "yesterday"}))
    assert X.check_dir(d)


def test_bug_files_statuses_and_qa_notes(repo):
    put(repo, "docs/bugs/b1.md", "# Crash on save\nStatus: Fixed\nSlice: s1\nCriterion: AC-1\n")
    put(repo, "docs/bugs/b2.md", "# No status\n")
    put(repo, "docs/bugs/b3.md", "# Weird\nStatus: invalid\n")
    put(repo, "docs/slices/s1/qa-notes.md", "# QA notes\n\n## Signature abc123\n- attempts 3\n- criteria: AC-1, AC-2\n- observed: boom\n- proposal: none\n")
    d = C.bug_log(src(repo))
    by = {i.get("id"): i for i in d["items"] if "id" in i}
    assert by["b1"]["status"] == "fixed" and by["b1"]["slice"] == "s1" and by["b1"]["criterion"] == "AC-1"
    assert by["b1"]["title"] == "Crash on save"
    assert by["b2"]["status"] == "invalid" and by["b3"]["status"] == "invalid"
    qa = [i for i in d["items"] if i.get("kind") == "qa-note"]
    assert len(qa) == 1 and "abc123" in qa[0]["text"] and qa[0]["attempts"] == 3


def test_empty_sources_are_not_available(repo):
    put(repo, "docs/bugs/.keep", "")
    put(repo, "ops/events.jsonl", "")
    s = src(repo)
    assert not C.bug_log(s)["available"] and "docs/bugs" in C.bug_log(s)["reason"]
    assert not C.hitl(s)["available"]


def test_hitl_historical(repo):
    put(repo, "docs/adr/ADR-001-x.md", "# X\n**Status:** **Proposed**\n")
    put(repo, "docs/adr/ADR-002-y.md", "# Y\nStatus: Accepted\n")
    put(repo, "docs/adr/ADR-003-z.md", "# Z\nStatus: pending owner\n")
    put(repo, "ops/events.jsonl", '{"at":"2020-01-01T00:00:00Z","stage":"hitl","verdict":"open"}\n{"stage":"7-qa"}\n')
    d = C.hitl(src(repo))
    assert sorted(i["id"] for i in d["items"] if i["kind"] == "adr") == ["ADR-001", "ADR-003"]
    assert sum(1 for i in d["items"] if i["kind"] == "event") == 1
    assert "hitl" in C.TABS and "hitl" in C.COLLECTORS


def test_hitl_events_after_commit_date_excluded(repo):
    put(repo, "ops/events.jsonl", '{"at":"2999-01-01T00:00:00Z","stage":"hitl","verdict":"open"}\n')
    assert not C.hitl(src(repo))["available"]


def test_runtime_stops_read_only_and_verified(tmp_path):
    d = R.collect_runtime(None, tmp_path / "ops")
    assert d["hitl"]["open"] == [] and not (tmp_path / ".factory").exists()
    H.request(tmp_path, "gate", "need owner", scope="run", by="agent:x")
    d = R.collect_runtime(None, tmp_path / "ops")["hitl"]
    assert [o["name"] for o in d["open"]] == ["gate"] and d["open"][0]["release_by"] == "human"
    log = tmp_path / ".factory/stops/log.jsonl"
    log.write_text(log.read_text().replace("need owner", "tampered"))
    d = R.collect_runtime(None, tmp_path / "ops")["hitl"]
    assert "stop ledger failed verification" in json.dumps(d) and d["open"] != []


def test_langfuse_message_and_declared(tmp_path):
    (tmp_path / "docs/slices/s1").mkdir(parents=True)
    (tmp_path / "docs/slices/s1/proposal.md").write_text("# s1\nllm_features: true\n")
    lf = R.collect_runtime(None, tmp_path / "ops")["langfuse"]
    assert lf["declared_in"] == ["s1"] and "LLM features declared in s1 but Langfuse is not configured" in lf["message"]
    assert lf["applicable"] is False  # existing contract kept


def test_init_langfuse_host(repo, capsys):
    put(repo, "a", "1")
    git(repo, "add", "a")
    git(repo, "commit", "-qm", "i")
    assert ops_main(["init", "--dir", str(repo), "--langfuse-host", "http://x.example"]) == 2
    assert not (repo / "ops/config.json").exists()
    put(repo, "ops/config.json", '{"keep": 1}')
    assert ops_main(["init", "--dir", str(repo), "--langfuse-host", "https://user:pw@lf.example/"]) == 0
    out = capsys.readouterr()
    cfg = json.loads((repo / "ops/config.json").read_text())
    assert cfg == {"keep": 1, "langfuse": {"host": "https://lf.example"}} and "pw" not in out.out + out.err


def test_viewer_script_parses():
    html = (Path(__file__).resolve().parents[1] / "ops/shell/index.html").read_text()
    assert html.count("<script>") == 1 and "hitl" in html and "human stops unknown" in html


def test_onepager_title_and_langfuse_host_only(repo, tmp_path):
    put(repo, "docs/prd/onepager.md", "# Core PRD\n\n## Journey: J\nSlices: x\n- s\n")
    assert C.prd_journeys(src(repo))["title"] == "Core PRD"
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"langfuse": {"host": "https://lf.example.com"}}))
    lf = R.collect_runtime(cfg)["langfuse"]
    assert lf["applicable"] and "lf.example.com" in json.dumps(lf["configured"])
    assert "not checked" in lf["traces"]["reason"]
