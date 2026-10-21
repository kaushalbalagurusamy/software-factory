"""L-09 serve: localhost bind, Host check, GET routes, the one token-guarded POST, file safety."""
from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.parse as up
from pathlib import Path

import pytest

from .conftest import PY, LSF, Rig, Server, find_key, free_port, require_lsf

OUTSIDE_SECRET = "OUTSIDE-SECRET-CONTENT-31337"


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("serve")
    rig = Rig(tmp)
    (tmp / "outside.txt").write_text(OUTSIDE_SECRET)
    (tmp / "outside_dir").mkdir()
    (tmp / "outside_dir" / "x.txt").write_text(OUTSIDE_SECRET)
    rig.write("src/a.py", "print('hello-from-a')\n")
    rig.write("big_ok.txt", "a" * (1024 * 1024))
    rig.write("big_over.txt", "a" * (1024 * 1024 + 1))
    rig.write("bin.dat", b"\xff\xfe\x00\x01\x80binary")
    rig.write(".env", "TOKEN=env-secret-1\n")
    rig.write(".env.local", "TOKEN=env-secret-2\n")
    rig.write("sub/.env.production", "TOKEN=env-secret-3\n")
    rig.write("docs/adr/ADR-0001-first.md", "# First\n**Status:** Accepted\n**Date:** 2026-10-01\n")
    os.symlink(tmp / "outside.txt", rig.repo / "link_out.txt")
    os.symlink(tmp / "outside_dir", rig.repo / "link_dir")
    os.symlink("src/a.py", rig.repo / "link_in.py")
    rig.commit(["src/a.py", "big_ok.txt", "big_over.txt", "bin.dat", "docs/adr/ADR-0001-first.md", "link_out.txt",
                "link_dir", "link_in.py"], "second")
    sha1 = rig.git("rev-parse", "HEAD")
    rig.write("docs/adr/ADR-0002-second.md", "# Second\n**Status:** Proposed\n**Date:** 2026-10-02\n")
    sha2 = rig.commit("docs/adr/ADR-0002-second.md", "third")
    rig.init()
    rig.write(".lsf/secrets.json", '{"k": "lsf-secret-1"}')
    rig.write(".lsf/token", "lsf-secret-2")
    srv = Server(rig)
    srv.sha1, srv.sha2 = sha1, sha2
    yield srv
    srv.stop()


def body_json(r):
    return json.loads(r[2].decode())


# ---------------------------------------------------------------- bind / host
def test_L09_binds_loopback_only(world):
    assert socket.create_connection(("127.0.0.1", world.port), 2)
    if not Path("/proc/net/tcp").exists():
        pytest.skip("needs /proc/net/tcp to inspect the bind address (Linux CI only)")
    rows = [l.split() for l in Path("/proc/net/tcp").read_text().splitlines()[1:]]
    mine = [r for r in rows if r[1].endswith(":%04X" % world.port) and r[3] == "0A"]
    assert mine and all(r[1].startswith("0100007F") for r in mine), mine


def test_L09_prints_url_with_token_fragment_once(world):
    out = world.output()
    assert f"http://127.0.0.1:{world.port}/#token={world.token}" in out
    assert len(world.token) >= 16


@pytest.mark.parametrize("host", ["evil.example", "evil.example:80", "127.0.0.1.evil.com", "localhost.evil.com",
                                  "0.0.0.0", "192.168.1.5:8765", ""])
def test_L09_foreign_host_header_gets_403(world, host):
    for path in ("/", "/api/state", "/api/file?path=README.md"):
        assert world.get(path, host=host)[0] == 403, (host, path)


@pytest.mark.parametrize("host", ["127.0.0.1:{p}", "localhost:{p}", "127.0.0.1", "localhost"])
def test_L09_localhost_host_headers_are_served(world, host):
    assert world.get("/", host=host.format(p=world.port))[0] == 200


def test_L09_foreign_host_cannot_release_even_with_token(world):
    world.rig.run("hitl", "request", "hostcheck", "--question", "q")
    r = world.release("hostcheck", host="evil.example")
    assert r[0] == 403
    assert world.rig.stop("hostcheck") is not None


# ---------------------------------------------------------------- GET routes
def test_L09_root_serves_the_dashboard(world):
    s, h, b = world.get("/")
    assert s == 200 and "text/html" in h["content-type"]
    assert b"<html" in b.lower() and b"Now" in b


def test_L09_state_is_json_and_built_per_request(world):
    s, h, b = world.get("/api/state")
    assert s == 200 and "json" in h["content-type"]
    d = json.loads(b)
    adrs = find_key(d, "adrs")
    assert adrs and adrs["available"] is True and len(adrs["items"]) >= 2
    world.rig.run("event", "7-implement", "pass", "--note", "marker-per-request-91827")
    assert b"marker-per-request-91827" in world.get("/api/state")[2]


