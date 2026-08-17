import argparse
import hashlib
import json
import pathlib
import random
import re
from collections import defaultdict

CASE_RE = re.compile(r"\[CASE-ID:\s*([A-Z]\d{2}-T\d{2})\]", re.IGNORECASE)
EXIT_RE = re.compile(r"Exit code:\s*(-?\d+)", re.IGNORECASE)
SKILL_PATH_RE = re.compile(
    r"(?:[\\/])skills[\\/](?:\.system[\\/])?([^\\/'\"\s]+)[\\/]SKILL\.md",
    re.IGNORECASE,
)
ALIASED_SKILL_RE = re.compile(r"\br\d+[\\/]([^\\/'\"\s]+)[\\/]SKILL\.md", re.IGNORECASE)
PSR_SKILL = "powershell-reliability"
PSR_MCP = "mcp__psr_reliability_native__"
SHELL_CALLS = ("tools.shell_command", "tools.exec_command")
VALID_GROUPS = {"should_trigger", "should_not_trigger", "boundary"}


def _is_shell_call(call_input: str) -> bool:
    return any(name in call_input for name in SHELL_CALLS)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest().upper()


def load_jsonl(path: pathlib.Path) -> list[dict]:
    rows = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"line {line_number} must contain a JSON object")
        rows.append(value)
    return rows


