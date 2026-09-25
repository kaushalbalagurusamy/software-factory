"""TB-05 path guard evals.

Sources: docs/prds/TB-05-path-guard.md (behaviours 1 to 7), docs/contracts/profile.md (paths and their defaults:
research_dir `research`, design_dirs `docs/prd docs/spec docs/adr`, audit_dir `docs/audit`),
docs/contracts/roles-and-generation.md and TB-02 B5 (bash modes: research, audit, design, review are `readonly`;
orchestrator, implement, test are `full`), docs/contracts/hook-io.md (main session maps to main_session_role,
default orchestrator). Profiles: evals/agents/profiles/base.yaml and alt.yaml.
"""
from __future__ import annotations

import os

import pytest

from evals.agents import lib

TB = "05"
HOOK = "factory.hooks.path_guard"
REQS = ("R-06", "R-10")


def case(cid: str, *values, reqs=REQS):
    tier = "golden" if "-G-" in cid else "diagnostic"
    return pytest.param(*values, marks=pytest.mark.case(cid, tier=tier, tb=TB, reqs=list(reqs)), id=cid)


FILES = {
    "src/app.py": "print('app')\n",
    "evals/case.py": "x = 1\n",
    "tests/held_out/h.py": "x = 1\n",
    "tests/frozen/f.py": "x = 1\n",
    "qa/cases/c.py": "x = 1\n",
    "research/old.md": "notes\n",
    "notes/research/old.md": "notes\n",
}


def _build(tmp_path, profile, setup):
    files = dict(FILES)
    files.update(setup.get("files", {}))
    if setup.get("freeze"):
        files[".factory/frozen"] = ""
    prof = profile if isinstance(profile, dict) else lib.profile_dict(profile)
    root = lib.make_project(tmp_path, prof, files=files, symlinks=setup.get("symlinks"))
    outside = tmp_path / "outside"
    outside.mkdir(exist_ok=True)
    (outside / "target.py").write_text("x = 1\n")
    for rel, out_rel in setup.get("outside_symlinks", {}).items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        os.symlink(outside / out_rel, p)
    return root, outside


def _path(spec: str, root, outside) -> str:
    """ROOT/... -> absolute inside the project; OUT/... -> absolute outside it; anything else is passed verbatim."""
    if spec.startswith("ROOT/"):
        return str(root) + "/" + spec[5:]
    if spec.startswith("OUT/"):
        return str(outside) + "/" + spec[4:]
    return spec


def _run(tmp_path, profile, agent, tool, tool_input, setup=None):
    setup = setup or {}
    root, outside = _build(tmp_path, profile, setup)
    ti = {k: (_path(v, root, outside) if k == "file_path" else v) for k, v in tool_input.items()}
    cwd = root / setup["cwd"] if setup.get("cwd") else root
    pl = lib.payload(root, tool_name=tool, tool_input=ti, agent_type=agent)
    pl["cwd"] = str(cwd)
    return lib.run_decide(HOOK, pl, root)


def _write(path):
    return {"file_path": path, "content": "hello\n"}


def _edit(path):
    return {"file_path": path, "old_string": "a", "new_string": "b"}


