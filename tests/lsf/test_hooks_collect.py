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


EXTRA = {
    "experiments/e3/resolved.json": json.dumps({"question": "q", "resolved_by": "research", "sources": ["s"], "as_of": "2026-10-01"}),
    "experiments/e4/resolved.json": "{bad",
    "docs/prd/onepager.md": "# Core\n## Journey: Buy\nSlices: s1, ghost\n- one\n- two\n## Journey: Lonely\n- x\n",
    "docs/prds/P-1.md": "# P1\n| **Delivers** | a thing |\n",
    "docs/bugs/b1.md": "# Bug one\nStatus: Fixed\nSlice: s1\nCriterion: C-1\n",
    "docs/bugs/b2.md": "# Bug two\nStatus: nonsense\n",
    "docs/slices/s1/qa-notes.md": "# QA\n## Signature abc\nattempts 3\ncriteria: C-1, C-2\nobserved boom\n",
}


def test_parity_with_factory_collectors(repo):
    sys.path.insert(0, str(ROOT))
    from factory.ops import collect
    _fixture(repo)
    for p, t in EXTRA.items():
        f = repo / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(t)
    mine = json.loads(run(repo, "bundle", "--json").stdout)["tabs"]
    theirs = collect.collect_all(collect.WorkTreeSource(repo))
    for tab in ("architecture", "research", "experiments", "adrs", "prd_journeys", "bug_log", "git"):
        assert mine[tab]["available"] is True and mine[tab]["items"] == theirs[tab]["items"], tab
        assert mine[tab]["summary"] == theirs[tab]["summary"], tab
    assert mine["prd_journeys"].get("warning") == theirs["prd_journeys"].get("warning")


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


def test_onepager_resolved_and_qa_notes_shapes(repo):
    for p, x in EXTRA.items():
        f = repo / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(x)
    tabs = json.loads(run(repo, "bundle", "--json").stdout)["tabs"]
    j = tabs["prd_journeys"]["items"][0]
    assert j["kind"] == "journey" and j["name"] == "Buy" and "unknown slice ghost" in j["flags"] and j["steps"] == ["one", "two"]
    assert tabs["prd_journeys"]["title"] == "Core"
    kinds = {(i["name"], i["kind"]) for i in tabs["experiments"]["items"]}
    assert ("e3", "resolved") in kinds and any("error" in i for i in tabs["experiments"]["items"])
    bugs = {i.get("id"): i for i in tabs["bug_log"]["items"]}
    assert bugs["b1"]["status"] == "fixed" and bugs["b2"]["status"] == "invalid"
    assert any(i.get("kind") == "qa-note" and i["attempts"] == 3 for i in tabs["bug_log"]["items"])


def test_bundle_at_sha(repo):
    _fixture(repo)
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    t = json.loads(run(repo, "bundle", "--json", "--sha", sha[:8]).stdout)["tabs"]
    assert t["research"]["available"]
    assert run(repo, "bundle", "--sha", "zzzz").returncode == 2
    assert run(repo, "bundle", "--sha", "deadbeef").returncode == 1


def test_free_form_qa_report_is_a_linked_entry(repo):
    for p, x in {"docs/slices/prefix/qa-notes.md": "# QA report: prefix\n\nRan 12 cases. 1 fails: login returns 500.\n",
                 "docs/slices/s1/qa-notes.md": EXTRA["docs/slices/s1/qa-notes.md"],
                 "docs/slices/s3/qa-notes.md": "# QA notes\n"}.items():
        f = repo / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(x)
    items = json.loads(run(repo, "bundle", "--json").stdout)["tabs"]["bug_log"]["items"]
    reps = [i for i in items if i.get("kind") == "qa-report"]
    assert [(i["slice"], i["path"], i["title"]) for i in reps] == [("prefix", "docs/slices/prefix/qa-notes.md", "QA report: prefix")]
    assert "login returns 500" in reps[0]["text"]
    assert any(i.get("kind") == "qa-note" and i["attempts"] == 3 for i in items)
