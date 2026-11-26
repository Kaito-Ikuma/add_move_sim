import unittest

from density_study import SPANS, placement, pure


class DensityTests(unittest.TestCase):
    def test_right_aligned_placements_and_pure_transport(self):
        ids = tuple(str(i) for i in range(24))
        for span, expected_wait, finish in zip(SPANS, (0, 0, 192), (109, 63, 63)):
            with self.subTest(span=span):
                people = placement(ids, span)
                pos = [p.position for p in people]
                self.assertEqual(pos, sorted(set(pos)))
                self.assertEqual(pos[-1], 96)
                self.assertGreater(pos[0], 96-span)
                rows, trials = pure(people)
                self.assertEqual(len(trials), finish)
                self.assertEqual(sum(p["intention_stop"] for p in rows), 0)
                self.assertEqual(sum(p["exclusion_stop"] for p in rows), expected_wait)
                self.assertTrue(all(p["move"] == 113-p["initial"] for p in rows))
