"""SFN-09 rollback acceptance: D-13..D-16 (CLI, HTTP, strict mode, hook guard, dashboard static checks)."""
from __future__ import annotations

import json
import re
import subprocess

import pytest

from .conftest import PY, LSF, api_stop, ask_ok, out, post_release

SENTENCE = "This adds a new commit that undoes it; history is kept."


# ------------------------------------------------------------------ fixture repo
class Hist:
    """A repo with root -> c1 (a.txt) -> c2 (b.txt) -> c3 (c.txt) -> c4 (edit f.txt) -> c5 (edit f.txt again)."""

    def __init__(self, rig):
        self.rig = rig
        rig.init()
        self.root = rig.git("rev-parse", "HEAD")
        self.branch = rig.git("rev-parse", "--abbrev-ref", "HEAD")
        rig.write("f.txt", "one\n")
        rig.write("a.txt", "a\n")
        self.c1 = rig.commit(["a.txt", "f.txt"], "add a")
        rig.write("b.txt", "b\n")
        self.c2 = rig.commit("b.txt", "add b")
        rig.write("c.txt", "c\n")
        self.c3 = rig.commit("c.txt", "add c")
        rig.write("f.txt", "two\n")
        self.c4 = rig.commit("f.txt", "f becomes two")
        rig.write("f.txt", "three\n")
        self.c5 = rig.commit("f.txt", "f becomes three")

    def head(self):
        return self.rig.git("rev-parse", "HEAD")

    def log(self):
        return self.rig.git("rev-list", "HEAD").split()

    def porcelain(self):
        return self.rig.git("status", "--porcelain", "--untracked-files=no")

    def rollback(self, sha, *extra):
        return self.rig.run("rollback", sha, *extra)

    def assert_untouched(self, head, log, events):
        assert self.head() == head and self.log() == log
        assert not (self.rig.repo / ".git" / "REVERT_HEAD").exists()
        assert self.porcelain() == ""
        assert len(self.rig.events()) == events


@pytest.fixture
def h(inited):
    return Hist(inited)


def snapshot(h):
    return h.head(), h.log(), len(h.rig.events())


# ------------------------------------------------------------------ D-13 CLI
def test_D13_dry_run_without_yes_exits_2_changes_nothing_and_describes(h):
    snap = snapshot(h)
    p = h.rollback(h.c2)
    assert p.returncode == 2, out(p)
    assert "add b" in out(p) and "b.txt" in out(p)
    h.assert_untouched(*snap)
    assert (h.rig.repo / "b.txt").exists()


def test_D13_dry_run_accepts_a_short_sha(h):
    assert h.rollback(h.c2[:8]).returncode == 2


def test_D13_yes_adds_exactly_one_revert_commit_and_keeps_history_prefix(h):
    before = h.log()
    p = h.rollback(h.c2, "--yes")
    assert p.returncode == 0, out(p)
    after = h.log()
    assert len(after) == len(before) + 1
    assert after[1:] == before, "history must only grow: old history is an unchanged suffix of the new log"
    assert h.rig.git("rev-parse", "HEAD~1") == before[0]
    assert not (h.rig.repo / "b.txt").exists()
    assert (h.rig.repo / "a.txt").exists() and (h.rig.repo / "c.txt").exists()
    assert h.porcelain() == ""
    assert h.rig.git("log", "-1", "--format=%s").lower().startswith("revert")
    assert h.rig.git("rev-list", "--parents", "-1", "HEAD").split()[1:] == [before[0]]


def test_D13_yes_never_rewrites_refs_or_resets(h):
    reflog_before = h.rig.git("reflog", "--format=%H").split()
    h.rollback(h.c2, "--yes")
    # every previous commit is still reachable from the branch and the old tip is the new tip's parent
    assert h.c5 in h.log() and h.rig.git("rev-parse", "HEAD~1") == h.c5
    assert h.rig.git("rev-parse", "--abbrev-ref", "HEAD") == h.branch
    assert set(reflog_before) <= set(h.rig.git("reflog", "--format=%H").split())


def test_D13_rollback_of_the_revert_restores_the_file(h):
    h.rollback(h.c2, "--yes")
    rev = h.head()
    assert h.rollback(rev, "--yes").returncode == 0
    assert (h.rig.repo / "b.txt").read_text() == "b\n"


def test_D13_event_is_emitted_with_both_short_shas(h):
    old = h.head()
    h.rollback(h.c2, "--yes")
    evs = [e for e in h.rig.events() if e.get("stage") == "rollback"]
    assert len(evs) == 1 and evs[0].get("verdict") == "reverted"
    blob = json.dumps(evs[0])
    assert h.c2[:7] in blob and h.head()[:7] in blob and old[:7] != h.head()[:7]