# (profile, agent, tool, path, expected, setup, clause)
WRITE_CASES = [
    # golden
    case("TB05-G-001", "base", "research", "Write", "ROOT/research/notes.md", "allow", {}, "B2 research -> paths.research_dir"),
    case("TB05-G-002", "base", "research", "Write", "ROOT/src/app.py", "deny", {}, "B2 research only under research_dir"),
    case("TB05-G-003", "base", "review", "Write", "ROOT/docs/audit/x.md", "deny", {}, "B2 orchestrator and review -> nowhere (deny)"),
    case("TB05-G-004", "base", None, "Write", "ROOT/src/app.py", "deny", {}, "B1 main session -> main_session_role (default orchestrator); B2 orchestrator -> nowhere"),
    case("TB05-G-005", "base", "implement", "Write", "ROOT/src/app.py", "allow", {}, "B2 implement -> anywhere except eval, held-out, frozen-test paths"),
    case("TB05-G-006", "base", "implement", "Write", "ROOT/evals/case.py", "deny", {}, "B2 implement not in eval paths"),
    case("TB05-G-007", "base", "test", "Write", "ROOT/evals/new_case.py", "allow", {}, "B2 test -> paths.eval before the freeze"),
    # research
    case("TB05-D-001", "base", "research", "Edit", "ROOT/research/old.md", "allow", {}, "B2 Edit follows the same rule as Write"),
    case("TB05-D-002", "base", "research", "Write", "ROOT/research2/x.md", "deny", {}, "B2 must lie inside research_dir (sibling prefix is outside)"),
    case("TB05-D-003", "base", "research", "Write", "ROOT/research/../src/app.py", "deny", {}, "B2 path normalised before the check"),
    case("TB05-D-004", "alt", "research", "Write", "ROOT/notes/research/a.md", "allow", {}, "B2 research_dir from the profile (alt: notes/research)"),
    case("TB05-D-005", "alt", "research", "Write", "ROOT/research/a.md", "deny", {}, "B2 profile research_dir replaces the default"),
    case("TB05-D-006", "base", "research", "Write", "ROOT/research/link.md", "deny",
         {"symlinks": {"research/link.md": "src/app.py"}}, "B2 symlinks resolved when the path exists"),
    # design
    case("TB05-D-007", "base", "design", "Write", "ROOT/docs/prd/a.md", "allow", {}, "B2 design -> paths.design_dirs (default docs/prd)"),
    case("TB05-D-008", "base", "design", "Write", "ROOT/docs/spec/a.md", "allow", {}, "B2 design_dirs default includes docs/spec"),
    case("TB05-D-009", "base", "design", "Write", "ROOT/docs/adr/0001.md", "allow", {}, "B2 design_dirs default includes docs/adr"),
    case("TB05-D-010", "base", "design", "Write", "ROOT/docs/plans/a.md", "deny", {}, "B2 design only its folders"),
    case("TB05-D-011", "base", "design", "Edit", "ROOT/src/app.py", "deny", {}, "B2 design never app code"),
    case("TB05-D-012", "base", "design", "Write", "ROOT/docs/prdx/a.md", "deny", {}, "B2 inside the folder, not a name prefix"),
    case("TB05-D-013", "alt", "design", "Write", "ROOT/design/prd/a.md", "allow", {}, "B2 design_dirs from profile (alt)"),
    case("TB05-D-014", "alt", "design", "Write", "ROOT/design/adr/a.md", "allow", {}, "B2 design_dirs from profile (alt)"),
    case("TB05-D-015", "alt", "design", "Write", "ROOT/docs/prd/a.md", "deny", {}, "B2 profile design_dirs replace the default"),
    case("TB05-D-016", "alt", "design", "Write", "ROOT/docs/spec/a.md", "deny", {}, "B2 profile design_dirs replace the default"),
    # audit
    case("TB05-D-017", "base", "audit", "Write", "ROOT/docs/audit/a.md", "allow", {}, "B2 audit -> paths.audit_dir"),
    case("TB05-D-018", "base", "audit", "Write", "ROOT/docs/adr/a.md", "deny", {}, "B2 audit only audit_dir"),
    case("TB05-D-019", "alt", "audit", "Write", "ROOT/notes/audit/a.md", "allow", {}, "B2 audit_dir from profile (alt)"),
    case("TB05-D-020", "alt", "audit", "Write", "ROOT/docs/audit/a.md", "deny", {}, "B2 profile audit_dir replaces default"),
    case("TB05-D-021", "base", "audit", "Edit", "ROOT/src/app.py", "deny", {}, "B2 audit never app code"),
    # test and the freeze
    case("TB05-D-022", "base", "test", "Write", "ROOT/src/app.py", "deny", {}, "B2 test only paths.eval"),
    case("TB05-D-023", "base", "test", "Write", "ROOT/tests/held_out/h2.py", "deny", {}, "B2 test -> paths.eval only (held_out is not eval)"),
    case("TB05-D-024", "alt", "test", "Write", "ROOT/qa/cases/c2.py", "allow", {}, "B2 eval paths from profile (alt)"),
    case("TB05-D-025", "alt", "test", "Write", "ROOT/qa/golden/g.py", "allow", {}, "B2 every eval glob counts (alt)"),
    case("TB05-D-026", "alt", "test", "Write", "ROOT/evals/x.py", "deny", {}, "B2 evals/** is not an eval path in alt"),
    case("TB05-D-027", "base", "test", "Write", "ROOT/evals/baselines/b.json", "allow", {"freeze": True}, "B3 after freeze test may write inside baseline_update"),
    case("TB05-D-028", "alt", "test", "Write", "ROOT/qa/baselines/b.json", "allow", {"freeze": True}, "B3 baseline_update from profile (alt)"),
    case("TB05-D-029", "alt", "test", "Write", "ROOT/qa/cases/c.py", "deny", {"freeze": True}, "B3 after freeze eval paths are closed"),
    case("TB05-D-030", "base", "test", "Edit", "ROOT/evals/case.py", "deny", {"freeze": True}, "B3 freeze applies to Edit too"),
    case("TB05-D-031", "base", "test", "Write", "ROOT/src/app.py", "deny", {"freeze": True}, "B3 after freeze only baseline_update"),
    case("TB05-D-032", "alt", "test", "Write", "ROOT/qa/baselines/b.json", "deny", {}, "B2 before the freeze test writes paths.eval only (alt baseline is outside eval)"),
    # implement
    case("TB05-D-033", "base", "implement", "Write", "ROOT/tests/held_out/h2.py", "deny", {}, "B2 implement not held-out paths"),
    case("TB05-D-034", "base", "implement", "Write", "ROOT/tests/frozen/f.py", "deny", {}, "B2 implement not frozen-test paths"),
    case("TB05-D-035", "base", "implement", "Write", "ROOT/tests/unit/t.py", "allow", {}, "B2 implement anywhere else"),
    case("TB05-D-036", "base", "implement", "Write", "ROOT/evals_helper/x.py", "allow", {}, "B2 glob evals/** does not cover evals_helper/"),
    case("TB05-D-037", "base", "implement", "Write", "ROOT/src/../evals/x.py", "deny", {}, "B2 normalised path lands in eval"),
    case("TB05-D-038", "base", "implement", "Edit", "ROOT/evals/case.py", "deny", {}, "B2 Edit same as Write"),
    case("TB05-D-039", "alt", "implement", "Write", "ROOT/qa/secret/s.py", "deny", {}, "B2 held_out from profile (alt)"),
    case("TB05-D-040", "alt", "implement", "Write", "ROOT/qa/frozen/f.py", "deny", {}, "B2 frozen_tests from profile (alt)"),
    case("TB05-D-041", "alt", "implement", "Write", "ROOT/evals/x.py", "allow", {}, "B2 evals/** is not protected in alt"),
    case("TB05-D-042", "base", "implement", "Write", "src/rel.py", "allow", {}, "B2 relative path resolved against cwd"),
    case("TB05-D-043", "base", "implement", "Write", "evals/rel.py", "deny", {}, "B2 relative path resolved against cwd"),
    case("TB05-D-044", "base", "implement", "Write", "ROOT/src/alias.py", "deny",
         {"symlinks": {"src/alias.py": "evals/case.py"}}, "B2 symlinks resolved when the path exists"),
    case("TB05-D-045", "base", "implement", "Write", "../evals/x.py", "deny", {"cwd": "src"}, "B2 resolved against cwd (cwd=src)"),
    # outside the root
    case("TB05-D-046", "base", "implement", "Write", "OUT/x.py", "deny", {}, "B4 outside the project root denied for every role"),
    case("TB05-D-047", "base", "research", "Write", "ROOT/../outside/x.md", "deny", {}, "B4 resolves outside the root"),
    case("TB05-D-048", "base", "implement", "Write", "ROOT/src/escape.py", "deny",
         {"outside_symlinks": {"src/escape.py": "target.py"}}, "B4 symlink resolving outside the root"),
    case("TB05-D-049", "base", "test", "Write", "OUT/x.py", "deny", {}, "B4 every role"),
    # orchestrator, review, unknown, main-session mapping
    case("TB05-D-050", "base", "orchestrator", "Write", "ROOT/docs/prd/a.md", "deny", {}, "B2 orchestrator -> nowhere"),
    case("TB05-D-051", "base", "review", "Edit", "ROOT/src/app.py", "deny", {}, "B2 review -> nowhere"),
    case("TB05-D-052", "base", "intruder", "Write", "ROOT/src/app.py", "deny", {}, "B1 unknown agent types denied for Write"),
    case("TB05-D-053", "base", "intruder", "Edit", "ROOT/src/app.py", "deny", {}, "B1 unknown agent types denied for Edit"),
    case("TB05-D-054", lib.profile_dict("base", main_session_role="implement"), None, "Write", "ROOT/src/app.py", "allow", {},
         "B1 main session role comes from main_session_role"),
    case("TB05-D-055", "alt", None, "Write", "ROOT/notes/research/a.md", "deny", {}, "B1 alt main_session_role orchestrator -> nowhere"),
    case("TB05-D-056", "base", "orchestrator", "Edit", "ROOT/src/app.py", "deny", {}, "B2 orchestrator -> nowhere"),
]


