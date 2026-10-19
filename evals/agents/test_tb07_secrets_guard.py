"""TB-07 secrets guard evals.

Sources: docs/prds/TB-07-secrets-guard.md (behaviours 1 to 7), R-12 and R-23 in docs/factory/requirements.md,
docs/contracts/profile.md (`secret_allow_patterns`), docs/contracts/hook-io.md (tool_input fields).

No key-shaped literal appears in this file (R-23 / METHODOLOGY section 6): every synthetic key is assembled at run
time from a prefix and a deterministic mixed-character body, so the fixtures are never real or scannable secrets.
"""
from __future__ import annotations

import os
import re

import pytest

from evals.agents import lib

TB = "07"
HOOK = "factory.hooks.secrets_guard"
REQS = ("R-12",)


def case(cid: str, *values, reqs=REQS):
    tier = "golden" if "-G-" in cid else "diagnostic"
    return pytest.param(*values, marks=pytest.mark.case(cid, tier=tier, tb=TB, reqs=list(reqs)), id=cid)


# ---------------------------------------------------------------- synthetic key material (built at run time)

ALNUM = "Q7m2Zr9Kp4Tn8Vb3Hd6Jc5Wf1Ls0GyRtUaDk"
UPPER = "Q7M2ZR9KP4TN8VB3HD6JC5WF1LS0GY"
HEX = "3f9a0c7e1b5d2468"
URLSAFE = ALNUM + "-_"


def mix(n: int, alphabet: str = ALNUM) -> str:
    return "".join(alphabet[(i * 7 + 3) % len(alphabet)] for i in range(n))


def j(*parts: str) -> str:
    return "".join(parts)


K = {
    "or": j("sk-", "or-v1-", mix(64, HEX)),
    "ant": j("sk-", "ant-", "api03-", mix(40, URLSAFE)),
    "sk": j("sk", "-", mix(48)),
    "ghp": j("gh", "p_", mix(36)),
    "gho": j("gh", "o_", mix(36)),
    "ghs": j("gh", "s_", mix(36)),
    "ghpat": j("github", "_pat_", mix(22), "_", mix(30)),
    "glpat": j("gl", "pat-", mix(20)),
    "akia": j("AK", "IA", mix(16, UPPER)),
    "xoxb": j("xo", "xb-", mix(24)),
    "xoxa": j("xo", "xa-", mix(24)),
    "xoxp": j("xo", "xp-", mix(24)),
    "xoxr": j("xo", "xr-", mix(24)),
    "xoxs": j("xo", "xs-", mix(24)),
    "aiza": j("AI", "za", mix(35, URLSAFE)),
}
PEM = {
    "rsa": j("-----BEGIN ", "RSA PRIVATE", " KEY-----"),
    "plain": j("-----BEGIN ", "PRIVATE", " KEY-----"),
    "openssh": j("-----BEGIN ", "OPENSSH PRIVATE", " KEY-----"),
    "ec": j("-----BEGIN ", "EC PRIVATE", " KEY-----"),
}
NEAR = {
    "or19": j("sk-", "or-v1-", mix(19, HEX)),
    "ant19": j("sk-", "ant-", mix(19)),
    "sk31": j("sk", "-", mix(31)),
    "ghp19": j("gh", "p_", mix(19)),
    "glpat19": j("gl", "pat-", mix(19)),
    "akia15": j("AK", "IA", mix(15, UPPER)),
    "xoxb9": j("xo", "xb-", mix(9)),
    "xoxz": j("xo", "xz-", mix(24)),
    "aiza34": j("AI", "za", mix(34, URLSAFE)),
}
V20 = mix(20)   # a quoted value of 20 characters, not a placeholder
V16 = mix(16)
V15 = mix(15)


def doc(line: str) -> str:
    """Wrap one line in a small file so the interesting value sits on line 2."""
    return f"# settings module\n{line}\nprint('ready')\n"


def _run(tmp_path, tool, tool_input, agent="implement", profile="base"):
    prof = profile if isinstance(profile, dict) else lib.profile_dict(profile)
    root = lib.make_project(tmp_path, prof, files={"src/app.py": "print('app')\n"})
    ti = dict(tool_input)
    if "file_path" in ti:
        ti["file_path"] = str(root / ti["file_path"])
    return lib.run_decide(HOOK, lib.payload(root, tool_name=tool, tool_input=ti, agent_type=agent), root)


def _w(content):
    return {"file_path": "src/config.py", "content": content}


def _check(d, expected, clause):
    assert d.kind == expected, clause
    if expected != "allow":
        assert d.reason


# ---------------------------------------------------------------- golden

