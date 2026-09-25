"""TB-08 bash guard evals: git hygiene and one-way doors.

Sources: docs/prds/TB-08-bash-guard.md (behaviours 1 to 6), R-13 and R-14 in docs/factory/requirements.md,
docs/contracts/profile.md (`deploy.route`, `one_way_door_patterns` "added to the built-in defaults"),
docs/contracts/hook-io.md (payload with no agent_type is the main session; default role orchestrator).
Profiles: base (deploy.route "deployctl push", pattern \\bmigrate\\s+--drop\\b) and alt (deploy.route
"cloudctl release", patterns \\bdb-reset\\b and \\bpurge-bucket\\b, main_session_role orchestrator).
"""
from __future__ import annotations

import pytest

from evals.agents import lib

TB = "08"
HOOK = "factory.hooks.bash_guard"
R13 = ["R-13"]
R14 = ["R-14"]


def case(cid: str, *values, reqs=R13):
    tier = "golden" if "-G-" in cid else "diagnostic"
    return pytest.param(*values, marks=pytest.mark.case(cid, tier=tier, tb=TB, reqs=list(reqs)), id=cid)


def _run(tmp_path, profile, agent, command, tool="Bash"):
    prof = profile if isinstance(profile, dict) else lib.profile_dict(profile)
    root = lib.make_project(tmp_path, prof, files={"src/app.py": "print('app')\n"})
    command = command.replace("{ROOT}", str(root))
    ti = {"command": command} if tool == "Bash" else {"file_path": str(root / "src/x.md"), "content": command}
    return lib.run_decide(HOOK, lib.payload(root, tool_name=tool, tool_input=ti, agent_type=agent), root)


def _check(d, expected, clause):
    assert d.kind == expected, clause
    if expected != "allow":
        assert d.reason, "B6: the reason names the rule that matched"


# ---------------------------------------------------------------- golden

GOLDEN = [
    case("TB08-G-001", "base", "orchestrator", "git push --force origin main", "ask", "B2 force push: orchestrator -> ask"),
    case("TB08-G-002", "base", "test", "git push --force origin main", "deny", "B2 force push: every other role -> deny"),
    case("TB08-G-003", "base", None, "git add -A", "ask", "B2 git add -A: the main session -> ask"),
    case("TB08-G-004", "base", "implement", 'git commit -m "wip"', "deny", "B3 implement never commits"),
    case("TB08-G-005", "base", "implement", "git diff src/app.py", "allow", "B3 read-only git allowed for implement"),
    case("TB08-G-006", "base", "orchestrator", "terraform destroy", "ask", "B4 resource deletion: orchestrator -> ask", reqs=R14),
    case("TB08-G-007", "base", "test", "kubectl delete pod web-1", "deny", "B4 other roles: same commands denied", reqs=R14),
    case("TB08-G-008", "base", "orchestrator", "deployctl push --prod", "ask", "B4 command starting with profile.deploy.route -> ask", reqs=R14),
    case("TB08-G-009", "base", "orchestrator", 'echo "git push --force"', "allow", "B5 not on substrings inside quoted echo arguments"),
    case("TB08-G-010", "base", "orchestrator", "pytest -q", "allow", "B5 a command with no match is allowed"),
]


@pytest.mark.parametrize("profile,agent,command,expected,clause", GOLDEN)
def test_golden(tmp_path, profile, agent, command, expected, clause):
    """TB-08 golden core: one clear clause of B2-B5 per case (see clause)."""
    _check(_run(tmp_path, profile, agent, command), expected, clause)


# ---------------------------------------------------------------- behaviour 2: git hygiene, all roles

HYGIENE = [
    "git add -A", "git add --all", "git add .", "git add *",
    "git commit --no-verify -m x", "git push --no-verify origin main",
    "git commit --amend", "git commit --amend --no-edit",
    "git rebase main", "git rebase -i HEAD~3",
    "git push --force", "git push -f origin main", "git push --force-with-lease", "git push origin main --force",
    "git reset --hard", "git reset --hard HEAD~1",
]

_hyg_cases = []
_n = 1
for _cmd in HYGIENE:
    _hyg_cases.append(case(f"TB08-D-{_n:03d}", "orchestrator", _cmd, "ask", "B2 orchestrator -> ask"))
    _hyg_cases.append(case(f"TB08-D-{_n + 1:03d}", "test", _cmd, "deny", "B2 every other role -> deny"))
    _n += 2
