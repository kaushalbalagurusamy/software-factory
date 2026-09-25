"""TB-11: Ticket ledger and its hooks (R-17).

Expectations come only from docs/prds/TB-11-ledger.md and docs/contracts/graph-and-ledger.md / hook-io.md.
The exact byte layout hashed by the chain is not published, so no case recomputes a chain value; tamper cases only
require that verify() reports a problem (see coverage/ambiguities-C.md).
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from evals.agents import lib

R = ["R-17"]
SECTIONS = ["Spec", "Research", "Architecture", "Evals", "Implementation", "Review", "Test Results", "Deploy Log",
            "Audit Trail"]
OWNERS = {  # contract: section ownership
    "research": {"Research"},
    "design": {"Spec", "Architecture"},
    "test": {"Evals", "Test Results", "Deploy Log"},
    "implement": {"Implementation"},
    "review": {"Review"},
    "orchestrator": {"Audit Trail", "Deploy Log"},
    "audit": set(),
}
T0 = datetime(2026, 9, 24, 12, 0, 0, tzinfo=timezone.utc)
CHAIN_RE = re.compile(r"^<!-- chain: ([0-9a-fA-F]{64}) -->\s*$", re.M)


def case(cid: str, tier: str = "diagnostic", reqs=None):
    return pytest.mark.case(cid, tier=tier, tb="11", reqs=reqs or R)


def L():
    return lib.need("factory.ledger", "create_ledger", "append", "verify", "load_summary", "LedgerError")


def heading_pos(text: str, name: str) -> int:
    m = re.search(rf"^#{{1,6}}\s+{re.escape(name)}\s*$", text, re.M)
    assert m, f"section heading {name!r} not found"
    return m.start()


def new_ledger(tmp_path: Path, name: str = "T-1") -> Path:
    led = L()
    p = tmp_path / "ledger" / f"{name}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    led.create_ledger(p, name, "Fixture ticket")
    return p


def fill(tmp_path: Path) -> Path:
    """Ledger with two Implementation entries (ALPHA, BRAVO) plus entries in Research and Review."""
    led = L()
    p = new_ledger(tmp_path)
    led.append(p, "Research", "research", "CHARLIE research note", T0)
    led.append(p, "Implementation", "implement", "ALPHA implementation note", T0 + timedelta(minutes=1))
    led.append(p, "Implementation", "implement", "BRAVO implementation note", T0 + timedelta(minutes=2))
    led.append(p, "Review", "review", "DELTA review note", T0 + timedelta(minutes=3))
    return p


def block(text: str, token: str) -> str:
    """The entry block containing `token`: from its `### ` header line through its chain line."""
    lines = text.splitlines(keepends=True)
    i = next(n for n, ln in enumerate(lines) if token in ln)
    h = max(n for n in range(i + 1) if lines[n].startswith("### "))
    c = next(n for n in range(i, len(lines)) if lines[n].startswith("<!-- chain:"))
    return "".join(lines[h:c + 1])


# ---------------------------------------------------------------- golden

@case("TB11-G-001", "golden")
def test_g001_create_writes_nine_sections_in_order(tmp_path):
    """PRD b1 + contract: `create_ledger` writes the fixed sections Spec, Research, Architecture, Evals,
    Implementation, Review, Test Results, Deploy Log, Audit Trail, in this order."""
    text = new_ledger(tmp_path).read_text()
    positions = [heading_pos(text, s) for s in SECTIONS]
    assert positions == sorted(positions)


@case("TB11-G-002", "golden")
def test_g002_create_over_existing_raises(tmp_path):
    """PRD b1: 'creating over an existing file raises `LedgerError`'."""
    led = L()
    p = new_ledger(tmp_path)
    with pytest.raises(led.LedgerError):
        led.create_ledger(p, "T-1", "again")


@case("TB11-G-003", "golden")
def test_g003_append_header_text_and_chain(tmp_path):
    """PRD b2 + contract: `append` adds a block with header `### <ISO 8601 UTC time> <role>`, the text, and a
    trailing `<!-- chain: <sha256 hex> -->` line, inside its section."""
    led = L()
    p = new_ledger(tmp_path)
    led.append(p, "Implementation", "implement", "ALPHA implementation note", T0)
    text = p.read_text()
    b = block(text, "ALPHA")
    assert re.match(r"^### 2026-09-24T12:00:00(\.0+)?(Z|\+00:00) implement\s*$", b.splitlines()[0])
    assert CHAIN_RE.search(b.splitlines()[-1])
    assert heading_pos(text, "Implementation") < text.index("ALPHA") < heading_pos(text, "Review")


@case("TB11-G-004", "golden")
def test_g004_wrong_role_raises(tmp_path):
    """PRD b3: `append` enforces section ownership and raises `LedgerError` for any other role (implement may not
    write Review)."""
    led = L()
    p = new_ledger(tmp_path)
    with pytest.raises(led.LedgerError):
        led.append(p, "Review", "implement", "self-approval", T0)


@case("TB11-G-005", "golden")
def test_g005_verify_intact_is_empty(tmp_path):
    """PRD b4: '`verify` returns an empty list for an intact ledger'."""
    assert L().verify(fill(tmp_path)) == []


@case("TB11-G-006", "golden")
def test_g006_verify_detects_edited_entry(tmp_path):
    """PRD b4 + contract: an edit to an earlier entry is detectable; `verify` names the section."""
    led = L()
    p = fill(tmp_path)
    p.write_text(p.read_text().replace("ALPHA implementation note", "ALPHA implementation n0te"))
    problems = led.verify(p)
    assert problems
    assert "Implementation" in " ".join(problems)


@case("TB11-G-007", "golden")
def test_g007_summary_has_headings_and_latest_entry(tmp_path):
    """PRD b5: `load_summary` returns the section headings and the latest entry of each section, at most 4,000
    characters."""
    s = L().load_summary(fill(tmp_path))
    assert len(s) <= 4000
    for name in SECTIONS:
        assert name in s, name
    assert "BRAVO implementation note" in s and "CHARLIE research note" in s and "DELTA review note" in s


def hook_env(root: Path, pl: dict):
    core = lib.need("factory.hooks.core", "parse_payload", "HookConfig")
    prof = lib.need("factory.agents.profile", "load_profile")
    cfg = core.HookConfig.from_profile(prof.load_profile(root / ".factory" / "profile.yaml"), root)
    return cfg, core.parse_payload(json.dumps(pl))


def ticket_project(tmp_path: Path, profile="base", ledger_dir=".factory/ledger", ticket: str | None = "T-7") -> Path:
    led = L()
    root = lib.make_project(tmp_path, profile)
    if ticket:
        (root / ".factory" / "current_ticket").write_text(ticket)
        p = root / ledger_dir / f"{ticket}.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        led.create_ledger(p, ticket, "Fixture ticket")
    return root


def stop_pl(root: Path, message: str, agent_type="research", agent_id="agent-77") -> dict:
    return lib.payload(root, event="SubagentStop", agent_type=agent_type, agent_id=agent_id,
                       agent_transcript_path=str(root.parent / "t.jsonl"), last_assistant_message=message,
                       stop_hook_active=False)


@case("TB11-G-008", "golden")
def test_g008_ledger_audit_allows_and_records(tmp_path):
    """PRD b6: `ledger_audit` `decide` always allows; `record` appends an Audit Trail entry naming the agent type
    and agent id to the ticket named by `.factory/current_ticket`."""
    hook = lib.need("factory.hooks.ledger_audit", "decide", "record")
    root = ticket_project(tmp_path)
    pl = stop_pl(root, "Research finished; three sources cited.")
    cfg, payload = hook_env(root, pl)
    assert hook.decide(payload, cfg).kind == "allow"
    hook.record(payload, cfg)
    text = (root / ".factory" / "ledger" / "T-7.md").read_text()
    trail = text[heading_pos(text, "Audit Trail"):]
    assert "research" in trail and "agent-77" in trail


@case("TB11-G-009", "golden")
def test_g009_session_start_without_ticket_single_line(tmp_path):
    """PRD b7: `session_start` `emit` prints ... 'a single line saying no ticket is active' when there is none."""
    hook = lib.need("factory.hooks.session_start", "emit")
    root = ticket_project(tmp_path, ticket=None)
    cfg, payload = hook_env(root, lib.payload(root, event="SessionStart"))
    out = hook.emit(payload, cfg).strip()
    assert out and "\n" not in out


# ---------------------------------------------------------------- diagnostic: create / append

@case("TB11-D-001")
def test_d001_each_section_heading_once(tmp_path):
    """PRD b1: exactly the nine fixed sections - each heading appears once."""
    text = new_ledger(tmp_path).read_text()
    for s in SECTIONS:
        assert len(re.findall(rf"^#{{1,6}}\s+{re.escape(s)}\s*$", text, re.M)) == 1, s


@case("TB11-D-002")
def test_d002_fresh_ledger_verifies(tmp_path):
    """PRD b4: a freshly created ledger with no entries is intact -> `verify` returns []."""
    assert L().verify(new_ledger(tmp_path)) == []


@case("TB11-D-003")
def test_d003_entry_lands_in_its_section(tmp_path):
    """Contract: 'Each entry appended to a section' - an Audit Trail entry sits after the Audit Trail heading and a
    Spec entry between Spec and Research."""
    led = L()
    p = new_ledger(tmp_path)
    led.append(p, "Spec", "design", "SPECTOKEN goals", T0)
    led.append(p, "Audit Trail", "orchestrator", "TRAILTOKEN run", T0 + timedelta(seconds=1))
    text = p.read_text()
    assert heading_pos(text, "Spec") < text.index("SPECTOKEN") < heading_pos(text, "Research")
    assert heading_pos(text, "Audit Trail") < text.index("TRAILTOKEN")


@case("TB11-D-004")
def test_d004_chain_is_sha256_hex(tmp_path):
    """Contract: the chain line is `<!-- chain: <sha256 hex> -->` (64 hex digits), one per entry."""
    led = L()
    p = new_ledger(tmp_path)
    for i in range(3):
        led.append(p, "Implementation", "implement", f"entry {i}", T0 + timedelta(minutes=i))
    assert len(CHAIN_RE.findall(p.read_text())) == 3


@case("TB11-D-005")
def test_d005_chain_is_deterministic(tmp_path):
    """PRD b2: the chain is a SHA-256 over the previous chain value and the entry text, so two ledgers given the
    same appends carry the same chain values."""
    led = L()
    chains = []
    for name in ("A", "B"):
        p = new_ledger(tmp_path / name, name="T-9")
        led.append(p, "Implementation", "implement", "same text", T0)
        led.append(p, "Implementation", "implement", "same second", T0 + timedelta(minutes=1))
        chains.append(CHAIN_RE.findall(p.read_text()))
    assert chains[0] == chains[1]


@case("TB11-D-006")
def test_d006_chain_covers_entry_text(tmp_path):
    """PRD b2: the hash covers the entry text - different text gives a different chain value."""
    led = L()
    vals = []
    for name, txt in (("A", "text one"), ("B", "text two")):
        p = new_ledger(tmp_path / name, name="T-9")
        led.append(p, "Implementation", "implement", txt, T0)
        vals.append(CHAIN_RE.findall(p.read_text())[0])
    assert vals[0] != vals[1]


@case("TB11-D-007")
def test_d007_chain_covers_previous_value(tmp_path):
    """PRD b2: the hash covers the previous chain value - the same second entry after a different first entry gets
    a different chain value."""
    led = L()
    vals = []
    for name, first in (("A", "first one"), ("B", "first two")):
        p = new_ledger(tmp_path / name, name="T-9")
        led.append(p, "Implementation", "implement", first, T0)
        led.append(p, "Implementation", "implement", "identical second", T0 + timedelta(minutes=1))
        vals.append(CHAIN_RE.findall(p.read_text())[1])
    assert vals[0] != vals[1]


@pytest.mark.parametrize("role", [
    pytest.param(r, marks=case(f"TB11-D-{i:03d}"), id=r) for i, r in enumerate(OWNERS, start=8)])
def test_d_ownership_matrix(tmp_path, role):
    """PRD b3 + contract section ownership: research->Research; design->Spec, Architecture; test->Evals, Test
    Results, Deploy Log; implement->Implementation; review->Review; orchestrator->Audit Trail, Deploy Log. Every
    owned section accepts the role; every other section raises `LedgerError` (audit owns none)."""
    led = L()
    p = new_ledger(tmp_path)
    for n, section in enumerate(SECTIONS):
        if section in OWNERS[role]:
            led.append(p, section, role, f"{role} writes {section}", T0 + timedelta(seconds=n))
        else:
            with pytest.raises(led.LedgerError):
                led.append(p, section, role, f"{role} intrudes {section}", T0 + timedelta(seconds=n))
    assert led.verify(p) == []


@case("TB11-D-015")
def test_d015_unknown_section_raises(tmp_path):
    """PRD b3: `append` raises `LedgerError` for an unknown section."""
    led = L()
    p = new_ledger(tmp_path)
    with pytest.raises(led.LedgerError):
        led.append(p, "Misc", "orchestrator", "x", T0)


@case("TB11-D-016")
def test_d016_unknown_role_raises(tmp_path):
    """PRD b3: any role other than the section's owner raises; an unknown role owns nothing."""
    led = L()
    p = new_ledger(tmp_path)
    with pytest.raises(led.LedgerError):
        led.append(p, "Implementation", "intern", "x", T0)


