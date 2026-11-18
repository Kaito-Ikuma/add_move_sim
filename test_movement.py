import json
import tempfile
import unittest
from fractions import Fraction
from pathlib import Path

from movement import Corridor, Person
from sample_run import CORRIDOR, INITIAL, INTENTION_SOURCE, SCHEDULE
from trajectory import Frame, read_run, write_run


class MovementTests(unittest.TestCase):
    def test_adjacent_people_use_old_occupancy(self):
        people = (Person("left", 1), Person("right", 2))
        step = Corridor(3, "periodic").step(people, [1, 1])
        self.assertEqual(step.people, (Person("left", 1), Person("right", 3)))
        self.assertEqual(
            [attempt.reason for attempt in step.attempts], ["exclusion_stop", "move"]
        )

    def test_exit_blocks_follower_for_the_same_trial(self):
        corridor = Corridor(4, "absorbing")
        people = (Person("rear", 3), Person("front", 4))
        intentions = [1, 1]
        first = corridor.step(people, intentions)
        self.assertEqual(intentions, [1, 1])
        self.assertEqual(first.people, (Person("rear", 3), Person("front", 5, False)))
        self.assertEqual(first.attempts[0].reason, "exclusion_stop")
        self.assertEqual(first.attempts[1].new_position, 5)
        self.assertTrue(first.attempts[1].exited)
        self.assertEqual(first.counts["move"], 1)

        intentions[1] = -1
        second = corridor.step(first.people, intentions)
        self.assertEqual(intentions, [1, -1])
        self.assertEqual(second.people, (Person("rear", 4), Person("front", 5, False)))
        outside = second.attempts[1]
        self.assertEqual((outside.id, outside.s, outside.reason), ("front", -1, "outside"))
        self.assertEqual((outside.active_before, outside.active_after, outside.exited),
                         (False, False, False))
        self.assertEqual((outside.old_position, outside.new_position), (None, None))

    def test_periodic_flows(self):
        length = updates = 12
        corridor = Corridor(length, "periodic")
        for pattern in ("1000", "10", "1110"):
            with self.subTest(pattern=pattern):
                cells = pattern * (length // len(pattern))
                people = tuple(Person(str(pos), pos) for pos, cell in enumerate(cells, 1)
                               if cell == "1")
                population = len(people)
                density = Fraction(population, length)
                expected_flow = min(density, 1 - density)
                expected_rate = expected_flow / density
                total_moves = 0
                for _ in range(updates):
                    step = corridor.step(people, (1,) * population)
                    total_moves += step.counts["move"]
                    self.assertEqual(step.counts["move"], expected_flow * length)
                    self.assertTrue(all(person.active for person in step.people))
                    self.assertFalse(any(attempt.exited for attempt in step.attempts))
                    people = step.people
                flow = Fraction(total_moves, length * updates)
                rate = Fraction(total_moves, population * updates)
                self.assertEqual((flow, rate), (expected_flow, expected_rate))
                print(f"\n密度 {float(density):.2f} | 移動 {total_moves:2} 回 | "
                      f"流量 {float(flow):.2f}（理論 {float(expected_flow):.2f}） | "
                      f"一人当たり移動率 {rate}（理論 {expected_rate}）", flush=True)

    def test_absorbing_invariants_at_each_time(self):
        # Keep the roster order independent of the physical order.
        people = tuple(reversed(INITIAL))
        initial_order = [p.id for p in sorted(INITIAL, key=lambda p: p.position)]
        cumulative_exits = 0
        for time in range(len(SCHEDULE) + 1):
            with self.subTest(time=time):
                if time > 0:
                    before = sum(person.active for person in people)
                    step = CORRIDOR.step(people, SCHEDULE[time - 1][::-1])
                    self.assertEqual(sum(step.counts.values()), before)
                    cumulative_exits += sum(attempt.exited for attempt in step.attempts)
                    people = step.people
                active = sorted((p for p in people if p.active), key=lambda p: p.position)
                self.assertEqual(len(active) + cumulative_exits, len(INITIAL))
                self.assertEqual(len({p.position for p in active}), len(active))
                self.assertTrue(all(1 <= p.position <= CORRIDOR.length for p in active))
                self.assertEqual([p.id for p in active], initial_order[:len(active)])
                self.assertEqual([p.id for p in people], [p.id for p in reversed(INITIAL)])
        self.assertEqual(cumulative_exits, len(INITIAL))

    def test_spaced_people_finish_after_length_plus_one_minus_rear_position(self):
        corridor = Corridor(8, "absorbing")
        for positions in ((1, 3, 6), (2, 5, 8), (8,)):
            with self.subTest(positions=positions):
                people = tuple(Person(str(pos), pos) for pos in positions)
                finish_time = corridor.length + 1 - min(positions)
                for time in range(1, finish_time + 1):
                    step = corridor.step(people, (1,) * len(people))
                    people = step.people
                    self.assertEqual(step.counts["exclusion_stop"], 0)
                    self.assertEqual(any(person.active for person in people), time < finish_time)


class TrajectoryTests(unittest.TestCase):
    def test_saved_open_trajectory_matches_runtime_and_hand_calculation(self):
        expected_states = [
            ({"A": 2, "B": 4, "C": 5}, None, 0),
            ({"A": 2, "B": 4}, (1, 1, 1), 1),
            ({"A": 3, "B": 5}, (0, 0, 2), 1),
            ({"A": 4, "B": 5}, (1, 0, 1), 1),
            ({"A": 4}, (0, 1, 1), 2),
            ({"A": 5}, (0, 0, 1), 2),
            ({}, (0, 0, 1), 3),
        ]
        expected = [
            Frame(time, positions,
                  dict(zip(("intention_stop", "exclusion_stop", "move"), counts))
                  if counts is not None else None, exits)
            for time, (positions, counts, exits) in enumerate(expected_states)
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.json"
            runtime = write_run(
                path, CORRIDOR, INITIAL, SCHEDULE, intention_source=INTENTION_SOURCE
            )
            self.assertEqual(read_run(path), runtime)
            self.assertEqual(runtime, expected)

            log = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(log["settings"], {
            "length": 5, "boundary": "absorbing", "intention_source": INTENTION_SOURCE,
        })
        for trial, intentions in zip(log["trials"], SCHEDULE):
            self.assertEqual([p["id"] for p in trial["people"]], ["A", "B", "C"])
            self.assertEqual(tuple(p["s"] for p in trial["people"]), intentions)
        self.assertEqual(log["trials"][0]["people"][2], {
            "id": "C", "s": 1, "active_before": True, "active_after": False,
            "old_position": 5, "new_position": 6, "reason": "move", "exited": True,
        })
        self.assertEqual(log["trials"][1]["people"][2], {
            "id": "C", "s": -1, "active_before": False, "active_after": False,
            "old_position": None, "new_position": None, "reason": "outside", "exited": False,
        })
        self.assertTrue(all("C" not in frame.positions for frame in runtime[1:]))


if __name__ == "__main__":
    unittest.main()
