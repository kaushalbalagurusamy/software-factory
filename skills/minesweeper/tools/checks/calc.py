#!/usr/bin/env python3
"""Back-of-envelope physics, so the model never does arithmetic in its head.

Every function is pure and takes its inputs explicitly. Nothing here carries a recalled price,
benchmark or hardware figure: anything that varies by vendor or date is a required argument.

CLI: python3 tools/checks/calc.py <check> key=value ...
     e.g. calc.py memory frames=5 width=8000 height=6000 channels=4 bytes_per_channel=4
"""
from __future__ import annotations

import json
import math
import sys

GB = 1e9  # decimal gigabyte, as storage and network vendors quote


def memory(frames: int, width: int, height: int, channels: int, bytes_per_channel: float) -> dict:
    """Resident bytes for `frames` uncompressed images held at once."""
    per_frame = width * height * channels * bytes_per_channel
    total = frames * per_frame
    return {"bytes_per_frame": per_frame, "bytes": total, "gb": total / GB}


def bandwidth(width: int, height: int, channels: int, bytes_per_channel: float, fps: float) -> dict:
    """Uncompressed stream rate."""
    bps = width * height * channels * bytes_per_channel * fps
    return {"bytes_per_s": bps, "gb_per_s": bps / GB, "gbit_per_s": bps * 8 / GB}


def fanout_tail(p_fast: float, n: int) -> dict:
    """Chance a request that waits on n independent calls hits at least one slow call.

    p_fast is the probability one call is within its percentile (0.99 for p99)."""
    if not 0 <= p_fast <= 1 or n < 1:
        raise ValueError("p_fast in [0,1], n >= 1")
    p_any_slow = 1 - p_fast ** n
    return {"p_any_slow": p_any_slow, "percent": 100 * p_any_slow}


def bft_quorum(f: int) -> dict:
    """Byzantine fault tolerance: n >= 3f+1 replicas, quorums of 2f+1."""
    if f < 0:
        raise ValueError("f >= 0")
    return {"min_replicas": 3 * f + 1, "quorum": 2 * f + 1, "tolerates": f}


def bft_tolerates(n: int) -> dict:
    """Largest f a BFT protocol tolerates with n replicas."""
    f = max((n - 1) // 3, 0)
    return {"replicas": n, "max_faulty": f, "quorum": 2 * f + 1}


def cft_quorum(f: int) -> dict:
    """Crash fault tolerance (Paxos/Raft): n >= 2f+1 replicas, majority quorums of f+1."""
    if f < 0:
        raise ValueError("f >= 0")
    return {"min_replicas": 2 * f + 1, "quorum": f + 1, "tolerates": f}


def egress_cost(gb: float, price_per_gb: float) -> dict:
    """Transfer cost. price_per_gb must come from the provider's current price page, cited."""
    return {"gb": gb, "price_per_gb": price_per_gb, "cost": gb * price_per_gb}


def payload_mtu(payload_bytes: int, mtu: int = 1500, header_bytes: int = 28) -> dict:
    """Packets needed for one payload. Default header is IPv4 (20) + UDP (8)."""
    room = mtu - header_bytes
    if room <= 0:
        raise ValueError("mtu must exceed header_bytes")
    packets = max(1, math.ceil(payload_bytes / room))
    return {"packets": packets, "fragmented": packets > 1, "room_per_packet": room}


def birthday_collision(bits: int, items: float) -> dict:
    """Approximate collision probability for `items` random values of `bits` bits
    (random nonces or ids): 1 - exp(-k^2 / 2^(bits+1))."""
    p = -math.expm1(-(items ** 2) / (2.0 ** (bits + 1)))
    return {"bits": bits, "items": items, "p_collision": p}


FUNCS = {
    "memory": memory,
    "bandwidth": bandwidth,
    "fanout_tail": fanout_tail,
    "bft_quorum": bft_quorum,
    "bft_tolerates": bft_tolerates,
    "cft_quorum": cft_quorum,
    "egress_cost": egress_cost,
    "payload_mtu": payload_mtu,
    "birthday_collision": birthday_collision,
}


def _num(v: str):
    try:
        return int(v)
    except ValueError:
        return float(v)


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in FUNCS:
        print("checks: " + ", ".join(FUNCS), file=sys.stderr)
        return 2
    kwargs = dict(a.split("=", 1) for a in argv[1:])
    print(json.dumps(FUNCS[argv[0]](**{k: _num(v) for k, v in kwargs.items()}), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