def test_D14_rollback_is_not_a_gate_and_never_touches_decisions(h):
    ask_ok(h.rig, "pick", ["Alpha", "Beta"])
    p = h.rollback(h.c2, "--yes")
    assert p.returncode == 0, out(p)
    s = h.rig.stop("pick")
    assert s["state"] == "asked" and s["answer"] is None
    assert h.rig.run("hitl", "status").returncode == 3


# ------------------------------------------------------------------ D-14 refusals (CLI exit 1, nothing changed)
def refused(h, sha, *extra):
    snap = snapshot(h)
    p = h.rollback(sha, "--yes", *extra)
    assert p.returncode == 1, out(p)
    assert out(p).strip(), "refusal must name the reason"
    h.assert_untouched(*snap)
    return p


def test_D14_dirty_tracked_change_refuses(h):
    h.rig.write("a.txt", "edited, not committed\n")
    snap_text = (h.rig.repo / "a.txt").read_text()
    snap = snapshot(h)
    p = h.rollback(h.c2, "--yes")
    assert p.returncode == 1 and out(p).strip()
    assert h.head() == snap[0] and h.log() == snap[1] and (h.rig.repo / "a.txt").read_text() == snap_text


def test_D14_staged_change_refuses(h):
    h.rig.write("a.txt", "staged\n")
    h.rig.git("add", "--", "a.txt")
    snap = snapshot(h)
    p = h.rollback(h.c2, "--yes")
    assert p.returncode == 1
    assert h.head() == snap[0] and h.log() == snap[1]
    assert h.rig.git("diff", "--cached", "--name-only") == "a.txt"


def test_D14_untracked_files_are_ignored(h):
    h.rig.write("scratch/untracked.txt", "x\n")
    h.rig.write("junk.log", "x\n")
    p = h.rollback(h.c2, "--yes")
    assert p.returncode == 0, out(p)
    assert (h.rig.repo / "scratch" / "untracked.txt").exists()


def test_D14_gitignored_files_are_ignored(h):
    h.rig.write(".gitignore", "*.log\n")
    h.rig.commit(".gitignore", "ignore logs")
    h.rig.write("junk.log", "x\n")
    assert h.rollback(h.c2, "--yes").returncode == 0


@pytest.mark.parametrize("sha", ["0" * 40, "deadbeefdeadbeef", "not-a-sha", "HEAD~99", ""])
def test_D14_unresolvable_sha_refuses(h, sha):
    snap = snapshot(h)
    p = h.rollback(sha, "--yes")
    assert p.returncode in (1, 2) and p.returncode != 0
    assert (p.returncode == 1) or sha == ""
    h.assert_untouched(*snap)


def test_D14_sha_that_is_not_a_commit_refuses(h):
    tree = h.rig.git("rev-parse", "HEAD^{tree}")
    refused(h, tree)


def test_D14_option_looking_argument_is_not_passed_through_to_git(h):
    snap = snapshot(h)
    p = h.rollback("--abort", "--yes")
    assert p.returncode != 0
    h.assert_untouched(*snap)


def test_D14_not_an_ancestor_of_head_refuses(h):
    h.rig.git("checkout", "-q", "-b", "side", h.c1)
    h.rig.write("side.txt", "s\n")
    side = h.rig.commit("side.txt", "side work")
    h.rig.git("checkout", "-q", h.branch)
    refused(h, side)


def test_D14_merge_commit_refuses(h):
    h.rig.git("checkout", "-q", "-b", "side", h.c5)
    h.rig.write("side.txt", "s\n")
    h.rig.commit("side.txt", "side work")
    h.rig.git("checkout", "-q", h.branch)
    h.rig.write("main.txt", "m\n")
    h.rig.commit("main.txt", "main work")
    h.rig.git("merge", "-q", "--no-ff", "-m", "merge side", "side")
    merge = h.head()
    assert len(h.rig.git("rev-list", "--parents", "-1", merge).split()) == 3
    refused(h, merge)


def test_D14_root_commit_refuses(h):
    refused(h, h.root)


