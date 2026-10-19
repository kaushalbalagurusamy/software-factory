"""Unit tests for the Bash guard (TB-08). Unit coverage, not the acceptance gate."""
from __future__ import annotations

import json

import pytest

from factory.agents.profile import parse_profile
from factory.hooks import bash_guard
from factory.hooks.core import HookConfig, parse_payload, run_hook


def make_cfg(tmp_path, **extra):
    data = {"schema_version": 1, "project": {"name": "demo"}, "paths": {"eval": ["evals/**"]}}
    data.update(extra)
    return HookConfig.from_profile(parse_profile(data), tmp_path)


def payload(command, agent_type=None, tool="Bash", event="PreToolUse"):
    d = {"session_id": "s", "cwd": "/x", "hook_event_name": event, "tool_name": tool,
         "tool_input": {"command": command}}
    if agent_type:
        d["agent_type"] = agent_type
        d["agent_id"] = "a1"
    return parse_payload(json.dumps(d))


@pytest.fixture
def cfg(tmp_path):
    return make_cfg(tmp_path)


def kind(cfg, command, role=None):
    return bash_guard.decide(payload(command, role), cfg).kind


# ---- scope ------------------------------------------------------------------------------------
def test_non_bash_tool_allowed(cfg):
    assert bash_guard.decide(payload("git add -A", tool="Write"), cfg).kind == "allow"


def test_non_pretooluse_allowed(cfg):
    assert bash_guard.decide(payload("git add -A", event="PostToolUse"), cfg).kind == "allow"


@pytest.mark.parametrize("ti", [{}, {"command": 5}, {"command": None}, {"command": ["git", "add"]}])
def test_malformed_bash_input_denied(cfg, ti):
    p = parse_payload(json.dumps({"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": ti}))
    d = bash_guard.decide(p, cfg)
    assert d.kind == "deny" and d.reason


@pytest.mark.parametrize("cmd", ["echo 'unterminated", 'echo "x', "echo $(git add -A", "echo `ls"])
def test_unparseable_denied(cfg, cmd):
    assert kind(cfg, cmd) == "deny"
    assert kind(cfg, cmd, "orchestrator") == "deny"


def test_empty_command_allowed(cfg):
    assert kind(cfg, "") == "allow"
    assert kind(cfg, "   ") == "allow"


# ---- ordinary commands are allowed -------------------------------------------------------------
ORDINARY = [
    "ls -la", "pytest -q tests/", "npm test", "make build", "python -m pytest tests/hooks",
    "git status", "git diff --stat", "git log --oneline -5", "git show HEAD", "git blame foo.py",
    "git add src/a.py tests/b.py", "git add -- src/a.py", "git add -u",
    "git commit -m 'Fix thing'", 'git commit -m "Update the add -A docs"', "git commit -am 'x'",
    "git push origin main", "git push -u origin feature", "git push --set-upstream origin feature",
    "git reset --soft HEAD~1", "git reset HEAD file.txt", "git checkout -b new", "git fetch --all",
    "git branch -d old", "git stash list", "git pull --ff-only",
    "git -C sub status", "git -c user.name=x commit -m y",
    "echo hello && ls", "cat a | grep b | wc -l", "cd /tmp && pytest",
    "rm -rf /tmp/build", "rm -rf node_modules", "rm -rf ./web/node_modules", "rm -rf .venv",
    "rm -rf /tmp/a /tmp/b", "rm -fr /tmp/x", "rm file.txt", "rm -r build", "rm -f build",
    "kubectl get pods", "terraform plan", "terraform apply", "gh repo view", "gh pr list",
    "psql -c 'SELECT 1'", "psql -c \"DELETE FROM t WHERE id = 1\"", "truncate -s 0 app.log",
    "echo 'DROP TABLE users'", 'printf "TRUNCATE users;\\n"', "echo git add -A",
    "echo 'git push --force'", 'git commit -m "never git push --force or --no-verify"',
    "git commit -m 'rm -rf / is bad'", "grep -r 'DROP TABLE' docs",
    "FOO=1 pytest", "env FOO=1 pytest", "ls # git add -A",
]


def _impl_ok(cmd):
    # the implement role may not run these git forms; they are asserted denied in the implement tests
    return not (cmd.startswith(("git add", "git commit", "git push", "git reset", "git checkout", "git stash",
                                "git -c", "git -C user")) or "git commit" in cmd)


ORDINARY_CASES = [(c, r) for c in ORDINARY for r in (None, "orchestrator", "test", "implement")
                  if r != "implement" or _impl_ok(c)]


@pytest.mark.parametrize("cmd,role", ORDINARY_CASES)
def test_ordinary_allowed(cfg, cmd, role):
    d = bash_guard.decide(payload(cmd, role), cfg)
    assert d.kind == "allow", (cmd, role, d)