def test_L09_state_never_contains_the_token(world):
    assert world.token.encode() not in world.get("/api/state")[2]
    assert world.token.encode() not in world.get("/")[2]


def test_L09_state_shows_open_stops_and_phase(world):
    world.rig.run("hitl", "request", "visible-stop", "--question", "Visible?")
    assert b"visible-stop" in world.get("/api/state")[2]


def test_L09_file_route_returns_text(world):
    s, _, b = world.get("/api/file?path=src/a.py")
    assert s == 200 and b"hello-from-a" in b
    assert world.get("/api/file?path=link_in.py")[0] == 200  # symlink that stays inside is fine


def test_L09_file_route_size_cap_is_one_mib(world):
    s, _, b = world.get("/api/file?path=big_ok.txt")
    assert s == 200 and len(b) >= 1024 * 1024
    s, _, b = world.get("/api/file?path=big_over.txt")
    assert 400 <= s < 500 and len(b) < 1024 * 1024


@pytest.mark.parametrize("path", [
    "../outside.txt", "..%2foutside.txt", "%2e%2e/outside.txt", "src/../../outside.txt", "src/%2e%2e/%2e%2e/outside.txt",
    "..\\outside.txt", "/etc/passwd", "a%00.py", "link_out.txt", "link_dir/x.txt", "....//outside.txt",
])
def test_L09_file_route_refuses_escapes(world, path):
    s, _, b = world.get("/api/file?path=" + path)
    assert 400 <= s < 500, (path, s)
    assert OUTSIDE_SECRET.encode() not in b and b"root:" not in b


def test_L09_absolute_path_inside_root_is_not_a_way_around_checks(world):
    s, _, b = world.get("/api/file?path=" + up.quote(str(world.rig.repo / ".env")))
    assert 400 <= s < 500 and b"env-secret" not in b


@pytest.mark.parametrize("path", [".git/config", ".git/HEAD", ".GIT/config", ".env", ".env.local", "sub/.env.production",
                                  ".lsf/secrets.json", ".lsf/token", "./.env"])
def test_L09_file_route_refuses_git_env_and_lsf_secrets(world, path):
    s, _, b = world.get("/api/file?path=" + path)
    assert 400 <= s < 500, (path, s)
    for needle in (b"env-secret", b"lsf-secret", b"[core]"):
        assert needle not in b


def test_L09_file_route_other_refusals(world):
    assert world.get("/api/file?path=nope.txt")[0] == 404
    assert 400 <= world.get("/api/file?path=src")[0] < 500  # directory
    assert 400 <= world.get("/api/file?path=bin.dat")[0] < 500  # not UTF-8
    assert 400 <= world.get("/api/file")[0] < 500  # missing parameter
    assert 400 <= world.get("/api/file?path=")[0] < 500


def test_L09_at_route_shows_history(world):
    s1 = world.get("/api/at?sha=" + world.sha1)
    s2 = world.get("/api/at?sha=" + world.sha2)
    assert s1[0] == 200 and s2[0] == 200
    a1, a2 = find_key(body_json(s1), "adrs"), find_key(body_json(s2), "adrs")
    assert [i["path"] for i in a1["items"]] == ["docs/adr/ADR-0001-first.md"]
    assert len(a2["items"]) == 2
    short = world.get("/api/at?sha=" + world.sha1[:10])
    assert short[0] == 200


@pytest.mark.parametrize("sha", ["", "zzzz", "--output=/tmp/lsf-pwn-should-not-exist", "HEAD;id", "$(id)",
                                 "-h", "0" * 40, "..", "a" * 5000])
def test_L09_at_route_rejects_bad_revisions(world, sha):
    s, _, b = world.get("/api/at?sha=" + up.quote(sha))
    assert 400 <= s < 500, (sha, s)
    assert not Path("/tmp/lsf-pwn-should-not-exist").exists()


# ---------------------------------------------------------------- the one POST
def test_L09_release_with_exact_token_works(world):
    world.rig.run("hitl", "request", "rel-ok", "--question", "q")
    s, _, b = world.release("rel-ok", note="approved from dashboard")
    assert s == 200, b
    last = json.loads(world.rig.stop_lines()[-1])
    assert "approved from dashboard" in json.dumps(last) and "rel-ok" in json.dumps(last)
    n = len(world.rig.stop_lines())
    assert world.rig.run("hitl", "release", "rel-ok").returncode in (1, 2)  # never double-recorded
    assert len(world.rig.stop_lines()) == n


