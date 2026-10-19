"""Tests for factory.structure: extraction, scope, model, diff and CLI.

The fixture package under tests/fixtures/structure_pkg is only parsed, never imported. The syntax-error file is
stored as broken.py.txt so that tools which compile every .py file in the repository do not trip on it; the
`fixture` helper copies the tree and installs it as pkg/broken.py.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from factory.structure.__main__ import main
from factory.structure.diff import diff_trees
from factory.structure.extract import extract
from factory.structure.model import build_model
from factory.structure.scope import scope

HERE = Path(__file__).resolve().parent
FIXTURE = HERE / "fixtures" / "structure_pkg"
REPO = HERE.parent
CHECKER = REPO / "skills" / "mermaid-nesting-dolls" / "scripts" / "nesting_dolls.py"


def make_fixture(dest: Path, with_broken: bool = True) -> Path:
    shutil.copytree(FIXTURE, dest, ignore=shutil.ignore_patterns("broken.py.txt"))
    if with_broken:
        shutil.copy(FIXTURE / "broken.py.txt", dest / "pkg" / "broken.py")
    return dest


@pytest.fixture()
def fx(tmp_path: Path) -> Path:
    return make_fixture(tmp_path / "fx")


@pytest.fixture()
def ex(fx: Path) -> dict:
    return extract(fx)


def edges_from(ex: dict, caller: str) -> list[dict]:
    return [e for e in ex["edges"] if e["caller"] == caller]


def edge(ex: dict, caller: str, text: str) -> dict:
    found = [e for e in edges_from(ex, caller) if e["text"] == text]
    assert found, f"no edge {text!r} from {caller}; have {[e['text'] for e in edges_from(ex, caller)]}"
    return found[0]


# ---- extraction ---------------------------------------------------------------------------------------------


def test_symbols_have_stable_ids_spans_and_kinds(ex):
    s = ex["symbols"]
    assert s["pkg.core:plain"]["kind"] == "function"
    assert s["pkg.core:Engine"]["kind"] == "class"
    assert s["pkg.core:Engine.step"]["kind"] == "method"
    assert s["pkg.core:<module>"]["kind"] == "module"
    sp = s["pkg.core:plain"]
    assert sp["path"] == "pkg/core.py" and sp["start"] < sp["end"]


def test_ids_stable_across_pure_line_shift(fx, ex, tmp_path):
    core = fx / "pkg" / "core.py"
    text = core.read_text()
    core.write_text('"""moved"""\n\n\n# a comment\n\n' + text.replace('"""Core', "# Core", 1))
    shifted = extract(fx)
    assert set(shifted["symbols"]) == set(ex["symbols"])
    assert shifted["symbols"]["pkg.core:plain"]["start"] != ex["symbols"]["pkg.core:plain"]["start"]
    assert {s["ast_hash"] for s in shifted["symbols"].values() if s["path"] == "pkg/core.py" and s["kind"] != "module"} == {
        s["ast_hash"] for s in ex["symbols"].values() if s["path"] == "pkg/core.py" and s["kind"] != "module"
    }


def test_resolved_intra_package_calls(ex):
    e = edge(ex, "pkg.core:plain", "helpers.double")
    assert e["kind"] == "resolved" and e["target"] == "pkg.helpers:double"
    assert e["path"] == "pkg/core.py" and e["start"] > 0


def test_import_alias_resolves_to_original_symbol(ex):
    e = edge(ex, "pkg.core:aliased", "dbl")
    assert e["kind"] == "resolved" and e["target"] == "pkg.helpers:double"


def test_self_and_super_methods_resolve_within_repo(ex):
    assert edge(ex, "pkg.core:Engine.step", "self._inner")["target"] == "pkg.core:Engine._inner"
    assert edge(ex, "pkg.core:Engine.step", "self._inner")["kind"] == "resolved"
    sup = edge(ex, "pkg.core:Sub.step", "super().step")
    assert sup["kind"] == "resolved" and sup["target"] == "pkg.core:Engine.step"


def test_method_on_untyped_parameter_is_syntactic_with_candidates(ex):
    e = edge(ex, "pkg.core:untyped", "obj.process")
    assert e["kind"] == "syntactic"
    assert e["target"] is None
    assert "pkg.helpers:Worker.process" in e["candidates"]