@pytest.mark.parametrize("profile,agent,tool,path,expected,setup,clause", WRITE_CASES)
def test_write_edit(tmp_path, profile, agent, tool, path, expected, setup, clause):
    """TB-05 B1-B4: Write and Edit targets must lie inside the role's allowed folders (clause per case)."""
    ti = _write(path) if tool == "Write" else _edit(path)
    d = _run(tmp_path, profile, agent, tool, ti, setup)
    assert d.kind == expected, clause
    if expected != "allow":
        assert d.reason


def test_freeze_reason_names_freeze(tmp_path):
    """B3: after the freeze, test outside baseline_update is denied 'with a reason naming the freeze'."""
    d = _run(tmp_path, "base", "test", "Write", _write("ROOT/evals/case.py"), {"freeze": True})
    assert d.kind == "deny"
    assert "freez" in d.reason.lower()


test_freeze_reason_names_freeze = pytest.mark.case("TB05-G-008", tier="golden", tb=TB, reqs=list(REQS))(
    test_freeze_reason_names_freeze)


# ---------------------------------------------------------------- behaviour 6: reads always allowed

@pytest.mark.parametrize("agent,tool,tool_input,clause", [
    case("TB05-D-057", "implement", "Read", {"file_path": "ROOT/evals/case.py"}, "B6 reads governed by the blindness hook"),
    case("TB05-D-058", "review", "Read", {"file_path": "ROOT/src/app.py"}, "B6 Read always allowed"),
    case("TB05-D-059", "orchestrator", "Grep", {"pattern": "x", "path": "."}, "B6 Grep always allowed"),
    case("TB05-D-060", "research", "Glob", {"pattern": "**/*"}, "B6 Glob always allowed"),
    case("TB05-D-061", "intruder", "Read", {"file_path": "ROOT/src/app.py"}, "B1 only Write/Edit/Bash denied for unknown; B6 reads allowed"),
])
def test_reads_allowed(tmp_path, agent, tool, tool_input, clause):
    """TB-05 B6: 'Read, Grep and Glob are always allowed by this hook'."""
    d = _run(tmp_path, "base", agent, tool, tool_input)
    assert d.kind == "allow", clause


