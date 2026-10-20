"""SFN-02 acceptance: doctor per-role skill resolution (A-06) and external skill pins (A-07)."""
from __future__ import annotations

import hashlib
import json
import shutil

from .conftest import EXTERNAL, lines


def out(r):
    return "\n".join(lines(r))


def line_with(r, status, *needles):
    return [l for l in lines(r) if l.startswith(status) and all(n in l for n in needles)]


# ---------------------------------------------------------------- A-06
def test_A06_clean_environment_every_role_skill_passes(ready):
    r = ready.doctor()
    assert r.returncode == 0, out(r)
    assert not [l for l in lines(r) if l.startswith("FAIL")], out(r)
    # one reported line per role/skill pair, e.g. the reviewer's minesweeper
    assert line_with(r, "PASS", "review", "minesweeper"), out(r)
    assert line_with(r, "PASS", "qa", "qa-supervisor"), out(r)
    assert line_with(r, "PASS", "design", "prd-writer"), out(r)


def test_A06_missing_skill_fails_naming_role_and_skill(stocked):
    shutil.rmtree(stocked.skills / "legacy-audit")  # carried by the audit role only
    r = stocked.doctor()
    assert r.returncode == 1
    assert line_with(r, "FAIL", "audit", "legacy-audit"), out(r)


def test_A06_plugin_skill_resolves_through_installed_plugins_json(stocked):
    shutil.rmtree(stocked.home / ".claude/plugins/cache/superpowers/skills/verification-before-completion")
    r = stocked.doctor()
    assert r.returncode == 1
    assert line_with(r, "FAIL", "superpowers:verification-before-completion"), out(r)
    assert not line_with(r, "FAIL", "superpowers:test-driven-development"), out(r)


def test_A06_builtin_claude_api_needs_no_install(stocked):
    assert not (stocked.skills / "claude-api").exists()
    r = stocked.doctor()
    assert not line_with(r, "FAIL", "claude-api"), out(r)
    assert line_with(r, "PASS", "implement", "claude-api"), out(r)


def test_A06_repo_skills_dir_also_resolves(stocked):
    # prd-writer exists only in the repo skills/, remove it from the user dir: still resolves
    (stocked.skills / "prd-writer").unlink()
    r = stocked.doctor()
    assert line_with(r, "PASS", "design", "prd-writer"), out(r)


def test_A06_non_sonnet_role_file_is_fail_unless_allowed(stocked):
    stocked.set_role("research", model="opus")
    stocked.stock_skills()
    r = stocked.doctor()
    assert r.returncode == 1
    assert line_with(r, "FAIL", "research", "opus"), out(r)
    r2 = stocked.doctor("--allow-model", "opus")
    assert not line_with(r2, "FAIL", "research", "opus"), out(r2)


def test_A06_non_sonnet_generated_agent_is_fail(stocked):
    p = stocked.proj / ".claude/agents/qa.md"
    p.write_text(p.read_text().replace("model: sonnet", "model: opus", 1))
    r = stocked.doctor()
    assert r.returncode == 1 and line_with(r, "FAIL", "qa"), out(r)


def test_A06_doctor_json_carries_role_skill_checks(stocked):
    r = stocked.doctor("--json")
    data = json.loads(r.stdout)
    names = [c["name"] + " " + c["detail"] for c in data["checks"]]
    assert any("review" in n and "minesweeper" in n for n in names)
    assert data["ok"] is True


# ---------------------------------------------------------------- A-07
def digest(d):
    return hashlib.sha256((d / "SKILL.md").read_bytes()).hexdigest()


def test_A07_pin_external_without_yes_exits_2_and_writes_nothing(rig):
    rig.stock_skills()
    before = rig.pins.read_bytes() if rig.pins.exists() else None
    r = rig.pin()
    assert r.returncode == 2 and "invalid choice" not in r.stderr  # the command exists; --yes is what is missing
    assert "--yes" in r.stdout + r.stderr
    assert (rig.pins.read_bytes() if rig.pins.exists() else None) == before


def test_A07_pin_external_yes_pins_all_ten_with_skill_md_sha256(rig):
    rig.stock_skills()
    r = rig.pin("--yes")
    assert r.returncode == 0, out(r)
    text = rig.pins.read_text()
    json.loads(text)
    for name in EXTERNAL:
        assert name in text, name
        assert digest(rig.skills / name) in text, name


def test_A07_hash_is_of_skill_md_bytes_only(rig):
    rig.stock_skills()
    (rig.skills / "good-night" / "notes.md").write_text("one")
    rig.pin("--yes")
    first = rig.pins.read_text()
    (rig.skills / "good-night" / "notes.md").write_text("two, other file changed")
    rig.pin("--yes")
    assert rig.pins.read_text() == first
    (rig.skills / "good-night" / "SKILL.md").write_bytes(b"different bytes\n")
    rig.pin("--yes")
    assert digest(rig.skills / "good-night") in rig.pins.read_text()
    assert rig.pins.read_text() != first


def test_A07_pin_external_prints_the_diff(rig):
    rig.stock_skills()
    rig.pin("--yes")
    (rig.skills / "minesweeper" / "SKILL.md").write_text("changed\n")
    r = rig.pin("--yes")
    assert r.returncode == 0
    o = out(r)
    assert "minesweeper" in o and digest(rig.skills / "minesweeper") in o


def test_A07_doctor_unchanged_pins_pass(ready):
    r = ready.doctor()
    assert not line_with(r, "FAIL", "good-night") and not line_with(r, "WARN"), out(r)
    assert line_with(r, "PASS", "good-night"), out(r)


def test_A07_changed_external_skill_warns_not_passes_and_exit_stays_0(ready):
    (ready.skills / "good-night" / "SKILL.md").write_text("---\nname: good-night\ndescription: x\n---\nnew\n")
    r = ready.doctor()
    assert line_with(r, "WARN", "good-night", "changed since pinned"), out(r)
    assert not line_with(r, "PASS", "good-night"), out(r)
    assert r.returncode == 0, out(r)


def test_A07_missing_external_skill_fails(ready):
    shutil.rmtree(ready.skills / "good-night")  # no role names it, so only the pin check can notice
    r = ready.doctor()
    assert r.returncode == 1
    assert line_with(r, "FAIL", "good-night"), out(r)


def test_A07_repo_ships_pins_for_exactly_the_ten_external_skills():
    from .conftest import REPO
    text = (REPO / "docs/external-skills.json").read_text()
    json.loads(text)
    for name in EXTERNAL:
        assert name in text, name
    assert len([h for h in text.replace('"', " ").split() if len(h) == 64 and all(c in "0123456789abcdef" for c in h)]) == 10


def test_A07_pin_external_requires_accept_changed_for_changed_skills(stocked):
    """Review finding: --yes alone must not launder a skill whose hash differs from its existing pin."""
    before = stocked.pins.read_bytes()
    p = stocked.pin("--yes", accept_changed=False)
    assert p.returncode == 2, p.stdout + p.stderr
    assert "changed since pinned" in (p.stdout + p.stderr)
    assert stocked.pins.read_bytes() == before, "nothing may be written without --accept-changed"
