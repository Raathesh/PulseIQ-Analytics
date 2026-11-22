
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DEPLOYMENT_PACKAGE = PROJECT_ROOT / "deployment_package"

sys.path.insert(0, str(DEPLOYMENT_PACKAGE))

from kpi_explorer import (
    is_group_publishable,
    complementary_suppression,
)


class TestPrimaryPrivacySuppression(unittest.TestCase):

    def test_headcount_groups_below_five_are_hidden(self):
        for size in [1, 2, 3, 4]:
            with self.subTest(group_size=size):
                self.assertFalse(
                    is_group_publishable("headcount", size)
                )

    def test_headcount_group_of_five_is_publishable(self):
        self.assertTrue(is_group_publishable("headcount", 5))

    def test_attrition_groups_below_ten_are_hidden(self):
        for size in [1, 2, 3, 4, 5, 6, 7, 8, 9]:
            with self.subTest(group_size=size):
                self.assertFalse(
                    is_group_publishable("attrition", size)
                )

    def test_attrition_group_of_ten_is_publishable(self):
        self.assertTrue(is_group_publishable("attrition", 10))

    def test_task_threshold_uses_task_count(self):
        self.assertFalse(
            is_group_publishable("task_completion", 4)
        )
        self.assertTrue(
            is_group_publishable("task_completion", 5)
        )

    def test_unknown_metric_is_rejected(self):
        with self.assertRaises(ValueError):
            is_group_publishable("unknown_metric", 10)

    def test_negative_group_size_is_rejected(self):
        with self.assertRaises(ValueError):
            is_group_publishable("headcount", -1)


class TestComplementarySuppression(unittest.TestCase):

    def test_single_small_group_hides_another_group(self):
        sizes = [3, 20, 25]
        result = complementary_suppression(sizes, 5)

        self.assertEqual(result, [True, True, False])

    def test_two_small_groups_are_primary_suppressed(self):
        sizes = [2, 3, 20]
        result = complementary_suppression(sizes, 5)

        self.assertEqual(result, [True, True, False])

    def test_no_small_groups_need_no_suppression(self):
        sizes = [10, 20, 25]
        result = complementary_suppression(sizes, 5)

        self.assertEqual(result, [False, False, False])

    def test_all_small_groups_are_suppressed(self):
        sizes = [1, 2, 3, 4]
        result = complementary_suppression(sizes, 5)

        self.assertEqual(result, [True, True, True, True])

    def test_negative_group_size_is_rejected(self):
        with self.assertRaises(ValueError):
            complementary_suppression([5, -1, 10], 5)


class TestAllMetricPrivacyBoundaries(unittest.TestCase):

    def test_employer_cost_threshold(self):
        self.assertFalse(
            is_group_publishable("employer_cost", 4)
        )
        self.assertTrue(
            is_group_publishable("employer_cost", 5)
        )

    def test_overtime_threshold(self):
        self.assertFalse(
            is_group_publishable("overtime", 4)
        )
        self.assertTrue(
            is_group_publishable("overtime", 5)
        )

    def test_attendance_threshold(self):
        self.assertFalse(
            is_group_publishable("attendance", 4)
        )
        self.assertTrue(
            is_group_publishable("attendance", 5)
        )

    def test_task_completion_boundary(self):
        self.assertFalse(
            is_group_publishable("task_completion", 4)
        )
        self.assertTrue(
            is_group_publishable("task_completion", 5)
        )

    def test_all_employee_metrics_reject_zero(self):
        employee_metrics = [
            "headcount",
            "attrition",
            "employer_cost",
            "overtime",
            "attendance",
        ]

        for metric in employee_metrics:
            with self.subTest(metric=metric):
                self.assertFalse(
                    is_group_publishable(metric, 0)
                )

class TestDifferencingAttackProtection(unittest.TestCase):

    def test_single_hidden_department_blocks_company_total(self):
        sizes = [3, 40, 60]
        suppressed = complementary_suppression(sizes, 5)

        self.assertEqual(suppressed, [True, True, False])

        visible_sizes = [
            size
            for size, hidden in zip(sizes, suppressed)
            if not hidden
        ]

        self.assertNotIn(40, visible_sizes)

    def test_two_hidden_departments_remain_hidden(self):
        sizes = [2, 3, 60]
        suppressed = complementary_suppression(sizes, 5)

        self.assertEqual(suppressed, [True, True, False])

    def test_no_department_is_hidden_when_all_meet_threshold(self):
        sizes = [10, 40, 60]
        suppressed = complementary_suppression(sizes, 5)

        self.assertEqual(suppressed, [False, False, False])


if __name__ == "__main__":
    unittest.main(verbosity=2)
