import argparse
import datetime
import hashlib
import json
import pathlib
import random
import statistics
from collections import defaultdict

import trigger_eval

VALID_ARMS = {"S", "M"}
VALID_LANES = {"train", "validation", "holdout"}
VALID_GROUPS = {"should_trigger", "should_not_trigger", "boundary"}
BOUNDARY_KINDS = {"none", "first_command_nonzero", "tool_output_contains"}
TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)
GATE_PASS = "PASS"
GATE_FAIL = "FAIL"
GATE_UNRESOLVED = "UNRESOLVED"


def workspace_identity(value: str) -> str:
    normalized = str(pathlib.PureWindowsPath(value)).replace("/", "\\").rstrip("\\").casefold()
    return trigger_eval._sha256_text(normalized)


def _fixture_sha256(files: dict[str, str]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(files):
        path = pathlib.PurePosixPath(relative.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise ValueError(f"fixture path must stay relative: {relative!r}")
        content = files[relative]
        if not isinstance(content, str):
            raise ValueError(f"fixture content for {relative!r} must be text")
        digest.update(str(path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(content.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest().upper()


def _validate_case(case: dict) -> None:
    if not isinstance(case.get("case_id"), str) or not case["case_id"]:
        raise ValueError("case_id must be a non-empty string")
    if case.get("lane") not in VALID_LANES:
        raise ValueError(f"invalid lane for {case['case_id']}")
    if case.get("group") not in VALID_GROUPS:
        raise ValueError(f"invalid group for {case['case_id']}")
    if not isinstance(case.get("prompt"), str) or not case["prompt"]:
        raise ValueError(f"case {case['case_id']} missing prompt")
    if "{workspace}" in case["prompt"]:
        raise ValueError("routing prompts must not contain {workspace}")
    detector = case.get("boundary_detector")
    if not isinstance(detector, dict) or detector.get("kind") not in BOUNDARY_KINDS:
        raise ValueError(f"invalid boundary detector for {case['case_id']}")
    if detector.get("kind") == "tool_output_contains" and not isinstance(detector.get("marker"), str):
        raise ValueError("tool_output_contains requires a marker")
    files = case.get("files") or {}
    if not isinstance(files, dict):
        raise ValueError(f"case {case['case_id']} files must be an object")
    _fixture_sha256(files)


def _write_fixture(workspace: pathlib.Path, files: dict[str, str]) -> None:
    workspace.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        target = workspace / pathlib.PurePosixPath(relative.replace("\\", "/"))
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")


def _render_prompt(case: dict, case_key: str, trial_id: str) -> str:
    prompt = case["prompt"]
    replacements = {
        "{case_key}": case_key,
        "{case_id}": case["case_id"],
        "{trial_id}": trial_id,
    }
    for token, value in replacements.items():
        prompt = prompt.replace(token, value)
    return prompt


def prepare_campaign(cases: list[dict], output_root: pathlib.Path, trials: int, seed: int) -> list[dict]:
    if trials < 1:
        raise ValueError("trials must be at least 1")
    if not cases:
        raise ValueError("at least one routing case is required")
    seen_ids = set()
    for case in cases:
        _validate_case(case)
        if case["case_id"] in seen_ids:
            raise ValueError(f"duplicate case_id {case['case_id']}")
        seen_ids.add(case["case_id"])
    prompts_dir = output_root / "prompts"
    workspaces_dir = output_root / "workspaces"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    workspaces_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    manifest = []
    for trial_number in range(1, trials + 1):
        trial_id = f"T{trial_number:02d}"
        round_cases = list(cases)
        rng.shuffle(round_cases)
        for pair_index, case in enumerate(round_cases):
            case_key = f"{case['case_id']}-{trial_id}"
            prompt = _render_prompt(case, case_key, trial_id)
            prompt_path = prompts_dir / f"{case_key}.txt"
            prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
            fixture_hash = _fixture_sha256(case.get("files") or {})
            first_arm = "S" if (pair_index + trial_number) % 2 == 0 else "M"
            arms = (first_arm, "M" if first_arm == "S" else "S")
            for arm in arms:
                workspace = workspaces_dir / arm / case_key
                _write_fixture(workspace, case.get("files") or {})
                manifest.append({
                    "case_key": case_key,
                    "case_id": case["case_id"],
                    "trial_id": trial_id,
                    "lane": case["lane"],
                    "group": case["group"],
                    "arm": arm,
                    "title": case.get("title"),
                    "prompt_path": str(prompt_path),
                    "prompt_sha256": trigger_eval._sha256_text(prompt),
                    "workspace": str(workspace),
                    "workspace_sha256": workspace_identity(str(workspace)),
                    "fixture_sha256": fixture_hash,
                    "expected_first_command_fragment": case.get("expected_first_command_fragment"),
                    "boundary_detector": dict(case["boundary_detector"]),
                })
    for sequence, row in enumerate(manifest, 1):
        row["sequence"] = sequence
    trigger_eval.write_jsonl(output_root / "manifest.jsonl", manifest)
    summary = {"schema_version": 1, "pair_count": len(manifest) // 2, "trial_row_count": len(manifest)}
    summary["case_count"] = len(cases)
    summary["trials_per_case"] = trials
    summary["seed"] = seed
    campaign_path = output_root / "campaign.json"
    campaign_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def _catalog_observation(rows: list[dict]) -> tuple[bool, bool]:
    for row in rows:
        if row.get("type") != "world_state":
            continue
        payload = row.get("payload") or {}
        host_skills = (((payload.get("state") or {}).get("host_skills") or {}).get("body"))
        if isinstance(host_skills, str):
            return True, "powershell-reliability:" in host_skills.lower()
    return False, False


def _turn_cwd(rows: list[dict]) -> str | None:
    payload = trigger_eval._first_payload(rows, "turn_context")
    value = payload.get("cwd")
    return value if isinstance(value, str) and value else None


def _scan_tool_events(rows: list[dict]) -> tuple[list[dict], dict[str, dict]]:
    calls = []
    outputs = {}
    for index, row in enumerate(rows):
        if row.get("type") != "response_item":
            continue
        payload = row.get("payload") or {}
        kind = payload.get("type")
        if kind == "custom_tool_call":
            calls.append({"index": index, "timestamp": row.get("timestamp"), "call_id": payload.get("call_id"), "input": payload.get("input") or ""})
        elif kind == "custom_tool_call_output":
            outputs[payload.get("call_id")] = {"index": index, "timestamp": row.get("timestamp"), "text": trigger_eval._flatten_text(payload.get("output"))}
    return calls, outputs


def _first_command(calls: list[dict], outputs: dict[str, dict]) -> dict | None:
    for call in calls:
        if trigger_eval.SHELL_CALL not in call["input"]:
            continue
        result = dict(call)
        output = outputs.get(call.get("call_id"))
        result["output_index"] = output.get("index") if output else None
        result["output_timestamp"] = output.get("timestamp") if output else None
        result["output_text"] = output.get("text", "") if output else ""
        match = trigger_eval.EXIT_RE.search(result["output_text"])
        result["exit_code"] = int(match.group(1)) if match else None
        return result
    return None


def find_eligible_boundary(rows: list[dict], manifest_row: dict, first_command: dict | None) -> dict | None:
    detector = manifest_row["boundary_detector"]
    kind = detector["kind"]
    if kind == "none":
        return None
    if kind == "first_command_nonzero":
        if first_command and first_command.get("exit_code") not in (None, 0) and first_command.get("output_index") is not None:
            return {"kind": kind, "index": first_command["output_index"], "timestamp": first_command.get("output_timestamp")}
        return None
    if kind == "tool_output_contains":
        marker = detector["marker"]
        for index, row in enumerate(rows):
            if row.get("type") != "response_item":
                continue
            payload = row.get("payload") or {}
            if payload.get("type") == "custom_tool_call_output" and marker in trigger_eval._flatten_text(payload.get("output")):
                return {"kind": kind, "index": index, "timestamp": row.get("timestamp")}
        return None
    raise ValueError(f"unsupported boundary detector {kind!r}")


def extract_trial(rows: list[dict], rollout_path: pathlib.Path, manifest_row: dict) -> dict:
    base = trigger_eval.extract_rollout(rows, rollout_path)
    if base is None:
        raise ValueError("rollout contains no routing case marker")
    calls, outputs = _scan_tool_events(rows)
    first_command = _first_command(calls, outputs)
    boundary = find_eligible_boundary(rows, manifest_row, first_command)
    skill_calls = [call for call in calls if trigger_eval.PSR_SKILL in trigger_eval._skill_names(call["input"])]
    mcp_calls = [call for call in calls if trigger_eval.PSR_MCP in call["input"]]
    skill_indexes = [call["index"] for call in skill_calls]
    mcp_indexes = [call["index"] for call in mcp_calls]
    boundary_index = boundary.get("index") if boundary else None
    invalid_reasons = []
    if base["case_key"] != manifest_row.get("case_key"):
        invalid_reasons.append("case_marker_mismatch")
    if base.get("prompt_sha256") != manifest_row.get("prompt_sha256"):
        invalid_reasons.append("prompt_hash_mismatch")
    cwd = _turn_cwd(rows)
    if cwd is None or workspace_identity(cwd) != manifest_row.get("workspace_sha256"):
        invalid_reasons.append("workspace_mismatch")
    catalog_observed, psr_visible = _catalog_observation(rows)
    if not catalog_observed:
        invalid_reasons.append("arm_catalog_unobserved")
    elif (manifest_row["arm"] == "S") != psr_visible:
        invalid_reasons.append("arm_catalog_mismatch")
    expected = manifest_row.get("expected_first_command_fragment")
    if expected:
        actual = first_command.get("input") if first_command else None
        if trigger_eval._norm_command(expected) not in trigger_eval._norm_command(actual):
            invalid_reasons.append("first_command_mismatch")
    premature = boundary_index is not None and any(index < boundary_index for index in skill_indexes)
    pre_boundary_mcp = (
        sum(index < boundary_index for index in mcp_indexes)
        if boundary_index is not None
        else len(mcp_indexes)
    )
    s_bypass = False
    if manifest_row["arm"] == "S":
        for mcp_index in mcp_indexes:
            if not any(skill_index < mcp_index for skill_index in skill_indexes):
                s_bypass = True
                break
    turn_complete_index = len(rows) - 1 if rows else None
    turn_complete_timestamp = rows[-1].get("timestamp") if rows else None
    record = {
        "schema_version": 1,
        "case_key": manifest_row["case_key"],
        "case_id": manifest_row["case_id"],
        "trial_id": manifest_row["trial_id"],
        "lane": manifest_row["lane"],
        "group": manifest_row["group"],
        "arm": manifest_row["arm"],
        "sequence": manifest_row.get("sequence"),
        "rollout_path": str(rollout_path),
        "session_id": base.get("session_id"),
        "originator": base.get("originator"),
        "cli_version": base.get("cli_version"),
        "model": base.get("model"),
        "effort": base.get("effort"),
        "approval_policy": base.get("approval_policy"),
        "sandbox_type": base.get("sandbox_type"),
        "prompt_sha256": base.get("prompt_sha256"),
        "workspace_sha256": manifest_row.get("workspace_sha256"),
        "fixture_sha256": manifest_row.get("fixture_sha256"),
        "psr_available_in_catalog": psr_visible if catalog_observed else None,
        "first_attempt_start_index": first_command.get("index") if first_command else None,
        "first_attempt_end_index": first_command.get("output_index") if first_command else None,
        "first_command_exit_code": first_command.get("exit_code") if first_command else None,
        "first_command_input_sha256": trigger_eval._sha256_text(first_command["input"]) if first_command else None,
        "eligible_boundary_kind": boundary.get("kind") if boundary else None,
        "eligible_boundary_index": boundary_index,
        "eligible_boundary_timestamp": boundary.get("timestamp") if boundary else None,
        "skill_activation_indexes": skill_indexes,
        "skill_activation_timestamps": [call.get("timestamp") for call in skill_calls],
        "skill_activation_count": len(skill_indexes),
        "premature_skill_activation": premature,
        "mcp_intervention_indexes": mcp_indexes,
        "mcp_intervention_timestamps": [call.get("timestamp") for call in mcp_calls],
        "mcp_intervention_count": len(mcp_indexes),
        "pre_boundary_mcp_call_count": pre_boundary_mcp,
        "s_protocol_bypass": s_bypass,
        "selected_other_skills": base.get("selected_other_skills") or [],
        "turn_complete_index": turn_complete_index,
        "turn_complete_timestamp": turn_complete_timestamp,
        "valid": not invalid_reasons,
        "invalid_reasons": invalid_reasons,
    }
    return record


def collect_rollouts(sessions_root: pathlib.Path, manifest: list[dict]) -> list[dict]:
    manifest_index = {}
    known_case_keys = set()
    for row in manifest:
        key = (row["case_key"], row["workspace_sha256"])
        if key in manifest_index:
            raise ValueError(f"duplicate manifest binding {key}")
        manifest_index[key] = row
        known_case_keys.add(row["case_key"])
    records = []
    seen = set()
    for path in sorted(sessions_root.rglob("rollout-*.jsonl")):
        raw_text = path.read_text(encoding="utf-8-sig", errors="replace")
        markers = {match.upper() for match in trigger_eval.CASE_RE.findall(raw_text)}
        if not (markers & known_case_keys):
            continue
        rows = trigger_eval.load_jsonl(path)
        case_key, _ = trigger_eval._case_user_message(rows)
        if case_key not in known_case_keys:
            continue
        cwd = _turn_cwd(rows)
        if cwd is None:
            continue
        manifest_row = manifest_index.get((case_key, workspace_identity(cwd)))
        if manifest_row is None:
            continue
        identity = (manifest_row["case_id"], manifest_row["trial_id"], manifest_row["arm"])
        if identity in seen:
            raise ValueError(f"duplicate rollout for routing trial {identity}")
        seen.add(identity)
        records.append(extract_trial(rows, path, manifest_row))
    return sorted(records, key=lambda row: row.get("sequence") or 0)