@pytest.mark.parametrize("tool,tool_input,agent,profile,expected,clause", [
    case("TB07-G-001", "Write", _w(doc(f"TOKEN_VALUE = {K['ghp']}")), "implement", "base", "deny", "B2 ghp_ + >=20"),
    case("TB07-G-002", "Write", _w(doc(f"aws = '{K['akia']}'")), "implement", "base", "deny", "B2 AKIA + 16 uppercase alnum"),
    case("TB07-G-003", "Write", _w(PEM["rsa"] + "\n" + mix(64) + "\n"), "implement", "base", "deny", "B2 PEM private-key header"),
    case("TB07-G-004", "Write", _w(doc(f'api_key = "{V20}"')), "implement", "base", "deny", "B2 quoted value >=16 assigned to api_key"),
    case("TB07-G-005", "Bash", {"command": f"export ANTHROPIC_API_KEY={K['ant']}"}, "orchestrator", "base", "deny", "B1 Bash command inspected; B2 sk-ant-"),
    case("TB07-G-006", "Write", _w(doc('key = "$OPENROUTER_API_KEY"')), "implement", "base", "allow", "B3 references by variable name allowed"),
    # Superseded by [C-39] item 1 (was "allow", B4 placeholder word 'your'): only a whole-value placeholder is exempt.
    case("TB07-G-007", "Write", _w(doc('api_key = "your-api-key-goes-here"')), "implement", "base", "deny", "[C-39] item 1 supersedes B4: a placeholder word inside the value no longer exempts it"),
    case("TB07-G-008", "Write", _w(doc('api_key = "FIXTURE-KEY-12345678901"')), "implement", "alt", "allow", "B5 value matching profile.secret_allow_patterns (alt)"),
    case("TB07-G-010", "Edit", {"file_path": "src/app.py", "old_string": "a", "new_string": doc(f"k = {K['sk']}")}, "review", "base", "deny", "B1 Edit new_string, every role; B2 sk- + >=32"),
])
def test_golden(tmp_path, tool, tool_input, agent, profile, expected, clause):
    """TB-07 golden core: one clear clause of B1-B5 per case (see clause)."""
    _check(_run(tmp_path, tool, tool_input, agent, profile), expected, clause)


@pytest.mark.case("TB07-G-009", tier="golden", tb=TB, reqs=list(REQS))
def test_reason_names_line_not_value(tmp_path):
    """TB-07 B6: 'Deny reasons name the pattern kind and the line number, never the matched value.'"""
    content = f"line one\nline two\nclient = {K['ghp']}\nline four\n"
    d = _run(tmp_path, "Write", _w(content))
    assert d.kind == "deny"
    assert re.search(r"(?<!\d)3(?!\d)", d.reason), "line number 3 must be named"
    assert K["ghp"] not in d.reason
    assert K["ghp"][4:14] not in d.reason


# ---------------------------------------------------------------- behaviour 2: every key shape (deny)

SHAPES = [
    case("TB07-D-001", K["or"], "B2 sk-or-v1- + >=20 hex"),
    case("TB07-D-002", K["ant"], "B2 sk-ant- + >=20 URL-safe"),
    case("TB07-D-003", K["sk"], "B2 sk- + >=32 alphanumerics"),
    case("TB07-D-004", K["ghp"], "B2 ghp_"),
    case("TB07-D-005", K["gho"], "B2 gho_"),
    case("TB07-D-006", K["ghs"], "B2 ghs_"),
    case("TB07-D-007", K["ghpat"], "B2 github_pat_ + alnum/underscore"),
    case("TB07-D-008", K["glpat"], "B2 glpat- + >=20"),
    case("TB07-D-009", K["akia"], "B2 AKIA + 16 uppercase alnum"),
    case("TB07-D-010", K["xoxb"], "B2 xoxb-"),
    case("TB07-D-011", K["xoxa"], "B2 xoxa-"),
    case("TB07-D-012", K["xoxp"], "B2 xoxp-"),
    case("TB07-D-013", K["xoxr"], "B2 xoxr-"),
    case("TB07-D-014", K["xoxs"], "B2 xoxs-"),
    case("TB07-D-015", K["aiza"], "B2 AIza + 35 URL-safe"),
    case("TB07-D-016", PEM["rsa"], "B2 PEM RSA private key header"),
    case("TB07-D-017", PEM["plain"], "B2 PEM PRIVATE KEY header"),
    case("TB07-D-018", PEM["openssh"], "B2 PEM OPENSSH private key header"),
    case("TB07-D-019", PEM["ec"], "B2 PEM EC private key header"),
    case("TB07-D-020", j("sk-", "or-v1-", mix(20, HEX)), "B2 sk-or-v1- boundary: exactly 20 hex"),
    case("TB07-D-021", j("sk", "-", mix(32)), "B2 sk- boundary: exactly 32"),
    case("TB07-D-022", j("gh", "p_", mix(20)), "B2 ghp_ boundary: exactly 20"),
    case("TB07-D-023", j("xo", "xb-", mix(10)), "B2 xoxb- boundary: exactly 10"),
    case("TB07-D-024", j("gl", "pat-", mix(20)), "B2 glpat- boundary: exactly 20"),
    case("TB07-D-025", j("sk-", "ant-", mix(20)), "B2 sk-ant- boundary: exactly 20"),
]


@pytest.mark.parametrize("value,clause", SHAPES)
def test_key_shapes_denied_in_write(tmp_path, value, clause):
    """TB-07 B2: Write content containing a key-shaped value is denied."""
    _check(_run(tmp_path, "Write", _w(doc(f"blob {value} end"))), "deny", clause)


ASSIGN_DENY = [
    case("TB07-D-026", f'API_KEY = "{V20}"', "B2 name contains api_key, case-insensitive"),
    case("TB07-D-027", f"apikey = '{V20}'", "B2 apikey, single-quoted value"),
    case("TB07-D-028", f'client_secret = "{V20}"', "B2 name contains secret"),
    case("TB07-D-029", f'GITHUB_TOKEN="{V20}"', "B2 name contains token (shell style)"),
    case("TB07-D-030", f'db_password = "{V20}"', "B2 name contains password"),
    case("TB07-D-031", f'myToken = "{V20}"', "B2 case-insensitive token"),
    case("TB07-D-032", f'ApiKey = "{V20}"', "B2 case-insensitive apikey"),
    case("TB07-D-033", f'api_key = "{V16}"', "B2 boundary: exactly 16 characters"),
    case("TB07-D-034", f'SECRET = "{V20}"', "B2 uppercase SECRET"),
]