@pytest.mark.parametrize("variant", ["missing", "wrong", "prefix", "suffix", "empty", "upper"])
def test_L09_release_with_bad_token_is_403_and_changes_nothing(world, variant):
    name = f"guarded-{variant}"
    world.rig.run("hitl", "request", name, "--question", "q")
    before = world.rig.stop_lines()
    tok = {"missing": None, "wrong": "x" * len(world.token), "prefix": world.token[:-1],
           "suffix": world.token + "x", "empty": "", "upper": world.token.upper()}[variant]
    if variant == "upper" and tok == world.token:
        pytest.skip("token has no lowercase letters")
    s, _, _ = world.release(name, token=tok)
    assert s == 403
    assert world.rig.stop_lines() == before
    assert world.rig.run("hitl", "status").returncode == 3


def test_L09_release_unknown_or_repeated_is_a_client_error(world):
    assert 400 <= world.release("never-existed")[0] < 500
    world.rig.run("hitl", "request", "twice", "--question", "q")
    assert world.release("twice")[0] == 200
    n = len(world.rig.stop_lines())
    assert 400 <= world.release("twice")[0] < 500
    assert len(world.rig.stop_lines()) == n


@pytest.mark.parametrize("body", ["", "not json", "[]", '{"note": "x"}', '{"name": 5}', '{"name": ""}'])
def test_L09_release_bad_bodies_are_client_errors(world, body):
    s, _, _ = world.req("POST", "/api/hitl/release", body, {"X-LSF-Token": world.token, "Content-Type": "application/json"})
    assert 400 <= s < 500


@pytest.mark.parametrize("path", ["/", "/api/state", "/api/file?path=README.md", "/api/at?sha=HEAD", "/api/hitl/request",
                                  "/api/event", "/api/phase", "/api/hitl", "/api/hitl/release/x", "/api/shutdown"])
def test_L09_no_other_post_route_exists(world, path):
    before = (world.rig.stop_lines(), len(world.rig.events()))
    s, _, _ = world.req("POST", path, json.dumps({"name": "x"}), {"X-LSF-Token": world.token,
                                                                "Content-Type": "application/json"})
    assert s in (404, 405, 501), (path, s)
    assert (world.rig.stop_lines(), len(world.rig.events())) == before


@pytest.mark.parametrize("method", ["PUT", "DELETE", "PATCH"])
def test_L09_other_methods_cannot_mutate(world, method):
    world.rig.run("hitl", "request", "no-" + method.lower(), "--question", "q")
    before = world.rig.stop_lines()
    s, _, _ = world.req(method, "/api/hitl/release", json.dumps({"name": "no-" + method.lower()}),
                        {"X-LSF-Token": world.token, "Content-Type": "application/json"})
    assert s >= 400
    assert world.rig.stop_lines() == before


def test_L09_get_on_the_release_route_does_not_release(world):
    world.rig.run("hitl", "request", "get-no", "--question", "q")
    before = world.rig.stop_lines()
    s, _, _ = world.get("/api/hitl/release?name=get-no&token=" + world.token)
    assert s in (404, 405)
    assert world.rig.stop_lines() == before


def test_L09_no_cross_origin_grant(world):
    for path in ("/", "/api/state"):
        assert "access-control-allow-origin" not in world.get(path)[1]
    s, h, _ = world.req("OPTIONS", "/api/hitl/release")
    assert "access-control-allow-origin" not in h


def test_L09_token_and_bodies_are_not_logged(world):
    world.rig.run("hitl", "request", "log-check", "--question", "q")
    world.release("log-check", note="PRIVATE-NOTE-BODY-5551")
    world.release("log-check", token="not-the-token-123")
    out = world.output()
    assert "PRIVATE-NOTE-BODY-5551" not in out
    assert out.count(world.token) == 1  # printed once, in the URL
    assert "not-the-token-123" not in out


# ---------------------------------------------------------------- startup failures
def test_L09_busy_port_exits_nonzero_with_message(rig):
    require_lsf()
    rig.init()
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    s.listen(1)
    port = s.getsockname()[1]
    try:
        p = subprocess.run([PY, str(LSF), "serve", "--port", str(port)], cwd=str(rig.repo), env=rig.env,
                           capture_output=True, text=True, timeout=15)
    finally:
        s.close()
    assert p.returncode == 1
    assert "Traceback" not in p.stderr and (p.stderr + p.stdout).strip()


def test_L09_serve_help_mentions_open_and_port(rig):
    out = rig.run("serve", "--help").stdout
    assert "--port" in out and "--open" in out
