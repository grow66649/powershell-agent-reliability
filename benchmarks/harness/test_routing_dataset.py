import copy
import unittest

import routing_dataset


GROUPS = ("should_trigger", "should_not_trigger", "boundary")


def _cases(lane, quotas, prefix):
    rows = []
    counter = 0
    for group in GROUPS:
        for _ in range(quotas[group]):
            counter += 1
            rows.append({
                "case_id": f"{prefix}-{counter:02d}",
                "lane": lane,
                "group": group,
            })
    return rows


def _reviews(cases):
    return [
        {
            "case_id": row["case_id"],
            "provenance_cluster": f"cluster-{row['case_id']}",
            "natural_task_rationale": "natural task",
            "expected_routing_rationale": "routing rationale",
            "failure_family": "coverage",
            "boundary_rationale": "bounded",
            "deterministic_success_condition": "observable result",
            "leakage_check": "clean",
            "safety_privacy_check": "clean",
            "outcome_visible_before_review": False,
            "decision": "approved",
        }
        for row in cases
    ]


def _core():
    train = _cases("train", {"should_trigger": 6, "should_not_trigger": 6, "boundary": 2}, "tr")
    validation = _cases("validation", {"should_trigger": 4, "should_not_trigger": 4, "boundary": 2}, "va")
    return train, _reviews(train), validation, _reviews(validation)


def _calibration_records():
    rows = []
    durations = [12000, 18000, 74000, 21000, 16000, 19000, 24000, 28000, 31000, 26000, 22000, 25000]
    index = 0
    for case_id in ("cal-fast", "cal-repair", "cal-slow"):
        for trial_id in ("T01", "T02"):
            for arm in ("S", "M"):
                rows.append({
                    "case_id": case_id,
                    "trial_id": trial_id,
                    "arm": arm,
                    "valid": True,
                    "turn_duration_ms": durations[index],
                })
                index += 1
    return rows


class FrozenCoreTests(unittest.TestCase):
    def test_valid_core_returns_bounded_counts(self):
        train, train_reviews, validation, validation_reviews = _core()
        self.assertEqual(
            routing_dataset.validate_frozen_core(train, train_reviews, validation, validation_reviews),
            {"train_count": 14, "validation_count": 10},
        )

    def test_train_quota_mismatch_is_rejected(self):
        train, train_reviews, validation, validation_reviews = _core()
        train.pop()
        with self.assertRaisesRegex(ValueError, "train quota"):
            routing_dataset.validate_frozen_core(train, train_reviews, validation, validation_reviews)

    def test_review_coverage_must_equal_core(self):
        train, train_reviews, validation, validation_reviews = _core()
        with self.assertRaisesRegex(ValueError, "review coverage"):
            routing_dataset.validate_frozen_core(train, train_reviews[:-1], validation, validation_reviews)

    def test_post_outcome_review_is_rejected(self):
        train, train_reviews, validation, validation_reviews = _core()
        train_reviews[0]["outcome_visible_before_review"] = True
        with self.assertRaisesRegex(ValueError, "review coverage"):
            routing_dataset.validate_frozen_core(train, train_reviews, validation, validation_reviews)

    def test_duplicate_case_id_is_rejected(self):
        train, train_reviews, validation, validation_reviews = _core()
        validation[0]["case_id"] = train[0]["case_id"]
        validation_reviews[0]["case_id"] = train[0]["case_id"]
        with self.assertRaisesRegex(ValueError, "case_id values must be unique"):
            routing_dataset.validate_frozen_core(train, train_reviews, validation, validation_reviews)

    def test_provenance_cluster_cannot_cross_lanes(self):
        train, train_reviews, validation, validation_reviews = _core()
        validation_reviews[0]["provenance_cluster"] = train_reviews[0]["provenance_cluster"]
        with self.assertRaisesRegex(ValueError, "provenance cluster crosses lanes"):
            routing_dataset.validate_frozen_core(train, train_reviews, validation, validation_reviews)


class TimeoutTests(unittest.TestCase):
    def test_max_74_seconds_freezes_to_150_seconds(self):
        self.assertEqual(routing_dataset.compute_timeout_seconds(_calibration_records()), 150)

    def test_requires_exactly_twelve_valid_records(self):
        records = _calibration_records()
        with self.assertRaisesRegex(ValueError, "12 valid calibration records"):
            routing_dataset.compute_timeout_seconds(records[:-1])

    def test_rejects_invalid_record(self):
        records = _calibration_records()
        records[0]["valid"] = False
        with self.assertRaisesRegex(ValueError, "12 valid calibration records"):
            routing_dataset.compute_timeout_seconds(records)

    def test_rejects_non_positive_duration(self):
        records = _calibration_records()
        records[0]["turn_duration_ms"] = 0
        with self.assertRaisesRegex(ValueError, "positive numbers"):
            routing_dataset.compute_timeout_seconds(records)

    def test_rejects_incomplete_matrix(self):
        records = _calibration_records()
        records[-1] = copy.deepcopy(records[-2])
        with self.assertRaisesRegex(ValueError, "calibration matrix"):
            routing_dataset.compute_timeout_seconds(records)


if __name__ == "__main__":
    unittest.main()