@case("TB11-D-017")
def test_d017_rejected_append_leaves_file_unchanged(tmp_path):
    """PRD b3 + append-only (R-17): a refused write must not alter the ledger."""
    led = L()
    p = fill(tmp_path)
    before = p.read_bytes()
    with pytest.raises(led.LedgerError):
        led.append(p, "Review", "test", "sneaky", T0 + timedelta(hours=1))
    assert p.read_bytes() == before


@case("TB11-D-018")
def test_d018_earlier_entries_preserved(tmp_path):
    """R-17 append-only: after later appends every earlier entry block is still present byte for byte."""
    led = L()
    p = new_ledger(tmp_path)
    led.append(p, "Implementation", "implement", "ALPHA implementation note", T0)
    first = block(p.read_text(), "ALPHA")
    led.append(p, "Implementation", "implement", "BRAVO implementation note", T0 + timedelta(minutes=1))
    led.append(p, "Research", "research", "CHARLIE", T0 + timedelta(minutes=2))
    assert first in p.read_text()


@case("TB11-D-019")
def test_d019_multiline_text_round_trips(tmp_path):
    """PRD b2 + b4: an entry whose text spans several lines is stored and the ledger still verifies."""
    led = L()
    p = new_ledger(tmp_path)
    led.append(p, "Test Results", "test", "suite: 42 passed\nfailures: none\nduration: 3s", T0)
    text = p.read_text()
    assert "suite: 42 passed" in text and "duration: 3s" in text
    assert led.verify(p) == []


