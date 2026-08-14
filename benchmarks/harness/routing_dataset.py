import argparse
import collections
import hashlib
import json
import math
import pathlib


CORE_QUOTAS = {
    "train": {"should_trigger": 6, "should_not_trigger": 6, "boundary": 2},
    "validation": {"should_trigger": 4, "should_not_trigger": 4, "boundary": 2},
}
REVIEW_REQUIRED = {
    "case_id",
    "provenance_cluster",
    "natural_task_rationale",
    "expected_routing_rationale",
    "failure_family",
    "boundary_rationale",
    "deterministic_success_condition",
    "leakage_check",
    "safety_privacy_check",
    "outcome_visible_before_review",
    "decision",
}


def _validate_lane(cases: list[dict], lane: str) -> None:
    counts = collections.Counter(row.get("group") for row in cases)
    if counts != collections.Counter(CORE_QUOTAS[lane]):
        raise ValueError(f"{lane} quota mismatch: {dict(counts)}")
    if any(row.get("lane") != lane for row in cases):
        raise ValueError(f"{lane} package contains another lane")


def validate_frozen_core(train_cases, train_reviews, validation_cases, validation_reviews) -> dict:
    _validate_lane(train_cases, "train")
    _validate_lane(validation_cases, "validation")
    cases = train_cases + validation_cases
    case_ids = [row.get("case_id") for row in cases]
    if len(case_ids) != 24 or len(set(case_ids)) != 24 or any(not isinstance(v, str) or not v for v in case_ids):
        raise ValueError("case_id values must be unique across the 24-case core")
    all_reviews = train_reviews + validation_reviews
    review_ids = [row.get("case_id") for row in all_reviews]
    if len(review_ids) != len(set(review_ids)):
        raise ValueError("review coverage contains duplicate case_id rows")
    reviews = {row.get("case_id"): row for row in all_reviews}
    if set(reviews) != set(case_ids):
        raise ValueError("review coverage must equal the frozen core")
    for row in reviews.values():
        if (
            not REVIEW_REQUIRED.issubset(row)
            or row.get("decision") != "approved"
            or row.get("outcome_visible_before_review") is not False
        ):
            raise ValueError("review coverage contains an unapproved or post-outcome row")
    lane_by_cluster = {}
    for case in cases:
        review = reviews[case["case_id"]]
        cluster = review.get("provenance_cluster")
        if not isinstance(cluster, str) or not cluster:
            raise ValueError("review coverage contains an empty provenance cluster")
        prior = lane_by_cluster.setdefault(cluster, case["lane"])
        if prior != case["lane"]:
            raise ValueError("provenance cluster crosses lanes")
    return {"train_count": 14, "validation_count": 10}


def ceil_to_30_seconds(value: float) -> int:
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValueError("duration must be positive")
    return int(math.ceil(value / 30.0) * 30)


def compute_timeout_seconds(records: list[dict]) -> int:
    if len(records) != 12 or any(row.get("valid") is not True for row in records):
        raise ValueError("need exactly 12 valid calibration records")
    case_ids = {row.get("case_id") for row in records}
    trial_ids = {row.get("trial_id") for row in records}
    arms = {row.get("arm") for row in records}
    identities = {(row.get("case_id"), row.get("trial_id"), row.get("arm")) for row in records}
    expected = {(case_id, trial_id, arm) for case_id in case_ids for trial_id in trial_ids for arm in ("S", "M")}
    if len(case_ids) != 3 or trial_ids != {"T01", "T02"} or arms != {"S", "M"} or identities != expected:
        raise ValueError("calibration matrix must be 3 cases x 2 trials x S/M")
    durations = [row.get("turn_duration_ms") for row in records]
    if any(not isinstance(value, (int, float)) or value <= 0 for value in durations):
        raise ValueError("all calibration durations must be positive numbers")
    return ceil_to_30_seconds(2 * max(durations) / 1000.0)


def _load_json(path: pathlib.Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: pathlib.Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _write_summary(path: pathlib.Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _validate_freeze(args) -> dict:
    train_cases_path = pathlib.Path(args.train_cases)
    train_review_path = pathlib.Path(args.train_review)
    validation_cases_path = pathlib.Path(args.validation_cases)
    validation_review_path = pathlib.Path(args.validation_review)
    result = validate_frozen_core(
        _load_json(train_cases_path),
        _load_jsonl(train_review_path),
        _load_json(validation_cases_path),
        _load_jsonl(validation_review_path),
    )
    summary = {
        "schema_version": 1,
        **result,
        "core_count": 24,
        "seed": args.seed,
        "train_cases_sha256": _sha256(train_cases_path),
        "train_review_sha256": _sha256(train_review_path),
        "validation_cases_sha256": _sha256(validation_cases_path),
        "validation_review_sha256": _sha256(validation_review_path),
    }
    _write_summary(pathlib.Path(args.output), summary)
    return summary


def _freeze_timeout(args) -> dict:
    records_path = pathlib.Path(args.records)
    records = _load_jsonl(records_path)
    timeout_seconds = compute_timeout_seconds(records)
    summary = {
        "schema_version": 1,
        "record_count": 12,
        "timeout_seconds": timeout_seconds,
        "records_sha256": _sha256(records_path),
    }
    _write_summary(pathlib.Path(args.output), summary)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate r4 dataset freezes and timeout calibration")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-freeze")
    validate.add_argument("--train-cases", required=True)
    validate.add_argument("--train-review", required=True)
    validate.add_argument("--validation-cases", required=True)
    validate.add_argument("--validation-review", required=True)
    validate.add_argument("--seed", type=int, required=True)
    validate.add_argument("--output", required=True)

    timeout = sub.add_parser("freeze-timeout")
    timeout.add_argument("--records", required=True)
    timeout.add_argument("--output", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "validate-freeze":
        summary = _validate_freeze(args)
    else:
        summary = _freeze_timeout(args)
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
