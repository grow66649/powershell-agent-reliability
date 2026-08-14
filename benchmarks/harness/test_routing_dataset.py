import copy
import unittest

import routing_dataset


GROUPS = ("should_trigger", "should_not_trigger", "boundary")


def _workspace_post_condition():
    return {
        "kind": "workspace_state",
        "mode": "all",
        "checks": [{"kind": "file_exists", "path": "result.txt"}],
    }


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
                "prompt": "Complete the requested disposable task and report the result.",
                "post_condition": _workspace_post_condition(),
            })
    return rows


def _reviews(cases):
    group_index = {"should_trigger": 0, "should_not_trigger": 0, "boundary": 0}
    trigger_families = (
        "command-resolution",
        "environment-staleness",
        "native-child-status",
        "real-timeout-cancellation",
    )
    no_trigger_families = (
        "native-semantic-nonzero",
        "native-success",
        "pre-failure-mention",
        "historical-failure-context",
    )
    rows = []
    for row in cases:
        group = row["group"]
        index = group_index[group]
        group_index[group] += 1
        family = "coverage"
        if group == "should_trigger" and index < len(trigger_families):
            family = trigger_families[index]
        elif group == "should_not_trigger" and index < len(no_trigger_families):
            family = no_trigger_families[index]
        rows.append({
            "case_id": row["case_id"],
            "provenance_cluster": f"cluster-{row['case_id']}",
            "provenance_basis": "sanitized unit-test provenance",
            "natural_task_rationale": "natural task",
            "expected_routing_rationale": group,
            "failure_family": family,
            "boundary_rationale": "bounded",
            "deterministic_success_condition": "observable result",
            "post_condition_rationale": "artifact task has deterministic evidence",
            "post_condition_category": "mechanical_workspace_state",
            "first_failure_preview": "bounded pre-outcome observation",
            "anti_coaching_check": "passed",
            "leakage_check": "clean",
            "safety_privacy_check": "clean",
            "outcome_visible_before_review": False,
            "decision": "approved",
        })
    return rows


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

    def test_frozen_core_applies_external_validity_gate(self):
        train, train_reviews, validation, validation_reviews = _core()
        train[0]["prompt"] = "Run the task; if it fails, recover conservatively."
        with self.assertRaisesRegex(ValueError, "workflow coaching"):
            routing_dataset.validate_frozen_core(train, train_reviews, validation, validation_reviews)

    def test_v3_review_metadata_is_required(self):
        for field in ("provenance_basis", "post_condition_category", "first_failure_preview"):
            with self.subTest(field=field):
                train, train_reviews, validation, validation_reviews = _core()
                del train_reviews[0][field]
                with self.assertRaisesRegex(ValueError, "review coverage"):
                    routing_dataset.validate_frozen_core(train, train_reviews, validation, validation_reviews)


def _external_validity_fixture():
    cases = [
        {"case_id": "TR-1", "lane": "train", "group": "should_trigger", "prompt": "Run helper.cmd and create result.txt containing READY.", "post_condition": _workspace_post_condition()},
        {"case_id": "TR-2", "lane": "train", "group": "should_trigger", "prompt": "Run resolve.ps1 and create the requested result artifact.", "post_condition": _workspace_post_condition()},
        {"case_id": "TR-3", "lane": "train", "group": "should_trigger", "prompt": "Run child-wrapper.cmd and record the requested artifact.", "post_condition": _workspace_post_condition()},
        {"case_id": "TR-4", "lane": "validation", "group": "should_trigger", "prompt": "Run sleeper.ps1 and report the requested artifact.", "post_condition": _workspace_post_condition()},
        {"case_id": "NT-1", "lane": "train", "group": "should_not_trigger", "prompt": "Run native-check.exe and report the current result.", "post_condition": _workspace_post_condition()},
        {"case_id": "NT-2", "lane": "train", "group": "should_not_trigger", "prompt": "Run native-success.exe and save the requested result.", "post_condition": _workspace_post_condition()},
        {"case_id": "NT-3", "lane": "train", "group": "should_not_trigger", "prompt": "The helper is mentioned in the task notes. Run task.ps1 here and report the current result.", "post_condition": _workspace_post_condition()},
        {"case_id": "NT-4", "lane": "validation", "group": "should_not_trigger", "prompt": "Yesterday a command behaved differently. Without running it now, explain which observations would distinguish slow from stuck.", "post_condition": {"kind": "none"}},
    ]
    families = (
        "command-resolution",
        "environment-staleness",
        "native-child-status",
        "real-timeout-cancellation",
        "native-semantic-nonzero",
        "native-success",
        "pre-failure-mention",
        "historical-failure-context",
    )
    reviews = []
    for case, family in zip(cases, families):
        is_none = case["post_condition"]["kind"] == "none"
        reviews.append({
            "case_id": case["case_id"],
            "provenance_cluster": f"cluster-{case['case_id']}",
            "provenance_basis": "sanitized unit-test provenance",
            "failure_family": family,
            "post_condition_rationale": "explanation-only task" if is_none else "mechanically scored workspace state",
            "post_condition_category": "explanation_only" if is_none else "mechanical_workspace_state",
            "first_failure_preview": "bounded pre-outcome observation",
            "anti_coaching_check": "passed",
        })
    return cases, reviews


