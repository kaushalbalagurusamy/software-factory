"""SFN-09 HTTP and dashboard acceptance: D-3 (HTTP half), D-4, D-7, D-9, D-10, D-11, D-12."""
from __future__ import annotations

import json
import re

import pytest

from .conftest import (SKILL, STALE, answer, api_state, api_stop, apply_, ask_ok, out, post_release, record,
                       state_of, to_applied, walk)


def body_of(r):
    try:
        return json.loads(r[2].decode())
    except ValueError:
        return {}


def msg(r):
    return r[2].decode("utf-8", "replace")


@pytest.fixture
def world(inited, serve):
    inited.write("docs/adr.md", "v1\n")
    ask_ok(inited, "pick", ["Alpha", "Beta"], artifacts=["docs/adr.md"])
    srv = serve(inited)
    srv.rig = inited
    srv.h = api_stop(srv, "pick")["proposal_hash"]
    return srv


def good(srv, **over):
    b = {"name": "pick", "note": "n", "answer": "Alpha", "proposal_hash": srv.h}
    b.update(over)
    return b


# ------------------------------------------------------------------ state exposure (D-7)
def test_D7_api_state_exposes_the_decision_fields(world):
    s = api_stop(world, "pick")
    for k in ("id", "state", "options", "proposal_hash", "answer", "answered_at", "recorded_where", "recorded_at",
              "applied_evidence", "applied_at"):
        assert k in s, k
    assert s["state"] == "asked" and s["options"] == ["Alpha", "Beta"] and s["id"] == "pick"
    assert re.fullmatch(r"[0-9a-f]{64}", s["proposal_hash"])


def test_D7_api_state_matches_cli_status_json(world):
    _, data = world.rig.hitl()
    cli = next(d for d in walk(data) if d.get("name") == "pick")
    http = api_stop(world, "pick")
    for k in ("state", "options", "proposal_hash", "answer", "id"):
        assert cli[k] == http[k], k


# ------------------------------------------------------------------ D-3/D-4 release over HTTP
def test_D4_valid_answer_with_hash_releases(world):
    r = post_release(world, good(world, answer="Beta"))
    assert r[0] == 200, msg(r)
    s = api_stop(world, "pick")
    assert s["state"] == "answered" and s["answer"] == "Beta" and s["proposal_hash"] == world.h
    last = json.loads(world.rig.stop_lines()[-1])
    assert last.get("answer") == "Beta" and last.get("proposal_hash") == world.h
    assert world.rig.run("hitl", "status").returncode == 0


def test_D4_missing_proposal_hash_is_400_and_releases_nothing(world):
    before = world.rig.stop_lines()
    r = post_release(world, {"name": "pick", "note": "n", "answer": "Alpha"})
    assert r[0] == 400, msg(r)
    assert world.rig.stop_lines() == before and state_of(world.rig, "pick") == "asked"


@pytest.mark.parametrize("hval", [None, "", 5])
def test_D4_null_empty_or_non_string_hash_is_a_client_error(world, hval):
    before = world.rig.stop_lines()
    r = post_release(world, good(world, proposal_hash=hval))
    assert 400 <= r[0] < 500
    assert world.rig.stop_lines() == before


def test_D3_stale_supplied_hash_is_409_and_releases_nothing(world):
    before = world.rig.stop_lines()
    r = post_release(world, good(world, proposal_hash=STALE))
    assert r[0] == 409, msg(r)
    assert "stale" in msg(r).lower()
    assert world.rig.stop_lines() == before and state_of(world.rig, "pick") == "asked"


def test_D3_artifact_drift_over_http_is_409_with_the_server_message(world):
    world.rig.write("docs/adr.md", "v2 edited after asking\n")
    before = world.rig.stop_lines()
    r = post_release(world, good(world))  # hash is the stored one, so only the drift check can refuse
    assert r[0] == 409, msg(r)
    assert "proposal changed since it was asked; ask again" in msg(r)
    assert world.rig.stop_lines() == before
    s = api_stop(world, "pick")
    assert s["state"] == "asked" and s["answer"] is None
    assert world.rig.run("hitl", "status").returncode == 3


def test_D3_drift_then_revert_allows_release(world):
    world.rig.write("docs/adr.md", "v2\n")
    assert post_release(world, good(world))[0] == 409
    world.rig.write("docs/adr.md", "v1\n")
    assert post_release(world, good(world))[0] == 200


@pytest.mark.parametrize("ans", ["Gamma", "alpha", "", None, 7, ["Alpha"]])
def test_D3_answer_not_an_option_is_400(world, ans):
    before = world.rig.stop_lines()
    r = post_release(world, good(world, answer=ans))
    assert r[0] == 400, msg(r)
    assert world.rig.stop_lines() == before and state_of(world.rig, "pick") == "asked"