# ---- git hygiene -------------------------------------------------------------------------------
HYGIENE = [
    "git add -A", "git add --all", "git add .", "git add *", "git add ./", "git add -- .",
    "git add -A src", "git add src -A", "git add -fA", "git add -vA", "git -C sub add -A",
    "git -c core.x=1 add .", "git --git-dir=.git add -A", "git --no-pager add .",
    "git add --al", "/usr/bin/git add -A", "sudo git add -A", "env GIT_X=1 git add .",
    "GIT_X=1 git add -A", "git add 'a.py' .", "git add \"*\"",
    "git commit --no-verify -m x", "git commit -m x --no-verify", "git push --no-verify",
    "git commit -n -m x", "git commit -nm x", "git merge --no-verify x",
    "git -c core.hooksPath=/dev/null commit -m x",
    "git commit --amend", "git commit --amend --no-edit", "git commit -m x --amend",
    "git commit -a --am", "git -C repo commit --amend",
    "git rebase main", "git rebase -i HEAD~3", "git rebase --continue", "git -C x rebase main",
    "git push --force", "git push -f", "git push origin main --force", "git push -f origin main",
    "git push --force-with-lease", "git push --force-with-lease=main origin main",
    "git push origin +main", "git push origin +HEAD:main", "git push -uf origin x",
    "git push --force-if-includes", "git -C r push -f", "git push origin main -f",
    "git reset --hard", "git reset --hard HEAD~1", "git reset HEAD~1 --hard", "git -C x reset --hard",
    "git reset --hard origin/main",
    "ls && git add -A", "git status; git push -f", "ls | git add .", "git status || git rebase x",
    "echo hi & git reset --hard", "(git add -A)", "{ git add -A; }", "if true; then git add .; fi",
    "for f in a; do git push --force; done", "echo $(git add -A)", "echo `git reset --hard`",
    "bash -c 'git add -A'", 'sh -c "git push -f"', "zsh -c 'git rebase x'", "bash -lc 'git add .'",
    "sudo bash -c 'git add -A'", "eval 'git add -A'", "eval git reset --hard",
    "git add -A # commit", "git add $'-A'", "X=-A; git add $X", "X='add -A'; git $X", "git ad\\d -A",
    "git add \\-A", "git 'add' '-A'", 'git "add" "."',
    "cat <<EOF\nhello\nEOF\ngit add -A", "bash <<<'x'; git add .",
    "git\tadd\t-A", "git   add    -A", "git add -A\n", "ls\ngit add -A",
    "git stash && git add .",
    "git add . 2>&1", "git add -A >/dev/null", "git push -f 2>&1 | tail",
    "git fetch && git commit --amend -m 'x'",
]


@pytest.mark.parametrize("cmd", HYGIENE)
def test_hygiene_ask_for_orchestrator(cfg, cmd):
    d = bash_guard.decide(payload(cmd, "orchestrator"), cfg)
    assert d.kind == "ask", (cmd, d)
    assert d.reason


@pytest.mark.parametrize("cmd", HYGIENE)
def test_hygiene_main_session_asks(cfg, cmd):
    assert bash_guard.decide(payload(cmd), cfg).kind == "ask"


@pytest.mark.parametrize("role", ["research", "design", "audit", "implement", "test", "review", "mystery"])
@pytest.mark.parametrize("cmd", HYGIENE)
def test_hygiene_denied_for_other_roles(cfg, role, cmd):
    d = bash_guard.decide(payload(cmd, role), cfg)
    assert d.kind == "deny", (cmd, role, d)
    assert d.reason


def test_main_session_with_other_role_gets_deny(tmp_path):
    cfg = make_cfg(tmp_path, main_session_role="test")
    assert bash_guard.decide(payload("git add -A"), cfg).kind == "deny"
    assert bash_guard.decide(payload("git add -A", "orchestrator"), cfg).kind == "ask"


def test_main_session_role_implement_blocks_commit(tmp_path):
    cfg = make_cfg(tmp_path, main_session_role="implement")
    assert bash_guard.decide(payload("git commit -m x"), cfg).kind == "deny"


def test_reason_names_rule_and_ask_describes_approval(cfg):
    d = bash_guard.decide(payload("git push --force origin main", "orchestrator"), cfg)
    assert d.kind == "ask"
    assert "force" in d.reason.lower() and "approve" in d.reason.lower()
    d = bash_guard.decide(payload("git add -A", "test"), cfg)
    assert d.kind == "deny" and "git add" in d.reason
    d = bash_guard.decide(payload("git commit --amend", "test"), cfg)
    assert "amend" in d.reason
    d = bash_guard.decide(payload("git reset --hard", "test"), cfg)
    assert "reset --hard" in d.reason
    d = bash_guard.decide(payload("git rebase x", "test"), cfg)
    assert "rebase" in d.reason
    d = bash_guard.decide(payload("git commit --no-verify -m x", "test"), cfg)
    assert "no-verify" in d.reason


# ---- implement never commits -------------------------------------------------------------------
IMPL_DENIED = [
    "git stash", "git stash pop", "git stash list", "git checkout main", "git checkout -b x",
    "git checkout -- file", "git restore file", "git restore --staged f", "git reset", "git reset HEAD f",
    "git reset --soft HEAD~1", "git clean -fd", "git clean -n", "git add src/a.py", "git add -u",
    "git commit -m x", "git commit", "git mv a b", "git rm a", "git rm --cached a", "git push",
    "git push origin main", "git merge x", "git cherry-pick abc", "git -C sub commit -m x",
    "git -c user.name=x commit -m y", "git --no-pager stash", "/usr/bin/git checkout x",
    "ls && git commit -m x", "git status && git add f", "bash -c 'git commit -m x'",
    "(git checkout x)", "git diff | cat; git stash",
]


