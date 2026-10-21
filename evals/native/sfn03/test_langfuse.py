"""SFN-03 T-06: Langfuse honesty. The tab never claims what is not configured; `sf ops init --langfuse-host` is https only."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from .conftest import dump, git, mkrepo, runtime, sf, shell_text, tree, write

SECRETS = {"LANGFUSE_SECRET_KEY": "sk-lf-0123456789abcdefSECRET", "LANGFUSE_PUBLIC_KEY": "pk-lf-0123456789abcdefPUBLIC",
           "LANGFUSE_HOST": "https://env-host.example.com"}


def proposal(llm):
    return f"# Slice\n\npriority: P1\nllm_features: {'true' if llm else 'false'}\n"


def llm_repo(tmp_path, flags: dict):
    return mkrepo(tmp_path, {f"docs/slices/{sid}/proposal.md": proposal(v) for sid, v in flags.items()})


def langfuse_tab(repo, config=None):
    runtime(repo, config if config is not None else {})
    return shell_text(repo, "langfuse")


def test_T06_unconfigured_tab_says_not_measured_with_a_reason(tmp_path):
    text = langfuse_tab(mkrepo(tmp_path))
    assert "not measured:" in text
    reason = text.split("not measured:", 1)[1].strip().splitlines()[0]
    assert len(reason.strip(" <")) > 8, "a reason follows 'not measured:'"


def test_T06_unconfigured_runtime_claims_no_measurement(tmp_path):
    rt = runtime(mkrepo(tmp_path))
    assert '"measured": true' not in dump(rt["langfuse"])


def test_T06_llm_features_declared_without_host_names_the_slices(tmp_path):
    repo = llm_repo(tmp_path, {"alpha": True, "beta": True, "gamma": False})
    text = langfuse_tab(repo)
    import re
    m = re.search(r"LLM features declared in ([^<\n]+?) but Langfuse is not configured", text)
    assert m, text[-1500:]
    assert set(re.split(r"[,\s]+", m.group(1).strip())) == {"alpha", "beta"}


def test_T06_no_llm_slices_means_no_declared_but_unconfigured_warning(tmp_path):
    text = langfuse_tab(llm_repo(tmp_path, {"gamma": False}))
    assert "LLM features declared" not in text
    assert "not measured:" in text


def test_T06_configured_host_removes_the_warning_and_shows_the_host(tmp_path):
    repo = llm_repo(tmp_path, {"alpha": True})
    text = langfuse_tab(repo, {"langfuse": {"host": "https://lf.example.com", "project": "proj-1"}})
    assert "LLM features declared" not in text and "but Langfuse is not configured" not in text
    assert "lf.example.com" in text


def test_T06_configured_host_does_not_claim_traces_were_measured(tmp_path):
    text = langfuse_tab(mkrepo(tmp_path), {"langfuse": {"host": "https://lf.example.com", "project": "p"}})
    assert "not measured" in text.lower(), "trace ingestion is still not checked, and says so"


# ---- sf ops init --langfuse-host ----------------------------------------------------------------------------

def test_T06_init_records_an_https_host(tmp_path):
    repo = mkrepo(tmp_path)
    p = sf(repo, "ops", "init", "--dir", str(repo), "--langfuse-host", "https://langfuse.example.com")
    assert p.returncode == 0, p.stdout + p.stderr
    cfg = json.loads((repo / "ops" / "config.json").read_text())
    assert cfg["langfuse"]["host"].rstrip("/") == "https://langfuse.example.com"


def test_T06_init_keeps_existing_config_keys_when_recording_the_host(tmp_path):
    repo = mkrepo(tmp_path, {"ops/config.json": json.dumps({"health_url": "https://app.example.com/health"})})
    p = sf(repo, "ops", "init", "--dir", str(repo), "--langfuse-host", "https://langfuse.example.com")
    assert p.returncode == 0, p.stdout + p.stderr
    cfg = json.loads((repo / "ops" / "config.json").read_text())
    assert cfg["health_url"] == "https://app.example.com/health"
    assert cfg["langfuse"]["host"].rstrip("/") == "https://langfuse.example.com"


@pytest.mark.parametrize("url", ["http://langfuse.example.com", "ftp://langfuse.example.com", "javascript:alert(1)",
                                 "file:///etc/passwd", "langfuse.example.com", "HTTP://x.example.com", ""])
def test_T06_init_refuses_non_https_hosts_with_exit_2_and_records_nothing(tmp_path, url):
    control = mkrepo(tmp_path, name="control")
    ok = sf(control, "ops", "init", "--dir", str(control), "--langfuse-host", "https://langfuse.example.com")
    assert ok.returncode == 0, "the flag exists and accepts https: " + ok.stderr
    repo = mkrepo(tmp_path)
    p = sf(repo, "ops", "init", "--dir", str(repo), "--langfuse-host", url)
    assert p.returncode == 2, p.stdout + p.stderr
    assert "unrecognized arguments" not in p.stderr and "https" in p.stderr.lower(), p.stderr
    cfgp = repo / "ops" / "config.json"
    cfg = json.loads(cfgp.read_text()) if cfgp.exists() else {}
    assert "langfuse" not in cfg


def test_T06_init_does_not_store_or_print_credentials(tmp_path):
    repo = mkrepo(tmp_path)
    p = sf(repo, "ops", "init", "--dir", str(repo), "--langfuse-host", "https://langfuse.example.com",
           extra_env=SECRETS)
    assert p.returncode == 0, p.stdout + p.stderr
    runtime(repo)
    blob = p.stdout + p.stderr
    for f in (repo / "ops").rglob("*"):
        if f.is_file() and f.stat().st_size < 3_000_000:
            blob += f.read_text(encoding="utf-8", errors="replace")
    for name in ("sk-lf-0123456789abcdefSECRET", "pk-lf-0123456789abcdefPUBLIC"):
        assert name not in blob


def test_T06_a_host_carrying_a_password_never_reaches_the_config_or_output(tmp_path):
    repo = mkrepo(tmp_path)
    p = sf(repo, "ops", "init", "--dir", str(repo), "--langfuse-host", "https://user:s3cretpw@langfuse.example.com")
    blob = p.stdout + p.stderr
    cfgp = repo / "ops" / "config.json"
    blob += cfgp.read_text() if cfgp.exists() else ""
    assert "s3cretpw" not in blob
    assert p.returncode in (0, 2) and "unrecognized arguments" not in p.stderr


def test_T06_init_without_the_flag_leaves_langfuse_unconfigured(tmp_path):
    repo = mkrepo(tmp_path)
    assert sf(repo, "ops", "init", "--dir", str(repo)).returncode == 0
    assert "langfuse" not in json.loads((repo / "ops" / "config.json").read_text())


def test_T06_init_with_a_host_twice_is_stable(tmp_path):
    repo = mkrepo(tmp_path)
    args = ("ops", "init", "--dir", str(repo), "--langfuse-host", "https://langfuse.example.com")
    assert sf(repo, *args).returncode == 0
    first = (repo / "ops" / "config.json").read_bytes()
    assert sf(repo, *args).returncode == 0
    assert (repo / "ops" / "config.json").read_bytes() == first
