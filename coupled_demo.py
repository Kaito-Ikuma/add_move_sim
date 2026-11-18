"""Run the small case, or export solely from an existing coupled log."""

import argparse
from dataclasses import asdict
import json
from pathlib import Path

from coupled import Clock, replay, run, save
from decisions import SocialRing
from figures import write_figure
from movement import Corridor, Person


ROOT = Path(__file__).resolve().parent
DEMO = ROOT / "outputs" / "demo"
LABELS = {"intention_stop": "意思停止", "exclusion_stop": "排他停止", "move": "実移動"}


def make_log(path):
    ids = ("A", "B", "C", "D", "E")
    # A and B alternate by copying each other; C, D, E have constant positive fields.
    ring = SocialRing.from_values(ids, 1, 0.2, (0,) * 5, (0, 0, -1, -1, -1),
                                  ((0, 2), (2, 0), (0, 0), (0, 0), (0, 0)), 1)
    people = tuple(Person(pid, x) for pid, x in zip(ids, (2, 3, 4, 6, 8)))
    log, original = run("demo-coupled-01", ring, Corridor(8, "absorbing"), people,
                        (-1, 1, -1, 1, 1), Clock(3, 24), lambda n: 0)
    save(path, log)
    _, restored = replay(path)
    if restored != original:
        raise RuntimeError("saved history differs from the calculated frames")
    print(f"{log['run_id']}: {len(restored)} frames match; {log['end_reason']}")


def export(path, directory):
    log, frames = replay(path)
    ids = log["social_ring"]["ids"]
    run_id = log["run_id"]
    exit_ids = {trial["t"]: [p["id"] for p in trial["people"] if p["exited"]]
                for trial in log["trials"]}
    data = {
        "run_id": run_id, "ids": ids, "length": log["settings"]["length"],
        "frames": [{**asdict(f), "exit_ids": exit_ids[f.t] if f.phase == "movement" else []}
                   for f in frames],
    }
    payload = json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    template = (ROOT / "presentation_template.html").read_text(encoding="utf-8")
    (directory / "replay.html").write_text(template.replace("__REPLAY_DATA__", payload),
                                          encoding="utf-8")
    movements = [f for f in frames if f.phase == "movement"]
    panels = [
        ("安全到達人数（累積）", len(ids),
         [("累積退出", [(0, 0)] + [(f.t, f.cumulative_exits) for f in movements])]),
        ("移動試行直前の在系者の分類（人）", len(ids),
         [(label, [(f.t, f.counts[key]) for f in movements]) for key, label in LABELS.items()]),
    ]
    write_figure(directory / "research.svg", "安全到達と移動の三分類",
                 f"run_id: {run_id}  /  Nd = {log['settings']['nd']}", panels, movements[-1].t)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-only", action="store_true")
    parser.add_argument("--mp4", action="store_true")
    args = parser.parse_args()
    DEMO.mkdir(parents=True, exist_ok=True)
    path = DEMO / "coupled_trajectory.json"
    if not args.replay_only:
        make_log(path)
    data = export(path, DEMO)
    if args.mp4:
        from video_export import write_mp4
        write_mp4(DEMO / "replay.mp4", data)


if __name__ == "__main__":
    main()