# _n is now 33
_hyg_cases += [
    case("TB08-D-033", None, "git reset --hard", "ask", "B2 main session -> ask"),
    case("TB08-D-034", None, "git push -f", "ask", "B2 main session -> ask"),
    case("TB08-D-035", "review", "git add -A", "deny", "B2 other role (review) -> deny"),
    case("TB08-D-036", "research", "git rebase main", "deny", "B2 other role (research) -> deny"),
    case("TB08-D-037", "audit", "git push -f", "deny", "B2 other role (audit) -> deny"),
    case("TB08-D-038", "design", "git reset --hard", "deny", "B2 other role (design) -> deny"),
    case("TB08-D-039", "implement", "git add -A", "deny", "B2/B3 implement -> deny"),
    case("TB08-D-040", "implement", "git push --force", "deny", "B2/B3 implement -> deny"),
    case("TB08-D-041", "test", "git  add   -A", "deny", "B1 parsed command (extra whitespace)"),
    case("TB08-D-042", "test", "cd repo && git add .", "deny", "B1 && segments inspected"),
    case("TB08-D-043", "test", "make lint; git reset --hard", "deny", "B1 ; segments inspected"),
    case("TB08-D-044", "test", "git status | cat && git push -f", "deny", "B1 pipeline and && segments"),
    case("TB08-D-045", "orchestrator", "npm test && git commit --amend", "ask", "B1 segments; B2 amend -> ask"),
    case("TB08-D-046", "test", "git commit -am 'msg' --no-verify", "deny", "B2 --no-verify anywhere in the git command"),
]


@pytest.mark.parametrize("agent,command,expected,clause", _hyg_cases)
def test_git_hygiene(tmp_path, agent, command, expected, clause):
    """TB-08 B2: git add -A/--all/./*, --no-verify, commit --amend, rebase, push --force/-f/--force-with-lease and
    reset --hard return ask for orchestrator and the main session, deny for every other role."""
    _check(_run(tmp_path, "base", agent, command), expected, clause)


# ---------------------------------------------------------------- behaviour 3: implement never commits

IMPLEMENT = [
    case("TB08-D-047", "git stash", "deny", "B3 stash"),
    case("TB08-D-048", "git stash list", "deny", "B3 stash"),
    case("TB08-D-049", "git checkout main", "deny", "B3 checkout"),
    case("TB08-D-050", "git checkout -- src/app.py", "deny", "B3 checkout"),
    case("TB08-D-051", "git restore src/app.py", "deny", "B3 restore"),
    case("TB08-D-052", "git reset HEAD~1", "deny", "B3 reset"),
    case("TB08-D-053", "git reset --soft HEAD~1", "deny", "B3 reset"),
    case("TB08-D-054", "git clean -fd", "deny", "B3 clean"),
    case("TB08-D-055", "git add src/app.py", "deny", "B3 add"),
    case("TB08-D-056", "git commit -m done", "deny", "B3 commit"),
    case("TB08-D-057", "git mv src/app.py src/main.py", "deny", "B3 mv"),
    case("TB08-D-058", "git rm src/app.py", "deny", "B3 rm"),
    case("TB08-D-059", "git push origin main", "deny", "B3 push"),
    case("TB08-D-060", "git merge main", "deny", "B3 merge"),
    case("TB08-D-061", "git cherry-pick abc1234", "deny", "B3 cherry-pick"),
    case("TB08-D-062", "make test && git commit -m done", "deny", "B1 segments; B3 commit"),
    case("TB08-D-063", "git log --oneline -5", "allow", "B3 read-only git: log"),
    case("TB08-D-064", "git show HEAD", "allow", "B3 read-only git: show"),
    case("TB08-D-065", "git status", "allow", "B3 read-only git: status"),
    case("TB08-D-066", "git blame src/app.py", "allow", "B3 read-only git: blame"),
    case("TB08-D-067", "git diff", "allow", "B3 read-only git: diff"),
    case("TB08-D-068", "pytest tests/unit -q", "allow", "B5 no match"),
]


@pytest.mark.parametrize("command,expected,clause", IMPLEMENT)
def test_implement_git(tmp_path, command, expected, clause):
    """TB-08 B3: 'for implement, deny git stash, checkout, restore, reset, clean, add, commit, mv, rm, push, merge,
    cherry-pick; read-only git (diff, log, show, status, blame) is allowed.'"""
    _check(_run(tmp_path, "base", "implement", command), expected, clause)


