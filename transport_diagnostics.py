"""Reconstruct the saved pilot and trace where differences first appear."""

import csv
import json
from dataclasses import dataclass
from itertools import repeat
from pathlib import Path

from coupled import Clock, run, save
from decisions import Disorder, Link, SocialRing
from movement import Corridor, Person, REASONS
from nd_pilot import observations


ROOT = Path(__file__).resolve().parent
PILOT = ROOT / "outputs" / "nd_pilot"
OUTPUT = ROOT / "outputs" / "transport_diagnostics"
AGREE = "観測窓内で一致"


@dataclass(frozen=True)
class Case:
    log: dict
    frames: list
    summary: dict
    trials: list
    states: list

    @property
    def movement_frames(self):
        return [f for f in self.frames if f.phase != "decision"]


def load_pilot():
    data = json.loads((PILOT / "observations.json").read_text())
    with (PILOT / "comparison.csv").open(newline="") as stream:
        table = {row["run_id"]: row for row in csv.DictReader(stream)}
    for recorded in data["runs"]:
        row = table.pop(recorded["run_id"])
        for key, value in recorded.items():
            if key != "trials" and row[key] != ("" if value is None else str(value)):
                raise ValueError(f"original CSV and JSON disagree: {row['run_id']} {key}")
    if table:
        raise ValueError("extra pilot CSV conditions")
    return data


def restore_sample(sample):
    values = sample["social_ring"]
    return SocialRing(
        tuple(values["ids"]), values["radius"], values["sigma"], tuple(values["mu"]),
        tuple(values["phi"]), tuple(tuple(Link(**link) for link in row) for row in values["links"]),
        values["sigma_j"], Disorder(**values["disorder"]),
    )


def calculate(data, sample, h, nd, run_id):
    settings = data["settings"]
    ring = restore_sample(sample)
    people = tuple(Person(pid, x) for pid, x in zip(ring.ids, sample["positions"], strict=True))
    clock = Clock(nd, settings["limit"], settings["cell_length_m"], settings["dt_move_s"])
    log, frames = run(run_id, ring, Corridor(settings["length"], settings["boundary"]),
                      people, sample["s"], clock, lambda n: h)
    summary, trials, states = observations(log, frames)
    return Case(log, frames, summary, trials, states)


def recurrence(states):
    first = {}
    for time, state in enumerate(states):
        if state in first:
            return {"transient": first[state], "period": time - first[state], "repeat_at": time}
        first[state] = time
    return None


def verify_social(sample, h, cases):
    last = max(len(c.states) for c in cases.values())
    path = list(restore_sample(sample).evolve(sample["s"], repeat(h, last - 1)))
    for case in cases.values():
        if case.states != path[:len(case.states)]:
            raise RuntimeError(f"decision history mismatch: {case.summary['run_id']}")
    return path


def physical_cycle(frames, social):
    if social is None:
        return None
    start, period = social["transient"], social["period"]
    offset = next((f.t for f in frames if f.n >= start), len(frames))
    keys = [((f.n - start) % period, tuple(sorted(f.positions.items()))) for f in frames[offset:]]
    cycle = recurrence(keys)
    if cycle is None:
        return None
    cycle_start = cycle["transient"] + offset
    positions = [positions for _, positions in keys[cycle["transient"]:cycle["repeat_at"]]]
    if any(p != positions[0] for p in positions):
        raise RuntimeError("absorbing right-only corridor repeated with movement")
    first_constant = cycle_start
    while first_constant and frames[first_constant - 1].positions == frames[cycle_start].positions:
        first_constant -= 1
    return {"joint_repeat_t": cycle["repeat_at"] + offset, "joint_period_t": cycle["period"],
            "physical_period_t": 1, "physical_transient_t": first_constant}


def first_differences(cases):
    fields = {
        "used_s": lambda row: row["s"],
        "classification": lambda row: row["reason"],
        "position": lambda row: row["new_position"] if row["active_after"] else None,
        "exit_event": lambda row: row["exited"],
    }
    result = dict.fromkeys((*fields, "classification_counts"), AGREE)
    grouped = [case.log["trials"] for case in cases.values()]
    for trials in zip(*grouped, strict=True):
        t = trials[0]["t"]
        for name, extract in fields.items():
            if result[name] != AGREE:
                continue
            details = {}
            for people in zip(*(trial["people"] for trial in trials), strict=True):
                values = [extract(row) for row in people]
                if len(set(values)) > 1:
                    details[people[0]["id"]] = dict(zip(cases, values))
            if details:
                result[name] = {"t": t, "ids": list(details), "by_id_and_nd": details}
        counts = {nd: case.trials[t - 1] for nd, case in cases.items()}
        signatures = {tuple(row[key] for key in REASONS) for row in counts.values()}
        if result["classification_counts"] == AGREE and len(signatures) > 1:
            changed = [
                rows[0]["id"] for rows in zip(*(trial["people"] for trial in trials), strict=True)
                if len({row["reason"] for row in rows}) > 1
            ]
            result["classification_counts"] = {
                "t": t, "ids": changed,
                "by_nd": {nd: {key: row[key] for key in REASONS} for nd, row in counts.items()},
            }
    return result