@pytest.mark.parametrize("cmd", IMPL_DENIED)
def test_implement_denied(cfg, cmd):
    d = bash_guard.decide(payload(cmd, "implement"), cfg)
    assert d.kind == "deny", cmd
    assert "implement" in d.reason


@pytest.mark.parametrize("cmd", IMPL_DENIED)
def test_implement_denied_is_not_ask_even_for_orchestrator_role_only(cfg, cmd):
    # the same plain commands are fine for the orchestrator unless a hygiene rule matches
    d = bash_guard.decide(payload(cmd, "orchestrator"), cfg)
    assert d.kind in ("allow", "ask")


IMPL_ALLOWED = [
    "git diff", "git diff --stat HEAD", "git log", "git log --oneline -3", "git show HEAD:file",
    "git status", "git status -s", "git blame f.py", "git -C sub diff", "git --no-pager log",
    "git rev-parse HEAD", "git branch", "git fetch", "git ls-files", "git config user.name",
    "pytest -q tests/hooks", "npm test", "python -m pytest tests", "ruff check .", "rm -rf /tmp/x",
    "rm tmp.txt", "mv a b", "echo git commit", "cat x | grep git",
    "git commit-tree abc", "git status-like-nothing",
]


@pytest.mark.parametrize("cmd", IMPL_ALLOWED)
def test_implement_allowed(cfg, cmd):
    assert bash_guard.decide(payload(cmd, "implement"), cfg).kind == "allow", cmd


def test_plain_rm_and_mv_not_restricted_for_implement(cfg):
    assert kind(cfg, "rm a.txt && mv a b", "implement") == "allow"


# ---- one-way doors -----------------------------------------------------------------------------
DOORS = [
    "psql -c 'DROP TABLE users'", "psql -c \"drop table users\"", "mysql -e 'DROP DATABASE prod'",
    "psql -c 'ALTER TABLE t DROP COLUMN c'", "psql -c 'DROP   TABLE   IF EXISTS x'",
    "psql -c 'TRUNCATE users'", "psql -c 'truncate table users'", "psql -c 'TRUNCATE TABLE a, b'",
    "psql -c 'DELETE FROM users'", "psql -c 'delete from users;'", "sqlite3 db.sqlite 'DELETE FROM t'",
    "psql -c 'DELETE FROM a; DELETE FROM b WHERE x=1'", "mysql -e \"DELETE\tFROM\tt\"",
    "psql -c 'select 1; drop table t'", "psql -d x -c 'Drop Table t'", "mysql -e DROP DATABASE x",
    "psql <<EOF\nDROP TABLE t;\nEOF", "psql <<'EOF'\nTRUNCATE t;\nEOF", "psql <<< 'DROP TABLE t'",
    "echo 'DROP TABLE t' | psql", "printf 'TRUNCATE t;' | mysql", "echo 'DELETE FROM t' | sqlite3 x.db",
    "python -c \"c.execute('DROP TABLE t')\"", "bash -c \"psql -c 'DROP TABLE t'\"",
    "terraform destroy", "terraform destroy -auto-approve", "terraform -chdir=infra destroy",
    "tofu destroy", "terraform apply -destroy",
    "kubectl delete pod x", "kubectl delete -f x.yaml", "kubectl -n prod delete deploy x",
    "kubectl --context prod delete ns x", "kubectl delete",
    "gh repo delete owner/name", "gh repo delete owner/name --yes", "gh repo delete",
    "rm -rf /", "rm -rf /home/u/project", "rm -rf src", "rm -fr src", "rm -Rf src",
    "rm -r -f src", "rm -f -r src", "rm --recursive --force src", "rm -rf --no-preserve-root /",
    "rm -rf *", "rm -rf ~", "rm -rf $HOME", "rm -rf .", "rm -rf ..", "rm -rf /tmp", "rm -rf /tmp/",
    "rm -rf /tmp/../etc", "rm -rf node_modules/../src", "rm -rf /tmp/a src", "rm -rf src /tmp/a",
    "rm -rf -- src", "rm -rf /tmpfoo", "rm -rf ./tmp", "rm -rf node_modules2", "rm -rf mynode_modules",
    "rm -vrf src", "sudo rm -rf /var/lib/x", "cd /x && rm -rf build", "echo y | rm -rf build",
    "bash -c 'rm -rf build'", "ls; rm -rf dist", "/bin/rm -rf dist", "command rm -rf dist",
    "echo $(rm -rf dist)", "find . -name x ; rm -rf dist",
    "X=build; rm -rf $X", "rm -rf 'my dir'",
]


@pytest.mark.parametrize("cmd", DOORS)
def test_doors_ask_for_orchestrator(cfg, cmd):
    d = bash_guard.decide(payload(cmd, "orchestrator"), cfg)
    assert d.kind == "ask", (cmd, d)
    assert d.reason