# ---------------------------------------------------------------- diagnostic: tamper detection (b4)

@case("TB11-D-020")
def test_d020_edit_last_entry_detected(tmp_path):
    """PRD b4: an edited entry is detected - also when it is the most recent entry."""
    led = L()
    p = fill(tmp_path)
    p.write_text(p.read_text().replace("DELTA review note", "DELTA review nope"))
    problems = led.verify(p)
    assert problems and "Review" in " ".join(problems)


@case("TB11-D-021")
def test_d021_removed_entry_detected(tmp_path):
    """PRD b4: 'a removed entry' is named - deleting the ALPHA block (followed by BRAVO) is detected."""
    led = L()
    p = fill(tmp_path)
    text = p.read_text()
    p.write_text(text.replace(block(text, "ALPHA"), ""))
    problems = led.verify(p)
    assert problems and "Implementation" in " ".join(problems)


@case("TB11-D-022")
def test_d022_reordered_entries_detected(tmp_path):
    """PRD b4: 'a reordered entry' is detected - swapping ALPHA and BRAVO."""
    led = L()
    p = fill(tmp_path)
    text = p.read_text()
    a, b = block(text, "ALPHA"), block(text, "BRAVO")
    p.write_text(text.replace(a, "\x00").replace(b, a).replace("\x00", b))
    assert p.read_text() != text
    problems = led.verify(p)
    assert problems and "Implementation" in " ".join(problems)


