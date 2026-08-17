import argparse
import datetime
import hashlib
import json
import pathlib
import random
import re
import secrets
import tempfile
import statistics
import stat
from collections import defaultdict

import trigger_eval

VALID_ARMS = {"S", "M"}
VALID_LANES = {"train", "validation", "holdout"}
VALID_GROUPS = {"should_trigger", "should_not_trigger", "boundary"}
BOUNDARY_KINDS = {"none", "first_command_nonzero", "tool_output_contains"}
POST_CONDITION_KINDS = {"none", "tool_output_marker", "workspace_state"}
WORKSPACE_CHECK_KINDS = {"file_exists", "file_absent", "directory_exists", "file_sha256", "file_size"}
MAX_POST_CONDITION_CHECKS = 32
MAX_WORKSPACE_PATH_BYTES = 32_768
MAX_POST_CONDITION_HASH_BYTES = 64 * 1024 * 1024
PAIR_CONSISTENCY_FIELDS = (
    "prompt_sha256", "fixture_sha256", "model", "effort",
    "approval_policy", "sandbox_type", "cli_version", "originator",
)
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


def _workspace_relative_path(value: str) -> pathlib.PurePosixPath:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > MAX_WORKSPACE_PATH_BYTES
        or "\0" in value
    ):
        raise ValueError("workspace-state path must be non-empty, bounded, and NUL-free")
    windows = pathlib.PureWindowsPath(value)
    path = pathlib.PurePosixPath(value.replace("\\", "/"))
    if windows.drive or windows.is_absolute() or path.is_absolute() or ".." in path.parts:
        raise ValueError("workspace-state path must stay relative to the trial workspace")
    return path


def _resolved_workspace_target(workspace: pathlib.Path, relative: str) -> pathlib.Path:
    base = workspace.resolve()
    target = (base / _workspace_relative_path(relative)).resolve(strict=False)
    if target != base and base not in target.parents:
        raise ValueError("workspace-state path escapes trial workspace")
    return target


def _bounded_nonnegative_int(value, field: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"workspace-state {field} must be a non-negative integer")
    return value


def _post_condition_rule(case: dict) -> dict:
    rule = case.get("post_condition", {"kind": "none"})
    if not isinstance(rule, dict) or rule.get("kind") not in POST_CONDITION_KINDS:
        raise ValueError(f"invalid post-condition rule for {case.get('case_id')}")
    if rule["kind"] == "tool_output_marker":
        pass_marker = rule.get("pass_marker")
        fail_marker = rule.get("fail_marker")
        if not isinstance(pass_marker, str) or not pass_marker or not isinstance(fail_marker, str) or not fail_marker:
            raise ValueError("post-condition markers must be non-empty strings")
        if pass_marker == fail_marker:
            raise ValueError("post-condition pass/fail markers must differ")
    elif rule["kind"] == "workspace_state":
        mode = rule.get("mode")
        checks = rule.get("checks")
        if mode not in {"all", "any"}:
            raise ValueError("workspace-state mode must be all or any")
        if not isinstance(checks, list) or not (1 <= len(checks) <= MAX_POST_CONDITION_CHECKS):
            raise ValueError("workspace-state checks must contain 1..32 entries")
        for check in checks:
            if not isinstance(check, dict) or check.get("kind") not in WORKSPACE_CHECK_KINDS:
                raise ValueError("workspace-state check kind is not supported")
            _workspace_relative_path(check.get("path"))
            if check["kind"] == "file_sha256":
                expected = check.get("expected_sha256")
                if not isinstance(expected, str) or len(expected) != 64 or any(ch not in "0123456789abcdefABCDEF" for ch in expected):
                    raise ValueError("workspace-state expected_sha256 must be 64 hex characters")
            if check["kind"] == "file_size":
                minimum = _bounded_nonnegative_int(check.get("min_bytes"), "min_bytes")
                maximum = _bounded_nonnegative_int(check.get("max_bytes"), "max_bytes")
                if minimum is not None and maximum is not None and minimum > maximum:
                    raise ValueError("workspace-state min_bytes must not exceed max_bytes")
    return rule


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
    expected_first_command = case.get("expected_first_command_fragment")
    if expected_first_command is not None and (
        not isinstance(expected_first_command, str) or not expected_first_command.strip()
    ):
        raise ValueError("expected first command fragment must be a non-empty string")
    detector = case.get("boundary_detector")
    if not isinstance(detector, dict) or detector.get("kind") not in BOUNDARY_KINDS:
        raise ValueError(f"invalid boundary detector for {case['case_id']}")
    if detector.get("kind") == "tool_output_contains" and not isinstance(detector.get("marker"), str):
        raise ValueError("tool_output_contains requires a marker")
    _post_condition_rule(case)
    files = case.get("files") or {}
    if not isinstance(files, dict):
        raise ValueError(f"case {case['case_id']} files must be an object")
    _fixture_sha256(files)


def _path_is_link_or_junction(path: pathlib.Path) -> bool:
    is_junction = getattr(path, "is_junction", lambda: False)
    return path.is_symlink() or bool(is_junction())


def _write_fixture(workspace: pathlib.Path, files: dict[str, str]) -> None:
    if not workspace.is_dir():
        raise ValueError("fixture workspace must already exist")
    for relative, content in files.items():
        try:
            target = _resolved_workspace_target(workspace, relative)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"fixture path must stay relative: {relative!r}") from exc
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


OPAQUE_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _opaque_token(token_factory=None) -> str:
    value = (token_factory or (lambda: secrets.token_hex(16)))()
    if not isinstance(value, str) or not OPAQUE_TOKEN_RE.fullmatch(value):
        raise ValueError("opaque runtime token must be exactly 32 lowercase hex characters")
    return value


