import json
import subprocess
import sys
from pathlib import Path

from conftest import LSF, SKILL, events, run

ROOT = Path(__file__).resolve().parents[2]


def test_hooks_print_install_idempotent_uninstall(repo, tmp_path):
    cfg = json.loads(run(repo, "hooks", "print").stdout)["hooks"]
    assert set(cfg) == {"SubagentStop", "Stop", "PostToolUse", "PreToolUse"} and cfg["PostToolUse"][0]["matcher"] == "Bash"
    proj = tmp_path / "p"
    (proj / ".claude").mkdir(parents=True)
    f = proj / ".claude" / "settings.local.json"
    existing = {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
    f.write_text(json.dumps(existing))
    r = run(repo, "hooks", "install", "--project", str(proj))
    assert r.returncode == 0 and "+" in r.stdout and json.loads(f.read_text()) == existing
    run(repo, "hooks", "install", "--project", str(proj), "--apply")
    once = f.read_text()
    assert "echo mine" in once and "Bash(ls)" in once
    assert "no change" in run(repo, "hooks", "install", "--project", str(proj), "--apply").stdout and f.read_text() == once
    run(repo, "hooks", "uninstall", "--project", str(proj), "--apply")
    assert json.loads(f.read_text()) == existing


def test_hook_always_zero_and_silent(repo):
    run(repo, "init")
    for payload in ("", "not json", "[1]", '{"tool_input": 3}', '{"agent_type": 5}'):
        r = run(repo, "hook", "Stop", stdin=payload)
        assert r.returncode == 0 and r.stdout == "" and (payload != "" and payload != "not json" or r.stderr == "")
    run(repo, "hook", "SubagentStop", stdin=json.dumps({"agent_type": "qa", "last_assistant_message": "done token=abc123def456ghi"}))
    e = events(repo)[-1]
    assert e["source"] == "hook" and e["role"] == "qa" and "abc123" not in e["note"] and len(e["note"]) <= 200
    n = len(events(repo))
    run(repo, "hook", "PostToolUse", stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}))
    assert len(events(repo)) == n
    run(repo, "hook", "PostToolUse", stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}))
    assert "git commit" in events(repo)[-1]["note"]


FIXTURE = {
    "research/a.md": "# Alpha\nAs of: 2026-10-01\n",
    "experiments/e1/results.json": '{"winner": "x"}',
    "experiments/e2/results.json": "{bad",
    "docs/adr/ADR-001-pick.md": "# Pick\n**Status:** Accepted\n**Date:** 2026-10-02\n",
    "docs/slices/s1/proposal.md": "# Slice one\npriority: 2\n## UX stories\n- As a user I act\n",
    "docs/bugs/b1.md": "# Bug one\nStatus: open\n",
    "docs/bug-log.jsonl": '{"id": 1}\nnot json\n',
    "docs/explorer/x.model.json": json.dumps({"meta": {"title": "T"}, "root": "r", "nodes": {"r": {"title": "R", "diagram": ["flowchart"]}}}),
}


def _fixture(repo):
    for p, t in FIXTURE.items():
        f = repo / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(t)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "fixture"], check=True)


def test_parity_with_factory_collectors(repo):
    sys.path.insert(0, str(ROOT))
    from factory.ops import collect
    _fixture(repo)
    mine = json.loads(run(repo, "bundle", "--json").stdout)["tabs"]
    theirs = collect.collect_all(collect.WorkTreeSource(repo))
    for tab in ("architecture", "research", "experiments", "adrs", "prd_journeys", "bug_log", "git"):
        assert mine[tab]["available"] is True and mine[tab]["items"] == theirs[tab]["items"], tab


def test_unavailable_tabs_name_the_path_and_never_empty_available(repo):
    tabs = json.loads(run(repo, "bundle", "--json").stdout)["tabs"]
    assert set(tabs) >= {"research", "experiments", "adrs", "bug_log", "prd_journeys", "architecture", "git", "docs"}
    for name, t in tabs.items():
        assert (t["available"] and t["items"]) or (not t["available"] and t["reason"]), name
    assert tabs["docs"] == {"available": False, "reason": "docs/eli12/index.json not found"}
    assert "research/*.md" in tabs["research"]["reason"]


def test_docs_tab_reads_eli12_index(repo):
    (repo / "docs/eli12").mkdir(parents=True)
    (repo / "pkg").mkdir()
    (repo / "pkg/m.py").write_text("x = 1\n\ndef go():\n    pass\n")
    (repo / "docs/eli12/pkg.m.md").write_text("# pkg/m.py\n\n## go\n**What it does:** goes.\n")
    (repo / "docs/eli12/index.json").write_text(json.dumps({"pkg/m.py": "docs/eli12/pkg.m.md"}))
    t = json.loads(run(repo, "bundle", "--json").stdout)["tabs"]["docs"]
    assert t["available"] and t["items"][0]["symbols"] == [{"name": "go", "line": 3}]


def test_onepager_and_resolved_and_qa_notes(repo):
    for p, t in {"docs/prd/onepager.md": "# P\n## Journey: Buy\nSlices: s1, ghost\n- step one\n",
                 "docs/slices/s1/qa-notes.md": "# QA\n## flaky thing\n",
                 "experiments/r1/resolved.json": '{"question": "q"}'}.items():
        f = repo / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(t)
    tabs = json.loads(run(repo, "bundle", "--json").stdout)["tabs"]
    j = tabs["prd_journeys"]["items"][0]
    assert j["name"] == "Buy" and j["unknown_slices"] == ["ghost"] and j["steps"] == ["step one"]
    assert tabs["bug_log"]["items"][0]["failures"] == ["flaky thing"]
    assert tabs["experiments"]["items"][0]["kind"] == "resolved"


def test_bundle_at_sha(repo):
    _fixture(repo)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    t = json.loads(run(repo, "bundle", "--json", "--sha", sha[:8]).stdout)["tabs"]
    assert t["research"]["available"]
    assert run(repo, "bundle", "--sha", "zzzz").returncode == 2
    assert run(repo, "bundle", "--sha", "deadbeef").returncode == 1