def write_jsonl(path: pathlib.Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def _flatten_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(_flatten_text(item) for item in value)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        return "\n".join(_flatten_text(item) for item in value.values())
    return ""


def _skill_names(call_input: str) -> list[str]:
    names = {match.group(1).lower() for match in SKILL_PATH_RE.finditer(call_input)}
    names.update(match.group(1).lower() for match in ALIASED_SKILL_RE.finditer(call_input))
    return sorted(names)


def _first_payload(rows: list[dict], record_type: str) -> dict:
    for row in rows:
        if row.get("type") == record_type and isinstance(row.get("payload"), dict):
            return row["payload"]
    return {}


def _first_user_message(rows: list[dict]) -> str:
    for row in rows:
        if row.get("type") != "event_msg":
            continue
        payload = row.get("payload") or {}
        if payload.get("type") == "user_message":
            return payload.get("message") or ""
    return ""


def _case_user_message(rows: list[dict]) -> tuple[str | None, str]:
    message = _first_user_message(rows)
    match = CASE_RE.search(message)
    if match:
        return match.group(1).upper(), message
    return None, message


def _desktop_prompt_text(message: str) -> str:
    if message.endswith("\r\n"):
        return message[:-2]
    if message.endswith("\n"):
        return message[:-1]
    return message


def extract_rollout(
    rows: list[dict],
    rollout_path: pathlib.Path,
    expected_case_key: str | None = None,
) -> dict | None:
    case_key, user_message = _case_user_message(rows)
    if case_key is None:
        if expected_case_key is None or not user_message:
            return None
        case_key = expected_case_key
    session_meta = _first_payload(rows, "session_meta")
    turn_context = _first_payload(rows, "turn_context")
    world_state = _first_payload(rows, "world_state")
    tool_calls = []
    outputs_by_call_id = {}
    selected_skills = []
    reliability_calls = []
    first_command = None
    for index, row in enumerate(rows):
        if row.get("type") != "response_item":
            continue
        payload = row.get("payload") or {}
        if payload.get("type") == "custom_tool_call":
            call_input = payload.get("input") or ""
            call = {
                "index": index,
                "call_id": payload.get("call_id"),
                "name": payload.get("name"),
                "input": call_input,
            }
            tool_calls.append(call)
            names = _skill_names(call_input)
            selected_skills.extend(names)
            if PSR_MCP in call_input:
                reliability_calls.append(call)
            if first_command is None and _is_shell_call(call_input):
                first_command = call
        elif payload.get("type") == "custom_tool_call_output":
            outputs_by_call_id[payload.get("call_id")] = _flatten_text(payload.get("output"))

    psr_indexes = [call["index"] for call in tool_calls if PSR_SKILL in _skill_names(call["input"])]
    first_command_index = first_command["index"] if first_command else None
    psr_first_index = min(psr_indexes) if psr_indexes else None
    selected_before = psr_first_index is not None and (
        first_command_index is None or psr_first_index < first_command_index
    )
    reliability_before = sum(
        1
        for call in reliability_calls
        if first_command_index is None or call["index"] < first_command_index
    )
    first_exit = None
    if first_command is not None:
        output = outputs_by_call_id.get(first_command.get("call_id"), "")
        match = EXIT_RE.search(output)
        if match:
            first_exit = int(match.group(1))
    host_skills = (((world_state.get("state") or {}).get("host_skills") or {}).get("body") or "")
    sandbox = turn_context.get("sandbox_policy") or {}
    selected_unique = sorted(set(selected_skills))
    return {
        "schema_version": 1,
        "case_key": case_key,
        "session_id": session_meta.get("session_id") or session_meta.get("id"),
        "rollout_path": str(rollout_path),
        "originator": session_meta.get("originator"),
        "cli_version": session_meta.get("cli_version"),
        "model": turn_context.get("model"),
        "effort": turn_context.get("effort"),
        "approval_policy": turn_context.get("approval_policy"),
        "sandbox_type": sandbox.get("type") if isinstance(sandbox, dict) else None,
        "psr_available_in_catalog": "powershell-reliability:" in host_skills.lower(),
        "prompt_sha256": _sha256_text(_desktop_prompt_text(user_message)),
        "psr_skill_selected": PSR_SKILL in selected_unique,
        "psr_skill_read_count": sum(name == PSR_SKILL for name in selected_skills),
        "psr_skill_selected_before_first_command": selected_before,
        "selected_other_skills": [name for name in selected_unique if name != PSR_SKILL],
        "reliability_mcp_calls": len(reliability_calls),
        "reliability_mcp_calls_before_first_command": reliability_before,
        "first_command_input": first_command.get("input") if first_command else None,
        "first_command_exit_code": first_exit,
        "custom_tool_call_count": len(tool_calls),
    }


def validate_expected_first_command_fragment(value) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected first command fragment must be a non-empty string")
    return value


def _norm_command(value: str | None) -> str:
    if value is None:
        return ""
    normalized = value.lower().replace("/", "\\")
    while "\\\\" in normalized:
        normalized = normalized.replace("\\\\", "\\")
    return " ".join(normalized.split())


_COMMAND_FRAGMENT_BOUNDARIES = set("\\/\"'()[]{};,&|<>")
_QUOTE_OPEN_BOUNDARIES = set(":({[,;|&<>")


def _command_component_char(value: str) -> bool:
    return not value.isspace() and value not in _COMMAND_FRAGMENT_BOUNDARIES


_STRUCTURED_TOOL_START_RE = re.compile(
    r"tools\.(shell_command|exec_command)\s*\(\s*\{",
    re.IGNORECASE,
)


def _quote_is_escaped(value: str, index: int, start: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= start and value[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _find_structured_tool_start(value: str):
    quote = None
    quote_start = 0
    index = 0
    while index < len(value):
        char = value[index]
        if quote is not None:
            if char == quote and not _quote_is_escaped(value, index, quote_start):
                quote = None
            index += 1
            continue
        if char in {"\"", "'"}:
            quote = char
            quote_start = index + 1
            index += 1
            continue
        match = _STRUCTURED_TOOL_START_RE.match(value, index)
        if match is not None:
            return match
        index += 1
    return None


def _consume_quoted_string(value: str, index: int) -> tuple[str, int] | None:
    quote = value[index]
    start = index + 1
    cursor = start
    decoded: list[str] = []
    segment_start = start
    while cursor < len(value):
        if value[cursor] == "\\" and cursor + 1 < len(value) and value[cursor + 1] == quote:
            decoded.append(value[segment_start:cursor])
            decoded.append(quote)
            cursor += 2
            segment_start = cursor
            continue
        if value[cursor] == quote and not _quote_is_escaped(value, cursor, start):
            decoded.append(value[segment_start:cursor])
            return "".join(decoded), cursor + 1
        cursor += 1
    return None


def _skip_structured_value(value: str, index: int) -> tuple[int, str] | None:
    quote = None
    quote_start = index
    stack: list[str] = []
    closers = {"(": ")", "[": "]", "{": "}"}
    while index < len(value):
        char = value[index]
        if quote is not None:
            if char == quote and not _quote_is_escaped(value, index, quote_start):
                quote = None
            index += 1
            continue
        if char in {"\"", "'"}:
            quote = char
            quote_start = index + 1
        elif char in closers:
            stack.append(closers[char])
        elif char in {")", "]", "}"}:
            if stack:
                if char != stack[-1]:
                    return None
                stack.pop()
            elif char == "}":
                return index, char
            else:
                return None
        elif char == "," and not stack:
            return index, char
        index += 1
    return None


def _structured_tool_command(value: str) -> tuple[bool, str | None]:
    match = _find_structured_tool_start(value)
    if match is None:
        return False, None
    target = "command" if match.group(1).lower() == "shell_command" else "cmd"
    index = match.end()
    command = None
    command_seen = False
    while index < len(value):
        while index < len(value) and value[index].isspace():
            index += 1
        if index >= len(value):
            return True, None
        if value[index] == "}":
            index += 1
            while index < len(value) and value[index].isspace():
                index += 1
            if index >= len(value) or value[index] != ")":
                return True, None
            return True, command if command_seen else None
        key_match = re.match(r"[A-Za-z_][A-Za-z0-9_]*", value[index:])
        if key_match is None:
            return True, None
        key = key_match.group(0).lower()
        index += len(key_match.group(0))
        while index < len(value) and value[index].isspace():
            index += 1
        if index >= len(value) or value[index] != ":":
            return True, None
        index += 1
        while index < len(value) and value[index].isspace():
            index += 1
        if key == target:
            if command_seen or index >= len(value) or value[index] not in {"\"", "'"}:
                return True, None
            parsed = _consume_quoted_string(value, index)
            if parsed is None:
                return True, None
            command, index = parsed
            command_seen = True
            while index < len(value) and value[index].isspace():
                index += 1
            if index >= len(value) or value[index] not in {",", "}"}:
                return True, None
            if value[index] == ",":
                index += 1
                continue
            continue
        boundary = _skip_structured_value(value, index)
        if boundary is None:
            return True, None
        index, delimiter = boundary
        if delimiter == ",":
            index += 1
            continue
    return True, None

def _command_match_candidates(value: str | None) -> list[str]:
    if not isinstance(value, str) or not value:
        return []
    recognized, command = _structured_tool_command(value)
    if recognized:
        return [command] if command is not None else []
    return [value]

def _left_fragment_boundary(command: str, index: int) -> bool:
    cursor = index - 1
    while cursor >= 0 and command[cursor] in {"\"", "'"}:
        cursor -= 1
    if cursor < 0:
        return True
    previous = command[cursor]
    return previous.isspace() or previous in _QUOTE_OPEN_BOUNDARIES or not _command_component_char(previous)


def _right_fragment_boundary(command: str, end: int) -> bool:
    cursor = end
    while cursor < len(command) and command[cursor] in {"\"", "'"}:
        cursor += 1
    return cursor >= len(command) or not _command_component_char(command[cursor])


def _cmd_c_single_token_quote_variant(fragment: str) -> str | None:
    prefix = "cmd.exe \\d \\c "
    if not fragment.startswith(prefix):
        return None
    tail = fragment[len(prefix):]
    if not tail or any(char.isspace() for char in tail) or any(char in "\"'" for char in tail):
        return None
    return prefix + '"' + tail


def _normalized_fragment_matches(fragment: str, command: str) -> bool:
    start = 0
    while True:
        index = command.find(fragment, start)
        if index < 0:
            return False
        end = index + len(fragment)
        left_ok = (
            not _command_component_char(fragment[0])
            or index == 0
            or _left_fragment_boundary(command, index)
        )
        right_ok = (
            not _command_component_char(fragment[-1])
            or _right_fragment_boundary(command, end)
        )
        if left_ok and right_ok:
            return True
        start = index + 1


def command_fragment_matches(expected: str | None, actual: str | None) -> bool:
    fragment = _norm_command(expected)
    if not fragment:
        return False
    fragments = [fragment]
    quote_variant = _cmd_c_single_token_quote_variant(fragment)
    if quote_variant is not None:
        fragments.append(quote_variant)
    for candidate in _command_match_candidates(actual):
        command = _norm_command(candidate)
        if command and any(_normalized_fragment_matches(item, command) for item in fragments):
            return True
    return False


def attach_manifest(records: list[dict], manifest: list[dict]) -> list[dict]:
    by_key = {row["case_key"]: row for row in manifest}
    attached = []
    for record in records:
        meta = by_key.get(record["case_key"])
        if meta is None:
            continue
        row = dict(record)
        for key in ("case_id", "trial_id", "group", "title", "sequence", "expected_first_command_fragment"):
            row[key] = meta.get(key)
        expected = validate_expected_first_command_fragment(meta.get("expected_first_command_fragment"))
        command_input = record.get("first_command_input")
        if expected is not None:
            row["first_command_matches_expectation"] = command_fragment_matches(expected, command_input)
        else:
            row["first_command_matches_expectation"] = None
        row["first_command_input_sha256"] = _sha256_text(command_input) if command_input else None
        row.pop("first_command_input", None)
        attached.append(row)
    return sorted(attached, key=lambda row: row.get("sequence") or 0)


def collect_rollouts(sessions_root: pathlib.Path, manifest: list[dict]) -> list[dict]:
    for row in manifest:
        validate_expected_first_command_fragment(row.get("expected_first_command_fragment"))
    known = {row["case_key"] for row in manifest}
    records = []
    seen = set()
    for path in sorted(sessions_root.rglob("rollout-*.jsonl")):
        raw_text = path.read_text(encoding="utf-8-sig", errors="replace")
        markers = {match.upper() for match in CASE_RE.findall(raw_text)}
        if not (markers & known):
            continue
        record = extract_rollout(load_jsonl(path), path)
        if record is None or record["case_key"] not in known:
            continue
        if record["case_key"] in seen:
            raise ValueError(f"duplicate rollout for {record['case_key']}")
        seen.add(record["case_key"])
        records.append(record)
    return attach_manifest(records, manifest)


def _validate_score_record(row: dict) -> None:
    if row.get("group") not in VALID_GROUPS:
        raise ValueError(f"unsupported trigger group {row.get('group')!r}")
    for key in ("case_id", "trial_id"):
        if not isinstance(row.get(key), str) or not row[key]:
            raise ValueError(f"{key} must be a non-empty string")
    for key in ("psr_skill_selected", "psr_skill_selected_before_first_command"):
        if not isinstance(row.get(key), bool):
            raise ValueError(f"{key} must be boolean")


def _rate(values: list[bool]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _group_report(rows: list[dict], expected: bool | None) -> dict:
    selections = [row["psr_skill_selected"] for row in rows]
    report = {
        "trial_count": len(rows),
        "selection_rate": _rate(selections),
        "pre_first_attempt_selection_violations": sum(
            row["psr_skill_selected_before_first_command"] for row in rows
        ),
        "reliability_mcp_call_count": sum(int(row.get("reliability_mcp_calls") or 0) for row in rows),
    }
    if expected is True:
        report["selection_recall"] = _rate(selections)
        report["false_negative_count"] = sum(not value for value in selections)
    elif expected is False:
        report["false_positive_rate"] = _rate(selections)
        report["false_positive_count"] = sum(selections)
    return report


def _case_stability(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["case_id"]].append(row["psr_skill_selected"])
    return [
        {
            "case_id": case_id,
            "trial_count": len(values),
            "selection_rate": _rate(values),
            "stable": len(set(values)) <= 1,
        }
        for case_id, values in sorted(grouped.items())
    ]


def _environment_consistency(rows: list[dict]) -> dict:
    keys = ("model", "effort", "cli_version", "approval_policy", "sandbox_type")
    variants = {
        key: sorted({str(row[key]) for row in rows if row.get(key) is not None})
        for key in keys
    }
    constant = all(len(values) <= 1 for values in variants.values()) and not any(
        row.get("psr_available_in_catalog") is False for row in rows
    )
    return {"constant": constant, **variants}


def score_records(records: list[dict]) -> dict:
    if not records:
        raise ValueError("at least one trigger-eval record is required")
    seen = set()
    for row in records:
        _validate_score_record(row)
        identity = (row["case_id"], row["trial_id"])
        if identity in seen:
            raise ValueError(f"duplicate trigger trial identity {identity}")
        seen.add(identity)
    should = [row for row in records if row["group"] == "should_trigger"]
    should_not = [row for row in records if row["group"] == "should_not_trigger"]
    boundary = [row for row in records if row["group"] == "boundary"]
    return {
        "schema_version": 1,
        "record_count": len(records),
        "implicit_should_trigger": _group_report(should, True),
        "implicit_should_not_trigger": _group_report(should_not, False),
        "boundary": _group_report(boundary, None),
        "implicit_overall": {
            "pre_first_attempt_selection_violations": sum(
                row["psr_skill_selected_before_first_command"] for row in records
            ),
            "collision_trial_count": sum(bool(row.get("selected_other_skills")) for row in records),
            "catalog_missing_trial_count": sum(row.get("psr_available_in_catalog") is False for row in records),
            "first_command_mismatch_count": sum(
                row.get("first_command_matches_expectation") is False for row in records
            ),
        },
        "case_stability": _case_stability(records),
        "environment_consistency": _environment_consistency(records),
    }


def load_cases(path: pathlib.Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list) or not value:
        raise ValueError("cases file must contain a non-empty JSON array")
    ids = set()
    for case in value:
        if case.get("case_id") in ids:
            raise ValueError(f"duplicate case_id {case.get('case_id')}")
        ids.add(case.get("case_id"))
        if case.get("group") not in VALID_GROUPS:
            raise ValueError(f"invalid group for {case.get('case_id')}")
        if "prompt" not in case or "title" not in case:
            raise ValueError(f"case {case.get('case_id')} missing title or prompt")
        validate_expected_first_command_fragment(case.get("expected_first_command_fragment"))
    return value


def prepare_campaign(cases: list[dict], output_root: pathlib.Path, trials: int, seed: int) -> list[dict]:
    if trials < 1:
        raise ValueError("trials must be at least 1")
    for case in cases:
        validate_expected_first_command_fragment(case.get("expected_first_command_fragment"))
    prompts_dir = output_root / "prompts"
    workspaces_dir = output_root / "workspaces"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for case in cases:
        for trial_number in range(1, trials + 1):
            trial_id = f"T{trial_number:02d}"
            case_key = f"{case['case_id']}-{trial_id}"
            workspace = workspaces_dir / case_key
            workspace.mkdir(parents=True, exist_ok=True)
            for relative, content in (case.get("files") or {}).items():
                target = workspace / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            prompt = case["prompt"]
            replacements = {
                "{workspace}": str(workspace).replace("/", "\\"),
                "{case_key}": case_key,
                "{case_id}": case["case_id"],
                "{trial_id}": trial_id,
            }
            for token, replacement in replacements.items():
                prompt = prompt.replace(token, replacement)
            manifest.append({
                "case_key": case_key,
                "case_id": case["case_id"],
                "trial_id": trial_id,
                "group": case["group"],
                "title": case["title"],
                "prompt": prompt,
                "prompt_sha256": _sha256_text(prompt),
                "workspace": str(workspace),
                "expected_first_command_fragment": case.get("expected_first_command_fragment"),
            })
    rng = random.Random(seed)
    ordered = []
    for trial_id in sorted({row["trial_id"] for row in manifest}):
        round_rows = [row for row in manifest if row["trial_id"] == trial_id]
        rng.shuffle(round_rows)
        ordered.extend(round_rows)
    manifest = ordered
    for sequence, row in enumerate(manifest, 1):
        row["sequence"] = sequence
        prompt_path = prompts_dir / f"{sequence:03d}.txt"
        prompt_path.write_text(row["prompt"], encoding="utf-8", newline="\n")
        row["prompt_path"] = str(prompt_path)
    write_jsonl(output_root / "manifest.jsonl", manifest)
    summary = {
        "schema_version": 1,
        "trial_count": len(manifest),
        "case_count": len(cases),
        "trials_per_case": trials,
        "seed": seed,
        "groups": {group: sum(case["group"] == group for case in cases) for group in sorted(VALID_GROUPS)},
    }
    (output_root / "campaign.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return manifest


def _status(manifest: list[dict], records: list[dict]) -> dict:
    collected = {row["case_key"] for row in records}
    remaining = [row for row in manifest if row["case_key"] not in collected]
    return {
        "expected_trials": len(manifest),
        "collected_trials": len(records),
        "remaining_trials": len(remaining),
        "next_prompt_path": remaining[0].get("prompt_path") if remaining else None,
        "next_case_key": remaining[0].get("case_key") if remaining else None,
    }


def _write_report(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare, collect, and score Codex Desktop Skill trigger trials")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--cases", type=pathlib.Path, required=True)
    prepare.add_argument("--output-root", type=pathlib.Path, required=True)
    prepare.add_argument("--trials", type=int, default=3)
    prepare.add_argument("--seed", type=int, default=20260813)

    collect = sub.add_parser("collect")
    collect.add_argument("--manifest", type=pathlib.Path, required=True)
    collect.add_argument("--sessions-root", type=pathlib.Path, required=True)
    collect.add_argument("--output", type=pathlib.Path, required=True)
    collect.add_argument("--report", type=pathlib.Path)

    score = sub.add_parser("score")
    score.add_argument("--records", type=pathlib.Path, required=True)
    score.add_argument("--output", type=pathlib.Path)

    args = parser.parse_args()
    try:
        if args.command == "prepare":
            manifest = prepare_campaign(load_cases(args.cases), args.output_root, args.trials, args.seed)
            print(json.dumps({"prepared_trials": len(manifest), "manifest": str(args.output_root / "manifest.jsonl")}, ensure_ascii=False))
        elif args.command == "collect":
            manifest = load_jsonl(args.manifest)
            records = collect_rollouts(args.sessions_root, manifest)
            write_jsonl(args.output, records)
            report = {"status": _status(manifest, records), "score": score_records(records) if records else None}
            if args.report:
                _write_report(args.report, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
        elif args.command == "score":
            report = score_records(load_jsonl(args.records))
            if args.output:
                _write_report(args.output, report)
            print(json.dumps(report, ensure_ascii=False, indent=2))
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