def test_D14_revert_conflict_aborts_leaves_tree_clean_and_no_revert_head(h):
    snap = snapshot(h)
    p = h.rollback(h.c4, "--yes")  # c5 edits the same line, so reverting c4 conflicts
    assert p.returncode == 1, out(p)
    assert "revert conflicts; resolve by hand" in out(p)
    h.assert_untouched(*snap)
    assert (h.rig.repo / "f.txt").read_text() == "three\n"
    assert h.rig.git("diff", "--name-only") == "" and h.rig.git("diff", "--cached", "--name-only") == ""
    # the repo is usable afterwards
    assert h.rollback(h.c2, "--yes").returncode == 0


def test_D14_refused_rollbacks_emit_no_reverted_event(h):
    h.rig.write("a.txt", "dirty\n")
    h.rollback(h.c2, "--yes")
    h.rollback(h.root, "--yes")
    assert not [e for e in h.rig.events() if e.get("stage") == "rollback" and e.get("verdict") == "reverted"]


# ------------------------------------------------------------------ D-13/D-14 HTTP
@pytest.fixture
def web(h, serve):
    srv = serve(h.rig)
    srv.h = h
    return srv


def post_rb(srv, body, token="default", host="default"):
    hdr = {"Content-Type": "application/json"}
    tok = srv.token if token == "default" else token
    if tok is not None:
        hdr["X-LSF-Token"] = tok
    return srv.req("POST", "/api/rollback", body if isinstance(body, str) else json.dumps(body), hdr, host=host)


def msg(r):
    return r[2].decode("utf-8", "replace")


def test_D13_http_success_reverts_and_returns_ok_reverted_new_head(web):
    h = web.h
    before = h.log()
    r = post_rb(web, {"sha": h.c2, "confirm_sha": h.c2})
    assert r[0] == 200, msg(r)
    b = json.loads(msg(r))
    assert b["ok"] is True and b["reverted"].startswith(h.c2[:7]) and b["new_head"] == h.head()
    assert h.log()[1:] == before and len(h.log()) == len(before) + 1
    assert not (h.rig.repo / "b.txt").exists()


def test_D13_http_event_is_emitted(web):
    h = web.h
    post_rb(web, {"sha": h.c2, "confirm_sha": h.c2})
    evs = [e for e in h.rig.events() if e.get("stage") == "rollback"]
    assert len(evs) == 1 and evs[0]["verdict"] == "reverted"
    assert h.c2[:7] in json.dumps(evs[0]) and h.head()[:7] in json.dumps(evs[0])


def test_D13_http_short_sha_resolves_when_confirm_is_the_full_sha(web):
    h = web.h
    assert post_rb(web, {"sha": h.c2[:8], "confirm_sha": h.c2})[0] == 200


@pytest.mark.parametrize("variant", ["missing", "wrong", "prefix", "suffix", "empty"])
def test_D13_http_token_is_required(web, variant):
    h = web.h
    snap = snapshot(h)
    tok = {"missing": None, "wrong": "x" * len(web.token), "prefix": web.token[:-1], "suffix": web.token + "x",
           "empty": ""}[variant]
    assert post_rb(web, {"sha": h.c2, "confirm_sha": h.c2}, token=tok)[0] == 403
    h.assert_untouched(*snap)


def test_D13_http_foreign_host_is_403_even_with_token(web):
    h = web.h
    snap = snapshot(h)
    assert post_rb(web, {"sha": h.c2, "confirm_sha": h.c2}, host="evil.example.com")[0] == 403
    h.assert_untouched(*snap)


@pytest.mark.parametrize("variant", ["short", "other_commit", "missing", "empty", "upper_ok_or_not_equal", "number"])
def test_D13_http_confirm_sha_must_equal_the_full_resolved_sha(web, variant):
    h = web.h
    snap = snapshot(h)
    body = {"sha": h.c2}
    confirm = {"short": h.c2[:7], "other_commit": h.c3, "empty": "", "upper_ok_or_not_equal": h.c2[:-1] + "x",
               "number": 5}
    if variant != "missing":
        body["confirm_sha"] = confirm[variant]
    r = post_rb(web, body)
    assert r[0] in (400, 409), msg(r)
    h.assert_untouched(*snap)


@pytest.mark.parametrize("body", ["", "not json", "[]", '{"confirm_sha": "x"}', '{"sha": 5, "confirm_sha": 5}'])
def test_D13_http_bad_bodies_are_client_errors(web, body):
    snap = snapshot(web.h)
    r = post_rb(web, body)
    assert 400 <= r[0] < 500
    web.h.assert_untouched(*snap)


def test_D13_http_oversized_body_is_refused(web):
    h = web.h
    snap = snapshot(h)
    r = post_rb(web, {"sha": h.c2, "confirm_sha": h.c2, "pad": "x" * (2 * 1024 * 1024)})
    assert 400 <= r[0] < 500
    h.assert_untouched(*snap)