def obstruction(case, social):
    frames = case.movement_frames
    final = frames[-1]
    final_order = sorted(final.positions, key=final.positions.get)
    lead = final_order[-1]
    first_final_queue = next(f.t for f in frames if f.positions == final.positions)
    last_exit = max((trial["t"] for trial in case.log["trials"]
                     if any(row["exited"] for row in trial["people"])), default=None)
    history = []
    for trial in case.log["trials"]:
        by_id = {row["id"]: row for row in trial["people"]}
        row = by_id[lead]
        history.append({"t": trial["t"], "s": row["s"], "reason": row["reason"],
                        "old": row["old_position"], "new": row["new_position"],
                        "rear_exclusion": sum(
                            other["reason"] == "exclusion_stop"
                            and other["old_position"] < row["old_position"]
                            for other in by_id.values())})
    nd = case.summary["nd"]
    cycle = physical_cycle(frames, social)
    phases = None
    if social:
        start, period = social["transient"], social["period"]
        start_t = max(1, (start + nd - 1) // nd)
        phases = {"first_t": start_t, "sampled_phase_order": list(dict.fromkeys(
            (nd * t - start) % period for t in range(start_t, start_t + period)))}
    exit_ids = ([] if last_exit is None else [row["id"] for row in
                case.log["trials"][last_exit - 1]["people"] if row["exited"]])
    return {"last_exit_t": last_exit, "last_exit_ids": exit_ids, "lead_id": lead, "lead_final_cell": final.positions[lead],
            "final_queue_t": first_final_queue, "final_order_back_to_front": final_order,
            "final_positions": final.positions,
            "final_s": dict(zip(case.log["social_ring"]["ids"], final.intentions)),
            "lead_history": history, "social_sampling": phases, "physical_cycle": cycle}


def plot_trajectories(path, cases, seed, h, horizon=75):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    fig, axes = plt.subplots(len(cases), 1, figsize=(12, 2.75 * len(cases)), sharex=True,
                             squeeze=False, layout="constrained")
    for ax, (nd, case) in zip(axes[:, 0], cases.items()):
        length = case.log["settings"]["length"]
        records = case.log["trials"][:horizon]
        points = {p["id"]: [(0, p["position"])] for p in case.log["initial"]["people"]}
        marks = {key: [] for key in (*REASONS, "exit")}
        for trial in records:
            for row in trial["people"]:
                if row["active_before"]:
                    xy = (trial["t"], row["new_position"])
                    points[row["id"]].append(xy)
                    marks["exit" if row["exited"] else row["reason"]].append(xy)
        for i, (pid, track) in enumerate(points.items()):
            tx, y = zip(*track)
            ax.step(tx, y, where="post", color=plt.cm.tab20(i % 20), lw=0.85, alpha=0.72)
            ax.text(tx[-1] + 0.65, y[-1], pid, fontsize=6, va="center")
        for key, marker, color in (("intention_stop", "o", "#a4392c"),
                                   ("exclusion_stop", "x", "#3159a6"), ("exit", "^", "#08604d")):
            if marks[key]:
                x, y = zip(*marks[key])
                ax.scatter(x, y, s=8, marker=marker, color=color, linewidths=0.6)
        ax.axhline(length + 1, color="#08604d", alpha=0.28)
        ax.set(ylim=(0, length + 4), xlim=(0, horizon + 5), ylabel=f"Cell / Nd={nd}")
        ax.grid(alpha=0.15)
    axes[-1, 0].set_xlabel("Movement trial t (seconds)")
    markers = [Line2D([], [], marker=shape, color=color, linestyle="", label=label)
               for shape, color, label in (("o", "#a4392c", "Intention stop"),
                                          ("x", "#3159a6", "Exclusion stop"),
                                          ("^", "#08604d", "Exit"))]
    axes[0, 0].legend(handles=markers, loc="lower right", ncol=3, fontsize=8)
    fig.suptitle(f"Individual trajectories | seed {seed} | h={h:g} | t=0–{horizon}")
    fig.savefig(path)
    plt.close(fig)


def diagnose():
    data = load_pilot()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    result = {}
    h = data["settings"]["h"]
    for sample in data["samples"]:
        seed = sample["seed"]
        cases = {}
        for saved in (row for row in data["runs"] if row["seed"] == seed):
            nd = saved["nd"]
            case = calculate(data, sample, h, nd, saved["run_id"])
            if case.trials != saved["trials"] or any(saved[k] != v for k, v in case.summary.items()):
                raise RuntimeError(f"original pilot does not match: {saved['run_id']}")
            cases[nd] = case
        path = verify_social(sample, h, cases)
        cycle = recurrence(path)
        result[seed] = {
            "first_differences": first_differences(cases),
            "social_cycle": cycle or "周期未確認",
            "cycle_states": path[cycle["transient"]:cycle["repeat_at"]] if cycle else [],
            "ids": list(cases[1].log["social_ring"]["ids"]),
            "by_nd": {nd: obstruction(case, cycle) for nd, case in cases.items()},
            "exited": cases[1].trials[-1]["cumulative_exits"],
        }
        if seed == 102:
            plot_trajectories(OUTPUT / "pilot_102_trajectories.svg", cases, seed, h, 55)
    save(OUTPUT / "diagnostics.json", result)
    print("15 pilot conditions reproduced; all 3,000 trial totals match")


if __name__ == "__main__":
    diagnose()