# ---------------------------------------------------------------- behaviour 5: read-only bash

BASH_CASES = [
    case("TB05-G-009", "research", "git log --oneline | head -5", "allow", "B5 every pipeline segment starts with an allowed command"),
    case("TB05-G-010", "research", "rm -rf research", "deny", "B5 rm is denied for readonly roles"),
    case("TB05-D-062", "audit", "git diff HEAD~1", "allow", "B5 git diff"),
    case("TB05-D-063", "review", "git show HEAD", "allow", "B5 git show"),
    case("TB05-D-064", "design", "git status", "allow", "B5 git status"),
    case("TB05-D-065", "audit", "git blame src/app.py", "allow", "B5 git blame"),
    case("TB05-D-066", "research", "ls -la", "allow", "B5 ls"),
    case("TB05-D-067", "research", "cat src/app.py", "allow", "B5 cat"),
    case("TB05-D-068", "audit", "head -n 5 src/app.py", "allow", "B5 head"),
    case("TB05-D-069", "audit", "tail -n 5 src/app.py", "allow", "B5 tail"),
    case("TB05-D-070", "audit", "wc -l src/app.py", "allow", "B5 wc"),
    case("TB05-D-071", "review", "grep -n print src/app.py", "allow", "B5 grep"),
    case("TB05-D-072", "review", "rg print src", "allow", "B5 rg"),
    case("TB05-D-073", "audit", "find src -name '*.py'", "allow", "B5 find without -delete or -exec"),
    case("TB05-D-074", "audit", "tree src", "allow", "B5 tree"),
    case("TB05-D-075", "design", "sf audit", "allow", "B5 sf audit"),
    case("TB05-D-076", "research", "sed -n 1,5p src/app.py", "allow", "B5 sed -n"),
    case("TB05-D-077", "audit", "awk '{print $1}' src/app.py", "allow", "B5 awk without redirection"),
    case("TB05-D-078", "research", "cat src/app.py | wc -l", "allow", "B5 pipeline of allowed segments"),
    case("TB05-D-079", "review", "git diff | head -50", "allow", "B5 pipeline of allowed segments"),
    case("TB05-D-080", "research", "grep 'a$(b)' src/app.py", "allow", "B5 command substitution inside quotes is not denied"),
    case("TB05-D-081", "research", "echo hi", "deny", "B5 only commands on the list"),
    case("TB05-D-082", "research", "python script.py", "deny", "B5 only commands on the list"),
    case("TB05-D-083", "audit", "ls > out.txt", "deny", "B5 redirection > denied"),
    case("TB05-D-084", "audit", "cat src/app.py >> docs/audit/a.md", "deny", "B5 redirection >> denied"),
    case("TB05-D-085", "research", "cat src/app.py | tee research/x.md", "deny", "B5 tee denied"),
    case("TB05-D-086", "review", "rm src/app.py", "deny", "B5 rm denied"),
    case("TB05-D-087", "design", "mv src/app.py src/b.py", "deny", "B5 mv denied"),
    case("TB05-D-088", "audit", "cp src/app.py docs/audit/app.py", "deny", "B5 cp denied"),
    case("TB05-D-089", "research", "chmod +x src/app.py", "deny", "B5 chmod denied"),
    case("TB05-D-090", "audit", "find . -name '*.pyc' -delete", "deny", "B5 find with -delete denied"),
    case("TB05-D-091", "audit", "find . -name '*.pyc' -exec rm {} \\;", "deny", "B5 find with -exec denied"),
    case("TB05-D-092", "research", "sed -i s/a/b/ src/app.py", "deny", "B5 only sed -n"),
    case("TB05-D-093", "audit", "awk '{print $1}' src/app.py > out.txt", "deny", "B5 awk with redirection denied"),
    case("TB05-D-094", "research", "cat $(ls src)", "deny", "B5 command substitution outside quotes denied"),
    case("TB05-D-095", "research", "cat `ls src`", "deny", "B5 command substitution (backticks) outside quotes denied"),
    case("TB05-D-096", "review", "git log && rm -rf src", "deny", "B5 rm in any segment denied"),
    case("TB05-D-097", "review", "ls; rm src/app.py", "deny", "B5 rm in any segment denied"),
    case("TB05-D-098", "review", "git push origin main", "deny", "B5 git push is not on the list"),
    case("TB05-D-099", "review", "git commit -m x", "deny", "B5 git commit is not on the list"),
    case("TB05-D-100", "design", "sf deploy", "deny", "B5 only sf audit"),
    case("TB05-D-101", "research", "ls | sh", "deny", "B5 every pipeline segment must be on the list"),
    case("TB05-D-102", "audit", "git checkout main", "deny", "B5 git checkout not on the list"),
    case("TB05-D-103", "intruder", "ls", "deny", "B1 unknown agent types denied for Bash"),
    case("TB05-D-104", "implement", "make build > build.log", "allow", "B5 applies only to readonly roles; implement is full"),
    case("TB05-D-105", "test", "pytest -q > test.log", "allow", "B5 applies only to readonly roles; test is full"),
    case("TB05-D-106", None, "git status", "allow", "B5 main session (orchestrator, full) not restricted by the list"),
]