@pytest.mark.parametrize("agent,command", [
    case("TB08-D-069", "test", "git stash"),
    case("TB08-D-070", "test", "git checkout main"),
    case("TB08-D-071", "orchestrator", 'git commit -m "fix parser"'),
    case("TB08-D-072", "orchestrator", "git add src/app.py"),
    case("TB08-D-073", "orchestrator", "git push origin main"),
    case("TB08-D-074", None, "git merge feature"),
    case("TB08-D-075", "test", "git push origin main"),
])
def test_shared_tree_rule_is_implement_only(tmp_path, agent, command):
    """TB-08 B3 applies to implement only; B5: other roles running a command outside the B2 and B4 lists are allowed."""
    _check(_run(tmp_path, "base", agent, command), "allow", "B3 implement only; B5 no match")


# ---------------------------------------------------------------- behaviour 4: one-way doors

DOORS = [
    'psql -c "DROP TABLE users;"',
    'psql -c "DROP DATABASE app;"',
    'psql -c "ALTER TABLE users DROP COLUMN email;"',
    'psql -c "TRUNCATE users;"',
    'psql -c "DELETE FROM users;"',
    "terraform destroy -auto-approve",
    "kubectl delete namespace prod",
    "gh repo delete owner/repo --yes",
    "rm -rf /var/data",
    "rm -rf src",
    "rm -fr build",
    "rm -rf /tmp/../etc",
    "deployctl push",
    "cd app && deployctl push",
    "./manage migrate --drop",
]
_door_cases = []
_m = 76
for _cmd in DOORS:
    _door_cases.append(case(f"TB08-D-{_m:03d}", "base", "orchestrator", _cmd, "ask", "B4 orchestrator -> ask", reqs=R14))
    _door_cases.append(case(f"TB08-D-{_m + 1:03d}", "base", "test", _cmd, "deny", "B4 other roles -> deny", reqs=R14))
    _m += 2
# _m is now 106
_door_cases += [
    case("TB08-D-106", "base", None, "terraform destroy", "ask", "B4 main session -> ask", reqs=R14),
    case("TB08-D-107", "base", "implement", "deployctl push", "deny", "B4 other roles (implement) -> deny", reqs=R14),
    case("TB08-D-108", "base", "review", 'psql -c "DROP TABLE users;"', "deny", "B4 other roles (review) -> deny", reqs=R14),
    case("TB08-D-109", "base", "orchestrator", "yes | terraform destroy", "ask", "B1 pipeline segments", reqs=R14),
    case("TB08-D-110", "base", "orchestrator", "true && kubectl delete pod web-1", "ask", "B1 && segments", reqs=R14),
    # alt profile: deploy route and one_way_door_patterns come from the profile
    case("TB08-D-111", "alt", "orchestrator", "cloudctl release v2", "ask", "B4 profile.deploy.route (alt)", reqs=R14),
    case("TB08-D-112", "alt", "test", "cloudctl release v2", "deny", "B4 profile.deploy.route (alt), other role", reqs=R14),
    case("TB08-D-113", "alt", None, "cloudctl release", "ask", "B4 alt main session (orchestrator)", reqs=R14),
    case("TB08-D-114", "alt", "orchestrator", "make db-reset", "ask", "B4 profile one_way_door_patterns (alt)", reqs=R14),
    case("TB08-D-115", "alt", "implement", "make db-reset", "deny", "B4 pattern, other role", reqs=R14),
    case("TB08-D-116", "alt", "orchestrator", "purge-bucket assets", "ask", "B4 profile one_way_door_patterns (alt)", reqs=R14),
    case("TB08-D-117", "alt", "orchestrator", "terraform destroy", "ask", "profile contract: patterns are added to the built-in defaults", reqs=R14),
    # boundaries: must stay allowed
    case("TB08-D-118", "base", "orchestrator", 'psql -c "DELETE FROM users WHERE id = 1;"', "allow", "B4 DELETE FROM with a WHERE is not a door", reqs=R14),
    case("TB08-D-119", "base", "test", 'psql -c "SELECT * FROM users;"', "allow", "B5 no match", reqs=R14),
    case("TB08-D-120", "base", "orchestrator", "rm -rf /tmp/build-cache", "allow", "B4 rm -rf inside /tmp is not a door", reqs=R14),
    case("TB08-D-121", "base", "test", "rm -rf node_modules", "allow", "B4 the project's node_modules is exempt", reqs=R14),
    case("TB08-D-122", "base", "test", "rm -rf .venv", "allow", "B4 the project's .venv is exempt", reqs=R14),
    case("TB08-D-123", "base", "orchestrator", "terraform plan", "allow", "B5 no match", reqs=R14),
    case("TB08-D-124", "base", "orchestrator", "kubectl get pods", "allow", "B5 no match", reqs=R14),
    case("TB08-D-125", "base", "orchestrator", "gh repo view owner/repo", "allow", "B5 no match", reqs=R14),
    case("TB08-D-126", "base", "orchestrator", "deployctl status", "allow", "B4 only commands starting with the route", reqs=R14),
    case("TB08-D-127", "base", "orchestrator", "./manage migrate --dry-run", "allow", "B4 pattern does not match", reqs=R14),
    case("TB08-D-128", "alt", "orchestrator", "deployctl push", "allow", "B4 route is profile data; not a door in alt", reqs=R14),
    case("TB08-D-129", "base", "orchestrator", "make db-reset", "allow", "B4 alt-only pattern is not a door in base", reqs=R14),
    case("TB08-D-130", "alt", "orchestrator", "./manage migrate --drop", "allow", "B4 base-only pattern is not a door in alt", reqs=R14),
]


