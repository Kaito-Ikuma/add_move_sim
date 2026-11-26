"""Coupled trial clock and lossless JSON logging/replay."""

import json
from dataclasses import asdict, dataclass
from itertools import count
from math import isfinite
from pathlib import Path
from typing import Callable, Sequence

from decisions import SocialRing
from movement import REASONS, Corridor, Person
from trajectory import active_positions


@dataclass(frozen=True)
class Clock:
    nd: int
    limit: int
    cell_length_m: float = 1.0
    dt_move_s: float = 1.0

    def __post_init__(self):
        if any(type(x) is not int or x < 1 for x in (self.nd, self.limit)):
            raise ValueError("nd and limit must be positive integers")
        if any(not isfinite(x) or x <= 0 for x in (self.cell_length_m, self.dt_move_s)):
            raise ValueError("physical scales must be finite and positive")


@dataclass(frozen=True)
class CoupledFrame:
    n: int
    t: int
    phase: str
    intentions: tuple[int, ...]
    positions: dict[str, int]
    counts: dict[str, int] | None
    cumulative_exits: int


def run(run_id: str, ring: SocialRing, corridor: Corridor, initial: Sequence[Person],
        initial_s: Sequence[int], clock: Clock, field_at: Callable[[int], float],
        *, stop_when_empty: bool = True):
    people, state = tuple(initial), tuple(initial_s)
    if tuple(p.id for p in people) != ring.ids or any(not p.active for p in people):
        raise ValueError("initial roster must match the active social ring in ID order")
    ring.validate_state(state)
    positions = active_positions(people)
    frames = [CoupledFrame(0, 0, "initial", state, positions, None, 0)]
    updates, trials = [], []
    numbers = count(1)
    exits = 0
    reason = "observation_limit"
    for t in range(1, clock.limit + 1):
        for _ in range(clock.nd):
            n = next(numbers)
            h = field_at(n)
            state = ring.update(state, h)
            updates.append({"n": n, "t": t, "h": h, "s": state})
            frames.append(CoupledFrame(n, t, "decision", state, positions, None, exits))
        step = corridor.step(people, state)
        people = step.people
        positions = active_positions(people)
        exits = len(ring.ids) - len(positions)
        trials.append({"n": n, "t": t, "people": [asdict(row) for row in step.attempts]})
        frames.append(CoupledFrame(n, t, "movement", state, positions, step.counts, exits))
        if stop_when_empty and exits == len(ring.ids):
            reason = "all_exited"
            break
    log = {
        "format_version": 2, "run_id": run_id, "social_ring": asdict(ring),
        "settings": {**asdict(clock), **asdict(corridor),
                     "dt_decision_s": clock.dt_move_s / clock.nd},
        "initial": {"people": [asdict(p) for p in initial], "s": tuple(initial_s)},
        "decisions": updates, "trials": trials, "end_reason": reason,
    }
    return log, frames


def save(path: Path, log):
    path.write_text(json.dumps(log, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                    encoding="utf-8")


def replay(path: Path):
    """Reconstruct every frame by reading records, without running either model."""
    log = json.loads(path.read_text(encoding="utf-8"))
    if log["format_version"] != 2:
        raise ValueError("expected coupled log format 2")
    initial = log["initial"]
    positions = {p["id"]: p["position"] for p in initial["people"]}
    exits = 0
    frames = [CoupledFrame(0, 0, "initial", tuple(initial["s"]), positions, None, exits)]
    trials = iter(log["trials"])
    trial = next(trials, None)
    for update in log["decisions"]:
        n, t, state = update["n"], update["t"], tuple(update["s"])
        frames.append(CoupledFrame(n, t, "decision", state, positions, None, exits))
        if trial is not None and n == trial["n"]:
            if t != trial["t"] or state != tuple(row["s"] for row in trial["people"]):
                raise ValueError("movement and last decision disagree")
            positions = {}
            counts = dict.fromkeys(REASONS, 0)
            for row in trial["people"]:
                if row["active_after"]:
                    positions[row["id"]] = row["new_position"]
                if row["active_before"]:
                    counts[row["reason"]] += 1
                exits += row["exited"]
            frames.append(CoupledFrame(n, t, "movement", state, positions, counts, exits))
            trial = next(trials, None)
    if trial is not None:
        raise ValueError("unmatched movement trial")
    return log, frames