@pytest.mark.parametrize("agent,command,expected,clause", BASH_CASES)
def test_bash_readonly(tmp_path, agent, command, expected, clause):
    """TB-05 B5: readonly roles may run only the read-only command list; redirections, tee, rm, mv, cp, chmod and
    unquoted command substitution are denied."""
    d = _run(tmp_path, "base", agent, "Bash", {"command": command})
    assert d.kind == expected, clause
    if expected != "allow":
        assert d.reason


# ---------------------------------------------------------------- behaviour 7: reasons

@pytest.mark.parametrize("profile,agent,tool,target,must_contain", [
    case("TB05-D-107", "alt", "research", "Write", "ROOT/src/app.py", ["research", "src/app.py", "notes/research"]),
    case("TB05-D-108", "alt", "design", "Write", "ROOT/src/x.py", ["design", "src/x.py", "design/prd", "design/adr"]),
    case("TB05-D-109", "alt", "audit", "Edit", "ROOT/src/app.py", ["audit", "src/app.py", "notes/audit"]),
    case("TB05-D-110", "base", "implement", "Write", "ROOT/evals/case.py", ["implement", "evals/case.py"]),
    case("TB05-D-111", "base", "review", "Write", "ROOT/src/app.py", ["review", "src/app.py"]),
])
def test_deny_reason_names_role_path_folders(tmp_path, profile, agent, tool, target, must_contain):
    """TB-05 B7: 'Every deny reason names the role, the offending path or command, and the allowed folders.'"""
    ti = _write(target) if tool == "Write" else _edit(target)
    d = _run(tmp_path, profile, agent, tool, ti)
    assert d.kind == "deny"
    for s in must_contain:
        assert s in d.reason, s