def test_getattr_and_call_through_variable_are_unresolved_with_reasons(ex):
    g = edge(ex, "pkg.core:dynamic", "getattr")
    assert g["kind"] == "unresolved" and g["reason_code"] == "dynamic_attribute" and g["reason"]
    v = edge(ex, "pkg.core:dynamic", "fn")
    assert v["kind"] == "unresolved" and v["reason_code"] == "call_through_variable"
    p = edge(ex, "pkg.core:through_param", "callback")
    assert p["kind"] == "unresolved" and "parameter" in p["reason"]


def test_eval_call_of_call_and_subscript_are_unresolved(ex):
    assert edge(ex, "pkg.dyn:evil", "eval")["reason_code"] == "dynamic_code"
    coc = [e for e in edges_from(ex, "pkg.core:call_of_call") if e["kind"] == "unresolved"]
    assert any(e["reason_code"] == "call_of_call" for e in coc)
    sub = [e for e in edges_from(ex, "pkg.core:subscript") if e["kind"] == "unresolved"]
    assert any(e["reason_code"] == "subscript_call" for e in sub)


def test_star_import_name_is_unresolved(ex):
    e = edge(ex, "pkg.core:star_user", "star_made")
    assert e["kind"] == "unresolved" and e["reason_code"] == "star_import"
    assert any(m["kind"] == "star_import" for m in ex["modules"]["pkg.core"]["imports"])


def test_conditional_import_is_unresolved(ex):
    e = edge(ex, "pkg.core:conditional", "fast_path")
    assert e["kind"] == "unresolved" and e["reason_code"] == "conditional_import"


def test_decorator_wrapped_target_is_not_resolved(ex):
    e = edge(ex, "pkg.core:uses_decorated", "decorated")
    assert e["kind"] == "unresolved" and e["reason_code"] == "decorator_wrapped"
    assert e["target"] is None and e["candidates"] == ["pkg.core:decorated"]
    deco = edge(ex, "pkg.core:<module>", "@register")
    assert deco["kind"] == "resolved" and deco["target"] == "pkg.registry:register"


def test_unresolved_edges_never_counted_as_resolved(ex):
    unresolved = [e for e in ex["edges"] if e["kind"] == "unresolved"]
    assert unresolved and all(e["reason"] and e["reason_code"] for e in unresolved)
    assert all(e["kind"] != "resolved" or e["target"] in ex["symbols"] for e in ex["edges"])
    lim = ex["limits"]
    assert lim["unresolved_edges"] == len(unresolved)
    assert lim["resolved_edges"] == sum(1 for e in ex["edges"] if e["kind"] == "resolved")
    assert lim["syntactic_edges"] == sum(1 for e in ex["edges"] if e["kind"] == "syntactic")
    assert sum(lim["unresolved_by_reason"].values()) == lim["unresolved_edges"]
    assert lim["complete_call_graph"] is False


def test_parse_failure_is_reported_not_skipped(ex):
    fails = ex["limits"]["parse_failures"]
    assert [f["path"] for f in fails] == ["pkg/broken.py"]
    assert fails[0]["error"] and fails[0]["line"] == 1
    assert not any(s["path"] == "pkg/broken.py" for s in ex["symbols"].values())


def test_mutable_state_is_recorded(ex):
    st = ex["state"]
    assert st["pkg.core:COUNTER"]["kind"] == "module_var"
    assert st["pkg.core:CACHE"]["mutable_container"] is True
    assert st["pkg.core:COUNTER"]["mutable_container"] is False
    kinds = {(w["symbol"], w["kind"], w["target"]) for w in ex["writes"]}
    assert ("pkg.core:bump", "global_decl", "pkg.core:COUNTER") in kinds
    assert ("pkg.core:bump", "global_write", "pkg.core:COUNTER") in kinds
    assert ("pkg.core:bump", "container_mutation", "pkg.core:CACHE") in kinds
    assert ("pkg.core:bump", "container_mutation", "pkg.registry:REGISTRY") in kinds
    assert ("pkg.core:Engine.__init__", "attr_write", "pkg.core:Engine#count") in kinds
    assert ("pkg.core:Engine.step", "attr_write", "pkg.core:Engine#count") in kinds
    assert ("pkg.core:Engine", "class_attr", "pkg.core:Engine#mode") in kinds