@pytest.mark.parametrize("method", ["GET", "PUT", "DELETE"])
def test_D13_http_other_methods_cannot_rollback(web, method):
    h = web.h
    snap = snapshot(h)
    hdr = {"X-LSF-Token": web.token}
    r = web.req(method, "/api/rollback?sha=%s&confirm_sha=%s" % (h.c2, h.c2), None, hdr)
    assert 400 <= r[0] < 500
    h.assert_untouched(*snap)


def test_D14_http_dirty_tree_is_409_and_unchanged(web):
    h = web.h
    h.rig.write("a.txt", "dirty\n")
    before = (h.head(), h.log())
    r = post_rb(web, {"sha": h.c2, "confirm_sha": h.c2})
    assert r[0] == 409 and msg(r).strip()
    assert (h.head(), h.log()) == before


@pytest.mark.parametrize("which", ["unknown", "root", "merge", "not_ancestor"])
def test_D14_http_refusals_are_409(web, which):
    h = web.h
    if which == "merge":
        h.rig.git("checkout", "-q", "-b", "side", h.c5)
        h.rig.write("side.txt", "s\n")
        h.rig.commit("side.txt", "side")
        h.rig.git("checkout", "-q", h.branch)
        h.rig.write("m.txt", "m\n")
        h.rig.commit("m.txt", "main")
        h.rig.git("merge", "-q", "--no-ff", "-m", "merge", "side")
        sha = h.head()
    elif which == "not_ancestor":
        h.rig.git("checkout", "-q", "-b", "side", h.c1)
        h.rig.write("side.txt", "s\n")
        sha = h.rig.commit("side.txt", "side")
        h.rig.git("checkout", "-q", h.branch)
    else:
        sha = {"unknown": "0" * 40, "root": h.root}[which]
    snap = snapshot(h)
    r = post_rb(web, {"sha": sha, "confirm_sha": sha})
    assert r[0] == 409, msg(r)
    h.assert_untouched(*snap)


def test_D14_http_conflict_is_409_with_the_message_and_clean_tree(web):
    h = web.h
    snap = snapshot(h)
    r = post_rb(web, {"sha": h.c4, "confirm_sha": h.c4})
    assert r[0] == 409 and "revert conflicts; resolve by hand" in msg(r)
    h.assert_untouched(*snap)


def test_D14_http_untracked_files_do_not_block(web):
    web.h.rig.write("untracked.txt", "x\n")
    assert post_rb(web, {"sha": web.h.c2, "confirm_sha": web.h.c2})[0] == 200


def test_D14_http_rollback_does_not_release_or_answer_a_decision(h, serve):
    ask_ok(h.rig, "pick", ["Alpha", "Beta"])
    srv = serve(h.rig)
    assert post_rb(srv, {"sha": h.c2, "confirm_sha": h.c2})[0] == 200
    s = api_stop(srv, "pick")
    assert s["state"] == "asked" and s["answer"] is None


def test_D14_http_open_stop_for_the_phase_is_not_a_reason_to_refuse(h, serve):
    h.rig.phase("start", "0-intake", 0)
    h.rig.phase("end", "0-intake", 5)
    srv = serve(h.rig)
    assert api_stop(srv, "0-intake-review")["state"] == "asked"
    assert post_rb(srv, {"sha": h.c2, "confirm_sha": h.c2})[0] == 200


# ------------------------------------------------------------------ D-16 strict mode and hook guard
def test_D16_strict_mode_without_a_tty_refuses_cli_rollback(rig):
    rig.init("--strict-hitl")
    rig.write("a.txt", "a\n")
    c1 = rig.commit("a.txt", "add a")
    rig.write("b.txt", "b\n")
    rig.commit("b.txt", "add b")
    head = rig.git("rev-parse", "HEAD")
    p = rig.run("rollback", rig.git("rev-parse", "HEAD"), "--yes")
    assert p.returncode != 0 and out(p).strip()
    assert rig.git("rev-parse", "HEAD") == head and (rig.repo / "b.txt").exists()
    assert c1


def test_D16_strict_mode_does_not_stop_the_dry_run_description(rig):
    rig.init("--strict-hitl")
    rig.write("b.txt", "b\n")
    sha = rig.commit("b.txt", "add b")
    assert rig.run("rollback", sha).returncode == 2