@pytest.mark.parametrize("line,clause", ASSIGN_DENY)
def test_assignments_denied(tmp_path, line, clause):
    """TB-07 B2: 'an assignment of a quoted value of at least 16 characters to a name containing api_key, apikey,
    secret, token or password (case-insensitive)'."""
    _check(_run(tmp_path, "Write", _w(doc(line))), "deny", clause)


# ---------------------------------------------------------------- near misses and references (allow)

ALLOW = [
    # too short / wrong shape
    case("TB07-D-035", doc(f"blob {NEAR['or19']} end"), "B2 sk-or-v1- needs >=20 hex"),
    case("TB07-D-036", doc(f"blob {NEAR['ant19']} end"), "B2 sk-ant- needs >=20"),
    case("TB07-D-037", doc(f"blob {NEAR['sk31']} end"), "B2 sk- needs >=32"),
    case("TB07-D-038", doc(f"blob {NEAR['ghp19']} end"), "B2 ghp_ needs >=20"),
    case("TB07-D-039", doc(f"blob {NEAR['glpat19']} end"), "B2 glpat- needs >=20"),
    case("TB07-D-040", doc(f"blob {NEAR['akia15']} end"), "B2 AKIA needs 16"),
    case("TB07-D-041", doc(f"blob {NEAR['xoxb9']} end"), "B2 xoxb- needs >=10"),
    case("TB07-D-042", doc(f"blob {NEAR['xoxz']} end"), "B2 only xox[baprs]-"),
    case("TB07-D-043", doc(f"blob {NEAR['aiza34']} end"), "B2 AIza needs 35"),
    case("TB07-D-044", j("-----BEGIN ", "PUBLIC", " KEY-----\n"), "B2 only PRIVATE KEY headers"),
    case("TB07-D-045", j("-----BEGIN ", "CERTIFICATE", "-----\n"), "B2 only PRIVATE KEY headers"),
    case("TB07-D-046", doc(f'api_key = "{V15}"'), "B2 quoted value must be >=16"),
    case("TB07-D-047", doc(f'username = "{V20}"'), "B2 name must contain a secret word"),
    case("TB07-D-048", doc(f"api_key = {V20}"), "B2 only a quoted value"),
    case("TB07-D-049", doc('password = ""'), "B2 empty value"),
    # references by variable name and bare mentions
    case("TB07-D-050", doc('api_key = os.environ["OPENROUTER_API_KEY"]'), "B3 os.environ[\"X\"] reference"),
    case("TB07-D-051", doc("const token = process.env.GITHUB_TOKEN"), "B3 process.env.X reference"),
    case("TB07-D-052", doc("url = f'https://x/?k=${GITHUB_TOKEN}'"), "B3 ${VAR} reference"),
    case("TB07-D-053", doc("Set OPENROUTER_API_KEY in the environment before running."), "B3 bare mention of a key name"),
    case("TB07-D-054", doc("Anthropic keys start with sk-ant- and GitHub tokens with ghp_ or github_pat_."), "B3 bare mention of a key shape"),
    case("TB07-D-055", doc('password = os.environ["DB_PASSWORD"]'), "B3 os.environ reference"),
    case("TB07-D-056", doc("AWS access key ids begin with AKIA."), "B3 bare mention of a shape without a value"),
    # placeholders
    case("TB07-D-057", doc('api_key = "xxxxxxxxxxxxxxxxxxxx"'), "B4 single repeated character / contains xxxx"),
    case("TB07-D-058", doc('api_key = "aaaaaaaaaaaaaaaaaaaa"'), "B4 single repeated character"),
    case("TB07-D-059", doc('token = "0000000000000000"'), "B4 single repeated character"),
    case("TB07-D-063", doc('api_key = "<insert-real-key-here>"'), "B4 contains < or >"),
]


@pytest.mark.parametrize("content,clause", ALLOW)
def test_allowed_content(tmp_path, content, clause):
    """TB-07 B2 near misses, B3 references and mentions, B4 placeholders: all allowed."""
    _check(_run(tmp_path, "Write", _w(content)), "allow", clause)


# Cases that expected "allow" under TB-07 behaviour 4 (a placeholder word anywhere in the value) and now expect "deny":
# [C-39] item 1: 'A matched secret is exempt only when the whole matched value (for a prefixed key, the whole body after
# the prefix; for an assignment, the whole assigned value) is itself a placeholder form ... A placeholder word elsewhere
# in the surrounding token or text no longer exempts a real key.' Same ids as before; only the expectation changed.
C39_SUPERSEDED = [
    case("TB07-D-060", doc('api_key = "example-key-1234567890"'), "[C-39] item 1 supersedes B4: 'example' inside the value is not a whole-value placeholder"),
    case("TB07-D-061", doc('secret = "placeholder-value-12345"'), "[C-39] item 1 supersedes B4: 'placeholder' inside the value"),
    case("TB07-D-062", doc('password = "changeme-changeme-123"'), "[C-39] item 1 supersedes B4: 'changeme' inside the value"),
    case("TB07-D-064", doc(f"blob {j('gh', 'p_', 'xxxx', mix(24))} end"), "[C-39] item 1 supersedes B4: 'xxxx' followed by a real body is not a repeated-character body"),
    case("TB07-D-066", doc('token = "your-token-goes-here-123"'), "[C-39] item 1 supersedes B4: 'your' inside the value"),
    case("TB07-D-067", doc(f"blob {j('sk-', 'ant-', 'your-key-', mix(20))} end"), "[C-39] item 1 supersedes B4: 'your-key-' prefix on a real body"),
]


