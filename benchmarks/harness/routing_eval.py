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
