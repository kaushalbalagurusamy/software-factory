"""Retry/escalation policy: built-in defaults, overridable in .sf/policy.yaml."""
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

ENV_PATTERNS = (
    r"\bENOSPC\b", r"no space left on device", r"\bout of memory\b", r"\bOOM\b", r"MemoryError",
    r"cannot allocate memory", r"killed by signal", r"\bSIGKILL\b", r"\bsignal 9\b", r"\bKilled\b",
    r"timed out", r"\btimeout\b", r"TimeoutExpired", r"\bETIMEDOUT\b", r"\bEADDRINUSE\b",
    r"address already in use", r"port \d+ (?:is )?(?:already )?in use", r"command not found",
    r"executable file not found", r"not recognized as an internal or external command",
)

DEFAULTS = {
    "attempts_per_signature": 4,
    "tiers": ["sonnet", "sonnet", "opus", "opus"],
    "slice_attempt_cap": 10,
    "budget": {"tokens": None, "cost_usd": None},
    "flake_reruns": 1,
    "environment": {"patterns": list(ENV_PATTERNS), "wait_max": 5},
    "escalation": {"min_samples": 5, "escalate_below": 0.2, "hold_above": 0.8},
}


class PolicyError(Exception):
    pass


@dataclass(frozen=True)
class Policy:
    attempts_per_signature: int
    tiers: tuple
    slice_attempt_cap: int
    budget_tokens: object
    budget_cost_usd: object
    flake_reruns: int
    env_patterns: tuple
    env_wait_max: int
    min_samples: int
    escalate_below: float
    hold_above: float

    def is_environment(self, text: str) -> bool:
        return any(re.search(p, text or "", re.I if p.islower() or " " in p else 0) for p in self.env_patterns)

    def as_dict(self) -> dict:
        return {
            "attempts_per_signature": self.attempts_per_signature, "tiers": list(self.tiers),
            "slice_attempt_cap": self.slice_attempt_cap,
            "budget": {"tokens": self.budget_tokens, "cost_usd": self.budget_cost_usd},
            "flake_reruns": self.flake_reruns,
            "environment": {"patterns": list(self.env_patterns), "wait_max": self.env_wait_max},
            "escalation": {"min_samples": self.min_samples, "escalate_below": self.escalate_below,
                           "hold_above": self.hold_above},
        }


def _merge(base: dict, over: dict, path="") -> dict:
    out = dict(base)
    for k, v in over.items():
        if k not in base:
            raise PolicyError(f"unknown policy key {path}{k}")
        if isinstance(base[k], dict):
            if not isinstance(v, dict):
                raise PolicyError(f"{path}{k} must be a mapping")
            out[k] = _merge(base[k], v, f"{path}{k}.")
        else:
            out[k] = v
    return out


def _int(v, name, minimum):
    if isinstance(v, bool) or not isinstance(v, int) or v < minimum:
        raise PolicyError(f"{name} must be an integer >= {minimum}")
    return v


def _opt_num(v, name):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v <= 0:
        raise PolicyError(f"{name} must be a positive number or null")
    return v


def _rate(v, name):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 1:
        raise PolicyError(f"{name} must be between 0 and 1")
    return float(v)


def load_policy(root) -> Policy:
    f = Path(root) / ".sf" / "policy.yaml"
    over = {}
    if f.is_file():
        try:
            over = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as e:
            raise PolicyError(f"{f}: invalid YAML: {e}") from e
        if not isinstance(over, dict):
            raise PolicyError(f"{f}: top level must be a mapping")
    d = _merge(DEFAULTS, over)
    tiers = d["tiers"]
    if not isinstance(tiers, list) or not tiers or not all(isinstance(t, str) and t for t in tiers):
        raise PolicyError("tiers must be a non-empty list of names")
    pats = d["environment"]["patterns"]
    if not isinstance(pats, list) or not all(isinstance(p, str) for p in pats):
        raise PolicyError("environment.patterns must be a list of regexes")
    for p in pats:
        try:
            re.compile(p)
        except re.error as e:
            raise PolicyError(f"environment.patterns: bad regex {p!r}: {e}") from e
    e = d["escalation"]
    return Policy(
        attempts_per_signature=_int(d["attempts_per_signature"], "attempts_per_signature", 1),
        tiers=tuple(tiers),
        slice_attempt_cap=_int(d["slice_attempt_cap"], "slice_attempt_cap", 1),
        budget_tokens=_opt_num(d["budget"]["tokens"], "budget.tokens"),
        budget_cost_usd=_opt_num(d["budget"]["cost_usd"], "budget.cost_usd"),
        flake_reruns=_int(d["flake_reruns"], "flake_reruns", 0),
        env_patterns=tuple(pats),
        env_wait_max=_int(d["environment"]["wait_max"], "environment.wait_max", 1),
        min_samples=_int(e["min_samples"], "escalation.min_samples", 1),
        escalate_below=_rate(e["escalate_below"], "escalation.escalate_below"),
        hold_above=_rate(e["hold_above"], "escalation.hold_above"),
    )
