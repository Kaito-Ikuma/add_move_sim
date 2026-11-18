import unittest

from movement import Corridor, Person
from phase_prediction import predict, verify
from transport_diagnostics import recurrence


class PhasePredictionTests(unittest.TestCase):
    def check_case(self, people, path, expected, nd=1, length=8):
        corridor = Corridor(length, "absorbing")
        cycle = recurrence(path)
        result = predict(corridor, people, path, cycle, nd)
        transitions = dict(zip(path, path[1:]))
        actual, arrivals = verify(corridor, people, path[0], transitions.__getitem__, nd, 100, 100)
        self.assertEqual(result["predicted_final"], expected)
        self.assertEqual(actual["verified_final"], expected)
        self.assertEqual(arrivals[-1], expected)
        return result, actual

    def test_precycle_exit_is_counted_and_frontmost_negative_blocks(self):
        people = (Person("A", 1), Person("B", 3), Person("C", 6), Person("D", 8))
        initial, prior, fixed = (1, 1, 1, -1), (-1, 1, -1, 1), (-1, 1, -1, -1)
        result, actual = self.check_case(people, [initial, prior, fixed, fixed], 1)
        self.assertEqual(result["first_periodic_t"], 2)
        self.assertEqual(result["prefix_exits"], 1)
        self.assertEqual(result["negative_only_ids"], ["A", "C", "D"])
        self.assertEqual(result["blocker_id"], "C")
        self.assertEqual(actual["first_exit"]["ids"], ["D"])

    def test_leader_moves_on_rare_positive_phase(self):
        people = (Person("A", 1), Person("B", 3), Person("C", 4))
        path = [(-1, -1, -1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1)]
        path.append(path[0])
        result, actual = self.check_case(people, path, 3, length=5)
        self.assertEqual(result["positive_phases_by_id"]["C"], [3])
        self.assertEqual(actual["first_exit"]["t"], 7)
        skipped, _ = self.check_case(people, path, 0, nd=2, length=5)
        self.assertEqual(skipped["phases"], [2, 0])
        self.assertEqual(skipped["blocker_id"], "C")

    def test_no_permanent_blocker_under_synchronous_exclusion(self):
        people = (Person("A", 1), Person("B", 2), Person("C", 3))
        state = (1, 1, 1)
        result, actual = self.check_case(people, [state, state], 3, length=3)
        self.assertIsNone(result["blocker_id"])
        self.assertEqual(actual["certificate"], "all_exited")
        self.assertEqual(actual["certificate_t"], 5)

    def test_cap_keeps_final_unknown_and_observed_count_separate(self):
        person = Person("A", 1)
        result, _ = verify(Corridor(5, "absorbing"), [person], (1,), lambda s: s, 1, 1, 1)
        self.assertIsNone(result["verified_final"])
        self.assertEqual(result["arrived_t200"], 0)