@pytest.mark.parametrize("cmd", DOORS)
def test_doors_main_session_asks(cfg, cmd):
    assert kind(cfg, cmd) == "ask"


@pytest.mark.parametrize("role", ["research", "design", "audit", "implement", "test", "review"])
@pytest.mark.parametrize("cmd", DOORS)
def test_doors_denied_for_other_roles(cfg, role, cmd):
    assert bash_guard.decide(payload(cmd, role), cfg).kind == "deny", (cmd, role)


def test_sql_case_insensitive(cfg):
    for c in ["psql -c 'dRoP tAbLe t'", "psql -c 'Truncate T'", "psql -c 'delete FROM t'"]:
        assert kind(cfg, c, "orchestrator") == "ask"


def test_delete_with_where_across_statements(cfg):
    assert kind(cfg, "psql -c 'DELETE FROM a WHERE x = 1; DELETE FROM b WHERE y = 2'", "test") == "allow"
    assert kind(cfg, "psql -c 'DELETE FROM a WHERE x = 1; DELETE FROM b'", "test") == "deny"


def test_rm_exemptions(cfg):
    for c in ["rm -rf /tmp/x", "rm -rf node_modules", "rm -rf a/b/node_modules", "rm -rf .venv",
              "rm -rf pkg/.venv", "rm -rf ./node_modules/", "rm -rf /tmp/a/b/c", "rm -rf /tmp/*",
              "rm -rf node_modules .venv /tmp/z", "rm -rf node_modules/.cache"]:
        assert kind(cfg, c, "orchestrator") == "allow", c
        assert kind(cfg, c, "test") == "allow", c


def test_door_reason_names_rule_and_what_is_approved(cfg):
    d = bash_guard.decide(payload("kubectl delete ns prod", "orchestrator"), cfg)
    assert d.kind == "ask" and "kubectl delete" in d.reason and "approve" in d.reason.lower()
    d = bash_guard.decide(payload("psql -c 'DROP TABLE t'", "test"), cfg)
    assert d.kind == "deny" and "DROP TABLE" in d.reason.upper()
    d = bash_guard.decide(payload("rm -rf src", "test"), cfg)
    assert d.kind == "deny" and "rm -rf" in d.reason


# ---- profile-driven: deploy route and patterns ---------------------------------------------------
def test_deploy_route_prefix(tmp_path):
    cfg = make_cfg(tmp_path, deploy={"route": "railway up"})
    for c in ["railway up", "railway up --service web", "cd app && railway up", "sudo railway up",
              "/usr/local/bin/railway up", "bash -c 'railway up'", "echo ok; railway up -d",
              "FOO=1 railway up", "railway  up"]:
        assert bash_guard.decide(payload(c, "orchestrator"), cfg).kind == "ask", c
        assert bash_guard.decide(payload(c), cfg).kind == "ask", c
        assert bash_guard.decide(payload(c, "test"), cfg).kind == "deny", c
    for c in ["railway status", "railway", "echo railway up", "git commit -m 'railway up'",
              "railway upgrade", "ls railway up"]:
        assert bash_guard.decide(payload(c, "orchestrator"), cfg).kind == "allow", c


def test_deploy_route_script_path(tmp_path):
    cfg = make_cfg(tmp_path, deploy={"route": "./scripts/deploy.sh"})
    assert kind(cfg, "./scripts/deploy.sh prod", "orchestrator") == "ask"
    assert kind(cfg, "scripts/deploy.sh", "orchestrator") == "ask"
    assert kind(cfg, "./scripts/deploy.sh", "implement") == "deny"
    assert kind(cfg, "./scripts/build.sh", "orchestrator") == "allow"


def test_no_deploy_route_nothing_special(cfg):
    assert kind(cfg, "railway up", "orchestrator") == "allow"
    cfg2 = make_cfg(cfg.project_root, deploy={"platform_server": "x"})
    assert kind(cfg2, "railway up", "orchestrator") == "allow"


def test_profile_patterns(tmp_path):
    cfg = make_cfg(tmp_path, one_way_door_patterns=[r"^fly\s+deploy", r"prod-migrate\b", r"--env=prod"])
    for c in ["fly deploy", "fly deploy --app x", "make prod-migrate", "cd x && fly deploy",
              "run.sh --env=prod", "bash -c 'fly deploy'", "FOO=1 fly deploy"]:
        assert bash_guard.decide(payload(c, "orchestrator"), cfg).kind == "ask", c
        assert bash_guard.decide(payload(c, "review"), cfg).kind == "deny", c
    for c in ["fly status", "echo 'fly deploy'", "git commit -m 'fly deploy'", "ls", "grep prod-migrate x"]:
        assert bash_guard.decide(payload(c, "orchestrator"), cfg).kind == "allow", c


def test_pattern_match_reason_mentions_pattern(tmp_path):
    cfg = make_cfg(tmp_path, one_way_door_patterns=[r"^fly\s+deploy"])
    d = bash_guard.decide(payload("fly deploy", "orchestrator"), cfg)
    assert "one_way_door_patterns" in d.reason and "fly" in d.reason