def test_D3_missing_answer_key_for_a_stop_with_options_is_400(world):
    r = post_release(world, {"name": "pick", "note": "n", "proposal_hash": world.h})
    assert r[0] == 400
    assert state_of(world.rig, "pick") == "asked"


def test_D4_token_is_still_required_even_with_a_perfect_body(world):
    before = world.rig.stop_lines()
    for tok in (None, "", "x" * len(world.token), world.token[:-1]):
        assert post_release(world, good(world), token=tok)[0] == 403
    assert world.rig.stop_lines() == before


def test_D4_foreign_host_still_403_with_token_and_perfect_body(world):
    h = {"Content-Type": "application/json", "X-LSF-Token": world.token}
    r = world.req("POST", "/api/hitl/release", json.dumps(good(world)), h, host="evil.example.com")
    assert r[0] == 403 and state_of(world.rig, "pick") == "asked"


def test_D4_oversized_body_is_still_refused(world):
    r = post_release(world, good(world, note="x" * (2 * 1024 * 1024)))
    assert 400 <= r[0] < 500 and state_of(world.rig, "pick") == "asked"


def test_D4_second_release_is_a_client_error_and_not_double_recorded(world):
    assert post_release(world, good(world))[0] == 200
    n = len(world.rig.stop_lines())
    assert 400 <= post_release(world, good(world, answer="Beta"))[0] < 500
    assert len(world.rig.stop_lines()) == n and api_stop(world, "pick")["answer"] == "Alpha"


def test_D4_stop_without_options_accepts_a_hashless_body(inited, serve):
    inited.phase("start", "0-intake", 0)
    inited.phase("end", "0-intake", 5)
    srv = serve(inited)
    assert re.fullmatch(r"[0-9a-f]{64}", api_stop(srv, "0-intake-review")["proposal_hash"])
    r = post_release(srv, {"name": "0-intake-review", "note": ""})
    assert r[0] == 200, msg(r)
    assert state_of(inited, "0-intake-review") == "answered"


def test_D4_optionless_stop_with_a_wrong_hash_is_still_409(inited, serve):
    ask_ok(inited, "plain", ())
    srv = serve(inited)
    before = inited.stop_lines()
    assert post_release(srv, {"name": "plain", "note": "", "proposal_hash": STALE})[0] == 409
    assert inited.stop_lines() == before


def test_D4_optionless_stop_hashless_body_still_hits_the_drift_check(inited, serve):
    inited.write("docs/adr.md", "v1\n")
    ask_ok(inited, "plain", (), artifacts=["docs/adr.md"])
    srv = serve(inited)
    inited.write("docs/adr.md", "v2\n")
    before = inited.stop_lines()
    r = post_release(srv, {"name": "plain", "note": ""})
    assert r[0] == 409 and "proposal changed" in msg(r)
    assert inited.stop_lines() == before


def test_D4_stop_without_options_releases_with_its_hash_and_no_answer(inited, serve):
    ask_ok(inited, "plain", ())
    srv = serve(inited)
    h = api_stop(srv, "plain")["proposal_hash"]
    r = post_release(srv, {"name": "plain", "note": "ok", "proposal_hash": h})
    assert r[0] == 200, msg(r)
    assert api_stop(srv, "plain")["state"] == "answered"


# ------------------------------------------------------------------ strict mode, recorded/applied after HTTP answer
def test_D4_D6_strict_mode_gates_only_release_not_recorded_or_applied(rig, serve):
    rig.init("--strict-hitl")
    rig.write("docs/rec.md", "x\n")
    ask_ok(rig, "d")
    assert answer(rig, "d", "Alpha").returncode != 0  # no TTY: refused
    assert state_of(rig, "d") == "asked"
    srv = serve(rig)
    h = api_stop(srv, "d")["proposal_hash"]
    assert post_release(srv, {"name": "d", "note": "", "answer": "Alpha", "proposal_hash": h})[0] == 200
    assert record(rig, "d", "docs/rec.md").returncode == 0
    assert apply_(rig, "d", "ok").returncode == 0
    assert state_of(rig, "d") == "applied"


# ------------------------------------------------------------------ D-9 dashboard static checks
@pytest.fixture
def page(inited, serve):
    srv = serve(inited)
    s, hdr, b = srv.get("/")
    assert s == 200
    return b.decode("utf-8", "replace")


def test_D9_banner_text_and_visibility_logic_ship(page):
    assert "decision(s) waiting for you" in page
    # banner is driven by the count of asked stops and is hidden otherwise
    assert re.search(r"asked", page) and re.search(r"hidden|display\s*[:=]\s*['\"]?none|\.hidden|style\.display", page)


