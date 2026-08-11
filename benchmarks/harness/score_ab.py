import argparse
import json
import pathlib
import statistics
from collections import defaultdict

REQUIRED_FIELDS = ("case_id", "trial_id", "path", "eligible_failure")
PATHS = {"A", "B"}


def load_jsonl(path: pathlib.Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {line_number}: {exc}") from exc
        rows.append(row)
    return rows


def _values(rows: list[dict], key: str, expected_type=None) -> list:
    values = []
    for row in rows:
        value = row.get(key)
        if value is None:
            continue
        if expected_type is not None and not isinstance(value, expected_type):
            raise ValueError(f"{key} has invalid type in {row.get('case_id', '<unknown>')}")
        values.append(value)
    return values
def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return sum(1 for value in values if value) / len(values)


def _median(values: list[float | int]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _validate_row(row: dict) -> None:
    missing = [field for field in REQUIRED_FIELDS if field not in row]
    if missing:
        raise ValueError(f"missing required fields {missing}")
    if row["path"] not in PATHS:
        raise ValueError(f"path must be A or B, got {row['path']!r}")
    if not isinstance(row["eligible_failure"], bool):
        raise ValueError("eligible_failure must be boolean")
    for key in ("case_id", "trial_id"):
        if not isinstance(row[key], str) or not row[key]:
            raise ValueError(f"{key} must be a non-empty string")
    for key in (
        "repair_turns",
        "wrong_repairs",
        "wall_ms",
        "tool_calls",
        "intervention_count",
        "mcp_startup_ms",
        "mcp_idle_mb",
    ):
        value = row.get(key)
        if value is not None and (not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0):
            raise ValueError(f"{key} must be a non-negative number when present")


def _score_path(rows: list[dict]) -> dict:
    completion = _values(rows, "completion", bool)
    false_completion = _values(rows, "false_completion", bool)
    post_condition_correct = _values(rows, "post_condition_correct", bool)
    first_action_correct = _values(rows, "first_action_correct", bool)
    repair_turns = _values(rows, "repair_turns", (int, float))
    wrong_repairs = _values(rows, "wrong_repairs", (int, float))
    wall_ms = _values(rows, "wall_ms", (int, float))
    tool_calls = _values(rows, "tool_calls", (int, float))
    mcp_startup_ms = _values(rows, "mcp_startup_ms", (int, float))
    mcp_idle_mb = _values(rows, "mcp_idle_mb", (int, float))

    classified = [
        row
        for row in rows
        if row.get("expected_class") is not None and row.get("predicted_class") is not None
    ]
    classification_accuracy = (
        sum(row["expected_class"] == row["predicted_class"] for row in classified) / len(classified)
        if classified
        else None
    )
    unknown_rate = (
        sum(row.get("predicted_class") == "UNKNOWN" for row in classified) / len(classified)
        if classified
        else None
    )

    controls = [row for row in rows if row["eligible_failure"] is False]
    control_interventions = [
        row.get("intervention_count") > 0
        for row in controls
        if isinstance(row.get("intervention_count"), (int, float))
    ]

    return {
        "run_count": len(rows),
        "eligible_failure_count": sum(row["eligible_failure"] for row in rows),
        "control_count": len(controls),
        "completion_rate": _rate(completion),
        "median_repair_turns": _median(repair_turns),
        "median_wrong_repairs": _median(wrong_repairs),
        "classification_accuracy": classification_accuracy,
        "unknown_rate": unknown_rate,
        "first_action_correct_rate": _rate(first_action_correct),
        "false_completion_rate": _rate(false_completion),
        "post_condition_accuracy": _rate(post_condition_correct),
        "control_false_intervention_rate": _rate(control_interventions),
        "median_wall_ms": _median(wall_ms),
        "median_tool_calls": _median(tool_calls),
        "median_mcp_startup_ms": _median(mcp_startup_ms),
        "median_mcp_idle_mb": _median(mcp_idle_mb),
    }


def score_rows(rows: list[dict]) -> dict:
    if not rows:
        raise ValueError("at least one benchmark row is required")
    seen = set()
    for row in rows:
        _validate_row(row)
        identity = (row["case_id"], row["trial_id"], row["path"])
        if identity in seen:
            raise ValueError(f"duplicate run identity {identity}")
        seen.add(identity)

    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        grouped[row["path"]].append(row)

    paths = {path: _score_path(grouped[path]) for path in sorted(grouped)}
    return {
        "schema_version": 1,
        "row_count": len(rows),
        "paths": paths,
        "guardrails": {
            "known_good_zero_intervention": _zero_intervention_guardrail(paths),
            "false_completion_non_regression": "requires paired/repeated A/B interpretation",
            "desktop_lifecycle_admission": "not scored from synthetic/local rows alone",
        },
    }
def _zero_intervention_guardrail(paths: dict[str, dict]) -> bool | None:
    path_b = paths.get("B")
    if not path_b:
        return None
    rate = path_b.get("control_false_intervention_rate")
    if rate is None:
        return None
    return rate == 0.0


def main() -> int:
    parser = argparse.ArgumentParser(description="Score PowerShell Reliability A/B JSONL runs")
    parser.add_argument("input", type=pathlib.Path)
    args = parser.parse_args()
    try:
        report = score_rows(load_jsonl(args.input))
    except ValueError as exc:
        print(json.dumps({"schema_version": 1, "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