def test_patterns_are_not_hard_coded(cfg):
    assert kind(cfg, "fly deploy", "orchestrator") == "allow"


# ---- severity and adapter -----------------------------------------------------------------------
def test_deny_beats_ask_across_segments(cfg):
    # for the orchestrator an ask-only chain stays ask
    assert kind(cfg, "git add -A && kubectl delete x", "orchestrator") == "ask"
    # an implement chain containing both is a deny
    assert kind(cfg, "git status && git commit -m x", "implement") == "deny"


def test_run_hook_adapter_exit_codes(cfg):
    ask = run_hook(bash_guard.decide, json.dumps({
        "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git add -A"},
        "agent_type": "orchestrator"}), cfg)
    assert ask.exit_code == 0 and json.loads(ask.stdout)["hookSpecificOutput"]["permissionDecision"] == "ask"
    deny = run_hook(bash_guard.decide, json.dumps({
        "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git add -A"},
        "agent_type": "test"}), cfg)
    assert deny.exit_code == 2 and deny.stderr
    ok = run_hook(bash_guard.decide, json.dumps({
        "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"}}), cfg)
    assert (ok.exit_code, ok.stdout, ok.stderr) == (0, "", "")


def test_deterministic(cfg):
    p = payload("git add -A && rm -rf src", "orchestrator")
    assert bash_guard.decide(p, cfg) == bash_guard.decide(p, cfg)


def test_deep_nesting_fails_closed(cfg):
    cmd = "echo $(" * 20 + "hi" + ")" * 20
    assert len(cmd) < 100_000
    assert kind(cfg, cmd, "test") == "deny"


def test_huge_but_plain_command_allowed(cfg):
    assert kind(cfg, "echo " + "a " * 5000) == "allow"


# ---- option-carried command strings (wrappers) ---------------------------------------------------
WRAPPED = [
    "env -S 'git push --force origin main'", "env --split-string='git add -A'",
    "env --split-string 'git add -A'", "env -S'rm -rf /'", "env -S 'rm -rf /'", "env -SX=1\\ rm\\ -rf\\ /",
    "env -iS 'git reset --hard'", "env -u FOO -S 'git rebase main'", "env FOO=1 -S 'git add .'",
    "env -S 'env -S \"git add -A\"'", "env -S 'FOO=1 git commit --amend'", "env -S 'kubectl delete ns x'",
    "sudo env -S 'git add -A'", "env -C /tmp -S 'git push -f'", "env -S \"psql -c 'DROP TABLE t'\"",
    "xargs git add -A", "xargs -n1 git push --force", "xargs -I{} git add .", "xargs -I {} git reset --hard",
    "echo x | xargs rm -rf src", "xargs -0 -P 4 kubectl delete",
    "sudo -s 'git add -A'", "sudo -i 'git push -f'", "sudo --shell 'git reset --hard'", "doas -s 'git add .'",
    "su -c 'git add -A' root", "su root -c 'git push --force'", "su --command='git reset --hard'",
    "runuser -u x -- true; runuser -c 'rm -rf src' x",
    "exec -a foo git add -A", "time -f %e git push -f", "stdbuf -o L git add .", "stdbuf -oL git add -A",
    "nice -n 5 git add -A", "timeout 5 git add -A", "timeout -s KILL 5 git push -f", "nohup git add -A",
    "command git add -A", "find . -exec git add -A \;", "find . -execdir rm -rf src \;",
    "find . -name x -exec git reset --hard {} +",
]


@pytest.mark.parametrize("cmd", WRAPPED)
def test_wrapped_commands_still_classified(cfg, cmd):
    assert kind(cfg, cmd, "orchestrator") == "ask", cmd
    assert kind(cfg, cmd) == "ask", cmd
    assert kind(cfg, cmd, "test") == "deny", cmd


@pytest.mark.parametrize("cmd", [
    "env -S 'ls -la'", "env --split-string='ls -la'", "env -S'ls -la'", "env -S 'FOO=1 pytest -q'",
    "env -u FOO -S 'git status'", "xargs ls", "xargs -n1 echo", "xargs -I{} cp {} /tmp/x",
    "sudo -s 'ls'", "exec -a foo ls", "find . -name x -exec grep y {} +",
    "find . -exec rm {} \;", "env -S 'rm -rf /tmp/x'", "env -S 'git commit -m x'",
])
@pytest.mark.parametrize("role", [None, "orchestrator", "test"])
def test_harmless_wrapped_allowed(cfg, cmd, role):
    assert kind(cfg, cmd, role) == "allow", (cmd, role)


@pytest.mark.parametrize("cmd", [
    "env -S 'git add -A", "env -S \"unterminated", "env -S", "env --split-string",
    "env -S 'a'\"'\" 'b",
])
def test_wrapper_string_unsplittable_denied(cfg, cmd):
    assert kind(cfg, cmd, "orchestrator") == "deny"
    assert kind(cfg, cmd, "test") == "deny"


def test_env_split_string_bounds(cfg):
    big = "echo " + "a" * 200_000
    assert kind(cfg, f"env -S '{big}'", "test") == "deny"
    deep = "env -S '" * 70 + "ls" + "'" * 70  # linear construction, only quote-balance matters
    assert len(deep) < 100_000
    assert kind(cfg, deep, "test") == "deny"  # wrapper depth exceeds the bound or cannot be split