@pytest.mark.parametrize("profile,agent,command,must_contain", [
    case("TB05-D-112", "alt", "research", "rm -rf notes", ["research", "rm", "notes/research"]),
])
def test_bash_deny_reason(tmp_path, profile, agent, command, must_contain):
    """TB-05 B7: every deny reason names the role, the offending command and the allowed folders."""
    d = _run(tmp_path, profile, agent, "Bash", {"command": command})
    assert d.kind == "deny"
    for s in must_contain:
        assert s in d.reason, s


# ---------------------------------------------------------------- command line

def test_cli_path_guard(tmp_path):
    """hook-io adapter + TB-05 B2: research Write outside research_dir through `python -m factory.hooks path_guard`
    exits 2 with the reason on stderr; an allowed write exits 0 with empty stdout."""
    lib.need("factory.hooks.core", "run_hook")
    lib.need("factory.agents.profile", "load_profile")
    lib.need(HOOK, "decide")
    root = lib.make_project(tmp_path, files=FILES)
    bad = lib.run_cli("path_guard", lib.payload(root, tool_name="Write", tool_input=_write(str(root / "src/app.py")),
                                                agent_type="research"), root)
    ok = lib.run_cli("path_guard", lib.payload(root, tool_name="Write", tool_input=_write(str(root / "research/n.md")),
                                               agent_type="research"), root)
    assert bad.returncode == 2 and bad.stderr.strip()
    assert ok.returncode == 0 and ok.stdout.strip() == ""


test_cli_path_guard = pytest.mark.case("TB05-D-113", tier="diagnostic", tb=TB, reqs=list(REQS))(test_cli_path_guard)



# ================================================================ clarifications (docs/contracts/clarifications.md)

CLAR_WRITE = [
    case("TB05-D-115", "base", "implement", "Write", "ROOT/.factory/frozen", "deny", {}, "[A-05-5] implement may not write under .factory/**"),
    case("TB05-D-116", "base", "implement", "Edit", "ROOT/.factory/profile.yaml", "deny", {}, "[A-05-5] implement may not write under .factory/**"),
    case("TB05-D-117", "base", "implement", "Write", "ROOT/.factory/ledger/T-1.md", "deny", {}, "[A-05-5] implement may not write under .factory/**"),
    case("TB05-D-118", "base", "implement", "Write", "ROOT/src/evlink/new_case.py", "deny",
         {"symlinks": {"src/evlink": "evals"}}, "[A-05-6] nearest existing ancestor resolved through symlinks (lands in evals)"),
    case("TB05-D-119", "base", "research", "Write", "ROOT/research/srclink/new.md", "deny",
         {"symlinks": {"research/srclink": "src"}}, "[A-05-6] nearest existing ancestor resolved (lands in src)"),
    case("TB05-D-120", "base", "implement", "Write", "ROOT/src/outlink/sub/new.py", "deny",
         {"outside_symlinks": {"src/outlink": "."}}, "[A-05-6] + B4 nearest existing ancestor resolves outside the root"),
    case("TB05-D-121", "base", "implement", "Write", "ROOT/src/brand/new/dir/x.py", "allow", {}, "[A-05-6] nonexistent chain under src stays in src"),
    case("TB05-D-122", "base", "research", "Write", "ROOT/research/deep/new/x.md", "allow", {}, "[A-05-6] nonexistent chain under research"),
]