class ExternalValidityTests(unittest.TestCase):
    def test_valid_external_validity_fixture_passes(self):
        cases, reviews = _external_validity_fixture()
        routing_dataset.validate_external_validity(cases, reviews)

    def test_workflow_coaching_phrase_is_rejected(self):
        cases, reviews = _external_validity_fixture()
        cases[0]["prompt"] = "Run helper.cmd; if it fails, recover conservatively and create result.txt."
        with self.assertRaisesRegex(ValueError, "workflow coaching"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_direct_command_resolution_coverage_is_required(self):
        cases, reviews = _external_validity_fixture()
        reviews[0]["failure_family"] = "other-trigger"
        with self.assertRaisesRegex(ValueError, "command-resolution"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_native_semantic_nonzero_negative_is_required(self):
        cases, reviews = _external_validity_fixture()
        reviews[4]["failure_family"] = "other-negative"
        with self.assertRaisesRegex(ValueError, "native-semantic-nonzero"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_hard_negative_families_must_be_should_not_trigger(self):
        cases, reviews = _external_validity_fixture()
        cases[6]["group"] = "boundary"
        with self.assertRaisesRegex(ValueError, "hard negative"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_post_condition_none_requires_review_rationale(self):
        cases, reviews = _external_validity_fixture()
        reviews[7]["post_condition_rationale"] = ""
        with self.assertRaisesRegex(ValueError, "post_condition_rationale"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_none_category_rationale_must_match_category(self):
        cases, reviews = _external_validity_fixture()
        reviews[7]["post_condition_rationale"] = "some arbitrary nonempty rationale"
        with self.assertRaisesRegex(ValueError, "post_condition_rationale"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_additional_taxonomy_shaped_marker_is_rejected(self):
        cases, reviews = _external_validity_fixture()
        cases[0]["files"] = {"input.txt": "COPY_OK"}
        with self.assertRaisesRegex(ValueError, "coaching"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_selected_tool_output_marker_is_rejected(self):
        cases, reviews = _external_validity_fixture()
        cases[0]["post_condition"] = {"kind": "tool_output_marker"}
        with self.assertRaisesRegex(ValueError, "workspace_state"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_workspace_state_requires_mechanical_category(self):
        cases, reviews = _external_validity_fixture()
        reviews[0]["post_condition_category"] = "diagnosis_only"
        with self.assertRaisesRegex(ValueError, "mechanical_workspace_state"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_none_category_must_be_explicitly_approved(self):
        cases, reviews = _external_validity_fixture()
        reviews[7]["post_condition_category"] = "freeform_none"
        with self.assertRaisesRegex(ValueError, "post_condition_category"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_provenance_basis_is_required(self):
        cases, reviews = _external_validity_fixture()
        reviews[0]["provenance_basis"] = ""
        with self.assertRaisesRegex(ValueError, "provenance_basis"):
            routing_dataset.validate_external_validity(cases, reviews)

    def test_new_required_family_coverage_is_enforced(self):
        required = {
            "environment-staleness": 1,
            "native-child-status": 2,
            "real-timeout-cancellation": 3,
            "native-success": 5,
        }
        for family, index in required.items():
            with self.subTest(family=family):
                cases, reviews = _external_validity_fixture()
                reviews[index]["failure_family"] = "other-family"
                with self.assertRaisesRegex(ValueError, family):
                    routing_dataset.validate_external_validity(cases, reviews)

    def test_taxonomy_shaped_labels_are_rejected_on_every_visible_surface(self):
        surfaces = ("prompt", "filename", "fixture", "first_command", "boundary_marker", "first_failure")
        for surface in surfaces:
            with self.subTest(surface=surface):
                cases, reviews = _external_validity_fixture()
                case = cases[0]
                review = reviews[0]
                if surface == "prompt":
                    case["prompt"] = "Run helper.cmd CWD_FAIL"
                elif surface == "filename":
                    case["files"] = {"CWD_FAIL.txt": "safe fixture text"}
                elif surface == "fixture":
                    case["files"] = {"input.txt": "CWD_FAIL"}
                elif surface == "first_command":
                    case["expected_first_command_fragment"] = "helper.cmd CWD_FAIL"
                elif surface == "boundary_marker":
                    case["boundary_detector"] = {"marker": "CWD_FAIL"}
                else:
                    review["first_failure_preview"] = "CWD_FAIL"
                with self.assertRaisesRegex(ValueError, "coaching"):
                    routing_dataset.validate_external_validity(cases, reviews)


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