def test_implement_env_split_commit_denied(cfg):
    assert kind(cfg, "env -S 'git commit -m x'", "implement") == "deny"
    assert kind(cfg, "env -S 'git status'", "implement") == "allow"


# ---- getopt-style option parsing: prefixes, clusters, attached values ---------------------------
GETOPT_BAD = [
    "env --split='git add -A'", "env --split-str='git push -f'", "env --split-string 'git reset --hard'",
    "env --sp='git add -A'", "env -iS'git add -A'", "env -i -S 'git add -A'", "env -0S 'rm -rf /'",
    "env -vS'git add .'", "env -u A -u B -S 'git add -A'", "env --unset=A --split='git add -A'",
    "env --chd=/tmp --split='git add -A'", "env --block-signal --split='git add -A'",
    "su -lc 'git add -A'", "su -lc'git add -A'", "su -cgit\\ add\\ -A", "su -c 'git add -A'", "su root -lc 'git add -A'",
    "su -l root -c 'git push -f'", "su --comm='git add -A'", "su --session-command='git add -A'", "su --session='git add -A'",
    "su -mc 'rm -rf src' x", "su - -c 'git add -A'", "su -s /bin/sh -c 'git add -A'", "su -g grp -c 'git add -A' u",
    "runuser -c 'git add -A' x", "runuser -lc 'git add -A' x", "runuser -l x -c 'git push -f'", "runuser --comm 'git add -A' x",
    "runuser -u x git add -A", "runuser -u x -- git add -A", "runuser -ux git add -A", "runuser --user=x -- git reset --hard",
    "runuser -u x -g y -- git rebase main", "runuser --user x git push -f",
    "sudo -Eu root git add -A", "sudo -Eu root -- git add -A", "sudo -uroot git add -A", "sudo -u root -E git add -A",
    "sudo -si 'git add -A'", "sudo -is 'git add -A'", "sudo -Es 'git add -A'", "sudo -sE 'git add -A'",
    "sudo --she 'git add -A'", "sudo --shell 'git add -A'", "sudo -nEs 'git reset --hard'",
    "sudo --user=root --group=g git add -A", "sudo --us root git add -A", "sudo -u root FOO=1 git add -A",
    "sudo --preserve-env git add -A", "sudo --preserve-env=PATH git add -A", "sudo -H -n git add -A",
    "doas -u root git add -A", "doas -sn 'git add -A'", "doas -Cx -s 'git add -A'",
    "xargs -0I{} sh -c 'git add -A'", "xargs -0I{} git add -A", "xargs -0 -I {} git add -A", "xargs -n1 -P4 git push -f",
    "xargs -n 1 -P 4 git add .", "xargs -rt git add -A", "xargs --null git add -A", "xargs --max-a=3 git add -A",
    "xargs --max-args 3 git add -A", "xargs --max-args=3 git reset --hard", "xargs -I{} -n1 git add -A",
    "xargs -s100 git add -A", "xargs -0rn1 git push --force", "xargs -a file git add -A", "xargs -E eof git add -A",
    "xargs -i git add -A", "xargs --replace git add -A", "xargs -l git add -A", "xargs -L2 git add -A",
    "nice -n5 git add -A", "nice -5 git add -A", "nice --adj=5 git add -A", "nice --adjustment 5 git add -A",
    "time -p git add -A", "time -ao f git add -A", "time -ofile git add -A", "time --format=%e git add -A", "time --for %e git add -A",
    "timeout 5 git add -A", "timeout -k 1 5 git add -A", "timeout -k1 -s KILL 5 git add -A", "timeout --signal=KILL 5 git add -A",
    "timeout --kill-after 1 5 git add -A", "timeout --sig KILL 5 git add -A", "timeout -fpv 5 git add -A", "timeout 5s git push -f",
    "nohup git add -A", "nohup -- git add -A", "command -p git add -A", "command -- git add -A", "exec -c git add -A",
    "exec -a x git add -A", "exec -cl git add -A", "setsid git add -A", "setsid -f git add -A", "setsid -cf git add -A",
    "setsid --fork git add -A", "setsid --wait git add -A", "stdbuf -i0 -o0 -e0 git add -A", "stdbuf -oL git add -A",
    "stdbuf --output=L git add -A", "stdbuf --out L git add -A",
    "bash -lc 'git add -A'", "bash -ec 'git add -A'", "bash -xec 'git add -A'", "bash -c 'git add -A' x", "bash -o pipefail -c 'git add -A'",
    "bash -co pipefail 'git add -A'", "bash --norc -c 'git add -A'", "bash --login -c 'git add -A'", "bash --noprof -c 'git add -A'",
    "bash +o history -c 'git add -A'", "sh -ic 'git add -A'", "zsh -fc 'git add -A'", "bash -O extglob -c 'git add -A'",
    "dash -c 'git add -A'", "sudo bash -lc 'git add -A'", "env bash -lc 'git add -A'", "timeout 5 env -S 'git add -A'",
    "nice -n 5 sudo -u root env FOO=1 git add -A", "env nice timeout 5 xargs git add -A",
]