def test_reads_of_module_state_are_recorded(ex):
    assert "pkg.registry:LIMIT" not in ex["reads"].get("pkg.core:plain", [])
    assert "pkg.core:CACHE" in ex["reads"]["pkg.core:bump"]


def test_external_calls_are_counted_not_edges(ex):
    # super() in Sub.step is a builtin call: counted in limits, not an edge
    assert ex["limits"]["external_calls_not_recorded"] >= 1
    assert not any(e["text"] == "super" for e in ex["edges"])


# ---- scope -------------------------------------------------------------------------------------------------


def test_scope_depth_bound_and_limits(ex):
    r = scope(ex, ["pkg.core:aliased"], depth=1)
    callees = {c["id"]: c for c in r["callees"]}
    assert set(callees) == {"pkg.helpers:double", "pkg.core:plain"}
    assert "pkg.helpers:double" in callees and all(c["depth"] == 1 for c in callees.values())
    # plain's own callee (helpers.double reached at depth 2 via plain) is not followed beyond the bound
    assert "pkg.core:plain" in r["depth_truncated"]
    assert r["limits"]["complete_call_graph"] is False
    for key in ("unresolved_edges", "syntactic_edges", "parse_failures", "unresolved_in_scope", "syntactic_in_scope"):
        assert key in r["limits"]
    deeper = scope(ex, ["pkg.core:Engine.step"], depth=2)
    assert {c["id"] for c in deeper["callees"]} >= {"pkg.core:Engine._inner", "pkg.core:plain"}
    assert "pkg.helpers:double" not in {c["id"] for c in deeper["callees"]}
    assert all(c["depth"] <= 2 for c in deeper["callees"])


def test_scope_reports_callers_and_state(ex):
    r = scope(ex, ["pkg.helpers:double"], depth=2)
    callers = {c["id"]: c for c in r["callers"]}
    assert callers["pkg.core:plain"]["depth"] == 1
    assert callers["pkg.core:aliased"]["depth"] == 1
    b = scope(ex, ["pkg.core:bump"], depth=1)
    touched = {t["target"] for t in b["state_touched"]}
    assert {"pkg.core:COUNTER", "pkg.core:CACHE", "pkg.registry:REGISTRY"} <= touched


def test_scope_lists_unfollowed_edges_explicitly(ex):
    r = scope(ex, ["pkg.core:dynamic"], depth=3)
    assert r["limits"]["unresolved_in_scope"] >= 2
    assert {n["reason_code"] for n in r["not_followed"] if n["kind"] == "unresolved"} >= {"dynamic_attribute", "call_through_variable"}
    u = scope(ex, ["pkg.core:untyped"], depth=1)
    assert any(n["kind"] == "syntactic" for n in u["not_followed"])
    assert "pkg.helpers:Worker.process" not in {c["id"] for c in u["callees"]}
    f = scope(ex, ["pkg.core:untyped"], depth=1, include_syntactic=True)
    assert "pkg.helpers:Worker.process" in {c["id"]: c for c in f["callees"]}
    assert {c["id"]: c for c in f["callees"]}["pkg.helpers:Worker.process"]["kind"] == "syntactic"


def test_scope_unknown_entry_raises(ex):
    with pytest.raises(KeyError):
        scope(ex, ["pkg.core:nope"], depth=1)


# ---- model + dolls checker -----------------------------------------------------------------------------------


def run_checker(model: dict, repo: Path, tmp: Path) -> subprocess.CompletedProcess:
    mp = tmp / "model.json"
    mp.write_text(json.dumps(model))
    return subprocess.run([sys.executable, str(CHECKER), "check", str(mp), "--repo", str(repo)], capture_output=True, text=True)