@pytest.mark.parametrize("profile,agent,tool,path,expected,setup,clause", CLAR_WRITE)
def test_write_edit_clarified(tmp_path, profile, agent, tool, path, expected, setup, clause):
    """clarifications [A-05-5] and [A-05-6] for Write and Edit (clause per case)."""
    ti = _write(path) if tool == "Write" else _edit(path)
    d = _run(tmp_path, profile, agent, tool, ti, setup)
    assert d.kind == expected, clause
    if expected != "allow":
        assert d.reason


CLAR_BASH = [
    case("TB05-D-123", None, "echo x > notes.txt", "allow", "[A-05-1] Bash writes by full-mode roles are not inspected (main session orchestrator)"),
    case("TB05-D-124", "orchestrator", "cp src/app.py src/b.py", "allow", "[A-05-1] orchestrator is full mode"),
    case("TB05-D-125", "implement", "rm -rf build && mv a b", "allow", "[A-05-1] implement is full mode"),
    case("TB05-D-126", "test", "chmod +x run.sh | tee log.txt", "allow", "[A-05-1] test is full mode"),
    case("TB05-D-127", "audit", "awk '{print > \"out.txt\"}' src/app.py", "allow", "[A-05-2] only shell redirection is checked for awk"),
    case("TB05-D-128", "research", 'grep "$(whoami)" src/app.py', "deny", "[A-05-3] double quotes do not exempt $(...)"),
    case("TB05-D-129", "research", 'grep "`whoami`" src/app.py', "deny", "[A-05-3] double quotes do not exempt backticks"),
    case("TB05-D-130", "review", "grep '`whoami`' src/app.py", "allow", "[A-05-3] backticks inside single quotes are exempt"),
]


@pytest.mark.parametrize("agent,command,expected,clause", CLAR_BASH)
def test_bash_clarified(tmp_path, agent, command, expected, clause):
    """clarifications [A-05-1], [A-05-2], [A-05-3] for Bash (clause per case)."""
    d = _run(tmp_path, "base", agent, "Bash", {"command": command})
    assert d.kind == expected, clause
    if expected != "allow":
        assert d.reason


@pytest.mark.parametrize("agent,tool,target", [
    case("TB05-D-131", "review", "Write", "ROOT/docs/audit/x.md"),
    case("TB05-D-132", "orchestrator", "Edit", "ROOT/src/app.py"),
])
def test_no_folder_reason(tmp_path, agent, tool, target):
    """clarifications [A-05-4]: 'For a role with no allowed folders the deny reason says no write access for role
    <role>.'"""
    ti = _write(target) if tool == "Write" else _edit(target)
    d = _run(tmp_path, "base", agent, tool, ti)
    assert d.kind == "deny"
    assert f"no write access for role {agent}" in d.reason



@pytest.mark.parametrize("tool,tool_input", [
    case("TB05-D-133", "Write", {"file_path": "ROOT/src/app.py", "content": "x"}),
    case("TB05-D-134", "Bash", {"command": "ls"}),
])
def test_unknown_agent_reason(tmp_path, tool, tool_input):
    """clarifications [U-4]: 'For an unknown agent type, path-guard deny reasons read unknown agent type <type>.'"""
    d = _run(tmp_path, "base", "intruder", tool, tool_input)
    assert d.kind == "deny"
    assert "unknown agent type intruder" in d.reason


# ---------------------------------------------------------------- R-24: published documentation

@pytest.mark.case("TB05-D-114", tier="diagnostic", tb="05", reqs=["R-24"])
def test_docs_hooks_path_guard_md():
    """TB-05 Acceptance: 'Document the component in the docs/hooks/ file you own, with one example payload or call
    (requirement R-24).' OWN list names docs/hooks/path_guard.md."""
    lib.need("factory.hooks.path_guard")
    doc_path = lib.REPO / "docs" / "hooks" / "path_guard.md"
    assert doc_path.is_file()
    text = doc_path.read_text()
    assert any(s in text for s in ("hook_event_name", "decide(", "python -m factory.hooks")), "one example payload or call"