@pytest.mark.parametrize("cmd", GETOPT_BAD)
def test_getopt_forms_classified(cfg, cmd):
    assert kind(cfg, cmd, "orchestrator") == "ask", cmd
    assert kind(cfg, cmd, "test") == "deny", cmd


@pytest.mark.parametrize("cmd", [
    "env FOO=1 ls", "env -i FOO=1 ls", "env -u FOO ls", "env --unset=FOO ls", "env --unset FOO ls", "env -C /tmp ls",
    "env --chdir=/tmp ls", "env -0 ls", "env - ls", "env -- ls", "env --ignore-environment ls", "sudo -si",
    "env", "env -S 'ls -la'", "env --split='ls -la'", "env --spl 'ls -la'",
    "sudo -u root ls", "sudo -Eu root ls", "sudo -n ls", "sudo --user=root ls", "sudo -H -u root ls", "sudo ls",
    "sudo -s", "sudo -i", "sudo -sE", "sudo -l", "sudo -v", "sudo --preserve-env=PATH ls", "sudo -u root FOO=1 ls",
    "nice -n 5 pytest", "nice -n5 pytest", "nice -5 pytest", "nice pytest", "nice --adjustment=5 pytest",
    "timeout 5 ls", "timeout -s KILL 5 ls", "timeout -k 1 5 ls", "timeout --signal=KILL 5s ls", "timeout 1.5 ls",
    "xargs -0 echo", "xargs -0I{} echo {}", "xargs -n1 echo", "xargs -P4 -n 1 ls", "xargs", "xargs -r ls",
    "time ls", "time -p ls", "time -f %e ls", "nohup ls", "command ls", "command -v git", "command -p ls",
    "exec ls", "exec -a x ls", "setsid ls", "stdbuf -oL ls", "stdbuf -o L ls",
    "bash -c 'ls'", "bash -lc 'ls'", "sh -ec 'ls -la'", "bash -o pipefail -c 'pytest -q'", "bash script.sh",
    "bash", "bash -x script.sh", "find . -name x", "builtin echo hi",
])
@pytest.mark.parametrize("role", [None, "test"])
def test_getopt_harmless_allowed(cfg, cmd, role):
    assert kind(cfg, cmd, role) == "allow", (cmd, role)


@pytest.mark.parametrize("cmd", [
    "env --zzz ls", "env --ign ls", "sudo --log ls", "env -Z ls", "env -u", "env --unset", "env --ignore-environment=1 ls",
    "env --b ls",  # ambiguous: block-signal / ... only one starts with b, so see below
    "sudo --zzz ls", "sudo -Z ls", "sudo -u", "sudo --shell=1 ls", "sudo --s ls",
    "xargs -Z ls", "xargs --zzz ls", "xargs -a", "xargs --max ls", "xargs --max-a",
    "nice -Z ls", "nice --a", "nice -n", "time -Z ls", "time --f", "timeout -Z 5 ls", "timeout -s",
    "timeout --kill", "nohup -Z ls", "nohup --zzz ls", "command -Z ls", "exec -Z ls", "exec -a",
    "setsid -Z ls", "stdbuf -Z ls", "stdbuf -i", "bash --zzz -c ls", "bash -o", "bash -c ls --h",
    "builtin -Z ls",
])
def test_unclassifiable_options_fail_closed(cfg, cmd):
    if cmd == "env --b ls":
        assert kind(cfg, cmd, "test") == "allow"  # unique prefix of --block-signal (optional value)
        return
    if cmd == "bash -c ls --h":
        return
    assert kind(cfg, cmd, "orchestrator") == "deny", cmd
    assert kind(cfg, cmd, "test") == "deny", cmd


@pytest.mark.parametrize("cmd", ['"git add -A"', "'git add -A' x", "env 'git add -A'", "sudo 'rm -rf /'",
                                 "nice -n 5 'git push -f'", "timeout 5 'git add -A'", "./'my script.sh'",
                                 "xargs 'git add -A'", "X='git add -A'; \"$X\""])
def test_leftover_command_word_with_whitespace_denied(cfg, cmd):
    assert kind(cfg, cmd, "orchestrator") == "deny"
    assert kind(cfg, cmd, "test") == "deny"


def test_getopt_unit_behaviour():
    sh, lg = bash_guard.ENV_SHORT, bash_guard.ENV_LONG
    opts, rest = bash_guard._getopt(["-iS", "cmd", "root"], sh, lg)
    assert [(o, v) for o, v, _k in opts] == [("i", None), ("S", "cmd")] and rest == ["root"]
    opts, _ = bash_guard._getopt(["--split=x"], sh, lg)
    assert opts == [("split-string", "x", "cmd")]
    opts, rest = bash_guard._getopt(["a", "-i"], sh, lg, permute=True)
    assert rest == ["a"] and [o for o, _v, _k in opts] == ["i"]
    with pytest.raises(bash_guard.ParseError):
        bash_guard._getopt(["--ignore", "x"], sh, lg)  # ambiguous: ignore-environment / ignore-signal
    with pytest.raises(bash_guard.ParseError):
        bash_guard._getopt(["--null=1"], sh, lg)


