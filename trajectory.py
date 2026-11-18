"""Write and replay movement trajectories using only the Python standard library."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Sequence

from movement import REASONS, Corridor, Person


@dataclass(frozen=True)
class Frame:
    time: int
    positions: dict[str, int]
    counts: dict[str, int] | None
    cumulative_exits: int


def active_positions(people: Sequence[Person]) -> dict[str, int]:
    return {person.id: person.position for person in people if person.active}


def write_run(
    path: Path,
    corridor: Corridor,
    initial: Sequence[Person],
    intention_schedule: Iterable[Sequence[int]],
    *,
    intention_source: str,
) -> list[Frame]:
    """Run the supplied schedule, write all attempts, and return runtime frames."""
    initial_people = tuple(initial)
    if any(not person.active for person in initial_people):
        raise ValueError("all people must be active at time zero")

    people = initial_people
    trials = []
    frames = [Frame(0, active_positions(people), None, 0)]
    cumulative_exits = 0
    for time, intentions in enumerate(intention_schedule, start=1):
        step = corridor.step(people, intentions)
        people = step.people
        cumulative_exits += sum(attempt.exited for attempt in step.attempts)
        frames.append(Frame(time, active_positions(people), step.counts, cumulative_exits))
        trials.append({"time": time, "people": [asdict(attempt) for attempt in step.attempts]})

    log = {
        "format_version": 1,
        "settings": {**asdict(corridor), "intention_source": intention_source},
        "initial": [asdict(person) for person in initial_people],
        "trials": trials,
    }
    path.write_text(json.dumps(log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return frames


def read_run(path: Path) -> list[Frame]:
    """Reconstruct frames from saved positions, reasons, and exit events."""
    log = json.loads(path.read_text(encoding="utf-8"))
    if log["format_version"] != 1:
        raise ValueError("unsupported trajectory format")

    initial_positions = {person["id"]: person["position"] for person in log["initial"]}
    frames = [Frame(0, initial_positions, None, 0)]
    cumulative_exits = 0
    for trial in log["trials"]:
        positions = {}
        counts = dict.fromkeys(REASONS, 0)
        for row in trial["people"]:
            if row["active_after"]:
                positions[row["id"]] = row["new_position"]
            if row["active_before"]:
                counts[row["reason"]] += 1
            cumulative_exits += row["exited"]
        frames.append(Frame(trial["time"], positions, counts, cumulative_exits))
    return frames