def _path_is_relative_to(child: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _prepare_campaign_impl(
    cases: list[dict],
    output_root: pathlib.Path,
    trials: int,
    seed: int,
    runtime_parent: pathlib.Path | None = None,
    token_factory=None,
) -> list[dict]:
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
    output_root = output_root.resolve(strict=False)
    runtime_parent = (runtime_parent or pathlib.Path(tempfile.gettempdir())).resolve(strict=False)
    campaign_token = _opaque_token(token_factory)
    raw_runtime_root = runtime_parent / campaign_token
    if _path_is_link_or_junction(raw_runtime_root):
        raise ValueError("runtime root must not be a symlink or junction")
    if raw_runtime_root.exists():
        raise ValueError("opaque runtime root must be new and empty")
    runtime_root = raw_runtime_root.resolve(strict=False)
    if runtime_root.parent != runtime_parent:
        raise ValueError("runtime root must remain a direct child of the neutral runtime parent")
    if _path_is_relative_to(runtime_root, output_root) or _path_is_relative_to(output_root, runtime_root):
        raise ValueError("coordinator and runtime roots must be disjoint")
    prompts_dir = output_root / "prompts"
    fixtures_dir = output_root / "fixtures"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    if _path_is_link_or_junction(prompts_dir) or _path_is_link_or_junction(fixtures_dir):
        raise ValueError("coordinator prompt/fixture directories must not be symlinks or junctions")
    runtime_parent.mkdir(parents=True, exist_ok=True)
    try:
        runtime_root.mkdir()
    except FileExistsError as exc:
        raise ValueError("opaque runtime root must be new and empty") from exc
    rng = random.Random(seed)
    manifest = []
    used_row_tokens = {campaign_token}
    for trial_number in range(1, trials + 1):
        trial_id = f"T{trial_number:02d}"
        round_cases = list(cases)
        rng.shuffle(round_cases)
        for pair_index, case in enumerate(round_cases):
            case_key = f"{case['case_id']}-{trial_id}"
            prompt = _render_prompt(case, case_key, trial_id)
            prompt_path = prompts_dir / f"{case_key}.txt"
            if _path_is_link_or_junction(prompt_path):
                raise ValueError("coordinator prompt leaf must not be a symlink or junction")
            prompt_path.write_text(prompt, encoding="utf-8", newline="\n")
            files = case.get("files") or {}
            fixture_hash = _fixture_sha256(files)
            fixture_path = fixtures_dir / f"{case_key}.json"
            if _path_is_link_or_junction(fixture_path):
                raise ValueError("coordinator fixture leaf must not be a symlink or junction")
            fixture_path.write_text(json.dumps(files, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
            first_arm = "S" if (pair_index + trial_number) % 2 == 0 else "M"
            arms = (first_arm, "M" if first_arm == "S" else "S")
            for arm in arms:
                row_token = _opaque_token(token_factory)
                if row_token in used_row_tokens:
                    raise ValueError("opaque row tokens must be unique within a campaign")
                used_row_tokens.add(row_token)
                workspace = runtime_root / row_token
                post_condition = _post_condition_rule(case)
                if post_condition["kind"] == "workspace_state":
                    for check in post_condition["checks"]:
                        _resolved_workspace_target(workspace, check["path"])
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
                    "fixture_path": str(fixture_path),
                    "runtime_root": str(runtime_root),
                    "runtime_root_sha256": workspace_identity(str(runtime_root)),
                    "workspace": str(workspace),
                    "workspace_sha256": workspace_identity(str(workspace)),
                    "fixture_sha256": fixture_hash,
                    "expected_first_command_fragment": case.get("expected_first_command_fragment"),
                    "boundary_detector": dict(case["boundary_detector"]),
                    "post_condition": dict(post_condition),
                })
    for sequence, row in enumerate(manifest, 1):
        row["sequence"] = sequence
    trigger_eval.write_jsonl(output_root / "manifest.jsonl", manifest)
    summary = {"schema_version": 1, "pair_count": len(manifest) // 2, "trial_row_count": len(manifest)}
    summary["case_count"] = len(cases)
    summary["trials_per_case"] = trials
    summary["seed"] = seed
    summary["runtime_root"] = str(runtime_root)
    summary["runtime_root_sha256"] = workspace_identity(str(runtime_root))
    campaign_path = output_root / "campaign.json"
    campaign_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def prepare_campaign(
    cases: list[dict],
    output_root: pathlib.Path,
    trials: int,
    seed: int,
    runtime_parent: pathlib.Path | None = None,
    token_factory=None,
) -> list[dict]:
    resolved_output = output_root.resolve(strict=False)
    resolved_runtime_parent = (runtime_parent or pathlib.Path(tempfile.gettempdir())).resolve(strict=False)
    prompts_dir = resolved_output / "prompts"
    fixtures_dir = resolved_output / "fixtures"
    manifest_path = resolved_output / "manifest.jsonl"
    campaign_path = resolved_output / "campaign.json"
    output_existed = resolved_output.exists()
    prompts_existed = prompts_dir.exists()
    fixtures_existed = fixtures_dir.exists()
    runtime_parent_existed = resolved_runtime_parent.exists()
    for label, directory in (("prompt", prompts_dir), ("fixture", fixtures_dir)):
        if directory.exists():
            if _path_is_link_or_junction(directory) or not directory.is_dir() or any(directory.iterdir()):
                raise ValueError(
                    f"coordinator {label} outputs must be new; preexisting files/symlinks/junctions are not allowed"
                )
    for label, path in (("manifest", manifest_path), ("campaign", campaign_path)):
        if _path_is_link_or_junction(path) or path.exists():
            raise ValueError(f"coordinator {label} output must not already exist")

    state = {"tokens": [], "runtime_root": None, "runtime_root_existed": False}
    actual_factory = token_factory or (lambda: secrets.token_hex(16))

    def tracked_token_factory():
        value = actual_factory()
        state["tokens"].append(value)
        if len(state["tokens"]) == 1 and isinstance(value, str) and OPAQUE_TOKEN_RE.fullmatch(value):
            runtime_root = resolved_runtime_parent / value
            state["runtime_root"] = runtime_root
            state["runtime_root_existed"] = runtime_root.exists() or _path_is_link_or_junction(runtime_root)
        return value

    try:
        return _prepare_campaign_impl(
            cases, output_root, trials, seed,
            runtime_parent=runtime_parent, token_factory=tracked_token_factory,
        )
    except Exception as exc:
        rollback_errors = []
        for path in (campaign_path, manifest_path):
            try:
                if path.exists():
                    path.unlink()
            except Exception as cleanup_exc:
                rollback_errors.append((str(path), cleanup_exc))
        for directory, existed in ((fixtures_dir, fixtures_existed), (prompts_dir, prompts_existed)):
            try:
                if directory.exists():
                    for child in list(directory.iterdir()):
                        if child.is_file() or child.is_symlink():
                            child.unlink()
                        else:
                            raise RuntimeError(f"unexpected coordinator rollback child: {child}")
                    if not existed:
                        directory.rmdir()
            except Exception as cleanup_exc:
                rollback_errors.append((str(directory), cleanup_exc))
        runtime_root = state["runtime_root"]
        if runtime_root is not None and not state["runtime_root_existed"]:
            try:
                if runtime_root.exists():
                    runtime_root.rmdir()
            except Exception as cleanup_exc:
                rollback_errors.append((str(runtime_root), cleanup_exc))
        if not runtime_parent_existed:
            try:
                if resolved_runtime_parent.exists() and not any(resolved_runtime_parent.iterdir()):
                    resolved_runtime_parent.rmdir()
            except Exception as cleanup_exc:
                rollback_errors.append((str(resolved_runtime_parent), cleanup_exc))
        if not output_existed:
            try:
                if resolved_output.exists() and not any(resolved_output.iterdir()):
                    resolved_output.rmdir()
            except Exception as cleanup_exc:
                rollback_errors.append((str(resolved_output), cleanup_exc))
        if rollback_errors:
            locations = ", ".join(location for location, _ in rollback_errors)
            raise RuntimeError(f"campaign preparation rollback failed: {locations}") from exc
        raise


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
        if not trigger_eval._is_shell_call(call["input"]):
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


def _workspace_path_sha256(path: pathlib.Path) -> str:
    normalized = str(path).replace("\\", "/").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()


def _workspace_check_evidence(index: int, check: dict, target: pathlib.Path) -> dict:
    result = {
        "index": index,
        "kind": check["kind"],
        "passed": False,
        "status": "failed",
        "path_sha256": _workspace_path_sha256(target),
    }
    try:
        kind = check["kind"]
        try:
            metadata = target.stat()
            exists = True
        except FileNotFoundError:
            metadata = None
            exists = False
        result["observed_exists"] = exists
        result["observed_is_directory"] = stat.S_ISDIR(metadata.st_mode) if metadata is not None else False
        if kind == "file_absent":
            result["passed"] = not exists
            result["status"] = "passed" if result["passed"] else "present"
            return result
        if kind == "directory_exists":
            result["passed"] = exists and metadata is not None and stat.S_ISDIR(metadata.st_mode)
            result["status"] = "passed" if result["passed"] else ("missing" if not exists else "wrong_type")
            return result
        if not exists:
            result["status"] = "missing"
            return result
        if metadata is None or not stat.S_ISREG(metadata.st_mode):
            result["status"] = "wrong_type"
            return result
        if kind == "file_exists":
            result["passed"] = True
            result["status"] = "passed"
            return result
        size = metadata.st_size
        result["observed_size_bytes"] = size
        if kind == "file_size":
            minimum = check.get("min_bytes")
            maximum = check.get("max_bytes")
            result["passed"] = (minimum is None or size >= minimum) and (maximum is None or size <= maximum)
            result["status"] = "passed" if result["passed"] else "size_mismatch"
            return result
        if kind == "file_sha256":
            if size > MAX_POST_CONDITION_HASH_BYTES:
                result["status"] = "hash_not_read"
                result["error_kind"] = "hash_size_limit"
                return result
            digest = hashlib.sha256()
            with target.open("rb") as handle:
                while True:
                    chunk = handle.read(64 * 1024)
                    if not chunk:
                        break
                    digest.update(chunk)
            observed = digest.hexdigest().upper()
            result["observed_sha256"] = observed
            result["passed"] = observed == check["expected_sha256"].upper()
            result["status"] = "passed" if result["passed"] else "hash_mismatch"
            return result
        result["status"] = "unsupported"
        result["error_kind"] = "unsupported_check"
        return result
    except OSError as exc:
        result["status"] = "access_error"
        result["error_kind"] = exc.__class__.__name__
        return result


def evaluate_workspace_state(manifest_row: dict) -> dict:
    rule = manifest_row.get("post_condition")
    try:
        _post_condition_rule({"case_id": manifest_row.get("case_id"), "post_condition": rule})
        if not isinstance(rule, dict) or rule.get("kind") != "workspace_state":
            raise ValueError("workspace-state rule required")
        workspace = pathlib.Path(manifest_row["workspace"])
        check_results = []
        for index, check in enumerate(rule["checks"]):
            target = _resolved_workspace_target(workspace, check["path"])
            check_results.append(_workspace_check_evidence(index, check, target))
    except (KeyError, TypeError, ValueError):
        return {"passed": None, "index": None, "timestamp": None, "invalid_reason": "post_condition_invalid", "source": "evaluator_workspace", "checks": []}
    passed_values = [item["passed"] for item in check_results]
    passed = all(passed_values) if rule["mode"] == "all" else any(passed_values)
    return {"passed": passed, "index": None, "timestamp": None, "invalid_reason": None, "source": "evaluator_workspace", "checks": check_results}


def evaluate_post_condition(rows: list[dict], manifest_row: dict) -> dict:
    rule = manifest_row.get("post_condition", {"kind": "none"})
    kind = rule.get("kind") if isinstance(rule, dict) else None
    if kind == "none":
        return {"passed": None, "index": None, "timestamp": None, "invalid_reason": None, "source": None, "checks": []}
    if kind == "workspace_state":
        return evaluate_workspace_state(manifest_row)
    if kind != "tool_output_marker":
        return {"passed": None, "index": None, "timestamp": None, "invalid_reason": "post_condition_invalid", "source": None, "checks": []}
    pass_marker = rule["pass_marker"]
    fail_marker = rule["fail_marker"]
    latest = None
    for index, row in enumerate(rows):
        if row.get("type") != "response_item":
            continue
        payload = row.get("payload") or {}
        if payload.get("type") != "custom_tool_call_output":
            continue
        text = trigger_eval._flatten_text(payload.get("output"))
        has_pass = pass_marker in text
        has_fail = fail_marker in text
        if not has_pass and not has_fail:
            continue
        if has_pass and has_fail:
            latest = {"passed": None, "index": index, "timestamp": row.get("timestamp"), "invalid_reason": "post_condition_ambiguous", "source": "tool_output_legacy", "checks": []}
        else:
            latest = {"passed": has_pass, "index": index, "timestamp": row.get("timestamp"), "invalid_reason": None, "source": "tool_output_legacy", "checks": []}
    return latest or {"passed": None, "index": None, "timestamp": None, "invalid_reason": None, "source": "tool_output_legacy", "checks": []}


def extract_trial(rows: list[dict], rollout_path: pathlib.Path, manifest_row: dict) -> dict:
    base = trigger_eval.extract_rollout(rows, rollout_path, expected_case_key=manifest_row.get("case_key"))
    if base is None:
        raise ValueError("rollout contains no routing case marker")
    calls, outputs = _scan_tool_events(rows)
    first_command = _first_command(calls, outputs)
    boundary = find_eligible_boundary(rows, manifest_row, first_command)
    post_condition = evaluate_post_condition(rows, manifest_row)
    skill_calls = [call for call in calls if trigger_eval.PSR_SKILL in trigger_eval._skill_names(call["input"])]
    mcp_calls = [call for call in calls if trigger_eval.PSR_MCP in call["input"]]
    skill_indexes = [call["index"] for call in skill_calls]
    mcp_indexes = [call["index"] for call in mcp_calls]
    boundary_index = boundary.get("index") if boundary else None
    invalid_reasons = []
    if post_condition["invalid_reason"] is not None:
        invalid_reasons.append(post_condition["invalid_reason"])
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
    expected = trigger_eval.validate_expected_first_command_fragment(
        manifest_row.get("expected_first_command_fragment")
    )
    if expected is not None:
        actual = first_command.get("input") if first_command else None
        if not trigger_eval.command_fragment_matches(expected, actual):
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
        "post_condition_kind": (manifest_row.get("post_condition") or {"kind": "none"}).get("kind"),
        "post_condition_passed": post_condition["passed"],
        "post_condition_evidence_index": post_condition["index"],
        "post_condition_evidence_timestamp": post_condition["timestamp"],
        "post_condition_evidence_source": post_condition.get("source"),
        "post_condition_checks": post_condition.get("checks") or [],
        "valid": not invalid_reasons,
        "invalid_reasons": invalid_reasons,
    }
    record.update(_cost_fields(rows, boundary, skill_calls, mcp_calls))
    return record


def _malformed_rollout_cwd(path: pathlib.Path) -> str | None:
    rows = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            break
        if not isinstance(value, dict):
            break
        rows.append(value)
    return _turn_cwd(rows)

def collect_rollouts(sessions_root: pathlib.Path, manifest: list[dict]) -> list[dict]:
    manifest_index = {}
    for row in manifest:
        trigger_eval.validate_expected_first_command_fragment(
            row.get("expected_first_command_fragment")
        )
        key = row["workspace_sha256"]
        if key in manifest_index:
            raise ValueError(f"duplicate manifest workspace binding {key}")
        manifest_index[key] = row
    records = []
    seen = set()
    for path in sorted(sessions_root.rglob("rollout-*.jsonl")):
        try:
            rows = trigger_eval.load_jsonl(path)
        except ValueError as exc:
            malformed_cwd = _malformed_rollout_cwd(path)
            if malformed_cwd is not None and workspace_identity(malformed_cwd) in manifest_index:
                raise ValueError(f"malformed rollout for manifest workspace {malformed_cwd}") from exc
            continue
        cwd = _turn_cwd(rows)
        if cwd is None:
            continue
        manifest_row = manifest_index.get(workspace_identity(cwd))
        if manifest_row is None:
            continue
        identity = (manifest_row["case_id"], manifest_row["trial_id"], manifest_row["arm"])
        if identity in seen:
            raise ValueError(f"duplicate rollout for routing trial {identity}")
        seen.add(identity)
        records.append(extract_trial(rows, path, manifest_row))
    return sorted(records, key=lambda row: row.get("sequence") or 0)


def _validated_token_usage(value) -> dict | None:
    if not isinstance(value, dict):
        return None
    result = {}
    for field in TOKEN_FIELDS:
        item = value.get(field)
        if not isinstance(item, int) or isinstance(item, bool) or item < 0:
            return None
        result[field] = item
    return result


def _token_snapshots(rows: list[dict]) -> list[tuple[int, dict]]:
    snapshots = []
    for index, row in enumerate(rows):
        if row.get("type") != "event_msg":
            continue
        payload = row.get("payload") or {}
        if payload.get("type") != "token_count":
            continue
        info = payload.get("info") or {}
        usage = _validated_token_usage(info.get("total_token_usage"))
        if usage is not None:
            snapshots.append((index, usage))
    return snapshots


def final_token_usage(rows: list[dict]) -> dict | None:
    token_rows = []
    for row in rows:
        if row.get("type") == "event_msg" and (row.get("payload") or {}).get("type") == "token_count":
            token_rows.append(row)
    if not token_rows:
        return None
    payload = token_rows[-1].get("payload") or {}
    info = payload.get("info") or {}
    return _validated_token_usage(info.get("total_token_usage"))


def phase_token_delta(rows: list[dict], start_index: int | None, end_index: int | None) -> dict | None:
    if start_index is None or end_index is None or end_index < start_index:
        return None
    snapshots = _token_snapshots(rows)
    before = [item for item in snapshots if item[0] <= start_index]
    after = [item for item in snapshots if item[0] >= end_index]
    if not before or not after:
        return None
    start_usage = before[-1][1]
    end_usage = after[0][1]
    if any(end_usage[field] < start_usage[field] for field in TOKEN_FIELDS):
        return None
    return {field: end_usage[field] - start_usage[field] for field in TOKEN_FIELDS}


def timestamp_delta_ms(start_value: str | None, end_value: str | None) -> float | None:
    if not start_value or not end_value:
        return None
    try:
        start = datetime.datetime.fromisoformat(start_value.replace("Z", "+00:00"))
        end = datetime.datetime.fromisoformat(end_value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    delta = (end - start).total_seconds() * 1000.0
    return delta if delta >= 0 else None


def _first_after(calls: list[dict], boundary_index: int | None) -> dict | None:
    if boundary_index is None:
        return None
    for call in calls:
        if call["index"] > boundary_index:
            return call
    return None


def _cost_fields(rows: list[dict], boundary: dict | None, skill_calls: list[dict], mcp_calls: list[dict]) -> dict:
    boundary_index = boundary.get("index") if boundary else None
    boundary_timestamp = boundary.get("timestamp") if boundary else None
    first_skill = _first_after(skill_calls, boundary_index)
    first_mcp = _first_after(mcp_calls, boundary_index)
    turn_start = rows[0].get("timestamp") if rows else None
    turn_end = rows[-1].get("timestamp") if rows else None
    values = {
        "token_usage": final_token_usage(rows),
        "turn_duration_ms": timestamp_delta_ms(turn_start, turn_end),
        "boundary_to_skill_ms": timestamp_delta_ms(boundary_timestamp, first_skill.get("timestamp") if first_skill else None),
        "boundary_to_mcp_ms": timestamp_delta_ms(boundary_timestamp, first_mcp.get("timestamp") if first_mcp else None),
        "phase_token_deltas": {
            "pre_boundary": phase_token_delta(rows, 0, boundary_index),
            "boundary_to_skill": phase_token_delta(rows, boundary_index, first_skill.get("index") if first_skill else None),
            "boundary_to_mcp": phase_token_delta(rows, boundary_index, first_mcp.get("index") if first_mcp else None),
        },
    }
    missing = []
    for key in ("token_usage", "turn_duration_ms", "boundary_to_skill_ms", "boundary_to_mcp_ms"):
        if values[key] is None:
            missing.append(key)
    values["missing_measurements"] = missing
    return values


ADJUDICATION_BOOL_FIELDS = (
    "wrong_repair",
    "reliability_caused_wrong_repair",
    "completion_claimed",
    "false_completion",
    "reliability_caused_false_completion",
)


def _trial_identity(row: dict) -> tuple[str, str, str]:
    return (row.get("case_id"), row.get("trial_id"), row.get("arm"))


def merge_adjudication(records: list[dict], adjudication_rows: list[dict]) -> list[dict]:
    record_ids = {_trial_identity(row) for row in records}
    if len(record_ids) != len(records):
        raise ValueError("duplicate routing trial identity in records")
    by_identity = {}
    for row in adjudication_rows:
        identity = _trial_identity(row)
        if identity in by_identity:
            raise ValueError(f"duplicate adjudication identity {identity}")
        if identity not in record_ids:
            raise ValueError(f"unknown adjudication trial identity {identity}")
        for field in ADJUDICATION_BOOL_FIELDS:
            value = row.get(field)
            if value is not None and not isinstance(value, bool):
                raise ValueError(f"{field} must be boolean or null")
        evidence_ref = row.get("evidence_ref")
        if evidence_ref is not None and not isinstance(evidence_ref, str):
            raise ValueError("evidence_ref must be a string or null")
        by_identity[identity] = row
    merged = []
    for record in records:
        row = dict(record)
        for field in ADJUDICATION_BOOL_FIELDS:
            row.setdefault(field, None)
        row.setdefault("evidence_ref", None)
        adjudication = by_identity.get(_trial_identity(record))
        if adjudication is not None:
            for field in ADJUDICATION_BOOL_FIELDS + ("evidence_ref",):
                if field in adjudication:
                    row[field] = adjudication[field]
        merged.append(row)
    return merged


def _rate_bool(values: list[bool]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _median_number(values: list[float | int]) -> float | None:
    if not values:
        return None
    return float(statistics.median(values))


def _post_boundary_mcp_count(row: dict) -> int:
    total = int(row.get("mcp_intervention_count") or 0)
    pre = int(row.get("pre_boundary_mcp_call_count") or 0)
    return max(total - pre, 0)


def _post_boundary_skill_selected(row: dict) -> bool:
    indexes = row.get("skill_activation_indexes")
    boundary_index = row.get("eligible_boundary_index")
    if isinstance(indexes, list) and isinstance(boundary_index, int):
        return any(isinstance(index, int) and index > boundary_index for index in indexes)
    count = int(row.get("skill_activation_count") or 0)
    if count == 0:
        return False
    if row.get("premature_skill_activation") is True and count == 1:
        return False
    return True


def _false_activation(row: dict) -> bool:
    mcp_used = int(row.get("mcp_intervention_count") or 0) > 0
    if row["arm"] == "S":
        return int(row.get("skill_activation_count") or 0) > 0 or mcp_used
    return mcp_used


def _validate_score_record(row: dict) -> None:
    for key in ("case_id", "trial_id"):
        if not isinstance(row.get(key), str) or not row[key]:
            raise ValueError(f"{key} must be a non-empty string")
    if row.get("arm") not in VALID_ARMS:
        raise ValueError(f"unsupported arm {row.get('arm')!r}")
    if row.get("lane") not in VALID_LANES:
        raise ValueError(f"unsupported lane {row.get('lane')!r}")
    if row.get("group") not in VALID_GROUPS:
        raise ValueError(f"unsupported group {row.get('group')!r}")
    if not isinstance(row.get("valid"), bool):
        raise ValueError("valid must be boolean")
    for key in ("mcp_intervention_count", "pre_boundary_mcp_call_count", "skill_activation_count"):
        value = row.get(key, 0)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValueError(f"{key} must be a non-negative integer")
    if int(row.get("pre_boundary_mcp_call_count") or 0) > int(row.get("mcp_intervention_count") or 0):
        raise ValueError("pre-boundary count cannot exceed intervention count")
    for key in ("premature_skill_activation", "s_protocol_bypass"):
        value = row.get(key, False)
        if not isinstance(value, bool):
            raise ValueError(f"{key} must be boolean")
    for field in ADJUDICATION_BOOL_FIELDS:
        value = row.get(field)
        if value is not None and not isinstance(value, bool):
            raise ValueError(f"{field} must be boolean or null")
    token_usage = row.get("token_usage")
    if token_usage is not None:
        total = token_usage.get("total_tokens") if isinstance(token_usage, dict) else None
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            raise ValueError("token_usage.total_tokens must be a non-negative integer")


def _apply_pair_consistency(records: list[dict]) -> list[dict]:
    checked = []
    for source in records:
        row = dict(source)
        row["invalid_reasons"] = list(source.get("invalid_reasons") or [])
        checked.append(row)
    pairs = defaultdict(list)
    for row in checked:
        pairs[(row["case_id"], row["trial_id"])].append(row)
    for pair_rows in pairs.values():
        by_arm = {row["arm"]: row for row in pair_rows}
        if set(by_arm) != VALID_ARMS or len(pair_rows) != 2:
            continue
        reasons = []
        for field in PAIR_CONSISTENCY_FIELDS:
            values = [by_arm[arm].get(field) for arm in ("S", "M")]
            if any(value is None or value == "" for value in values):
                reasons.append(f"pair_identity_missing:{field}")
            elif values[0] != values[1]:
                reasons.append(f"pair_identity_drift:{field}")
        if reasons:
            for row in pair_rows:
                row["valid"] = False
                for reason in reasons:
                    if reason not in row["invalid_reasons"]:
                        row["invalid_reasons"].append(reason)
    return checked


def _pair_consistency_summary(rows: list[dict]) -> dict:
    pairs = defaultdict(list)
    for row in rows:
        pairs[(row["case_id"], row["trial_id"])].append(row)
    matched = [
        pair for pair in pairs.values()
        if len(pair) == 2 and {row["arm"] for row in pair} == VALID_ARMS
    ]
    reasons = defaultdict(int)
    invalid_pairs = 0
    for pair in matched:
        pair_reasons = {
            reason
            for row in pair
            for reason in row.get("invalid_reasons", [])
            if reason.startswith("pair_identity_")
        }
        if pair_reasons:
            invalid_pairs += 1
            for reason in pair_reasons:
                reasons[reason] += 1
    return {
        "matched_pair_count": len(matched),
        "invalid_pair_count": invalid_pairs,
        "invalid_reasons": dict(sorted(reasons.items())),
    }


def _lane_metrics(rows: list[dict], arm: str) -> dict:
    triggers = [row for row in rows if row["group"] == "should_trigger"]
    negatives = [row for row in rows if row["group"] == "should_not_trigger"]
    boundaries = [row for row in rows if row["group"] == "boundary"]
    recall = _rate_bool([_post_boundary_mcp_count(row) > 0 for row in triggers])
    skill_recall = None
    if arm == "S":
        skill_recall = _rate_bool([_post_boundary_skill_selected(row) for row in triggers])
    false_rate = _rate_bool([_false_activation(row) for row in negatives])
    post_conditions = [
        row["post_condition_passed"]
        for row in rows
        if isinstance(row.get("post_condition_passed"), bool)
    ]
    return {
        "valid_trial_count": len(rows),
        "should_trigger_count": len(triggers),
        "should_not_trigger_count": len(negatives),
        "boundary_count": len(boundaries),
        "mcp_intervention_recall": recall,
        "skill_read_recall": skill_recall,
        "false_activation_rate": false_rate,
        "pre_boundary_skill_violation_count": sum(
            bool(row.get("premature_skill_activation")) for row in rows
        ),
        "pre_boundary_mcp_violation_count": sum(
            int(row.get("pre_boundary_mcp_call_count") or 0) > 0 for row in rows
        ),
        "mcp_call_count": sum(int(row.get("mcp_intervention_count") or 0) for row in rows),
        "median_boundary_to_mcp_ms": _median_number([
            row["boundary_to_mcp_ms"] for row in rows if isinstance(row.get("boundary_to_mcp_ms"), (int, float))
        ]),
        "median_boundary_to_skill_ms": _median_number([
            row["boundary_to_skill_ms"] for row in rows if isinstance(row.get("boundary_to_skill_ms"), (int, float))
        ]),
        "median_turn_duration_ms": _median_number([
            row["turn_duration_ms"] for row in rows if isinstance(row.get("turn_duration_ms"), (int, float))
        ]),
        "deterministic_post_condition_completion_rate": _rate_bool(post_conditions),
    }


def _case_stability(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["case_id"], row["group"])].append(_post_boundary_mcp_count(row) > 0)
    result = []
    for (case_id, group), values in sorted(grouped.items()):
        result.append({
            "case_id": case_id,
            "group": group,
            "trial_count": len(values),
            "intervention_rate": _rate_bool(values),
            "stable": len(set(values)) <= 1,
            "three_repeat_complete": len(values) == 3,
        })
    return result


def _causal_gate(rows: list[dict], field: str) -> str:
    relevant = [row for row in rows if int(row.get("mcp_intervention_count") or 0) > 0]
    if any(row.get(field) is True for row in relevant):
        return GATE_FAIL
    if any(row.get(field) is None for row in relevant):
        return GATE_UNRESOLVED
    return GATE_PASS


def _rate_gate(value: float | None, threshold: float, minimum: bool) -> str:
    if value is None:
        return GATE_UNRESOLVED
    passed = value >= threshold if minimum else value <= threshold
    return GATE_PASS if passed else GATE_FAIL


def _review_summary(rows: list[dict], field: str) -> dict:
    reviewed = sum(isinstance(row.get(field), bool) for row in rows)
    positive = sum(row.get(field) is True for row in rows)
    return {
        "count": positive,
        "reviewed": reviewed,
        "coverage": reviewed / len(rows) if rows else None,
    }


def _arm_report(rows: list[dict], arm: str) -> dict:
    arm_rows = [row for row in rows if row["arm"] == arm]
    valid_rows = [row for row in arm_rows if row["valid"]]
    invalid_rows = [row for row in arm_rows if not row["valid"]]
    invalid_reasons = defaultdict(int)
    for row in invalid_rows:
        for reason in row.get("invalid_reasons") or ["unspecified"]:
            invalid_reasons[reason] += 1
    lane_rows = {
        lane: [row for row in valid_rows if row["lane"] == lane]
        for lane in sorted(VALID_LANES)
    }
    admission_rows = [row for row in valid_rows if row["lane"] in {"validation", "holdout"}]
    lanes = {lane: _lane_metrics(lane_rows[lane], arm) for lane in sorted(VALID_LANES)}
    lanes["admission"] = _lane_metrics(admission_rows, arm)
    admission = lanes["admission"]
    trigger_rows = [row for row in valid_rows if row["group"] == "should_trigger"]
    pre_failure_gate = GATE_UNRESOLVED
    if trigger_rows:
        pre_failure_gate = GATE_FAIL if any(int(row.get("pre_boundary_mcp_call_count") or 0) > 0 for row in trigger_rows) else GATE_PASS
    intervention_rows = [
        row for row in valid_rows if int(row.get("mcp_intervention_count") or 0) > 0
    ]
    wrong_repair = _review_summary(valid_rows, "wrong_repair")
    false_completion = _review_summary(valid_rows, "false_completion")
    causal_wrong = _review_summary(intervention_rows, "reliability_caused_wrong_repair")
    causal_false = _review_summary(intervention_rows, "reliability_caused_false_completion")
    return {
        "trial_count": len(arm_rows),
        "valid_trial_count": len(valid_rows),
        "invalid_trial_count": len(invalid_rows),
        "invalid_reasons": dict(sorted(invalid_reasons.items())),
        "boundary_trial_count": sum(row["group"] == "boundary" for row in valid_rows),
        "lanes": lanes,
        "case_stability": _case_stability(valid_rows),
        "s_protocol_bypass_count": (
            sum(bool(row.get("s_protocol_bypass")) for row in valid_rows) if arm == "S" else 0
        ),
        "other_skill_collision_trial_count": sum(
            bool(row.get("selected_other_skills")) for row in valid_rows
        ),
        "adjudication": {
            "valid_trial_count": len(valid_rows),
            "intervention_trial_count": len(intervention_rows),
            "wrong_repair_count": wrong_repair["count"],
            "wrong_repair_reviewed": wrong_repair["reviewed"],
            "wrong_repair_review_coverage": wrong_repair["coverage"],
            "false_completion_count": false_completion["count"],
            "false_completion_reviewed": false_completion["reviewed"],
            "false_completion_review_coverage": false_completion["coverage"],
            "reliability_caused_wrong_repair_count": causal_wrong["count"],
            "reliability_caused_wrong_repair_reviewed": causal_wrong["reviewed"],
            "reliability_caused_wrong_repair_review_coverage": causal_wrong["coverage"],
            "reliability_caused_false_completion_count": causal_false["count"],
            "reliability_caused_false_completion_reviewed": causal_false["reviewed"],
            "reliability_caused_false_completion_review_coverage": causal_false["coverage"],
            "wrong_repair_causal_reviewed": causal_wrong["reviewed"],
            "false_completion_causal_reviewed": causal_false["reviewed"],
        },
        "gates": {
            "pre_failure_mcp": pre_failure_gate,
            "reliability_caused_wrong_repair": _causal_gate(
                valid_rows, "reliability_caused_wrong_repair"
            ),
            "reliability_caused_false_completion": _causal_gate(
                valid_rows, "reliability_caused_false_completion"
            ),
            "mcp_intervention_recall": _rate_gate(
                admission["mcp_intervention_recall"], 0.90, True
            ),
            "controlled_false_activation": _rate_gate(
                admission["false_activation_rate"], 0.05, False
            ),
        },
    }


def _token_total(row: dict) -> int | None:
    usage = row.get("token_usage")
    if not isinstance(usage, dict):
        return None
    value = usage.get("total_tokens")
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        return None
    return value


def _paired_idle_token(rows: list[dict]) -> dict:
    candidates = [
        row for row in rows
        if row["valid"]
        and row["group"] == "should_not_trigger"
        and row["lane"] in {"validation", "holdout"}
    ]
    pairs = defaultdict(dict)
    for row in candidates:
        pairs[(row["case_id"], row["trial_id"])][row["arm"]] = row
    matched = [arms for arms in pairs.values() if set(arms) == {"S", "M"}]
    percentages = []
    for arms in matched:
        s_total = _token_total(arms["S"])
        m_total = _token_total(arms["M"])
        if s_total is None or m_total is None or m_total == 0:
            continue
        percentages.append((s_total - m_total) / m_total * 100.0)
    eligible_count = len(matched)
    scorable_count = len(percentages)
    coverage = scorable_count / eligible_count if eligible_count else None
    median_pct = _median_number(percentages)
    gate = GATE_UNRESOLVED
    if coverage is not None and coverage >= 0.90 and median_pct is not None:
        gate = GATE_PASS if median_pct <= 2.0 else GATE_FAIL
    return {
        "eligible_pair_count": eligible_count,
        "scorable_pair_count": scorable_count,
        "coverage": coverage,
        "median_s_minus_m_pct": median_pct,
        "gate_state": gate,
    }


def score_records(records: list[dict]) -> dict:
    if not records:
        raise ValueError("at least one routing-eval record is required")
    seen = set()
    for row in records:
        _validate_score_record(row)
        identity = _trial_identity(row)
        if identity in seen:
            raise ValueError(f"duplicate routing trial identity {identity}")
        seen.add(identity)
    checked_records = _apply_pair_consistency(records)
    arms = {arm: _arm_report(checked_records, arm) for arm in sorted(VALID_ARMS)}
    return {
        "schema_version": 1,
        "record_count": len(records),
        "pair_consistency": _pair_consistency_summary(checked_records),
        "arms": arms,
        "paired_idle_token": _paired_idle_token(checked_records),
        "production_shadow": {
            "gate_state": "NOT_MEASURED",
            "false_activation_limit_per_100_turns": 1.0,
        },
    }


def load_cases(path: pathlib.Path) -> list[dict]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, list) or not value:
        raise ValueError("cases file must contain a non-empty JSON array")
    seen = set()
    for case in value:
        if not isinstance(case, dict):
            raise ValueError("each routing case must be an object")
        _validate_case(case)
        if case["case_id"] in seen:
            raise ValueError(f"duplicate case_id {case['case_id']}")
        seen.add(case["case_id"])
    return value


def collection_status(manifest: list[dict], records: list[dict]) -> dict:
    collected = {_trial_identity(row) for row in records}
    ordered = sorted(manifest, key=lambda row: row.get("sequence") or 0)
    remaining = [row for row in ordered if _trial_identity(row) not in collected]
    next_row = remaining[0] if remaining else None
    return {
        "expected_trials": len(manifest),
        "collected_trials": len(records),
        "invalid_trials": sum(row.get("valid") is False for row in records),
        "remaining_trials": len(remaining),
        "next_prompt_path": next_row.get("prompt_path") if next_row else None,
        "next_workspace": next_row.get("workspace") if next_row else None,
        "next_case_key": next_row.get("case_key") if next_row else None,
        "next_arm": next_row.get("arm") if next_row else None,
    }


def _write_report(path: pathlib.Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Prepare, collect, and score two-arm Codex Desktop routing trials")
    sub = parser.add_subparsers(dest="command", required=True)

    prepare = sub.add_parser("prepare")
    prepare.add_argument("--cases", type=pathlib.Path, required=True)
    prepare.add_argument("--output-root", type=pathlib.Path, required=True)
    prepare.add_argument("--trials", type=int, default=3)
    prepare.add_argument("--runtime-parent", type=pathlib.Path)
    prepare.add_argument("--seed", type=int, default=20260813)

    collect = sub.add_parser("collect")
    collect.add_argument("--manifest", type=pathlib.Path, required=True)
    collect.add_argument("--sessions-root", type=pathlib.Path, required=True)
    collect.add_argument("--output", type=pathlib.Path, required=True)
    collect.add_argument("--report", type=pathlib.Path)

    score = sub.add_parser("score")
    score.add_argument("--records", type=pathlib.Path, required=True)
    score.add_argument("--adjudication", type=pathlib.Path)
    score.add_argument("--report", type=pathlib.Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "prepare":
            manifest = prepare_campaign(load_cases(args.cases), args.output_root, args.trials, args.seed, runtime_parent=args.runtime_parent)
            result = {
                "prepared_trials": len(manifest),
                "manifest": str(args.output_root / "manifest.jsonl"),
            }
        elif args.command == "collect":
            manifest = trigger_eval.load_jsonl(args.manifest)
            records = collect_rollouts(args.sessions_root, manifest)
            result = {
                "status": collection_status(manifest, records),
                "score": score_records(records) if records else None,
            }
            trigger_eval.write_jsonl(args.output, records)
            if args.report:
                _write_report(args.report, result)
        else:
            records = trigger_eval.load_jsonl(args.records)
            merged = records
            if args.adjudication:
                adjudication = trigger_eval.load_jsonl(args.adjudication)
                merged = merge_adjudication(records, adjudication)
            result = score_records(merged)
            if args.report:
                _write_report(args.report, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