# ---- privilege/context-switching wrappers: always ask (orchestrator) / deny (others) -------------
ALWAYS = [
    "su", "su -", "su root", "su - root", "su -l root", "su -c ls root", "su -c 'ls' root", "su -lc 'ls' root",
    "su user -- -c 'git add -A'", "su -- user -c cmd", "su -s /bin/sh -c cmd", "su -s /bin/sh user", "su -Z root",
    "su --zzz root", "su -g", "su root -- ls", "su root ls", "su -- -c 'rm -rf /'", "su -c",
    "runuser", "runuser -u u -- git add -A", "runuser -u u ls", "runuser -u x -- ls", "runuser -l x -c 'ls'",
    "runuser -u", "runuser --zzz -u x ls", "runuser user -- -c 'git add -A'", "runuser -- u -c cmd",
    "doas", "doas git add -A", "doas ls", "doas -u root ls", "doas -s", "doas -- ls",
    "pkexec ls", "pkexec --user root ls", "pkexec", "machinectl shell root@host ls", "machinectl shell",
    "nsenter -t 1 -m ls", "nsenter ls", "chroot /mnt ls", "chroot /mnt", "ssh host ls", "ssh -p 2 host 'git add -A'",
    "ssh host", "watch ls", "watch -n1 'git add -A'", "flock /tmp/l ls", "flock -c ls /tmp/l", "parallel echo ::: a",
    "sudo su", "sudo -u root su - x", "env su", "nice -n 1 ssh h ls", "timeout 5 watch ls", "xargs ssh h",
    "ls && su root", "echo x | doas tee f", "bash -c 'su root'", "/usr/bin/su root", "FOO=1 ssh h ls",
    "find . -exec ssh h ls \\;",
]


@pytest.mark.parametrize("cmd", ALWAYS)
def test_unanalysable_wrappers_always_ask_or_deny(cfg, cmd):
    d = bash_guard.decide(payload(cmd, "orchestrator"), cfg)
    assert d.kind == "ask" and "unanalysable-wrapper" in d.reason, (cmd, d)
    assert kind(cfg, cmd) == "ask", cmd
    for role in ("research", "design", "audit", "implement", "test", "review"):
        assert kind(cfg, cmd, role) == "deny", (cmd, role)


@pytest.mark.parametrize("cmd", ["ssh-keygen -l -f k", "suspend", "watchman ls", "machinectl status", "chrootish ls",
                                 "echo su", "echo 'ssh host ls'", "git commit -m 'su root'", "grep ssh f", "ls su"])
def test_similar_names_not_wrappers(cfg, cmd):
    assert kind(cfg, cmd, "test") == "allow", cmd


# ---- bounded linear fuzzing of wrapper option clusters ----------------------------------------
def test_option_cluster_fuzz_never_hides_a_hygiene_command(cfg):
    """Random wrapper/option/cluster mixes ending in `git add -A` are never allowed to pass as a
    plain command: the result is ask/deny, never allow. Generator is linear and capped."""
    import random
    rng = random.Random(8)
    wrappers = ["env", "sudo", "nice", "timeout", "xargs", "time", "nohup", "command", "exec", "setsid",
                "stdbuf", "su", "runuser", "doas", "bash", "sh"]
    pieces = ["-i", "-u", "-n", "-S", "-s", "-c", "-lc", "-Eu", "-0I{}", "-p", "--user=x", "--spl",
              "--split-string", "--sh", "-o", "L", "5", "x", "FOO=1", "--zz", "-Z", "-cx", "-ec", "-a"]
    for _ in range(600):
        n = rng.randint(1, 4)
        parts = [rng.choice(wrappers)] + [rng.choice(pieces) for _ in range(n)]
        cmd = " ".join(parts) + " git add -A"
        assert len(cmd) < 200
        d = bash_guard.decide(payload(cmd, "test"), cfg)
        # either the leaf is reached (deny: hygiene) or the shape is unclassifiable (deny): never allow,
        # except when an option legitimately consumes the leaf as its value or script
        if d.kind == "allow":
            ws = cmd.split()
            assert parts[0] in ("bash", "sh") or any(w in ("FOO=1", "-c", "-lc", "-ec", "-cx", "-s", "-o", "-S", "--user=x", "-u", "-a", "-n", "-Eu", "L", "5", "x")
                       or w.startswith(("--spl", "--sh")) for w in ws[:-3]), cmd


@pytest.mark.parametrize("cmd", [
    "env -- git add -A", "nice -- git add -A", "nice -n 1 -- git add -A", "timeout -- 5 git add -A",
    "xargs -- git add -A", "exec -- git add -A", "sudo -- git add -A", "sudo -u root -- git push -f",
    "stdbuf -oL -- git add -A", "setsid -- git add -A", "time -- git add -A", "env -i -- git reset --hard",
])
def test_operands_after_double_dash_are_analysed(cfg, cmd):
    assert kind(cfg, cmd, "orchestrator") == "ask", cmd
    assert kind(cfg, cmd, "test") == "deny", cmd