@pytest.mark.parametrize("content,clause", C39_SUPERSEDED)
def test_old_placeholder_words_now_denied(tmp_path, content, clause):
    """[C-39] item 1 (supersedes TB-07 behaviour 4 and [A-07-3]): a placeholder word inside a real-looking value no
    longer exempts it, so these formerly allowed values are denied."""
    _check(_run(tmp_path, "Write", _w(content)), "deny", clause)


# ---------------------------------------------------------------- behaviour 5: profile allow patterns

@pytest.mark.parametrize("profile,content,expected,clause", [
    case("TB07-D-068", "base", doc('api_key = "FIXTURE-KEY-12345678901"'), "deny", "B5 without the allow pattern the assignment is a secret"),
    case("TB07-D-069", "alt", doc(f"blob {K['ghp']} end"), "deny", "B5 only values matching the allow regex are exempt"),
    case("TB07-D-070", lib.profile_dict("base", secret_allow_patterns=["ghp_TESTONLY[A-Za-z0-9]+"]),
         doc(f"blob {j('gh', 'p_', 'TESTONLY', mix(30))} end"), "allow", "B5 key-shaped value matching an allow regex"),
    case("TB07-D-071", "base", doc(f"blob {j('gh', 'p_', 'TESTONLY', mix(30))} end"), "deny", "B5 same value without the allow regex"),
    case("TB07-D-072", "alt", doc('client_secret = "FIXTURE-KEY-9876543210"'), "allow", "B5 allow regex (alt) exempts a secret-named assignment"),
])
def test_allow_patterns(tmp_path, profile, content, expected, clause):
    """TB-07 B5: 'Allows values matching any regex in profile.secret_allow_patterns.'"""
    _check(_run(tmp_path, "Write", _w(content), profile=profile), expected, clause)


# ---------------------------------------------------------------- behaviour 1: tools and roles

@pytest.mark.parametrize("agent", [
    case("TB07-D-073", "implement"), case("TB07-D-074", "orchestrator"), case("TB07-D-075", "test"),
    case("TB07-D-076", "review"), case("TB07-D-077", "research"), case("TB07-D-078", "design"),
    case("TB07-D-079", "audit"), case("TB07-D-080", None),
])
def test_every_role(tmp_path, agent):
    """TB-07 B1: 'Inspects Write content, Edit new_string and Bash command, for every role' (None = main session)."""
    _check(_run(tmp_path, "Write", _w(doc(f"x = {K['glpat']}")), agent), "deny", "B1 every role")


@pytest.mark.parametrize("tool,tool_input,expected,clause", [
    case("TB07-D-081", "Edit", {"file_path": "src/app.py", "old_string": doc(f"k = {K['sk']}"), "new_string": "k = None\n"},
         "allow", "B1 only Edit new_string is inspected (removing a secret)"),
    case("TB07-D-082", "Bash", {"command": f'curl -H "Authorization: Bearer {K["ghp"]}" https://api.invalid/user'}, "deny", "B1 Bash command"),
    case("TB07-D-083", "Bash", {"command": 'curl -H "Authorization: Bearer ${GITHUB_TOKEN}" https://api.invalid/user'}, "allow", "B3 ${VAR} in Bash"),
    case("TB07-D-084", "Bash", {"command": "echo $OPENROUTER_API_KEY | wc -c"}, "allow", "B3 $VAR in Bash"),
    case("TB07-D-085", "Bash", {"command": f"git remote add origin https://oauth2:{K['glpat']}@gitlab.invalid/r.git"}, "deny", "B1 Bash; B2 glpat-"),
    case("TB07-D-086", "Read", {"file_path": "src/app.py"}, "allow", "B1 other tools are allowed"),
    case("TB07-D-087", "Grep", {"pattern": K["ghp"], "path": "src"}, "allow", "B1 other tools are allowed (Grep pattern not inspected)"),
    case("TB07-D-088", "Glob", {"pattern": "**/*.pem"}, "allow", "B1 other tools are allowed"),
    case("TB07-D-089", "Bash", {"command": f"echo 'AWS={K['akia']}' >> .env"}, "deny", "B1 Bash command; B2 AKIA"),
    case("TB07-D-090", "Edit", {"file_path": "src/app.py", "old_string": "a", "new_string": PEM["openssh"] + "\n"}, "deny", "B1 Edit new_string; B2 PEM"),
])
def test_tools(tmp_path, tool, tool_input, expected, clause):
    """TB-07 B1: Write content, Edit new_string and Bash command are inspected; other tools are allowed."""
    _check(_run(tmp_path, tool, tool_input), expected, clause)


# ---------------------------------------------------------------- behaviour 6: reasons