def test_D16_strict_mode_dashboard_rollback_still_needs_token_but_works_with_it(rig, serve):
    rig.init("--strict-hitl")
    rig.write("b.txt", "b\n")
    sha = rig.commit("b.txt", "add b")
    rig.write("c.txt", "c\n")
    rig.commit("c.txt", "add c")
    srv = serve(rig)
    assert post_rb(srv, {"sha": sha, "confirm_sha": sha}, token=None)[0] == 403
    assert post_rb(srv, {"sha": sha, "confirm_sha": sha})[0] == 200


def guard(rig, cmd):
    return rig.run("hook", "guard", input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))


@pytest.mark.parametrize("cmd", [
    "curl -X POST localhost:8765/api/rollback",
    "curl -s -X POST -H 'X-LSF-Token: abc' -d '{\"sha\":\"a\",\"confirm_sha\":\"a\"}' http://127.0.0.1:8765/api/rollback",
    "python3 -c \"import urllib.request as u; u.urlopen('http://localhost:1/api/rollback', b'{}')\"",
])
def test_D16_hook_guard_denies_agent_bash_calling_the_rollback_endpoint(inited, cmd):
    r = guard(inited, cmd)
    assert r.returncode == 2 and r.stderr.strip() and r.stdout == "", cmd


@pytest.mark.parametrize("cmd", ["ls", "git log --oneline", "lsf hitl status", "curl localhost:8765/api/state"])
def test_D16_hook_guard_still_allows_ordinary_commands(inited, cmd):
    r = guard(inited, cmd)
    assert r.returncode == 0 and r.stdout == "" and r.stderr == "", cmd


def test_D16_hook_guard_still_denies_release(inited):
    assert guard(inited, "curl -X POST localhost:8765/api/hitl/release").returncode == 2


# ------------------------------------------------------------------ D-15 dashboard static checks
@pytest.fixture
def page(inited, serve):
    s, _, b = serve(inited).get("/")
    assert s == 200
    return b.decode("utf-8", "replace")


def test_D15_rollback_controls_ship(page):
    for word in ("Rollback", "Confirm rollback", "Cancel"):
        assert word in page, word


def test_D15_the_history_is_kept_sentence_ships_verbatim(page):
    assert SENTENCE in page


def test_D15_confirm_posts_confirm_sha_to_the_rollback_endpoint(page):
    assert "/api/rollback" in page and "confirm_sha" in page


def test_D15_without_a_token_the_command_is_shown_instead(page):
    assert re.search(r"lsf rollback [^\n]*--yes", page)


def test_D15_merges_and_the_root_commit_get_no_rollback_button(page):
    # the row renderer must branch on parent count / root; cheap static proxy
    assert re.search(r"parents|is_merge|isMerge|merge", page, re.I) and re.search(r"root|parents", page, re.I)


def test_D15_rollback_does_not_add_external_resources(page):
    assert not re.search(r"<script[^>]+src=['\"]https?://", page)


# ------------------------------------------------------------------ D-16 addenda: guard variants, no abbreviations
@pytest.mark.parametrize("cmd", [
    "lsf rollback abc1234 --y",
    "lsf rollback abc1234 --ye",
    "lsf rollback abc1234 --yes",
    "lsf rollback abc1234",
    "python3 skills/lsf/scripts/lsf.py rollback abc1234",
])
def test_D16_hook_guard_denies_agent_bash_lsf_rollback_in_every_form(inited, cmd):
    r = guard(inited, cmd)
    assert r.returncode == 2 and r.stderr.strip() and r.stdout == "", (cmd, r.returncode, r.stdout, r.stderr)


@pytest.mark.parametrize("flag", ["--y", "--ye"])
def test_D16_cli_rejects_abbreviated_yes_with_a_usage_error_and_changes_nothing(h, flag):
    snap = snapshot(h)
    p = h.rollback(h.c2, flag)
    assert p.returncode == 2, out(p)
    assert re.search(r"usage|unrecognized|ambiguous|invalid", p.stderr, re.I), p.stderr
    h.assert_untouched(*snap)
    assert (h.rig.repo / "b.txt").exists()


def test_D16_cli_rejects_abbreviated_answer_on_hitl_release(inited):
    ask_ok(inited, "pick", ["Alpha", "Beta"])
    before = inited.stop_lines()
    p = inited.run("hitl", "release", "pick", "--ans", "Alpha")
    assert p.returncode == 2, out(p)
    assert re.search(r"usage|unrecognized|ambiguous|invalid", p.stderr, re.I), p.stderr
    assert inited.stop_lines() == before and inited.stop("pick")["state"] == "asked"