@pytest.mark.parametrize("profile,agent,command,expected,clause", _door_cases)
def test_one_way_doors(tmp_path, profile, agent, command, expected, clause):
    """TB-08 B4: destructive SQL, resource deletion, commands starting with profile.deploy.route and profile
    one_way_door_patterns return ask for orchestrator and the main session; the same commands are denied for other
    roles."""
    _check(_run(tmp_path, profile, agent, command), expected, clause)


# ---------------------------------------------------------------- behaviour 5: quoted-argument false positives

QUOTED = [
    case("TB08-D-131", "base", "test", 'echo "git push --force is dangerous"', "B5 quoted echo argument"),
    case("TB08-D-132", "base", "orchestrator", "printf 'git reset --hard\\n'", "B5 quoted printf argument"),
    case("TB08-D-133", "base", "orchestrator", 'git commit -m "stop using git add -A"', "B5 git commit -m message"),
    case("TB08-D-134", "base", "test", 'git commit -m "remove --no-verify from hooks"', "B5 git commit -m message"),
    case("TB08-D-135", "base", "test", 'echo "DROP TABLE users"', "B5 quoted echo argument", reqs=R14),
    case("TB08-D-136", "base", "orchestrator", "echo 'terraform destroy'", "B5 quoted echo argument", reqs=R14),
    case("TB08-D-137", "base", "test", 'echo "rm -rf /"', "B5 quoted echo argument", reqs=R14),
    case("TB08-D-138", "base", "orchestrator", 'git commit -m "document deployctl push"', "B5 git commit -m message", reqs=R14),
    case("TB08-D-139", "alt", "orchestrator", 'echo "run db-reset later"', "B5 quoted echo argument (profile pattern)", reqs=R14),
    case("TB08-D-140", "base", "test", "printf '%s\\n' 'git rebase main'", "B5 quoted printf argument"),
    case("TB08-D-141", "base", "orchestrator", 'git commit -m "kubectl delete is gated now"', "B5 git commit -m message", reqs=R14),
]


@pytest.mark.parametrize("profile,agent,command,clause", QUOTED)
def test_quoted_arguments_allowed(tmp_path, profile, agent, command, clause):
    """TB-08 B5: 'Matching is on the parsed command, not on substrings inside quoted arguments to echo, printf or
    git commit -m messages.'"""
    _check(_run(tmp_path, profile, agent, command), "allow", clause)


# ---------------------------------------------------------------- behaviour 1: Bash only

@pytest.mark.parametrize("tool,content", [
    case("TB08-D-142", "Write", "git push --force origin main\nterraform destroy\n"),
])
def test_non_bash_tools_ignored(tmp_path, tool, content):
    """TB-08 B1: 'Applies to Bash only.' A Write whose content mentions guarded commands is allowed by this hook."""
    _check(_run(tmp_path, "base", "orchestrator", content, tool=tool), "allow", "B1 Bash only")


