"""Run the matched 15-case Nd pilot and save trial-level observations."""

import csv
from dataclasses import asdict
from math import ceil
from pathlib import Path
from random import Random

from coupled import Clock, run, save
from decisions import Disorder, SocialRing
from figures import write_figure
from movement import Corridor, Person


OUTPUT = Path(__file__).resolve().parent / "outputs" / "nd_pilot"
SEEDS = (101, 102, 103)
NDS = (1, 2, 3, 4, 8)
M, RADIUS, SIGMA = 24, 4, 0.2
INITIAL_SPAN, LENGTH, LIMIT = 48, 64, 200
H = 0.35


def observations(log, frames):
    initial = frames[0]
    movement = [f for f in frames if f.phase == "movement"]
    size = len(initial.intentions)

    def first_at(target):
        return next((f.t for f in movement if f.cumulative_exits >= target), None)

    states = [tuple(initial.intentions)] + [d["s"] for d in log["decisions"]]
    fixed_verified_n = next(
        (n for n, (before, after) in enumerate(zip(states, states[1:]), 1)
         if before == after), None
    )
    trials = [{"t": f.t, **f.counts, "cumulative_exits": f.cumulative_exits}
              for f in movement]
    before = size
    for trial in trials:
        if sum(trial[k] for k in ("intention_stop", "exclusion_stop", "move")) != before:
            raise RuntimeError("invalid trial classification total")
        before = size - trial["cumulative_exits"]
    return {
        "run_id": log["run_id"], "nd": log["settings"]["nd"],
        "dt_decision_s": log["settings"]["dt_decision_s"],
        "t90": first_at(ceil(0.9 * size)), "t_all": first_at(size),
        "trials_observed": movement[-1].t, "unreached": before,
        "fixed_verified_n": fixed_verified_n, "end_reason": log["end_reason"],
    }, trials, states


def make_sample(seed):
    ids = tuple(f"P{i:02d}" for i in range(1, M + 1))
    disorder = Disorder(0.45, 0.25, 0, 0.45, 0.7, seed)
    ring = SocialRing.sample(ids, RADIUS, SIGMA, disorder)
    init_rng = Random(seed + 1000)
    positions = sorted(init_rng.sample(range(1, INITIAL_SPAN + 1), M))
    sample = {"seed": seed, "initial_seed": seed + 1000, "social_ring": asdict(ring),
              "positions": positions, "s": tuple(init_rng.choice((-1, 1)) for _ in ids)}
    return sample, ring


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    corridor = Corridor(LENGTH, "absorbing")
    samples, rows, results = [], [], []
    for seed in SEEDS:
        sample, ring = make_sample(seed)
        initial = tuple(Person(pid, x) for pid, x in zip(ring.ids, sample["positions"]))
        initial_s = sample["s"]
        samples.append(sample)
        previous_states = []
        for nd in NDS:
            log, frames = run(f"pilot-{seed}-nd{nd}", ring, corridor, initial, initial_s,
                              Clock(nd, LIMIT, cell_length_m=1.0, dt_move_s=1.0),
                              lambda n: H)
            summary, trials, states = observations(log, frames)
            # Under a constant field, different clocks sample the same decision path.
            shared = min(len(states), len(previous_states))
            if states[:shared] != previous_states[:shared]:
                raise RuntimeError("Nd cases do not share the same underlying decision path")
            if len(states) > len(previous_states):
                previous_states = states
            row = {"seed": seed, **summary}
            rows.append(row)
            results.append({**row, "trials": trials})
    with (OUTPUT / "comparison.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    save(OUTPUT / "observations.json", {
        "settings": {"m": M, "radius": RADIUS, "sigma": SIGMA, "rho_initial": M / INITIAL_SPAN,
                     "initial_span": INITIAL_SPAN, **asdict(corridor), "limit": LIMIT,
                     "h": H, "cell_length_m": 1, "dt_move_s": 1, "nd_values": NDS,
                     "representative_seed": min(SEEDS)},
        "samples": samples, "runs": results,
    })
    arrivals, moves = [], []
    for result in results:
        if result["seed"] == min(SEEDS):
            points = [(0, 0)] + [(r["t"], r["cumulative_exits"]) for r in result["trials"]]
            if points[-1][0] < LIMIT:
                points.append((LIMIT, M))
            label = f"Nd = {result['nd']}"
            arrivals.append((label, points))
            moves.append((label, [(r["t"], r["move"]) for r in result["trials"]]))
    move_max = max(1, max(y for _, points in moves for _, y in points))
    write_figure(OUTPUT / "representative.svg", "Nd予備比較 · 安全到達",
                 f"pilot-{min(SEEDS)}-nd{{1,2,3,4,8}}  /  seed = {min(SEEDS)}",
                 [("安全到達人数（累積）", M, arrivals),
                  ("試行ごとの実移動人数", move_max, moves)], LIMIT)
    print(f"{len(results)} cases saved; {sum(r['end_reason'] == 'all_exited' for r in results)} all exited")


if __name__ == "__main__":
    main()
