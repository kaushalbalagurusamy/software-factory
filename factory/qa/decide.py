"""The `next` decision: pure over (facts, state, policy, tier stats), plus an applying wrapper."""
from factory.hitl import store as hitl
from .store import AuditError
from .stats import slice_dirs, tier_stats

ACTIONS = ("retry_same_tier", "escalate_model", "propose_regression", "hand_to_reviewer", "mark_blocked",
           "accept", "rerun_for_flake", "environment_wait", "human_stop")


def _d(action, reason, **kw):
    return {"action": action, "reason": reason, **kw}


def _tier_for(k, last_tier, pol, stats):
    """Ladder tier for attempt k+1, adjusted by measured outcomes of the tier in use."""
    tiers = pol.tiers
    want = tiers[min(k, len(tiers) - 1)]
    s = stats.get(last_tier) or {}
    n, ok = s.get("attempts", 0), s.get("successes", 0)
    if last_tier and n >= pol.min_samples:
        rate = ok / n
        later = [t for t in tiers[tiers.index(last_tier) + 1:] if t != last_tier] if last_tier in tiers else []
        if want == last_tier and rate < pol.escalate_below and later:
            return later[0], f"{last_tier} succeeded {ok}/{n} (< {pol.escalate_below}); escalating early"
        if want != last_tier and rate >= pol.hold_above:
            return last_tier, f"{last_tier} succeeded {ok}/{n} (>= {pol.hold_above}); holding tier"
    return want, f"ladder position {min(k, len(tiers) - 1) + 1}"


def decide(facts, state, pol, stats) -> dict:
    if state["status"] == "blocked":
        return _d("mark_blocked", "already blocked", waits_on=state.get("waits_on"))
    if facts["env_pending"]:
        if facts["env_consecutive"] > pol.env_wait_max:
            return _d("mark_blocked", "environment kept failing",
                      waits_on=f"environment: {facts['env_consecutive']} consecutive environment failures "
                               f"({(facts['last'] or {}).get('error_norm', '')[:120]})")
        return _d("environment_wait", "environment crash; gate stays failed until a clean run")
    sig = facts["current_sig"]
    if facts["trailing_suspects"] > 0:
        return _d("rerun_for_flake", f"{facts['trailing_suspects']} suspect failure(s); rerun before counting",
                  signature=sig, tier=facts["last_tier"])
    crit = state.get("criteria", [])
    missing = sorted(set(crit) - set(state.get("verified", [])))
    if facts["gate"] == "passed":
        if not missing:
            return _d("accept", "gate passed and all criteria verified")
        return _d("retry_same_tier", f"criteria unverified: {', '.join(missing)}", tier=facts["last_tier"])
    if sig is None:
        return _d("retry_same_tier", "first attempt", tier=pol.tiers[0])
    k = len(facts["fails_by_sig"].get(sig, []))
    info = facts["sig_info"].get(sig, {})
    if k >= 2 and sig not in state["proposals"]:
        return _d("propose_regression", f"signature recurred {k} times after claimed fixes", signature=sig,
                  criterion=info.get("criterion") or info.get("case"))
    cap = None
    if k >= pol.attempts_per_signature:
        cap = f"signature cap {pol.attempts_per_signature} reached"
    elif facts["counted_window"] >= pol.slice_attempt_cap:
        cap = f"slice attempt cap {pol.slice_attempt_cap} reached"
    elif pol.budget_tokens is not None and facts["tokens"] > pol.budget_tokens:
        cap = f"token budget {pol.budget_tokens} exceeded"
    elif pol.budget_cost_usd is not None and facts["cost_usd"] > pol.budget_cost_usd:
        cap = f"cost budget {pol.budget_cost_usd} exceeded"
    if cap:
        v = state["reviewer"].get(sig)
        if v and v["verdict"] == "unresolved" and v["at_len"] >= facts["last_fail_seq"]:
            return _d("mark_blocked", cap, signature=sig,
                      waits_on=f"reviewer could not resolve {sig} ({info.get('criterion') or info.get('case')}): {v['note']}")
        return _d("hand_to_reviewer", cap, signature=sig, criterion=info.get("criterion") or info.get("case"))
    last = facts["last_tier_by_sig"].get(sig)
    tier, why = _tier_for(k, last, pol, stats)
    return _d("retry_same_tier" if tier == last else "escalate_model", why, signature=sig, tier=tier)


def decide_next(store, pol, tier_stats_=None, apply=False) -> dict:
    problems = store.audit()
    if problems:
        raise AuditError("; ".join(problems))
    try:
        stops = [s["name"] for s in hitl.blocking_for(store.dir, f"slice:{store.id}")]
        why = "an open human stop applies; nothing is retried, escalated or accepted until a human releases it"
    except hitl.StopLedgerError as e:
        stops, why = ["<ledger>"], f"human-stop ledger tampered or unreadable (failing closed): {e}"
    if stops:
        return _d("human_stop", why, stops=stops)
    stats = tier_stats_ if tier_stats_ is not None else tier_stats(slice_dirs(store.root))
    d = decide(store.facts(), store.state, pol, stats)
    if apply:
        a = d["action"]
        if a == "mark_blocked" and store.state["status"] != "blocked":
            store.set_status("blocked", d["waits_on"])
        elif a == "hand_to_reviewer":
            store.set_status("stuck", d["reason"])
        elif a == "accept":
            store.set_status("accepted")
    return d
