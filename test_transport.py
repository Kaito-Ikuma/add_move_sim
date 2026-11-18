import unittest

from coupled import CoupledFrame
from field_comparison import compact, compare_curve
from transport_diagnostics import physical_cycle, recurrence
from transport_replay import select_pair


class TransportTests(unittest.TestCase):
    def test_transient_difference_with_identical_endpoints(self):
        result = compare_curve([0, 0, 2, 2], [0, 1, 1, 2])
        self.assertEqual(result, {
            "max_abs_difference": 1, "first_peak_t": 1,
            "signed_difference_at_first_peak": 1, "first_difference_t": 1,
            "end_difference": 0,
        })
        self.assertIsNone(compare_curve([0, 1], [0, 1])["first_peak_t"])

    def test_only_complete_evacuation_can_be_padded(self):
        trials = [{"cumulative_exits": 2, "intention_stop": 0, "exclusion_stop": 0, "move": 2}]
        self.assertEqual(compact(trials, 3, 2)["arrivals"], [0, 2, 2, 2])
        with self.assertRaises(ValueError):
            compact(trials, 3, 3)

    def test_separate_social_and_physical_cycles(self):
        social = recurrence([(1,), (-1,), (1,)])
        self.assertEqual(social, {"transient": 0, "period": 2, "repeat_at": 2})
        frames = [CoupledFrame(t, t, "movement", (1,), {"A": min(t + 1, 2)}, None, 0)
                  for t in range(4)]
        self.assertIsNone(physical_cycle(frames[:-1], social))
        self.assertEqual(physical_cycle(frames, social), {
            "joint_repeat_t": 3, "joint_period_t": 2,
            "physical_period_t": 1, "physical_transient_t": 1,
        })

    def test_selection_uses_earliest_peak_then_smallest_nd(self):
        common = {"seed": "102", "h": "0.0", "max_abs_difference": "16", "first_peak_t": "88"}
        rows = [{**common, "nd": "4"}, {**common, "nd": "2"},
                {**common, "nd": "8", "first_peak_t": "89"}]
        self.assertEqual(select_pair(rows)[0]["nd"], "2")
        rows[0].update(first_peak_t="87")
        self.assertEqual(select_pair(rows)[0]["nd"], "4")
