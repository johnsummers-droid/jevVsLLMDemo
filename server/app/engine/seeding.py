"""Deterministic per-call seeds (plan1.txt D6, refined by t4-plan.txt decision 1).

The seed covers the run seed, the ticket, the node type, the params the provider actually sees
and the node's input values with their taint. Node ids are not part of it, so two teams with the
same node, params and inputs get the same draws. Params applied after the provider call (such as
the router's threshold) must stay out, so that changing them never redraws the decision.
Python's hash() is never used: it is salted per process.
"""

import hashlib
import json
import random
from typing import Any

from app.models import PortValue


def _fingerprint_inputs(inputs: dict[str, PortValue]) -> dict[str, Any]:
    # Taint is a set; sort it so the JSON does not depend on set iteration order.
    return {port: {"type": v.type, "value": v.value, "taint": sorted(v.taint)}
            for port, v in inputs.items()}


def derive_seed(run_seed: int, ticket_id: str, node_type: str, seed_params: dict[str, Any],
                inputs: dict[str, PortValue], stream: str = "decision") -> int:
    payload = json.dumps(
        {"run_seed": run_seed, "ticket": ticket_id, "node": node_type, "params": seed_params,
         "inputs": _fingerprint_inputs(inputs), "stream": stream},
        sort_keys=True, separators=(",", ":"), default=str,
    )
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")


def seeded_rng(*args: Any, **kwargs: Any) -> random.Random:
    """A random.Random seeded by derive_seed(*args, **kwargs)."""
    return random.Random(derive_seed(*args, **kwargs))