@pytest.mark.case("TB08-D-143", tier="diagnostic", tb=TB, reqs=R13)
def test_read_ignored(tmp_path):
    """TB-08 B1: Applies to Bash only; a Read is allowed."""
    root = lib.make_project(tmp_path, files={"src/app.py": "x\n"})
    d = lib.run_decide(HOOK, lib.payload(root, tool_name="Read", tool_input={"file_path": str(root / "src/app.py")},
                                         agent_type="test"), root)
    assert d.kind == "allow"


# ---------------------------------------------------------------- behaviour 6: reasons

@pytest.mark.case("TB08-D-144", tier="diagnostic", tb=TB, reqs=["R-13", "R-14"])
def test_reasons_name_the_rule(tmp_path):
    """TB-08 B6: 'The reason names the rule that matched' - different rules give different, non-empty reasons."""
    a = _run(tmp_path / "a", "base", "orchestrator", "git push --force")
    b = _run(tmp_path / "b", "base", "orchestrator", "terraform destroy")
    c = _run(tmp_path / "c", "base", "orchestrator", "deployctl push")
    assert a.kind == b.kind == c.kind == "ask"
    assert a.reason and b.reason and c.reason
    assert len({a.reason, b.reason, c.reason}) == 3


# ---------------------------------------------------------------- command line

