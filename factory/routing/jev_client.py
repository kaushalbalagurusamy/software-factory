"""
Jev routing client (shadow mode).

Asks TypeSafe Jev, a decisions model, to pick one option for a routing question, and combines
the answer with deterministic rules and probability bands from ``jev-policy.yaml``.

Design rules (see the orchestration skill, ``reference/jev-routing.md``):
  * deterministic rules run first; Jev is asked only when no rule decides;
  * the model is pinned by the policy file and the endpoint is the decisions API, not chat;
  * any fault (timeout, HTTP error, malformed answer, ``unknown``) falls back, never raises
    into the caller, and is never retried;
  * the API key is read from ``OPENROUTER_API_KEY`` and never stored or logged;
  * tests use recorded responses through the ``transport`` argument, never a live call.

Wire format: verified on 2026-09-24 with one live call (HTTP 200, about 250 ms, about $0.00002).
The API rejected a question without an ``instructions`` field ("questions.pick.instructions"), and
accepted ``instructions`` as a string. The response echoes a dated model snapshot
(``typesafe/jev-1.13-20260917`` for the pinned ``typesafe/jev-1.13``), which is worth logging.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional

import yaml

POLICY_PATH = Path(__file__).with_name("jev-policy.yaml")

Transport = Callable[[str, Dict[str, Any], float], Dict[str, Any]]


class JevFault(Exception):
    """Any failure to obtain a usable answer from Jev."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


@dataclass(frozen=True)
class Routing:
    decision: str
    choice: str
    action: str
    source: str  # "rule", "jev" or "fallback"
    band: str  # "rule", "act", "flag", "human" or "fault"
    policy_version: str
    top_prob: Optional[float] = None
    margin: Optional[float] = None
    probabilities: Mapping[str, float] = field(default_factory=dict)
    fault: Optional[str] = None
    latency_ms: Optional[float] = None


def load_policy(path: Path = POLICY_PATH) -> Dict[str, Any]:
    policy = yaml.safe_load(path.read_text())
    for name, dec in policy["decisions"].items():
        options = set(dec["options"])
        if "unknown" not in options:
            raise ValueError(f"decision {name!r} has no 'unknown' option")
        if set(dec["action"]) != options:
            raise ValueError(f"decision {name!r}: action keys must match options")
    return policy


def _rule_matches(when: Mapping[str, Any], state: Mapping[str, Any]) -> bool:
    for key, expected in when.items():
        if key.endswith("_at_least"):
            if not state.get(key[: -len("_at_least")], 0) >= expected:
                return False
        elif key.endswith("_contains_any"):
            text = str(state.get(key[: -len("_contains_any")], ""))
            if not any(token in text for token in expected):
                return False
        else:
            raise ValueError(f"unknown rule condition {key!r}")
    return True


def build_request(policy: Mapping[str, Any], decision: str, state: Mapping[str, Any]) -> Dict[str, Any]:
    """Body for POST /api/alpha/decisions (shape verified live on 2026-09-24, see module docstring)."""
    dec = policy["decisions"][decision]
    allowed = set(dec["state_fields"])
    extra = set(state) - allowed
    if extra:
        raise ValueError(f"state fields not allowed for {decision!r}: {sorted(extra)}")
    return {
        "model": policy["model"],
        "state": dict(state),
        "questions": {
            "pick": {
                "type": "choice",
                "instructions": dec["question"],
                "criteria": {name: " ".join(text.split()) for name, text in dec["options"].items()},
            }
        },
    }


def _default_transport(url: str, body: Dict[str, Any], timeout_s: float) -> Dict[str, Any]:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise JevFault("no_api_key")
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read())
    except TimeoutError as exc:
        raise JevFault("timeout") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise JevFault("timeout") from exc
        raise JevFault("transport_error", type(exc).__name__) from exc
    except (urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise JevFault("http_or_decode_error", type(exc).__name__) from exc


def parse_answer(response: Mapping[str, Any], options: List[str]) -> Dict[str, float]:
    """Return {option: probability} from the observed response shape, or raise JevFault."""
    try:
        answer = response["answers"]["pick"]
        probs = {str(k): float(v) for k, v in answer["probabilities"].items()}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise JevFault("schema_invalid", "missing answers.pick.probabilities") from exc
    if not probs or set(probs) - set(options):
        raise JevFault("schema_invalid", "probabilities missing or outside offered options")
    if any(p < 0 or p > 1 for p in probs.values()) or abs(sum(probs.values()) - 1.0) > 0.05:
        raise JevFault("schema_invalid", "probabilities do not form a distribution")
    return probs


def _band(policy: Mapping[str, Any], top: float, margin: float) -> str:
    for name in ("act", "flag"):
        b = policy["bands"][name]
        if top >= b["min_top"] and margin >= b["min_margin"]:
            return name
    return "human"


def route(
    decision: str,
    state: Mapping[str, Any],
    policy: Optional[Mapping[str, Any]] = None,
    transport: Optional[Transport] = None,
    clock: Callable[[], float] = time.monotonic,
) -> Routing:
    """Route one decision. Never raises for a Jev fault; the fault is recorded in the result."""
    policy = policy or load_policy()
    dec = policy["decisions"][decision]
    version = policy["policy_version"]

    for rule in dec.get("rules_first", []):
        if _rule_matches(rule["when"], state):
            choice = rule["choose"]
            return Routing(decision, choice, dec["action"][choice], "rule", "rule", version)

    request = build_request(policy, decision, state)
    options = list(dec["options"])
    started = clock()
    try:
        response = (transport or _default_transport)(
            policy["endpoint"], request, policy["transport_timeout_ms"] / 1000.0
        )
        probs = parse_answer(response, options)
    except JevFault as fault:
        return Routing(
            decision, "unknown", dec["action"]["unknown"], "fallback", "fault", version,
            fault=fault.kind, latency_ms=(clock() - started) * 1000.0,
        )
    latency = (clock() - started) * 1000.0

    ranked = sorted(probs.items(), key=lambda kv: kv[1], reverse=True)
    top_name, top = ranked[0]
    margin = top - (ranked[1][1] if len(ranked) > 1 else 0.0)
    band = _band(policy, top, margin)
    if top_name == "unknown" or band == "human":
        return Routing(
            decision, "unknown", dec["action"]["unknown"],
            "fallback", "human", version, top, margin, probs, latency_ms=latency,
        )
    return Routing(decision, top_name, dec["action"][top_name], "jev", band, version, top, margin, probs, latency_ms=latency)


def log_record(result: Routing, state_digest: str) -> Dict[str, Any]:
    """Content-free record for calibration: digest, probabilities, policy version, outcome."""
    return {
        "decision": result.decision,
        "state_digest": state_digest,
        "policy_version": result.policy_version,
        "source": result.source,
        "band": result.band,
        "choice": result.choice,
        "action": result.action,
        "top_prob": result.top_prob,
        "margin": result.margin,
        "probabilities": dict(result.probabilities),
        "fault": result.fault,
        "latency_ms": result.latency_ms,
    }
