"""Trigger check against the INSTALLED skill: fires if the first tool call is Skill(<name>) or a Read of its SKILL.md."""
import json, os, subprocess, sys, time, select
from concurrent.futures import ThreadPoolExecutor

def run_one(query, name, timeout=90):
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY")}
    p = subprocess.Popen(["claude","-p",query,"--output-format","stream-json","--verbose","--include-partial-messages"],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, cwd="/tmp", env=env)
    buf = ""; tool = None; acc = ""; t0 = time.time(); res = False
    try:
        while time.time() - t0 < timeout:
            if p.poll() is not None:
                buf += (p.stdout.read() or b"").decode("utf-8","replace")
            else:
                r,_,_ = select.select([p.stdout],[],[],1.0)
                if not r: continue
                c = os.read(p.stdout.fileno(), 8192)
                if not c: break
                buf += c.decode("utf-8","replace")
            done = p.poll() is not None
            while "\n" in buf:
                line, buf = buf.split("\n",1)
                try: ev = json.loads(line)
                except Exception: continue
                if ev.get("type") != "stream_event": continue
                se = ev["event"]; ty = se.get("type")
                if ty == "content_block_start" and se["content_block"].get("type") == "tool_use":
                    tool = se["content_block"]["name"]; acc = ""
                    if tool not in ("Skill","Read"): return False
                elif ty == "content_block_delta" and tool:
                    acc += se["delta"].get("partial_json","")
                    if name in acc: return True
                elif ty == "content_block_stop" and tool:
                    return name in acc
            if done: break
        return res
    finally:
        if p.poll() is None: p.kill()

def main(setfile, name, runs=2, workers=4):
    qs = json.load(open(setfile))
    jobs = [(q["query"], name) for q in qs for _ in range(runs)]
    with ThreadPoolExecutor(workers) as ex: out = list(ex.map(lambda a: run_one(*a), jobs))
    rows = []
    for i,q in enumerate(qs):
        hits = sum(out[i*runs:(i+1)*runs]); rows.append((q["should_trigger"], hits, runs, q["query"][:80]))
    pos = [r for r in rows if r[0]]; neg = [r for r in rows if not r[0]]
    print(f"{name}: positives fired {sum(r[1] for r in pos)}/{sum(r[2] for r in pos)} runs; near-misses fired {sum(r[1] for r in neg)}/{sum(r[2] for r in neg)} runs (want 0)")
    for r in rows: print("  ", "POS" if r[0] else "NEG", f"{r[1]}/{r[2]}", r[3])

if __name__ == "__main__": main(sys.argv[1], sys.argv[2])