@case("TB11-D-023")
def test_d023_missing_chain_line_detected(tmp_path):
    """PRD b4: 'a missing chain line' is detected and named."""
    led = L()
    p = fill(tmp_path)
    text = p.read_text()
    b = block(text, "ALPHA")
    chain_line = b.splitlines(keepends=True)[-1]
    p.write_text(text.replace(b, b[: -len(chain_line)]))
    problems = led.verify(p)
    assert problems and "Implementation" in " ".join(problems)


@case("TB11-D-024")
def test_d024_edit_in_earlier_section_named(tmp_path):
    """PRD b4: the problem names the section of the edited entry (Research), not only a later one."""
    led = L()
    p = fill(tmp_path)
    p.write_text(p.read_text().replace("CHARLIE research note", "CHARLIE research n0te"))
    problems = led.verify(p)
    assert problems and "Research" in " ".join(problems)


@case("TB11-D-025")
def test_d025_forged_chain_value_detected(tmp_path):
    """Contract: 'any edit to an earlier entry is detectable' - replacing a stored chain value with another valid-
    looking digest is detected."""
    led = L()
    p = fill(tmp_path)
    text = p.read_text()
    b = block(text, "ALPHA")
    forged = CHAIN_RE.sub("<!-- chain: " + "ab" * 32 + " -->", b)
    assert forged != b
    p.write_text(text.replace(b, forged))
    assert led.verify(p)