def test_D9_submit_controls_ship(page):
    assert "Submit answer" in page
    assert re.search(r"type\s*=\s*['\"]?radio|type\s*[:=]\s*['\"]radio|['\"]radio['\"]", page)
    assert "Approve" in page, "stops without options keep the Approve button"
    assert "proposal_hash" in page, "submit must send the stop's proposal_hash"
    assert "/api/hitl/release" in page


def test_D9_four_step_chips_ship_in_order(page):
    pos = [page.find(w) for w in ("Asked", "Answered", "Recorded", "Applied")]
    assert all(p >= 0 for p in pos), pos
    assert re.search(r"Asked[\s\S]{0,400}Answered[\s\S]{0,400}Recorded[\s\S]{0,400}Applied", page)


def test_D9_not_applied_yet_wording_ships(page):
    assert "not applied yet" in page


def test_D9_a_conflict_response_message_is_shown(page):
    assert re.search(r"409", page), "dashboard must handle the 409 path and show the server message"


def test_D9_banner_is_outside_the_tab_panels(page):
    i = page.find("decision(s) waiting for you")
    assert i >= 0
    # it must be a top-level element, not text inside a single tab: no tab-panel opener may sit between <body> and it
    # without being closed. Cheap proxy: the banner string appears before the first tab-switch handler markup.
    first_tab = min([p for p in (page.find("data-tab"), page.find("role=\"tabpanel\""), page.find("tabpanel")) if p >= 0]
                    or [len(page)])
    assert i < first_tab or "banner" in page[max(0, i - 400):i + 200].lower()


def test_D9_dashboard_shows_the_word_unbound(page):
    assert "unbound" in page


def test_D9_dashboard_stays_self_contained(page):
    assert not re.search(r"<script[^>]+src=['\"]https?://", page)
    assert not re.search(r"<link[^>]+href=['\"]https?://", page)


def test_D9_dashboard_asset_is_the_one_served(page):
    asset = (SKILL / "assets" / "dashboard.html")
    assert asset.is_file()
    assert "Submit answer" in asset.read_text()


# ------------------------------------------------------------------ D-10 dashboard/API never says applied early
def test_D10_api_state_never_marks_answered_or_recorded_as_applied(inited, serve):
    inited.write("docs/rec.md", "x\n")
    ask_ok(inited, "d")
    srv = serve(inited)
    h = api_stop(srv, "d")["proposal_hash"]
    assert api_stop(srv, "d")["state"] == "asked"
    post_release(srv, {"name": "d", "note": "", "answer": "Alpha", "proposal_hash": h})
    for stage in ("answered", "recorded"):
        s = api_stop(srv, "d")
        assert s["state"] == stage
        assert s["applied_evidence"] is None and s["applied_at"] is None
        assert "applied" not in [str(v).lower() for k, v in s.items() if k == "state"]
        if stage == "answered":
            assert record(inited, "d", "docs/rec.md").returncode == 0
    assert apply_(inited, "d", "proof").returncode == 0
    s = api_stop(srv, "d")
    assert s["state"] == "applied" and s["applied_evidence"] == "proof"


def test_D10_http_release_output_does_not_say_applied(world):
    r = post_release(world, good(world))
    assert r[0] == 200 and "applied" not in msg(r).lower()


# ------------------------------------------------------------------ D-12 pending is live, never from a bundle
def test_D12_state_pending_follows_the_live_ledger_not_a_bundle(inited, serve):
    ask_ok(inited, "d")
    inited.run("bundle", "--json", timeout=30)
    srv = serve(inited)
    h = api_stop(srv, "d")["proposal_hash"]
    assert api_stop(srv, "d")["state"] == "asked"
    assert post_release(srv, {"name": "d", "note": "", "answer": "Alpha", "proposal_hash": h})[0] == 200
    inited.run("bundle", "--json", timeout=30)
    assert api_stop(srv, "d")["state"] == "answered"
    asked = [d for d in walk(api_state(srv)) if d.get("name") == "d" and d.get("state") == "asked"]
    assert not asked


# ------------------------------------------------------------------ D-11 docs
def mac_quick_start():
    text = (SKILL / "SKILL.md").read_text()
    m = re.search(r"## Mac quick start\n(.*?)(?=\n## )", text, re.S)
    assert m, "Mac quick start section missing"
    return m.group(1)


def test_D11_mac_quick_start_documents_the_lifecycle():
    sec = mac_quick_start().lower()
    for token in ("--option", "--answer", "hitl recorded", "hitl applied", "--evidence", "--where"):
        assert token in sec, token
    for state in ("asked", "answered", "recorded", "applied"):
        assert state in sec, state


def test_D11_lifecycle_is_documented_in_about_five_lines():
    sec = mac_quick_start()
    lines = [l for l in sec.splitlines() if re.search(r"hitl (request|recorded|applied)|--answer|decision", l, re.I)]
    assert 1 <= len(lines) <= 8, lines
