import json
import pathlib
import tempfile
import unittest

import score_ab


class ScoreAbTests(unittest.TestCase):
    def test_aggregates_paths_without_turning_missing_into_zero(self):
        rows = [
            {
                "case_id": "c1",
                "trial_id": "1",
                "path": "A",
                "eligible_failure": True,
                "completion": False,
                "repair_turns": 3,
                "wrong_repairs": 1,
                "expected_class": "CWD_PATH_IDENTITY",
                "predicted_class": "UNKNOWN",
                "false_completion": False,
            },
            {
                "case_id": "c1",
                "trial_id": "1",
                "path": "B",
                "eligible_failure": True,
                "completion": True,
                "repair_turns": 1,
                "wrong_repairs": 0,
                "expected_class": "CWD_PATH_IDENTITY",
                "predicted_class": "CWD_PATH_IDENTITY",
                "first_action_correct": True,
                "false_completion": False,
            },
        ]
        report = score_ab.score_rows(rows)
        self.assertEqual(report["paths"]["A"]["completion_rate"], 0.0)
        self.assertEqual(report["paths"]["B"]["completion_rate"], 1.0)
        self.assertEqual(report["paths"]["A"]["median_repair_turns"], 3.0)
        self.assertEqual(report["paths"]["B"]["median_repair_turns"], 1.0)
        self.assertIsNone(report["paths"]["A"]["first_action_correct_rate"])
        self.assertEqual(report["paths"]["B"]["first_action_correct_rate"], 1.0)
        self.assertEqual(report["paths"]["A"]["classification_accuracy"], 0.0)
        self.assertEqual(report["paths"]["B"]["classification_accuracy"], 1.0)

    def test_known_good_false_intervention_is_scored_separately(self):
        rows = [
            {
                "case_id": "control",
                "trial_id": "1",
                "path": "B",
                "eligible_failure": False,
                "completion": True,
                "intervention_count": 1,
            },
            {
                "case_id": "control",
                "trial_id": "2",
                "path": "B",
                "eligible_failure": False,
                "completion": True,
                "intervention_count": 0,
            },
        ]
        report = score_ab.score_rows(rows)
        self.assertEqual(report["paths"]["B"]["control_false_intervention_rate"], 0.5)
    def test_jsonl_round_trip_and_validation(self):
        row = {
            "case_id": "c1",
            "trial_id": "1",
            "path": "A",
            "eligible_failure": True,
            "completion": True,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            path = pathlib.Path(temp_dir) / "runs.jsonl"
            path.write_text(json.dumps(row) + "\n", encoding="utf-8")
            loaded = score_ab.load_jsonl(path)
        self.assertEqual(loaded, [row])

        with self.assertRaises(ValueError):
            score_ab.score_rows(
                [{"case_id": "x", "trial_id": "1", "path": "C", "eligible_failure": True}]
            )


if __name__ == "__main__":
    unittest.main()

class ScoreAbValidationTests(unittest.TestCase):
    def test_rejects_negative_metrics_and_duplicate_trial_identity(self):
        invalid = {
            "case_id": "c1",
            "trial_id": "1",
            "path": "A",
            "eligible_failure": True,
            "repair_turns": -1,
        }
        with self.assertRaises(ValueError):
            score_ab.score_rows([invalid])

        row = {
            "case_id": "c1",
            "trial_id": "1",
            "path": "A",
            "eligible_failure": True,
        }
        with self.assertRaises(ValueError):
            score_ab.score_rows([row, dict(row)])

class ScoreAbContractTests(unittest.TestCase):
    def test_reports_eligible_and_control_metrics_separately_with_confusion_matrix(self):
        rows = [
            {
                "case_id": "failure",
                "trial_id": "1",
                "path": "A",
                "eligible_failure": True,
                "completion": False,
                "expected_class": "CWD_PATH_IDENTITY",
                "predicted_class": "UNKNOWN",
            },
            {
                "case_id": "control",
                "trial_id": "1",
                "path": "A",
                "eligible_failure": False,
                "completion": True,
                "intervention_count": 0,
            },
        ]
        path_a = score_ab.score_rows(rows)["paths"]["A"]
        self.assertEqual(path_a["eligible"]["completion_rate"], 0.0)
        self.assertEqual(path_a["controls"]["completion_rate"], 1.0)
        self.assertEqual(
            path_a["eligible"]["confusion_matrix"],
            {"CWD_PATH_IDENTITY": {"UNKNOWN": 1}},
        )