@case("TB11-D-026")
def test_d026_forged_entry_without_chain_detected(tmp_path):
    """PRD b4: a block inserted by hand without a chain line (a missing chain line) is detected."""
    led = L()
    p = fill(tmp_path)
    text = p.read_text()
    b = block(text, "BRAVO")
    p.write_text(text.replace(b, b + "\n### 2026-09-24T12:30:00Z implement\nforged approval\n"))
    assert led.verify(p)


# ---------------------------------------------------------------- diagnostic: load_summary (b5)

@case("TB11-D-027")
def test_d027_summary_omits_older_entries(tmp_path):
    """PRD b5: the summary carries 'the latest entry of each' section - BRAVO, not the older ALPHA."""
    s = L().load_summary(fill(tmp_path))
    assert "BRAVO implementation note" in s
    assert "ALPHA implementation note" not in s


@case("TB11-D-028")
def test_d028_summary_capped_at_4000(tmp_path):
    """PRD b5 boundary: 'at most 4,000 characters' even when latest entries are 3,000 characters each."""
    led = L()
    p = new_ledger(tmp_path)
    for n, (section, role) in enumerate([("Research", "research"), ("Implementation", "implement"),
                                         ("Review", "review"), ("Audit Trail", "orchestrator")]):
        led.append(p, section, role, (f"{section} " * 600)[:3000], T0 + timedelta(minutes=n))
    assert len(led.load_summary(p)) <= 4000


@case("TB11-D-029")
def test_d029_summary_deterministic(tmp_path):
    """PRD b5: 'deterministically' - two calls, and two identical ledgers, give identical summaries."""
    led = L()
    a = fill(tmp_path / "a")
    b = fill(tmp_path / "b")
    assert led.load_summary(a) == led.load_summary(a) == led.load_summary(b)


@case("TB11-D-030")
def test_d030_summary_of_empty_ledger_has_headings(tmp_path):
    """PRD b5 (empty boundary): a ledger with no entries summarises to its nine section headings."""
    s = L().load_summary(new_ledger(tmp_path))
    assert len(s) <= 4000
    for name in SECTIONS:
        assert name in s, name


@case("TB11-D-031")
def test_d031_summary_does_not_modify_ledger(tmp_path):
    """PRD b5: `load_summary` 'returns the text' - reading a summary leaves the ledger bytes unchanged."""
    led = L()
    p = fill(tmp_path)
    before = p.read_bytes()
    led.load_summary(p)
    assert p.read_bytes() == before


# ---------------------------------------------------------------- diagnostic: ledger_audit (b6)

def audit_record(tmp_path, message, **kw):
    hook = lib.need("factory.hooks.ledger_audit", "decide", "record")
    root = ticket_project(tmp_path, **{k: v for k, v in kw.items() if k in ("profile", "ledger_dir")})
    pl = stop_pl(root, message, **{k: v for k, v in kw.items() if k in ("agent_type", "agent_id")})
    cfg, payload = hook_env(root, pl)
    hook.record(payload, cfg)
    return root


@case("TB11-D-032")
def test_d032_record_keeps_first_200_characters(tmp_path):
    """PRD b6: the entry carries 'the first 200 characters of the last message' - the 200-character prefix is
    present and text beyond it is not."""
    head = ("a" * 195) + "BOUND"
    root = audit_record(tmp_path, head + "EXTRAOVERFLOW" * 5)
    text = (root / ".factory" / "ledger" / "T-7.md").read_text()
    assert head in text
    assert "EXTRAOVERFLOW" not in text


@case("TB11-D-033")
def test_d033_record_removes_secret_values(tmp_path):
    """PRD b6: the message excerpt has 'secret-shaped values removed'."""
    key = "ghp" + "_" + "Ab3Xy9" * 6
    root = audit_record(tmp_path, f"Configured the client with {key} and finished.")
    text = (root / ".factory" / "ledger" / "T-7.md").read_text()
    assert key not in text
    assert "Configured the client with" in text


@case("TB11-D-034")
def test_d034_record_without_current_ticket_does_nothing(tmp_path):
    """PRD b6: 'if that file is absent it does nothing' - no exception and no ledger file created."""
    hook = lib.need("factory.hooks.ledger_audit", "decide", "record")
    root = ticket_project(tmp_path, ticket=None)
    cfg, payload = hook_env(root, stop_pl(root, "done"))
    hook.record(payload, cfg)
    led_dir = root / ".factory" / "ledger"
    assert not led_dir.exists() or not any(led_dir.iterdir())


