"""Security regressions for factory.ops and the dolls viewer (from the commit security review)."""
import http.client
import json
import subprocess
import sys
import threading
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
from factory.ops import bundle as B  # noqa: E402
from factory.ops import collect as C  # noqa: E402
from factory.ops import runtime as R  # noqa: E402


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
                          capture_output=True, text=True, check=True).stdout.strip()


# ---- 3. a symlink in the working tree must not expose files outside the repo --------------------------------

def test_worktree_source_does_not_follow_symlinks(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("TOP SECRET")
    repo = tmp_path / "repo"
    (repo / "docs" / "adr").mkdir(parents=True)
    (repo / "docs" / "adr" / "ADR-0001-x.md").write_text("# ADR-0001: x\n")
    git_init = ["init", "-q"]
    git(repo, *git_init)
    (repo / "docs" / "adr" / "ADR-0002-link.md").symlink_to(outside)
    src = C.WorkTreeSource(repo)
    assert src.read("docs/adr/ADR-0002-link.md") is None
    assert "docs/adr/ADR-0002-link.md" not in src.paths()
    assert src.read("docs/adr/ADR-0001-x.md") is not None


# ---- 4. the bundle must not write through a symlink or outside its output root -------------------------------

def test_atomic_refuses_symlinked_output_directory(tmp_path):
    out = tmp_path / "ops"
    out.mkdir()
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (out / "blobs").symlink_to(elsewhere)
    with pytest.raises(ValueError, match="symlink"):
        B.put_blob(out, {"a": 1})
    assert list(elsewhere.iterdir()) == []


def test_atomic_refuses_symlinked_target_file_and_escape(tmp_path):
    out = tmp_path / "ops"
    (out / "blobs").mkdir(parents=True)
    victim = tmp_path / "victim.txt"
    victim.write_text("keep")
    (out / "index.json").symlink_to(victim)
    with pytest.raises(ValueError, match="symlink"):
        B._atomic(out / "index.json", b"{}", out)
    assert victim.read_text() == "keep"
    with pytest.raises(ValueError, match="outside"):
        B._atomic(tmp_path / "other" / "x.json", b"{}", out)


def test_atomic_writes_normally(tmp_path):
    out = tmp_path / "ops"
    B._atomic(out / "blobs" / "x.json", b"{}", out)
    assert (out / "blobs" / "x.json").read_bytes() == b"{}"


# ---- 2. the server serves only the dashboard's artifacts and only to local Host headers ----------------------

@pytest.fixture
def server(tmp_path):
    root = tmp_path / "ops"
    (root / "shell").mkdir(parents=True)
    (root / "blobs").mkdir()
    (root / "shell" / "index.html").write_text("<html>shell</html>")
    (root / "blobs" / "a.json").write_text("{}")
    (root / "runtime.json").write_text("{}")
    (root / "index.json").write_text("{}")
    (root / "config.json").write_text('{"health_url": "http://internal/secret"}')
    (root / ".env").write_text("TOKEN=abc")
    (root / "notes.txt").write_text("private")
    srv = R.make_server(root, "127.0.0.1", 0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def get(port, path, host=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.putrequest("GET", path, skip_host=True)
    c.putheader("Host", host or f"127.0.0.1:{port}")
    c.endheaders()
    r = c.getresponse()
    body = r.read()
    c.close()
    return r.status, body


def test_server_serves_only_allowlisted_artifacts(server):
    for ok in ("/shell/index.html", "/blobs/a.json", "/runtime.json", "/index.json"):
        assert get(server, ok)[0] == 200, ok
    for denied in ("/config.json", "/.env", "/notes.txt", "/shell/../config.json", "/%2e%2e/config.json",
                   "/blobs/../.env", "/snapshots/../config.json"):
        status, body = get(server, denied)
        assert status in (403, 404), denied
        assert b"secret" not in body and b"TOKEN" not in body


def test_server_rejects_foreign_host_header(server):
    assert get(server, "/shell/index.html", host="evil.example.com")[0] == 403
    assert get(server, "/shell/index.html", host="localhost:1")[0] == 200


# ---- 1. the viewer only loads same-origin models and validates ids before building HTML --------------------

def test_viewer_restricts_model_url_and_validates_ids():
    tpl = (REPO / "skills" / "mermaid-nesting-dolls" / "assets" / "template.html").read_text(encoding="utf-8")
    assert "mu.origin!==location.origin" in tpl          # same-origin only
    assert 'credentials:"omit"' in tpl                   # no ambient credentials on the model fetch
    assert "unsafe node id" in tpl and "unknown coverage status" in tpl
    assert "^https?:" in tpl or "https?:\\/\\/" in tpl   # repoUrl scheme restriction


def test_viewer_validation_rejects_hostile_ids_when_executed():
    """Run the real validation block under node with a stub DOM: a hostile id must call fail() and throw."""
    tpl = (REPO / "skills" / "mermaid-nesting-dolls" / "assets" / "template.html").read_text(encoding="utf-8")
    start = tpl.index("(function(){\n  var ID=")
    end = tpl.index("})();", start) + len("})();")
    block = tpl[start:end]
    js = f"""
var STATUS={{built:1}};var META={{repoUrl:"javascript:alert(1)"}};var msgs=[];
function fail(m){{msgs.push(m)}}
function run(N,ROOT){{ {block} }}
var res=[];
for (const [N,ROOT] of [
  [{{a:{{}}}}, "a"],
  [{{'a"><img src=x onerror=alert(1)>':{{}}}}, 'a"><img src=x onerror=alert(1)>'],
  [{{a:{{children:['b" onclick="x']}}}}, "a"],
  [{{a:{{coverage:{{status:'evil'}}}}}}, "a"],
]) {{ try {{ run(N,ROOT); res.push("ok") }} catch(e) {{ res.push("threw") }} }}
console.log(JSON.stringify({{res,msgs,repoUrl:META.repoUrl}}));
"""
    out = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout
    data = json.loads(out)
    assert data["res"] == ["ok", "threw", "threw", "threw"]
    assert data["repoUrl"] == ""
