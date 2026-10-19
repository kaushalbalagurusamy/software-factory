"""Record one gate run. Classifies pass / fail / flake / environment and keeps the chain."""
from .signature import normalize_error, signature


def record_run(store, pol, *, status, case=None, criterion=None, error="", tier=None, duration_s=0,
               tokens=0, cost_usd=0.0, commit=None, rerun=False, verified=None, environment=False) -> dict:
    """status is the gate result ("pass" or "fail"); the stored outcome adds suspect, flake, environment.

    A first failure is "suspect" until the policy's flake reruns are used up; a rerun that passes is a
    "flake" (not an attempt); a failure that survives the reruns is a counted "fail"; a failure matching an
    environment pattern is "environment" (no attempt consumed, gate stays failed)."""
    if status not in ("pass", "fail"):
        raise ValueError("status must be pass or fail")
    f = store.facts()
    if rerun and f["trailing_suspects"] == 0:
        raise ValueError("rerun recorded but no suspect failure is pending")
    if not rerun and f["trailing_suspects"] > 0:
        raise ValueError("a flake rerun is pending; record it with rerun=True")
    sig, key = None, case or criterion or "unknown"
    if status == "pass":
        outcome = "flake" if rerun else "pass"
    elif environment or pol.is_environment(error):
        outcome = "environment"
    else:
        sig = signature(key, error)
        outcome = "suspect" if f["trailing_suspects"] < pol.flake_reruns else "fail"
    last = f["last"]
    line = {"kind": "run", "outcome": outcome, "signature": sig, "case": case, "criterion": criterion,
            "tier": tier or (last or {}).get("tier") or pol.tiers[0], "duration_s": duration_s,
            "tokens": tokens, "cost_usd": cost_usd, "commit": commit}
    if outcome == "environment":
        line["error_norm"] = normalize_error(error)[:300]
    out = store.append("attempts.jsonl", line)
    if outcome in ("fail", "suspect"):
        store.append("failures.jsonl", {"signature": sig, "case": case, "criterion": criterion,
                                        "outcome": outcome, "error_norm": normalize_error(error)[:500]})
    if outcome in ("pass", "flake"):
        store.mark_verified(store.state["criteria"] if verified is None else verified)
    return out