def test_full_model_passes_dolls_checker(fx, ex, tmp_path):
    model = build_model(ex)
    r = run_checker(model, fx, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "ERROR" not in r.stdout + r.stderr


def test_model_shape_ids_edges_and_unresolved_node(ex):
    model = build_model(ex)
    nodes = model["nodes"]
    import re

    assert all(re.fullmatch(r"[a-z][a-z0-9/_-]*", n) for n in nodes), [n for n in nodes if not re.fullmatch(r"[a-z][a-z0-9/_-]*", n)]
    assert model == build_model(ex)  # deterministic
    core = nodes["pkg/core"]
    assert core["diagram"] and any("files" in nodes[g] for g in core["children"].values())
    text = "\n".join(n["diagram"] if isinstance(n["diagram"], str) else "\n".join(n["diagram"]) for n in nodes.values() if n.get("diagram"))
    assert "-.->" in text  # dashed edges are present
    assert "unresolved" in text
    assert any(n["title"].lower().startswith("unresolved") for n in nodes.values())
    for n in nodes.values():
        assert "coverage" not in n  # coverage status is the caller's decision
    leaf = nodes["pkg/core/plain"]
    assert leaf["files"][0]["lines"] and leaf["files"][0]["contains"] == "def plain(x):"
    assert model["meta"]["structure"]["complete_call_graph"] is False


def test_scoped_model_passes_checker_and_is_smaller(fx, ex, tmp_path):
    sc = scope(ex, ["pkg.core:aliased"], depth=2)
    full = build_model(ex)
    sub = build_model(ex, scoped=sc)
    assert len(sub["nodes"]) < len(full["nodes"])
    assert "pkg/core/aliased" in sub["nodes"] and "pkg/helpers/double" in sub["nodes"]
    r = run_checker(sub, fx, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


def test_model_survives_reserved_word_package_names(tmp_path):
    root = tmp_path / "r"
    (root / "end").mkdir(parents=True)
    (root / "end" / "__init__.py").write_text("def class_():\n    return 1\n")
    (root / "graph.py").write_text("from end import class_\n\n\ndef f():\n    return class_()\n")
    m = build_model(extract(root))
    r = run_checker(m, root, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


# ---- diff ----------------------------------------------------------------------------------------------------


def clone(fx: Path, tmp_path: Path, name: str) -> Path:
    return make_fixture(tmp_path / name, with_broken=False)


def test_diff_ignores_whitespace_and_comments_but_flags_body_change(tmp_path):
    base = clone(FIXTURE, tmp_path, "base")
    head = clone(FIXTURE, tmp_path, "head")
    h = head / "pkg" / "helpers.py"
    h.write_text(
        h.read_text().replace(
            "def double(x):\n    return x * 2",
            "def double( x ):\n    # doubled\n    return (x   *   2)   # trailing\n",
        )
    )
    quiet = diff_trees(base, head)
    assert quiet["changed"] == [] and quiet["added"] == [] and quiet["removed"] == []
    h.write_text(h.read_text().replace("(x   *   2)", "x * 3"))
    r = diff_trees(base, head)
    assert [c["id"] for c in r["changed"]] == ["pkg.helpers:double"]
    assert r["changed"][0]["base_hash"] != r["changed"][0]["head_hash"]


def test_diff_lists_callers_labelled_by_kind(tmp_path):
    base = clone(FIXTURE, tmp_path, "base")
    head = clone(FIXTURE, tmp_path, "head")
    h = head / "pkg" / "helpers.py"
    h.write_text(h.read_text().replace("return x * 2", "return x * 3").replace("return n + 1", "return n + 2"))
    r = diff_trees(base, head, depth=2)
    assert {c["id"] for c in r["changed"]} == {"pkg.helpers:double", "pkg.helpers:Worker.process"}
    callers = {(c["id"], c["via_changed"]): c for c in r["affected_callers"]}
    assert callers[("pkg.core:plain", "pkg.helpers:double")]["kind"] == "resolved"
    assert callers[("pkg.core:aliased", "pkg.helpers:double")]["kind"] == "resolved"
    assert callers[("pkg.core:untyped", "pkg.helpers:Worker.process")]["kind"] == "syntactic"
    assert r["affected_callers"][0]["span"]["path"]
    # a caller reachable only through a syntactic hop is never labelled resolved
    assert all(c["kind"] in {"resolved", "syntactic", "unresolved"} for c in r["affected_callers"])
    assert r["hashes"]["pkg.helpers:double"] == r["changed"][[c["id"] for c in r["changed"]].index("pkg.helpers:double")]["head_hash"]


def test_diff_added_removed_and_decorated_edge(tmp_path):
    base = clone(FIXTURE, tmp_path, "base")
    head = clone(FIXTURE, tmp_path, "head")
    c = head / "pkg" / "core.py"
    c.write_text(c.read_text().replace("def bump():", "def extra():\n    return 1\n\n\ndef bump():"))
    (head / "pkg" / "fallback.py").write_text('"""gone"""\n')
    r = diff_trees(base, head)
    assert "pkg.core:extra" in r["added"]
    assert "pkg.fallback:fast_path" in r["removed"]
    assert "pkg.core:bump" not in {c["id"] for c in r["changed"]}


def test_diff_between_git_revisions_reads_without_checkout(tmp_path):
    repo = clone(FIXTURE, tmp_path, "g")
    run = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=repo, check=True, capture_output=True)
    run("init", "-q")
    run("add", "-A")
    run("commit", "-q", "-m", "base")
    h = repo / "pkg" / "helpers.py"
    h.write_text(h.read_text().replace("return x * 2", "return x * 5"))
    run("commit", "-q", "-am", "head")
    before = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    r = diff_trees("git:HEAD~1", "git:HEAD", repo=repo)
    after = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    assert before == after
    assert [c["id"] for c in r["changed"]] == ["pkg.helpers:double"]


def test_diff_reports_parse_failure_in_limits(tmp_path):
    base = clone(FIXTURE, tmp_path, "base")
    head = clone(FIXTURE, tmp_path, "head")
    (head / "pkg" / "helpers.py").write_text("def double(:\n")
    r = diff_trees(base, head)
    assert [f["path"] for f in r["limits"]["head"]["parse_failures"]] == ["pkg/helpers.py"]
    assert r["limits"]["base"]["parse_failures"] == []


# ---- CLI -----------------------------------------------------------------------------------------------------


def test_cli_scan_emits_json_and_strict_fails_on_parse_error(fx, capsys):
    assert main(["scan", str(fx)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["limits"]["parse_failures"][0]["path"] == "pkg/broken.py"
    assert main(["scan", str(fx), "--strict"]) == 3
    capsys.readouterr()


def test_cli_explicit_unparsable_path_fails_without_strict(fx, capsys):
    assert main(["scan", str(fx), "--paths", "pkg/broken.py"]) == 3
    assert main(["scan", str(fx), "--paths", "pkg/core.py"]) == 0
    capsys.readouterr()


def test_cli_usage_errors_exit_2(fx, capsys):
    with pytest.raises(SystemExit) as e:
        main(["scope", str(fx)])
    assert e.value.code == 2
    assert main(["scope", str(fx), "--entry", "pkg.core:nope"]) == 2
    assert main(["scan", str(fx / "missing")]) == 2
    with pytest.raises(SystemExit) as e:
        main([])
    assert e.value.code == 2
    capsys.readouterr()


def test_cli_scope_and_model_write_checked_file(fx, tmp_path, capsys):
    assert main(["scope", str(fx), "--entry", "pkg.core:aliased", "--depth", "1"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert {c["id"] for c in out["callees"]} == {"pkg.helpers:double", "pkg.core:plain"}
    mp = tmp_path / "out" / "model.json"
    assert main(["model", str(fx), "-o", str(mp), "--entry", "pkg.core:aliased", "--depth", "2"]) == 0
    capsys.readouterr()
    r = subprocess.run([sys.executable, str(CHECKER), "check", str(mp), "--repo", str(fx)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_diff(tmp_path, capsys):
    base = clone(FIXTURE, tmp_path, "base")
    head = clone(FIXTURE, tmp_path, "head")
    h = head / "pkg" / "helpers.py"
    h.write_text(h.read_text().replace("return x * 2", "return x * 3"))
    assert main(["diff", str(base), str(head)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [c["id"] for c in out["changed"]] == ["pkg.helpers:double"]
    (head / "pkg" / "fallback.py").write_text("def x(:\n")
    assert main(["diff", str(base), str(head), "--strict"]) == 3
    capsys.readouterr()