@pytest.mark.parametrize("tool,tool_input,line,value", [
    case("TB07-D-091", "Write", _w("a\nb\nc\nd\n" + f"e = {K['akia']}\n"), 5, K["akia"]),
    case("TB07-D-092", "Edit", {"file_path": "src/app.py", "old_string": "a", "new_string": f"k = {K['sk']}\n"}, 1, K["sk"]),
    case("TB07-D-093", "Bash", {"command": f"export OPENAI_API_KEY={K['sk']}"}, 1, K["sk"]),
    case("TB07-D-094", "Write", _w(f'one\napi_key = "{V20}"\n'), 2, V20),
])
def test_reason_line_and_no_value(tmp_path, tool, tool_input, line, value):
    """TB-07 B6: 'Deny reasons name the pattern kind and the line number, never the matched value.'"""
    d = _run(tmp_path, tool, tool_input)
    assert d.kind == "deny"
    assert re.search(rf"(?<!\d){line}(?!\d)", d.reason), f"line {line} must be named"
    assert value not in d.reason
    assert value[-12:] not in d.reason


# ---------------------------------------------------------------- behaviour 7: never logs or persists

def _tree_contains(base, needle: str) -> list:
    hits = []
    for dirpath, _dirs, files in os.walk(base):
        for f in files:
            p = os.path.join(dirpath, f)
            try:
                with open(p, "rb") as fh:
                    if needle.encode() in fh.read():
                        hits.append(p)
            except OSError:
                pass
    return hits


@pytest.mark.case("TB07-D-095", tier="diagnostic", tb=TB, reqs=["R-12", "R-23"])
def test_decide_persists_nothing(tmp_path):
    """TB-07 B7: 'The hook never logs or persists the content it inspected' (in-process decide leaves no copy
    anywhere under the fixture directory)."""
    d = _run(tmp_path, "Write", _w(doc(f"x = {K['ghs']}")))
    assert d.kind == "deny"
    assert _tree_contains(tmp_path, K["ghs"]) == []


