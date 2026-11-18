"""Predict eventual exits from the first sampled cycle; verify by direct dynamics."""

import argparse
import csv
from itertools import islice, repeat
from math import gcd
import json
from time import perf_counter

from coupled import save
from field_comparison import FIELDS, OUTPUT as FIELD_OUTPUT, case_id, write_csv
from movement import Corridor, Person
from nd_pilot import make_sample
from transport_diagnostics import ROOT, load_pilot, recurrence, restore_sample

OUTPUT = ROOT / "outputs" / "phase_prediction"
N_LIMIT = 4096
T_LIMIT = 4096
WINDOW = 200
PRIORITY = {(102, 0.0), (102, 0.35), (101, 0.70)}


def decision_orbit(ring, initial, h, limit):
    states = []

    def capture():
        for state in islice(ring.evolve(initial, repeat(h)), limit + 1):
            states.append(state)
            yield state

    return states, recurrence(capture())


def predict(corridor, initial, states, cycle, nd):
    """Advance only the pre-cycle trials, then classify by IDs and phase signs."""
    if cycle is None:
        return {}
    start, period = cycle["transient"], cycle["period"]
    first_t = max(1, (start + nd - 1) // nd)
    people = tuple(initial)
    for t in range(1, first_t):
        people = corridor.step(people, states[t * nd]).people

    count = period // gcd(period, nd)
    phases = [(t * nd - start) % period for t in range(first_t, first_t + count)]
    vectors = [states[start + phase] for phase in phases]
    orbit_vectors = states[start:start + period]
    phase_by_vector = {vector: phase for phase, vector in enumerate(orbit_vectors)}
    # Follow transitions through the actual vectors until the first sampled vector repeats.
    sampled = []
    index = first_t * nd
    while (vector := orbit_vectors[(index - start) % period]) not in sampled:
        sampled.append(vector)
        index += nd
    if len(sampled) != count or [phase_by_vector[v] for v in sampled] != phases:
        raise RuntimeError("visited vectors disagree with the gcd phase count")

    positive = {
        p.id: [phase for phase, vector in zip(phases, vectors) if vector[i] == 1]
        for i, p in enumerate(people)
    }
    active = [p for p in people if p.active]
    negative = [p for p in active if not positive[p.id]]
    blocker = max(negative, key=lambda p: p.position, default=None)
    ahead = [p.id for p in active if blocker is None or p.position > blocker.position]
    exited = len(people) - len(active)
    return {
        "cycle_start_n": start, "period_n": period, "first_periodic_t": first_t,
        "first_periodic_n": first_t * nd, "first_phase": phases[0],
        "phase_count": count, "phases": phases, "sampled_vectors": vectors,
        "prefix_exits": exited, "prefix_positions": {p.id: p.position for p in active},
        "blocker_id": blocker.id if blocker else None,
        "blocker_cell": blocker.position if blocker else None,
        "predicted_final": exited + len(ahead), "future_exit_ids": ahead,
        "positive_phases_by_id": positive,
        "negative_only_ids": [pid for pid, signs in positive.items() if not signs],
    }


def verify(corridor, people, initial_s, update, nd, limit, window):
    """Start fresh and use only actual updates and observed joint-state recurrence."""
    people, state = tuple(people), tuple(initial_s)
    size = len(people)
    seen = {(people, state): 0}
    arrivals = [0]
    first_exit = None
    stop, repeat_from = "limit", None
    for t in range(1, limit + 1):
        for _ in range(nd):
            state = update(state)
        step = corridor.step(people, state)
        people = step.people
        arrivals.append(size - sum(p.active for p in people))
        if first_exit is None and arrivals[-1]:
            first_exit = {"t": t, "ids": [a.id for a in step.attempts if a.exited],
                          "before_exit_cells": {a.id: a.old_position for a in step.attempts if a.exited}}
        key = (people, state)
        if arrivals[-1] == size:
            stop = "all_exited"
            break
        if key in seen:
            stop, repeat_from = "joint_repeat", seen[key]
            if arrivals[repeat_from] != arrivals[-1]:
                raise RuntimeError("joint recurrence with changing number of exits")
            break
        seen[key] = t
    if stop != "limit":
        arrivals.extend([arrivals[-1]] * max(0, window + 1 - len(arrivals)))
    return {
        "verified_final": arrivals[-1] if stop != "limit" else None,
        "arrived_t200": arrivals[window] if len(arrivals) > window else None,
        "certificate": stop, "certificate_t": t, "repeat_from_t": repeat_from,
        "first_exit": first_exit,
    }, arrivals[:window + 1]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def checkpoint(path, records):
    pending = path.with_suffix(".tmp")
    save(pending, records)
    pending.replace(path)


def run_seed(sample, ring, settings, groups, existing_curves):
    seed = sample["seed"]
    directory = OUTPUT / "checkpoints"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"seed_{seed}.json"
    records = read_json(path) if path.exists() else {}
    corridor = Corridor(settings["length"], settings["boundary"])
    people = tuple(Person(pid, x) for pid, x in zip(ring.ids, sample["positions"], strict=True))
    for h in groups:
        choices = [(nd, case_id(seed, h, nd)) for nd in settings["nd_values"]]
        if all(rid in records for _, rid in choices):
            continue
        states, social = decision_orbit(ring, sample["s"], h, N_LIMIT)
        for nd, rid in choices:
            if rid in records:
                continue
            prediction = predict(corridor, people, states, social, nd)
            outcome, arrivals = verify(corridor, people, sample["s"],
                                       lambda state: ring.update(state, h), nd, T_LIMIT, WINDOW)
            if rid in existing_curves and arrivals != existing_curves[rid]["arrivals"]:
                raise RuntimeError(f"saved arrival series disagrees for {rid}")
            pred, actual = prediction.get("predicted_final"), outcome["verified_final"]
            status = "undetermined" if pred is None or actual is None else (
                "match" if pred == actual else "mismatch")
            records[rid] = {"run_id": rid, "seed": seed, "h": h, "nd": nd,
                            "roster": list(ring.ids), **prediction, **outcome, "status": status}
            checkpoint(path, records)
            if status == "mismatch":
                checkpoint(OUTPUT / f"counterexample_{rid}.json", {
                    "sample": sample, "settings": settings, "record": records[rid],
                })
    return records


def report(filename, records):
    columns = ("run_id", "seed", "h", "nd", "cycle_start_n", "period_n", "first_periodic_t",
               "first_periodic_n", "first_phase", "phase_count", "phases", "prefix_exits",
               "blocker_id", "blocker_cell", "predicted_final", "verified_final", "arrived_t200",
               "certificate", "certificate_t", "repeat_from_t", "status")
    rows = []
    for record in sorted(records, key=lambda r: (r["seed"], r["h"], r["nd"])):
        row = {key: record.get(key) for key in columns}
        row["phases"] = " ".join(map(str, row["phases"] or []))
        first = record["first_exit"]
        row["first_exit_t"] = first["t"] if first else None
        row["first_exit_ids"] = " ".join(first["ids"]) if first else ""
        rows.append(row)
    write_csv(OUTPUT / filename, rows)
    counts = {key: sum(r["status"] == key for r in records)
              for key in ("match", "mismatch", "undetermined")}
    print(filename, len(records), counts)
    return counts


def main(stage):
    pilot = load_pilot()
    settings = pilot["settings"]
    existing_curves = read_json(FIELD_OUTPUT / "series.json")
    if stage in ("priority", "existing"):
        records = []
        for sample in pilot["samples"]:
            seed = sample["seed"]
            groups = [h for h in FIELDS if stage == "existing" or (seed, h) in PRIORITY]
            if groups:
                saved = run_seed(sample, restore_sample(sample), settings, groups, existing_curves)
                records.extend(r for r in saved.values() if r["h"] in groups)
        report(f"{stage}.csv", records)
        return

    records = []
    for seed in range(104, 112):
        path = OUTPUT / "checkpoints" / f"seed_{seed}.json"
        start = perf_counter()
        sample, ring = make_sample(seed)
        complete = path.exists() and len(read_json(path)) == len(FIELDS) * len(settings["nd_values"])
        saved = run_seed(sample, ring, settings, FIELDS, {})
        if seed == 104 and not complete and not (OUTPUT / "benchmark.json").exists():
            save(OUTPUT / "benchmark.json", {
                "seed": seed, "conditions": len(saved), "wall_seconds": perf_counter() - start,
                "checkpoint_bytes": path.stat().st_size,
                "note": "Elapsed time includes generation, prediction, verification and checkpoint writes.",
            })
        records.extend(saved.values())
    counts = report("new_seeds.csv", records)
    sensitivity = []
    for h in FIELDS:
        groups = [[r["verified_final"] for r in records if r["seed"] == seed and r["h"] == h]
                  for seed in range(104, 112)]
        complete = [group for group in groups if len(group) == 5 and None not in group]
        sensitivity.append({"h": h, "changed": sum(len(set(g)) > 1 for g in complete),
                            "complete_seeds": len(complete), "total_seeds": len(groups)})
    save(OUTPUT / "new_summary.json", {"counts": counts, "paired_sensitivity": sensitivity})
    print(sensitivity)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("priority", "existing", "new"))
    main(parser.parse_args().stage)
