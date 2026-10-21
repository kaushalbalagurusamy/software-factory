import http.client
import json
import os
import subprocess
import sys
import time

import pytest

from conftest import LSF, run


@pytest.fixture
def server(repo):
    run(repo, "init")
    (repo / "docs").mkdir()
    (repo / "docs/a.md").write_text("hello\n")
    (repo / ".env").write_text("K=1\n")
    (repo / "docs/.env.local").write_text("K=1\n")
    (repo / "docs/bin.dat").write_bytes(b"\xff\xfe\x00")
    (repo / "docs/big.txt").write_text("x" * (1024 * 1024 + 5))
    (repo / "docs/link.md").symlink_to(repo / "docs/a.md")
    (repo / ".lsf/my-secret.txt").write_text("s")
    (repo / ".lsf/api_token").write_text("s")
    outside = repo.parent / "outside.txt"
    outside.write_text("nope")
    (repo / "docs/escape.md").symlink_to(outside)
    subprocess.run(["git", "-C", str(repo), "add", "docs/a.md"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "docs"], check=True)
    run(repo, "hitl", "request", "gate", "--question", "ok?")
    env = dict(os.environ)
    p = subprocess.Popen([sys.executable, str(LSF), "serve", "--port", "0", "--root", str(repo)], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env=env)
    line = p.stdout.readline()
    assert "#token=" in line
    port = int(line.split("127.0.0.1:")[1].split("/")[0])
    token = line.strip().split("#token=")[1]
    yield port, token, repo
    p.terminate()
    p.wait(10)


def req(port, method, path, headers=None, body=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=20)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read().decode("utf-8", "replace")
    return r.status, r, data


def test_dashboard_and_state(server):
    port, token, repo = server
    s, r, body = req(port, "GET", "/")
    assert s == 200 and "<html" in body.lower() and token not in body
    s, r, body = req(port, "GET", "/api/state")
    d = json.loads(body)
    assert s == 200 and "tabs" in d and d["runtime"]["stops"][0]["name"] == "gate"
    assert req(port, "GET", "/api/state", {"Host": "evil.example.com"})[0] == 403
    assert req(port, "GET", "/nothing")[0] == 404
    assert not any(k.lower().startswith("access-control") for k in r.headers)


def test_file_route(server):
    port, token, repo = server
    assert req(port, "GET", "/api/file?path=docs/a.md")[2] == "hello\n"
    assert req(port, "GET", "/api/file?path=docs/link.md")[0] == 200
    codes = {p: req(port, "GET", "/api/file?path=" + p)[0] for p in (
        "nothing.md", "../outside.txt", "/etc/passwd", "docs/escape.md", ".git/config", ".env", "docs/.env.local",
        ".lsf/my-secret.txt", ".lsf/api_token", "docs/big.txt", "docs/bin.dat", "", "docs/../docs/a.md", "docs")}
    assert codes["nothing.md"] == 404
    assert all(400 <= v < 500 for v in codes.values()), codes
    assert req(port, "GET", "/api/file?path=.lsf/events.jsonl")[0] in (200, 404)


def test_at_route(server):
    port, token, repo = server
    sha = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    for s in (sha, sha[:7]):
        st, _, body = req(port, "GET", "/api/at?sha=" + s)
        assert st == 200 and "git" in json.loads(body)["tabs"]
    assert req(port, "GET", "/api/at?sha=nothex")[0] == 400
    assert req(port, "GET", "/api/at?sha=deadbeef")[0] == 400
    assert req(port, "GET", "/api/at")[0] == 400


def test_release_route(server):
    port, token, repo = server
    H = {"Content-Type": "application/json"}
    body = json.dumps({"name": "gate", "note": "n"})
    assert req(port, "POST", "/api/hitl/release", H, body)[0] == 403
    assert req(port, "POST", "/api/hitl/release", dict(H, **{"X-LSF-Token": "wrong"}), body)[0] == 403
    assert req(port, "POST", "/api/hitl/release", dict(H, **{"X-LSF-Token": token, "Host": "evil.com"}), body)[0] == 403
    assert run(repo, "hitl", "status").returncode == 3
    good = dict(H, **{"X-LSF-Token": token})
    assert req(port, "POST", "/api/hitl/release", good, "{bad")[0] == 400
    assert req(port, "POST", "/api/hitl/release", good, json.dumps({"name": "ghost"}))[0] == 409
    assert req(port, "POST", "/api/other", good, body)[0] == 404
    assert req(port, "PUT", "/api/hitl/release", good, body)[0] in (404, 405, 501)
    assert req(port, "POST", "/api/hitl/release", good, body)[0] == 200
    assert run(repo, "hitl", "status").returncode == 0
    assert req(port, "POST", "/api/hitl/release", good, body)[0] == 409


def test_localhost_only(server):
    port, token, repo = server
    out = subprocess.run([sys.executable, "-c", "import socket,sys;s=socket.socket();s.settimeout(2);\n"
                          "import socket as k\nprint(k.gethostbyname(k.gethostname()))"], capture_output=True, text=True).stdout.strip()
    if out and not out.startswith("127."):
        c = http.client.HTTPConnection(out, port, timeout=3)
        with pytest.raises(OSError):
            c.request("GET", "/")
            c.getresponse()


def test_dashboard_release_records_the_actual_transport(server):
    port, token, repo = server
    headers = {'Content-Type':'application/json','X-LSF-Token':token}
    body = json.dumps({'name':'gate','note':'Codex acting as delegated HITL reviewer'})
    assert req(port,'POST','/api/hitl/release',headers,body)[0] == 200
    entries = [json.loads(line) for line in (repo/'.lsf/stops.jsonl').read_text().splitlines()]
    release = next(e for e in entries if e['kind'] == 'release')
    assert release['via'] == 'dashboard'
    assert 'delegated HITL' in release['note']