@pytest.mark.case("TB07-D-096", tier="diagnostic", tb=TB, reqs=["R-12", "R-23"])
def test_cli_persists_nothing(tmp_path):
    """TB-07 B7 + hook-io adapter: through `python -m factory.hooks secrets_guard` a secret Write exits 2, the value
    appears in neither stdout nor stderr, and nothing under the project or a scratch HOME contains it."""
    lib.need("factory.hooks.core", "run_hook")
    lib.need("factory.agents.profile", "load_profile")
    lib.need(HOOK, "decide")
    root = lib.make_project(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    pl = lib.payload(root, tool_name="Write", tool_input={"file_path": str(root / "src/c.py"),
                                                          "content": doc(f"x = {K['xoxp']}")}, agent_type="implement")
    r = lib.run_cli("secrets_guard", pl, root, env={"HOME": str(home), "TMPDIR": str(home)})
    assert r.returncode == 2
    assert K["xoxp"] not in r.stdout + r.stderr
    assert _tree_contains(tmp_path, K["xoxp"]) == []


@pytest.mark.case("TB07-D-097", tier="diagnostic", tb=TB, reqs=list(REQS))
def test_cli_allow(tmp_path):
    """hook-io adapter: a clean Write through the command line exits 0 with empty stdout."""
    lib.need("factory.hooks.core", "run_hook")
    lib.need("factory.agents.profile", "load_profile")
    lib.need(HOOK, "decide")
    root = lib.make_project(tmp_path)
    pl = lib.payload(root, tool_name="Write", tool_input={"file_path": str(root / "src/c.py"),
                                                          "content": doc('key = os.environ["OPENROUTER_API_KEY"]')},
                     agent_type="implement")
    r = lib.run_cli("secrets_guard", pl, root)
    assert r.returncode == 0 and r.stdout.strip() == ""



# ================================================================ clarifications (docs/contracts/clarifications.md)

CLAR = [
    # [A-07-1] colon assignments
    case("TB07-D-099", doc(f'{{"api_key": "{V20}"}}'), "deny", "[A-07-1] JSON colon assignment counts"),
    case("TB07-D-100", doc(f'password: "{V20}"'), "deny", "[A-07-1] YAML colon assignment counts"),
    case("TB07-D-101", doc(f"  client_secret: '{V20}'"), "deny", "[A-07-1] YAML colon assignment, single quotes"),
    case("TB07-D-102", doc(f'"username": "{V20}"'), "allow", "[A-07-1] colon assignment to a non-secret name"),
    # [A-07-2] quoted variable reference
    case("TB07-D-103", doc('password = "${DB_PASSWORD_FROM_ENV}"'), "allow", "[A-07-2] quoted value is exactly ${X}"),
    case("TB07-D-104", doc('api_key = "$OPENROUTER_API_KEY_VALUE"'), "allow", "[A-07-2] quoted value is exactly $X"),
    case("TB07-D-105", doc('"token": "${GITHUB_TOKEN_FOR_CI}"'), "allow", "[A-07-1]+[A-07-2] colon form with a variable reference"),
    case("TB07-D-106", doc(f'password = "${{X}}{V20}"'), "deny", "[A-07-2] only a value that is exactly a reference is exempt"),
    # [A-07-3] token-level placeholder rule
    case("TB07-D-107", doc(f"blob {j('sk', '-', mix(40))}... end"), "deny", "[C-39] item 1 supersedes [A-07-3]: a trailing ... is not a whole-value placeholder"),
    case("TB07-D-108", doc(f"blob {j('sk', '-', '0' * 40)} end"), "allow", "[A-07-3] sk-000...0 is a placeholder"),
    case("TB07-D-109", doc(f"blob {j('gh', 'p_', '0' * 36)} end"), "allow", "[A-07-3] repeated-character body is a placeholder"),
    case("TB07-D-110", doc(f"k = \"{j('sk', '-', mix(40))}...\""), "deny", "[C-39] item 1 supersedes [A-07-3]: a trailing ... is not a whole-value placeholder"),
    # [A-07-4] case-insensitive placeholder words
    case("TB07-D-111", doc('api_key = "EXAMPLE-KEY-1234567890"'), "deny", "[C-39] item 1 supersedes [A-07-4]: placeholder word EXAMPLE inside a longer value no longer exempts it"),
    case("TB07-D-112", doc('token = "YOUR-TOKEN-GOES-HERE-1"'), "deny", "[C-39] item 1 supersedes [A-07-4]: placeholder word YOUR inside a longer value no longer exempts it"),
    case("TB07-D-113", doc('password = "CHANGEME-CHANGEME-123"'), "deny", "[C-39] item 1 supersedes [A-07-4]: placeholder word CHANGEME inside a longer value no longer exempts it"),
    case("TB07-D-114", doc('secret = "PlaceHolder-Value-12345"'), "deny", "[C-39] item 1 supersedes [A-07-4]: placeholder word PlaceHolder inside a longer value no longer exempts it"),
    case("TB07-D-115", doc(f"blob {j('gh', 'p_', 'XXXX', mix(24))} end"), "deny", "[C-39] item 1 supersedes [A-07-4]: placeholder word XXXX inside a longer value no longer exempts it"),
    # [A-07-5] AIza 35 or more
    case("TB07-D-116", doc(f"blob {j('AI', 'za', mix(40, URLSAFE))} end"), "deny", "[A-07-5] AIza + 40"),
    case("TB07-D-117", doc(f"blob {j('AI', 'za', mix(36, URLSAFE))} end"), "deny", "[A-07-5] AIza + 36"),
]


@pytest.mark.parametrize("content,expected,clause", CLAR)
def test_clarified_content(tmp_path, content, expected, clause):
    """clarifications [A-07-1] to [A-07-5] for Write content (clause per case). Cases D-107, D-110 and D-111 to D-115
    expected "allow" under [A-07-3] / [A-07-4] and now expect "deny": [C-39] item 1 supersedes the token-level
    placeholder rule ('A matched secret is exempt only when the whole matched value ... is itself a placeholder
    form'). D-108 and D-109 stay allow (the whole body is one repeated character)."""
    _check(_run(tmp_path, "Write", _w(content)), expected, clause)


# ---------------------------------------------------------------- R-24: published documentation

@pytest.mark.case("TB07-D-098", tier="diagnostic", tb="07", reqs=["R-24"])
def test_docs_hooks_secrets_guard_md():
    """TB-07 Acceptance: 'Document the component in the docs/hooks/ file you own, with one example payload or call
    (requirement R-24).' OWN list names docs/hooks/secrets_guard.md."""
    lib.need("factory.hooks.secrets_guard")
    doc_path = lib.REPO / "docs" / "hooks" / "secrets_guard.md"
    assert doc_path.is_file()
    text = doc_path.read_text()
    assert any(s in text for s in ("hook_event_name", "decide(", "python -m factory.hooks")), "one example payload or call"


# ================================================================ clarifications C-38 item 4 and C-39 (secrets guard)

def _multi(*new_strings):
    return {"file_path": "src/app.py", "edits": [{"old_string": f"o{i}", "new_string": s} for i, s in enumerate(new_strings)]}


def _nb(source):
    return {"notebook_path": "src/n.ipynb", "new_source": source, "edit_mode": "replace", "cell_id": "c1"}


def _run_nb(tmp_path, tool, tool_input, agent="implement"):
    root = lib.make_project(tmp_path, lib.profile_dict("base"), files={"src/app.py": "print('app')\n"})
    ti = dict(tool_input)
    for k in ("file_path", "notebook_path"):
        if k in ti:
            ti[k] = str(root / ti[k])
    return lib.run_decide(HOOK, lib.payload(root, tool_name=tool, tool_input=ti, agent_type=agent), root)


C38_TOOLS = [
    case("TB07-D-118", "MultiEdit", _multi(doc(f"k = {K['ghp']}")), "deny", "[C-38] 4 MultiEdit edits[0].new_string is scanned"),
    case("TB07-D-119", "MultiEdit", _multi("x = 1\n", doc(f"k = {K['akia']}")), "deny", "[C-38] 4 every MultiEdit edit is scanned (second edit)"),
    case("TB07-D-120", "MultiEdit", _multi("x = 1\n", "y = 2\n", PEM["rsa"] + "\n"), "deny", "[C-38] 4 third MultiEdit edit, PEM header"),
    case("TB07-D-121", "MultiEdit", _multi(doc(f'api_key = "{V20}"')), "deny", "[C-38] 4 MultiEdit assignment of a quoted value"),
    case("TB07-D-122", "MultiEdit", _multi("x = 1\n", doc('key = os.environ["OPENROUTER_API_KEY"]')), "allow", "[C-38] 4 MultiEdit clean edits allowed"),
    case("TB07-D-123", "MultiEdit", {"file_path": "src/app.py", "edits": [{"old_string": doc(f"k = {K['sk']}"), "new_string": "k = None\n"}]},
         "allow", "[C-38] 4 only new_string is scanned (old_string removing a secret is fine)"),
    case("TB07-D-124", "NotebookEdit", _nb(doc(f"k = {K['ghs']}")), "deny", "[C-38] 4 NotebookEdit new_source is scanned"),
    case("TB07-D-125", "NotebookEdit", _nb(f'token = "{V20}"\n'), "deny", "[C-38] 4 NotebookEdit assignment of a quoted value"),
    case("TB07-D-126", "NotebookEdit", _nb(PEM["openssh"] + "\n"), "deny", "[C-38] 4 NotebookEdit PEM header"),
    case("TB07-D-127", "NotebookEdit", _nb("import os\nkey = os.environ['OPENROUTER_API_KEY']\n"), "allow", "[C-38] 4 NotebookEdit clean source allowed"),
]


@pytest.mark.parametrize("tool,tool_input,expected,clause", C38_TOOLS)
def test_multiedit_notebookedit_scanned(tmp_path, tool, tool_input, expected, clause):
    """[C-38] item 4: 'secrets_guard scans MultiEdit edits[*].new_string and NotebookEdit new_source'."""
    _check(_run_nb(tmp_path, tool, tool_input), expected, clause)


@pytest.mark.parametrize("agent", [case("TB07-D-128", "review"), case("TB07-D-129", None)])
def test_multiedit_every_role(tmp_path, agent):
    """[C-38] item 4 + TB-07 B1 (every role): MultiEdit is scanned for the review role and the main session too."""
    _check(_run_nb(tmp_path, "MultiEdit", _multi(doc(f"k = {K['glpat']}")), agent), "deny", "every role")


@pytest.mark.parametrize("tool,tool_input,line", [
    case("TB07-D-130", "MultiEdit", _multi("a\n", f"b\nk = {K['ghp']}\n"), 2),
    case("TB07-D-131", "NotebookEdit", _nb(f"a\nb\nk = {K['akia']}\n"), 3),
])
def test_multiedit_reason_no_value(tmp_path, tool, tool_input, line):
    """[C-38] item 4 + TB-07 B6: the reason names a line number and never the matched value."""
    d = _run_nb(tmp_path, tool, tool_input)
    assert d.kind == "deny"
    assert re.search(rf"(?<!\d){line}(?!\d)", d.reason)
    for v in (K["ghp"], K["akia"]):
        assert v not in d.reason and v[-12:] not in d.reason


# ---- C-39 item 1: whole-value placeholders

C39_PLACEHOLDER = [
    # denied: a placeholder word elsewhere in the token or text never exempts a real key
    case("TB07-G-011", doc(f"your_key={K['ghp']}"), "deny", "[C-39] 1 'your_key=<real key>' is denied"),
    case("TB07-D-132", doc(f"your_key = {K['sk']}"), "deny", "[C-39] 1 placeholder word in the name, real sk- key"),
    case("TB07-D-133", doc(f"# example: {K['glpat']}"), "deny", "[C-39] 1 'example' next to a real key"),
    case("TB07-D-134", doc(f"changeme {K['xoxb']} placeholder"), "deny", "[C-39] 1 placeholder words around a real key"),
    case("TB07-D-135", doc(f"<{K['ghp']}>"), "deny", "[C-39] 1 angle brackets around a real key do not make the matched value a placeholder"),
    case("TB07-D-136", doc(f"blob {j('sk-', 'ant-', 'xxxx', mix(30))} end"), "deny", "[C-39] 1 prefixed key whose body merely contains xxxx"),
    case("TB07-D-137", doc(f'api_key = "{j("your-", V20)}"'), "deny", "[C-39] 1 assigned value starting with 'your-' then a real value"),
    case("TB07-D-138", doc(f'token = "{j(V20, "-example")}"'), "deny", "[C-39] 1 assigned value ending in -example"),
    case("TB07-D-139", doc(f'password = "{j(V16, "...")}"'), "deny", "[C-39] 1 assigned value ending in ... is not a placeholder form"),
    case("TB07-D-140", doc(f"export TOKEN=YOUR_{K['ghp']}"), "deny", "[C-39] 1 YOUR_ glued before a real key"),
    # allowed: the whole value is a placeholder form
    case("TB07-D-141", doc('api_key = "<paste-your-key-here-please>"'), "allow", "[C-39] 1 whole assigned value is <...>"),
    case("TB07-D-142", doc('secret = "<' + V20 + '>"'), "allow", "[C-39] 1 whole value spanning <...>"),
    case("TB07-D-143", doc('token = "zzzzzzzzzzzzzzzzzzzz"'), "allow", "[C-39] 1 whole value is one repeated character"),
    case("TB07-D-144", doc(f"blob {j('sk-', 'ant-', 'z' * 30)} end"), "allow", "[C-39] 1 prefixed key whose whole body is one repeated character"),
    case("TB07-D-145", doc('password = "$DATABASE_PASSWORD_VALUE"'), "allow", "[C-39] 1 whole value is $VAR"),
    case("TB07-D-146", doc('api_key = "${SERVICE_API_KEY_VALUE}"'), "allow", "[C-39] 1 whole value is ${VAR}"),
]


@pytest.mark.parametrize("content,expected,clause", C39_PLACEHOLDER)
def test_c39_whole_value_placeholders(tmp_path, content, expected, clause):
    """[C-39] item 1: 'A matched secret is exempt only when the whole matched value ... is itself a placeholder form:
    an angle-bracket form <...> spanning the value, a single repeated character, or a $VAR / ${VAR} reference.'"""
    _check(_run(tmp_path, "Write", _w(content)), expected, clause)


@pytest.mark.case("TB07-D-147", tier="diagnostic", tb=TB, reqs=list(REQS))
def test_c39_allow_patterns_match_value_only(tmp_path):
    """[C-39] item 1: 'secret_allow_patterns from the profile still apply and are matched against the matched value
    only': a value matching an allow regex stays allowed (alt profile FIXTURE-KEY-<digits>)."""
    _check(_run(tmp_path, "Write", _w(doc('api_key = "FIXTURE-KEY-12345678901"')), profile="alt"), "allow", "[C-39] 1 allow pattern")


@pytest.mark.case("TB07-D-148", tier="diagnostic", tb=TB, reqs=list(REQS))
def test_c39_allow_pattern_text_elsewhere_does_not_exempt(tmp_path):
    """[C-39] item 1: allow patterns are matched against the matched value only, so a FIXTURE-KEY token elsewhere on the
    line does not exempt a real key."""
    _check(_run(tmp_path, "Write", _w(doc(f"FIXTURE-KEY-123 {K['ghp']}")), profile="alt"), "deny", "[C-39] 1 value only")


# ---- C-39 item 2: bounded scanning

LIMIT = 2_000_000
_LINE = "abc def\n"                       # 8 characters, no key shape; 250,000 lines = exactly 2,000,000 characters
_AT_LIMIT = _LINE * (LIMIT // len(_LINE))


@pytest.mark.case("TB07-D-149", tier="diagnostic", tb=TB, reqs=list(REQS))
def test_c39_over_limit_write_denied_too_large(tmp_path):
    """[C-39] item 2: 'Text longer than 2,000,000 characters is denied (fail closed) with a reason saying the content
    is too large to scan.'"""
    assert len(_AT_LIMIT) == LIMIT
    d = _run(tmp_path, "Write", _w(_AT_LIMIT + "x"))
    assert d.kind == "deny"
    assert "too large" in d.reason.lower()


@pytest.mark.case("TB07-D-150", tier="diagnostic", tb=TB, reqs=list(REQS))
def test_c39_exactly_at_limit_allowed(tmp_path):
    """[C-39] item 2: only text LONGER than 2,000,000 characters is denied, so exactly 2,000,000 clean characters pass."""
    _check(_run(tmp_path, "Write", _w(_AT_LIMIT)), "allow", "[C-39] 2 boundary")


@pytest.mark.case("TB07-D-151", tier="diagnostic", tb=TB, reqs=list(REQS))
def test_c39_over_limit_bash_denied(tmp_path):
    """[C-39] item 2: the bound applies to Bash commands too."""
    d = _run(tmp_path, "Bash", {"command": "echo " + _AT_LIMIT})
    assert d.kind == "deny"
    assert "too large" in d.reason.lower()


@pytest.mark.case("TB07-D-152", tier="diagnostic", tb=TB, reqs=list(REQS))
def test_c39_over_limit_multiedit_denied(tmp_path):
    """[C-39] item 2 + [C-38] item 4: an oversized MultiEdit new_string is denied as too large."""
    d = _run_nb(tmp_path, "MultiEdit", _multi("x = 1\n", _AT_LIMIT + "x"))
    assert d.kind == "deny"
    assert "too large" in d.reason.lower()


# ---- C-39 item 3: quoting does not hide a key in Bash

_ANT = j("ant-", "api03-", mix(40, URLSAFE))
C39_BASH = [
    case("TB07-D-153", f'export ANTHROPIC_API_KEY="sk-""{_ANT}"', "deny", "[C-39] 3 key split by adjacent double-quoted literals"),
    case("TB07-D-154", f"export K='sk-''{_ANT}'", "deny", "[C-39] 3 key split by adjacent single-quoted literals"),
    case("TB07-D-155", f"echo gh\\p_{mix(36)}", "deny", "[C-39] 3 backslash escape inside the prefix"),
    case("TB07-D-156", f"echo $'\\x67hp_{mix(36)}'", "deny", "[C-39] 3 ANSI-C $'...' escape unescaped before scanning"),
    case("TB07-D-157", f'echo "gh"p_{mix(36)}', "deny", "[C-39] 3 quoted fragment joined to a plain fragment"),
    case("TB07-D-158", f"echo 'AK'\"IA\"{mix(16, UPPER)}", "deny", "[C-39] 3 AKIA split across mixed quote styles"),
    case("TB07-D-159", 'echo "hello" \'world\' && ls -la "src dir"', "allow", "[C-39] 3 an ordinary quoted command stays allowed"),
    case("TB07-D-160", 'git commit -m "fix: handle empty input" && git status', "allow", "[C-39] 3 a harmless command with quotes stays allowed"),
    case("TB07-D-161", 'pytest -q "tests/unit" -k \'not slow\'', "allow", "[C-39] 3 another harmless quoted command stays allowed"),
]


@pytest.mark.parametrize("command,expected,clause", C39_BASH)
def test_c39_dequoted_bash_scan(tmp_path, command, expected, clause):
    """[C-39] item 3: 'the command is scanned both as written and in a de-quoted form (single and double quotes and
    backslash escapes removed, $'...' sequences unescaped, adjacent literals joined)'."""
    _check(_run(tmp_path, "Bash", {"command": command}, agent="orchestrator"), expected, clause)
