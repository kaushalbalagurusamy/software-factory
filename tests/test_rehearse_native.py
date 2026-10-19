"""The rehearsal runner's stream parsing decides pass or fail, so it must read events correctly (no claude is run here)."""
import importlib.util
import json
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "rehearse-native.py"
spec = importlib.util.spec_from_file_location("rehearse_native", SCRIPT)
rn = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rn)


def stream(tmp_path, events):
    p = tmp_path / "s.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events))
    return p


def test_digest_reads_models_tools_hooks_results_and_text(tmp_path):
    ev = [
        {"type": "system", "subtype": "init", "model": "claude-sonnet-5-5", "skills": ["sf"], "agents": ["implement"]},
        {"type": "system", "subtype": "hook_response", "hook_name": "PreToolUse:Bash", "hook_event": "PreToolUse", "exit_code": 2, "output": "denied"},
        {"type": "assistant", "message": {"model": "claude-sonnet-5-5", "content": [{"type": "text", "text": "hello"},
         {"type": "tool_use", "name": "Read", "input": {"file_path": "evals/x.py"}}]}},
        {"type": "assistant", "parent_tool_use_id": "t1", "message": {"model": "claude-sonnet-5-5", "content": [{"type": "text", "text": "sub"}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "is_error": True, "content": "hook error"}]}},
        {"type": "result", "subtype": "success", "num_turns": 1},
    ]
    d = rn.digest(stream(tmp_path, ev))
    assert d["models"] == {"claude-sonnet-5-5"}
    assert d["texts"] == ["hello"]  # subagent text is not counted as the main session's text
    assert d["tool_uses"][0]["name"] == "Read" and "evals" in json.dumps(d["tool_uses"][0]["input"])
    assert d["hooks"][0]["exit"] == 2 and d["results"][0]["error"] is True
    assert d["result"]["subtype"] == "success" and d["init"]["skills"] == ["sf"]


def test_a_non_sonnet_model_in_the_stream_is_visible_to_the_check(tmp_path):
    ev = [{"type": "assistant", "message": {"model": "claude-opus-5-5", "content": []}}]
    assert rn.digest(stream(tmp_path, ev))["models"] != {rn.SONNET}


def test_garbage_lines_are_ignored_not_fatal(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text('not json\n{"type": "result", "subtype": "success"}\n')
    assert rn.digest(p)["result"]["subtype"] == "success"