@case("TB11-D-035")
def test_d035_recorded_entry_keeps_chain_intact(tmp_path):
    """PRD b6 + b4: the Audit Trail entry is a proper ledger entry, so `verify` still returns []."""
    led = L()
    root = audit_record(tmp_path, "Review finished.")
    assert led.verify(root / ".factory" / "ledger" / "T-7.md") == []
    assert len(CHAIN_RE.findall((root / ".factory" / "ledger" / "T-7.md").read_text())) == 1


@case("TB11-D-036")
def test_d036_decide_always_allows(tmp_path):
    """PRD b6: `ledger_audit` 'decide always allows' - for every agent type and any message, including empty."""
    hook = lib.need("factory.hooks.ledger_audit", "decide", "record")
    root = ticket_project(tmp_path)
    for agent_type in ("research", "design", "audit", "implement", "test", "review", "orchestrator", "mystery"):
        for message in ("", "x" * 10000, "VERDICT: REJECT"):
            cfg, payload = hook_env(root, stop_pl(root, message, agent_type=agent_type))
            assert hook.decide(payload, cfg).kind == "allow"


@case("TB11-D-037")
def test_d037_ledger_audit_cli(tmp_path):
    """PRD b6 + hook-io: through the command line, `ledger_audit` exits 0 with empty stdout (allow) and its record
    appends the Audit Trail entry."""
    lib.need("factory.hooks.ledger_audit", "decide", "record")
    lib.need("factory.hooks.registry")
    root = ticket_project(tmp_path)
    proc = lib.run_cli("ledger_audit", stop_pl(root, "cli run finished", agent_id="agent-cli"), root)
    assert proc.returncode == 0 and proc.stdout.strip() == ""
    assert "agent-cli" in (root / ".factory" / "ledger" / "T-7.md").read_text()


@case("TB11-D-038")
def test_d038_record_uses_profile_ledger_dir(tmp_path):
    """Contract: the ledger lives at `<ledger_dir>/<ticket_id>.md`; with `paths.ledger_dir: records/ledger` in the
    profile, the Audit Trail entry lands there."""
    prof = lib.profile_dict("base")
    prof["paths"]["ledger_dir"] = "records/ledger"
    root = audit_record(tmp_path, "custom dir", profile=prof, ledger_dir="records/ledger", agent_id="agent-dir")
    assert "agent-dir" in (root / "records" / "ledger" / "T-7.md").read_text()


# ---------------------------------------------------------------- diagnostic: session_start (b7)

@case("TB11-D-039")
def test_d039_session_start_emits_summary(tmp_path):
    """PRD b7: `emit` prints `load_summary` of the current ticket's ledger."""
    led = L()
    hook = lib.need("factory.hooks.session_start", "emit")
    root = ticket_project(tmp_path)
    p = root / ".factory" / "ledger" / "T-7.md"
    led.append(p, "Implementation", "implement", "ECHO implementation note", T0)
    cfg, payload = hook_env(root, lib.payload(root, event="SessionStart"))
    assert hook.emit(payload, cfg).strip() == led.load_summary(p).strip()


@case("TB11-D-040")
def test_d040_session_start_cli_prints_summary(tmp_path):
    """PRD b7 + hook-io: through the command line SessionStart exits 0 and prints the summary on stdout."""
    led = L()
    lib.need("factory.hooks.session_start", "emit")
    lib.need("factory.hooks.registry")
    root = ticket_project(tmp_path)
    p = root / ".factory" / "ledger" / "T-7.md"
    led.append(p, "Review", "review", "FOXTROT review note", T0)
    proc = lib.run_cli("session_start", lib.payload(root, event="SessionStart"), root)
    assert proc.returncode == 0
    assert proc.stdout.strip() == led.load_summary(p).strip()


@case("TB11-D-041")
def test_d041_session_start_cli_no_ticket(tmp_path):
    """PRD b7: with no current ticket the command line prints a single line (exit 0)."""
    lib.need("factory.hooks.session_start", "emit")
    lib.need("factory.hooks.registry")
    root = ticket_project(tmp_path, ticket=None)
    proc = lib.run_cli("session_start", lib.payload(root, event="SessionStart"), root)
    assert proc.returncode == 0
    out = proc.stdout.strip()
    assert out and "\n" not in out
