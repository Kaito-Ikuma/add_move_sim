"""Generate or replay the small absorbing-boundary example."""

import argparse
from pathlib import Path

from movement import Corridor, Person
from trajectory import read_run, write_run


SAMPLE_PATH = Path(__file__).with_name("sample_trajectory.json")
CORRIDOR = Corridor(5, "absorbing")
INITIAL = (Person("A", 2), Person("B", 4), Person("C", 5))
# The columns always refer to A, B, C, including after an exit.
SCHEDULE = (
    (-1, 1, 1),
    (1, 1, -1),
    (1, -1, 1),
    (1, 1, -1),
    (1, -1, 1),
    (1, 1, -1),
)
INTENTION_SOURCE = "検算用に外部から指定した意思列"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay", action="store_true", help="read the saved example")
    args = parser.parse_args()

    if not args.replay:
        runtime = write_run(
            SAMPLE_PATH, CORRIDOR, INITIAL, SCHEDULE, intention_source=INTENTION_SOURCE
        )
    replay = read_run(SAMPLE_PATH)
    if not args.replay and runtime != replay:
        raise RuntimeError("保存ログと実行時の軌道が一致しません")

    for frame in replay:
        positions = ", ".join(f"{pid}={pos}" for pid, pos in frame.positions.items()) or "なし"
        counts = frame.counts
        classification = "初期配置" if counts is None else (
            f"意思停止 {counts['intention_stop']}、排他停止 {counts['exclusion_stop']}、"
            f"移動 {counts['move']}"
        )
        print(f"t={frame.time} | 在系 {positions} | {classification} | 累積退出 {frame.cumulative_exits}")


if __name__ == "__main__":
    main()
