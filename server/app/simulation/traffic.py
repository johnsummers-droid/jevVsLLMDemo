"""Arrival schedule for a run (t5-plan.txt decision 5).

The whole pack arrives over the window in a seeded shuffled order, one request per equal slot
with seeded jitter inside the slot. traffic_spike repeats the pack's tickets up to
round(n x spike) requests; injection_wave adds one more copy of every injection ticket.
"""

from dataclasses import dataclass

from app.engine.seeding import seeded_rng
from app.models import RunConfig, ScenarioPack, Ticket


@dataclass(frozen=True)
class Arrival:
    request_id: str
    arrival_ms: float
    ticket: Ticket


def window_ms(config: RunConfig) -> float:
    """The arrival window in simulated ms: duration_s of wall-clock time at the run's speed."""
    return config.duration_s * 1000 * config.speed


def schedule(pack: ScenarioPack, config: RunConfig) -> list[Arrival]:
    tickets = pack.tickets
    count = max(1, round(len(tickets) * config.traffic_spike))
    chosen = [tickets[i % len(tickets)] for i in range(count)]
    if config.injection_wave:
        chosen += [t for t in tickets if t.category == "prompt_injection"]
    rng = seeded_rng(config.seed, pack.id, "traffic", {"spike": config.traffic_spike,
                                                       "wave": config.injection_wave}, {})
    rng.shuffle(chosen)
    slot = window_ms(config) / len(chosen)
    return [Arrival(request_id=f"r{i:04d}", arrival_ms=i * slot + rng.uniform(0, slot),
                    ticket=ticket)
            for i, ticket in enumerate(chosen)]
