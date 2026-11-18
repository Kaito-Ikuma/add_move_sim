from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from coupled import Clock, replay, run, save
from decisions import Disorder, SocialRing
from movement import Corridor, Person


IDS = ("A", "B", "C")


def swap_ring():
    # A copies B, B copies A, and C always has a positive field at h=0.
    return SocialRing.from_values(IDS, 1, 0.2, (0, 0, 0), (0, 0, -1),
                                  ((0, 2), (2, 0), (0, 0)), 1)


class CouplingTests(unittest.TestCase):
    def test_kernel_and_seeded_directed_disorder(self):
        params = Disorder(0.4, 0.2, 0.1, 0.3, 0.7, 12)
        ids = tuple(map(str, range(9)))
        ring = SocialRing.sample(ids, 4, 0.2, params)
        self.assertEqual(ring, SocialRing.sample(ids, 4, 0.2, params))
        for i, row in enumerate(ring.links):
            self.assertEqual(len({link.target for link in row}), 8)
            self.assertNotIn(i, [link.target for link in row])
            self.assertAlmostEqual(sum(link.weight for link in row), 1)
            self.assertAlmostEqual(sum(link.weight for link in row[::2]), 0.5)
            self.assertAlmostEqual(sum(link.weight for link in row[1::2]), 0.5)
            for link in row:
                self.assertEqual(link.j, ring.mu[i] + params.sigma_j * link.xi)
        self.assertNotEqual(ring.links[0][1].xi, ring.links[1][0].xi)

    def test_ties_and_synchronous_swap(self):
        self.assertEqual(swap_ring().update((-1, 1, -1), 0), (1, -1, 1))
        # Updating A first in place would make B copy +1.
        self.assertEqual(swap_ring().update((1, 1, -1), 0)[1], 1)
        ties = SocialRing.from_values(IDS, 1, 0, (0, 0, 0), (0, 0, 0),
                                      ((0, 0),) * 3, 1)
        self.assertEqual(ties.update((-1, 1, -1), 0), (-1, 1, -1))

    def test_independence_at_every_update_and_influence_after_exit(self):
        ring, initial = swap_ring(), (-1, 1, 1)
        fields = (0, 0, 0, 0.2)
        solo = list(ring.evolve(initial, fields))
        runs = []
        for positions in ((8, 1, 4), (3, 1, 4)):
            people = tuple(Person(pid, x) for pid, x in zip(IDS, positions))
            log, frames = run("test", ring, Corridor(8, "absorbing"), people, initial,
                              Clock(1, len(fields)), lambda n: fields[n - 1])
            states = [frame.intentions for frame in frames if frame.phase != "movement"]
            self.assertEqual(states, solo)
            runs.append(log)
        first, second = runs
        self.assertTrue(first["trials"][0]["people"][0]["exited"])
        self.assertFalse(second["trials"][0]["people"][0]["exited"])
        self.assertEqual(first["trials"][1]["people"][0]["s"], -1)
        self.assertEqual(first["trials"][1]["people"][0]["reason"], "outside")
        self.assertTrue(first["trials"][2]["people"][1]["active_before"])
        self.assertEqual(solo[3][1], -1)
        self.assertEqual(ring.update((1, *solo[2][1:]), 0)[1], 1)

    def test_last_decision_drives_move_and_saved_frames_match(self):
        people = tuple(Person(pid, x) for pid, x in zip(IDS, (8, 1, 4)))
        log, frames = run("roundtrip", swap_ring(), Corridor(8, "absorbing"), people,
                          (-1, 1, 1), Clock(2, 4), lambda n: 0)
        self.assertEqual([f.intentions[0] for f in frames[:4]], [-1, 1, -1, -1])
        self.assertEqual([f.positions["A"] for f in frames[:4]], [8] * 4)
        self.assertEqual(log["trials"][0]["people"][0]["reason"], "intention_stop")
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "coupled.json"
            save(path, log)
            _, restored = replay(path)
        self.assertEqual(restored, frames)
        for before, after in zip(frames, frames[1:]):
            if after.phase == "decision":
                self.assertEqual(after.positions, before.positions)
                self.assertEqual(after.cumulative_exits, before.cumulative_exits)
            else:
                self.assertEqual(after.intentions, before.intentions)
                self.assertEqual(sum(after.counts.values()), len(before.positions))
            self.assertEqual(len(after.positions) + after.cumulative_exits, 3)