@pytest.mark.case("TB08-D-145", tier="diagnostic", tb=TB, reqs=["R-13", "R-14"])
def test_cli_ask_and_deny(tmp_path):
    """hook-io adapter + TB-08 B2/B4: through `python -m factory.hooks bash_guard`, an orchestrator force push prints
    the ask JSON with exit 0, and the same command from test exits 2 with a reason on stderr."""
    import json
    lib.need("factory.hooks.core", "run_hook")
    lib.need("factory.agents.profile", "load_profile")
    lib.need(HOOK, "decide")
    root = lib.make_project(tmp_path)
    r_ask = lib.run_cli("bash_guard", lib.payload(root, tool_name="Bash", tool_input={"command": "git push --force"},
                                                  agent_type="orchestrator"), root)
    r_deny = lib.run_cli("bash_guard", lib.payload(root, tool_name="Bash", tool_input={"command": "git push --force"},
                                                   agent_type="test"), root)
    assert r_ask.returncode == 0
    out = json.loads(r_ask.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and out["permissionDecision"] == "ask" and out["permissionDecisionReason"]
    assert r_deny.returncode == 2 and r_deny.stderr.strip()



# ================================================================ clarifications (docs/contracts/clarifications.md)

CLAR = [
    # [A-08-1] main session with a non-orchestrator main_session_role
    case("TB08-D-147", lib.profile_dict("base", main_session_role="test"), None, "git add -A", "deny",
         "[A-08-1] main session gets its role's treatment (test -> deny)"),
    case("TB08-D-148", lib.profile_dict("base", main_session_role="test"), None, "terraform destroy", "deny",
         "[A-08-1] main session one-way door as test -> deny", reqs=R14),
    case("TB08-D-149", lib.profile_dict("base", main_session_role="implement"), None, "git commit -m x", "deny",
         "[A-08-1] main session as implement never commits"),
    # [A-08-2] plain rm and mv are not restricted for implement
    case("TB08-D-150", "base", "implement", "rm build/out.txt", "allow", "[A-08-2] plain rm not restricted"),
    case("TB08-D-151", "base", "implement", "mv src/a.py src/b.py", "allow", "[A-08-2] plain mv not restricted"),
    # [A-08-3] case-insensitive SQL
    case("TB08-D-152", "base", "orchestrator", 'psql -c "drop table users;"', "ask", "[A-08-3] lowercase DROP TABLE", reqs=R14),
    case("TB08-D-153", "base", "test", 'psql -c "truncate users;"', "deny", "[A-08-3] lowercase TRUNCATE", reqs=R14),
    case("TB08-D-154", "base", "orchestrator", 'psql -c "delete from users;"', "ask", "[A-08-3] lowercase DELETE FROM without WHERE", reqs=R14),
    case("TB08-D-155", "base", "orchestrator", 'psql -c "delete from users where id = 1;"', "allow", "[A-08-3] lowercase with where", reqs=R14),
    case("TB08-D-156", "base", "test", 'psql -c "Drop Database app;"', "deny", "[A-08-3] mixed case", reqs=R14),
    # [A-08-4] sh/bash/zsh -c string parsed
    case("TB08-D-157", "base", "orchestrator", 'bash -c "git push --force"', "ask", "[A-08-4] bash -c string parsed"),
    case("TB08-D-158", "base", "test", "sh -c 'git add -A'", "deny", "[A-08-4] sh -c string parsed"),
    case("TB08-D-159", "base", "test", 'zsh -c "terraform destroy"', "deny", "[A-08-4] zsh -c string parsed", reqs=R14),
    case("TB08-D-160", "base", "implement", 'bash -c "git commit -m x"', "deny", "[A-08-4] parsed for implement's rule"),
    case("TB08-D-161", "base", "orchestrator", 'bash -c "ls -la"', "allow", "[A-08-4] parsed string with no match"),
    # [A-08-5] rm -rf exemption forms
    case("TB08-D-162", "base", "orchestrator", "rm -rf ./node_modules", "allow", "[A-08-5] node_modules at any depth", reqs=R14),
    case("TB08-D-163", "base", "test", "rm -rf app/web/node_modules", "allow", "[A-08-5] nested node_modules", reqs=R14),
    case("TB08-D-164", "base", "orchestrator", "rm -rf {ROOT}/node_modules", "allow", "[A-08-5] absolute node_modules", reqs=R14),
    case("TB08-D-165", "base", "test", "rm -rf packages/a/.venv", "allow", "[A-08-5] nested .venv", reqs=R14),
    case("TB08-D-166", "base", "orchestrator", "rm -rf /tmp/x/y/z", "allow", "[A-08-5] anything under /tmp", reqs=R14),
    case("TB08-D-167", "base", "orchestrator", "rm -rf node_modules_backup", "ask", "[A-08-5] not a node_modules directory", reqs=R14),
    case("TB08-D-168", "base", "test", "rm -rf .venv-old", "deny", "[A-08-5] not a .venv directory", reqs=R14),
    # [A-08-6] +refspec force push and git global options
    case("TB08-D-169", "base", "orchestrator", "git push origin +main", "ask", "[A-08-6] +refspec is a force push"),
    case("TB08-D-170", "base", "test", "git push origin +feature:main", "deny", "[A-08-6] +refspec is a force push"),
    case("TB08-D-171", "base", "test", "git -C . add -A", "deny", "[A-08-6] -C <dir> skipped"),
    case("TB08-D-172", "base", "orchestrator", "git -c core.editor=true rebase main", "ask", "[A-08-6] -c k=v skipped"),
    case("TB08-D-173", "base", "test", "git --git-dir=.git --work-tree=. reset --hard", "deny", "[A-08-6] --git-dir/--work-tree skipped"),
    case("TB08-D-174", "base", "implement", "git -C sub commit -m x", "deny", "[A-08-6] -C skipped for implement's rule"),
    case("TB08-D-175", "base", "implement", "git -C src diff", "allow", "[A-08-6] -C skipped; diff is read-only"),
    # [U-3] normalise before the /tmp exemption
    case("TB08-D-176", "base", "orchestrator", "rm -rf ../sibling-project", "ask", "[U-3] ../sibling is not exempt", reqs=R14),
    case("TB08-D-177", "base", "test", "rm -rf ../sibling-project", "deny", "[U-3] ../sibling is not exempt", reqs=R14),
    case("TB08-D-178", "base", "orchestrator", "rm -rf /tmp/a/../../var/lib", "ask", "[U-3] normalised path leaves /tmp", reqs=R14),
    case("TB08-D-179", "base", "test", "rm -rf /tmp/a/../b", "allow", "[U-3] normalised path stays under /tmp", reqs=R14),
]


@pytest.mark.parametrize("profile,agent,command,expected,clause", CLAR)
def test_clarified(tmp_path, profile, agent, command, expected, clause):
    """clarifications [A-08-1] to [A-08-6] (clause per case)."""
    _check(_run(tmp_path, profile, agent, command), expected, clause)


# ---------------------------------------------------------------- R-24: published documentation

@pytest.mark.case("TB08-D-146", tier="diagnostic", tb="08", reqs=["R-24"])
def test_docs_hooks_bash_guard_md():
    """TB-08 Acceptance: 'Document the component in the docs/hooks/ file you own, with one example payload or call
    (requirement R-24).' OWN list names docs/hooks/bash_guard.md."""
    lib.need("factory.hooks.bash_guard")
    doc_path = lib.REPO / "docs" / "hooks" / "bash_guard.md"
    assert doc_path.is_file()
    text = doc_path.read_text()
    assert any(s in text for s in ("hook_event_name", "decide(", "python -m factory.hooks")), "one example payload or call"
