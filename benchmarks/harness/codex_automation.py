import argparse
import hashlib
import json
import ntpath
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import tomllib

import routing_eval

TOP_LEVEL_ALLOWLIST = (
    "approval_policy",
    "disable_response_storage",
    "model_reasoning_effort",
    "model_reasoning_summary",
    "model_verbosity",
    "sandbox_mode",
    "service_tier",
    "model_provider",
    "model",
)


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest().upper()


def load_live_config(path: pathlib.Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def ensure_external_evidence_root(evidence_root: pathlib.Path) -> pathlib.Path:
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    resolved = evidence_root.resolve(strict=False)
    try:
        resolved.relative_to(repo_root)
    except ValueError:
        return resolved
    raise ValueError("raw automation evidence must stay outside the repository")


def _git_rev_parse(ref: str, runner=subprocess.run) -> str:
    repo_root = pathlib.Path(__file__).resolve().parents[2]
    completed = runner(["git", "-C", str(repo_root), "rev-parse", ref], capture_output=True, text=True, check=False)
    value = (completed.stdout or "").strip()
    if completed.returncode != 0 or not re.fullmatch(r"[0-9a-fA-F]{40}", value):
        raise RuntimeError(f"could not resolve repository identity: {ref}")
    return value.lower()


def campaign_identity_payload(cli_identity: dict, skill_path: pathlib.Path, skill_sha256: str, mcp_path: pathlib.Path, mcp_sha256: str, profile_meta: dict, model: str | None = None, public_main_sha: str | None = None) -> dict:
    if not isinstance(public_main_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", public_main_sha):
        raise ValueError("public main SHA must be an exact 40-character Git commit id")
    return {
        "schema_version": 1,
        "cli_path": str(pathlib.Path(cli_identity["path"]).resolve(strict=False)),
        "cli_version": cli_identity["version"],
        "cli_sha256": cli_identity["sha256"].upper(),
        "skill_path": str(skill_path.resolve(strict=False)),
        "skill_sha256": skill_sha256.upper(),
        "mcp_path": str(mcp_path.resolve(strict=False)),
        "mcp_sha256": mcp_sha256.upper(),
        "live_config_sha256": profile_meta["live_config_sha256"].upper(),
        "model": model if model is not None else profile_meta.get("model"),
        "provider": profile_meta.get("provider"),
        "provider_base_url": profile_meta.get("provider_base_url"),
        "provider_wire_api": profile_meta.get("provider_wire_api"),
        "reasoning_effort": profile_meta.get("effort"),
        "approval_policy": profile_meta.get("approval_policy"),
        "sandbox_mode": profile_meta.get("sandbox_mode"),
        "harness_git_head": _git_rev_parse("HEAD"),
        "public_main_sha": public_main_sha.lower(),
    }


def verify_or_create_campaign_identity_lock(lock_path: pathlib.Path, payload: dict, allow_create: bool) -> str:
    ensure_external_evidence_root(lock_path.parent)
    lock_path = lock_path.resolve(strict=False)

    def read_existing() -> dict:
        try:
            return json.loads(lock_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError("campaign identity lock is unreadable") from exc

    if lock_path.exists():
        existing = read_existing()
        if existing != payload:
            raise ValueError("campaign identity lock does not match current runtime identity")
    else:
        if not allow_create:
            raise ValueError("campaign identity lock is required before row execution")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        try:
            with lock_path.open("x", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        except FileExistsError:
            existing = read_existing()
            if existing != payload:
                raise ValueError("campaign identity lock does not match current runtime identity")
    return sha256_file(lock_path)


def ensure_evidence_outside_workspace(evidence_root: pathlib.Path, workspace: pathlib.Path) -> pathlib.Path:
    resolved_evidence = evidence_root.resolve(strict=False)
    resolved_workspace = workspace.resolve(strict=False)
    if resolved_evidence == resolved_workspace:
        raise ValueError("evidence root must not equal or descend from the row workspace")
    try:
        resolved_evidence.relative_to(resolved_workspace)
    except ValueError:
        return resolved_evidence
    raise ValueError("evidence root must not equal or descend from the row workspace")


def ensure_evidence_runtime_disjoint(evidence_root: pathlib.Path, runtime_root: pathlib.Path) -> pathlib.Path:
    resolved_evidence = evidence_root.resolve(strict=False)
    resolved_runtime = runtime_root.resolve(strict=False)
    if _is_relative_to(resolved_evidence, resolved_runtime) or _is_relative_to(resolved_runtime, resolved_evidence):
        raise ValueError("evidence root and runtime root must be disjoint")
    return resolved_evidence


def workspace_fixture_sha256(workspace: pathlib.Path) -> str:
    is_junction = getattr(workspace, "is_junction", lambda: False)
    if workspace.is_symlink() or is_junction():
        raise ValueError("workspace root must not be a symlink or junction")
    if not workspace.is_dir():
        raise ValueError("workspace must exist before row execution")
    files = {}
    for path in sorted(workspace.rglob("*"), key=lambda item: item.as_posix().casefold()):
        if path.is_symlink():
            raise ValueError(f"workspace fixture must not contain symlinks: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(workspace).as_posix()
        try:
            files[relative] = path.read_text(encoding="utf-8", newline="")
        except UnicodeDecodeError as exc:
            raise ValueError(f"workspace fixture must contain UTF-8 text files only: {relative}") from exc
    return routing_eval._fixture_sha256(files)


def _path_is_link_or_junction(path: pathlib.Path) -> bool:
    is_junction = getattr(path, "is_junction", lambda: False)
    return path.is_symlink() or bool(is_junction())


def _filesystem_object_identity(path: pathlib.Path) -> tuple[int, int]:
    try:
        info = os.stat(path, follow_symlinks=False)
    except OSError as exc:
        raise RuntimeError("runtime boundary entry is missing or unreadable") from exc
    return int(info.st_dev), int(info.st_ino)


def validate_runtime_workspace_boundary(row: dict, workspace: pathlib.Path, expected=None, require_workspace: bool = True):
    raw_runtime_root = pathlib.Path(row["runtime_root"])
    raw_workspace = pathlib.Path(row["workspace"])
    if _path_is_link_or_junction(raw_runtime_root) or _path_is_link_or_junction(raw_workspace):
        raise RuntimeError("runtime root/workspace boundary changed to a symlink or junction")
    runtime_root = raw_runtime_root.resolve(strict=False)
    expected_workspace = raw_workspace.resolve(strict=False)
    observed_workspace = pathlib.Path(workspace).resolve(strict=False)
    if observed_workspace != expected_workspace or expected_workspace.parent != runtime_root:
        raise RuntimeError("runtime root/workspace boundary containment changed")
    if routing_eval.workspace_identity(str(runtime_root)) != row.get("runtime_root_sha256"):
        raise RuntimeError("runtime root identity changed")
    if routing_eval.workspace_identity(str(expected_workspace)) != row.get("workspace_sha256"):
        raise RuntimeError("workspace identity changed")
    if not runtime_root.is_dir():
        raise RuntimeError("runtime root must remain a directory")
    if require_workspace and not observed_workspace.is_dir():
        raise RuntimeError("workspace must remain a directory")
    current_root_identity = _filesystem_object_identity(raw_runtime_root)
    current_workspace_identity = None
    if require_workspace:
        current_workspace_identity = _filesystem_object_identity(raw_workspace)
    if expected is not None:
        if current_root_identity != expected["runtime_root"]:
            raise RuntimeError("runtime root filesystem identity changed")
        if require_workspace and current_workspace_identity != expected["workspace"]:
            raise RuntimeError("workspace filesystem identity changed")
    return runtime_root, observed_workspace


def capture_runtime_workspace_boundary(row: dict, workspace: pathlib.Path) -> dict:
    runtime_root, observed_workspace = validate_runtime_workspace_boundary(row, workspace)
    return {
        "runtime_root": _filesystem_object_identity(runtime_root),
        "workspace": _filesystem_object_identity(observed_workspace),
    }


def materialize_row_workspace(row: dict) -> pathlib.Path:
    raw_workspace = pathlib.Path(row["workspace"])
    raw_runtime_root = pathlib.Path(row["runtime_root"])
    if _path_is_link_or_junction(raw_runtime_root) or _path_is_link_or_junction(raw_workspace):
        raise ValueError("runtime root/workspace must not be a symlink or junction")
    workspace = raw_workspace.resolve(strict=False)
    runtime_root = raw_runtime_root.resolve(strict=False)
    if not routing_eval.OPAQUE_TOKEN_RE.fullmatch(runtime_root.name):
        raise ValueError("runtime root must end in an opaque 32-hex token")
    if not routing_eval.OPAQUE_TOKEN_RE.fullmatch(workspace.name):
        raise ValueError("workspace must use an opaque 32-hex row token")
    if workspace.parent != runtime_root:
        raise ValueError("workspace must be a direct child of the frozen runtime root")
    if routing_eval.workspace_identity(str(runtime_root)) != row.get("runtime_root_sha256"):
        raise ValueError("runtime root identity mismatch")
    if routing_eval.workspace_identity(str(workspace)) != row.get("workspace_sha256"):
        raise ValueError("workspace identity mismatch")
    if not runtime_root.is_dir():
        raise RuntimeError("runtime root must exist before row materialization")
    if workspace.exists() or any(runtime_root.iterdir()):
        raise RuntimeError("runtime root must be empty before row materialization")
    fixture_path = pathlib.Path(row["fixture_path"])
    try:
        files = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("frozen fixture payload is unreadable") from exc
    if not isinstance(files, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in files.items()):
        raise ValueError("frozen fixture payload must map text paths to text content")
    workspace_created = False
    try:
        workspace.mkdir(parents=False, exist_ok=False)
        workspace_created = True
        routing_eval._write_fixture(workspace, files)
        actual_hash = workspace_fixture_sha256(workspace)
        if actual_hash != row.get("fixture_sha256"):
            raise ValueError("workspace fixture SHA256 mismatch")
        return workspace
    except Exception:
        if workspace_created:
            remove_runtime_workspace(workspace)
        raise


def remove_runtime_workspace(workspace: pathlib.Path) -> None:
    is_junction = getattr(workspace, "is_junction", lambda: False)
    if workspace.is_symlink():
        workspace.unlink()
        if os.path.lexists(workspace):
            raise RuntimeError(f"runtime workspace cleanup failed: {workspace}")
        raise RuntimeError("runtime workspace became a symlink during cleanup")
    if is_junction():
        workspace.rmdir()
        if os.path.lexists(workspace):
            raise RuntimeError(f"runtime workspace cleanup failed: {workspace}")
        raise RuntimeError("runtime workspace became a junction during cleanup")
    if os.path.lexists(workspace):
        shutil.rmtree(workspace)
    if os.path.lexists(workspace):
        raise RuntimeError(f"runtime workspace cleanup failed: {workspace}")


def _toml_literal(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return repr(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_literal(item) for item in value) + "]"
    if isinstance(value, dict):
        parts = [f"{key} = {_toml_literal(item)}" for key, item in value.items()]
        return "{ " + ", ".join(parts) + " }"
    raise ValueError(f"unsupported TOML value type: {type(value).__name__}")


def build_profile_text(
    live: dict,
    arm: str,
    skill_path: str,
    mcp_path: str,
    disabled_skill_paths=(),
) -> str:
    if arm not in {"S", "M"}:
        raise ValueError("arm must be S or M")
    provider_name = live.get("model_provider")
    provider_tables = live.get("model_providers")
    if provider_tables is None or (isinstance(provider_tables, dict) and provider_name not in provider_tables):
        if provider_name != "openai":
            raise ValueError("selected model provider table is missing")
        provider = None
    else:
        if not isinstance(provider_tables, dict):
            raise ValueError("selected model provider table is missing")
        provider = provider_tables.get(provider_name)
        if not isinstance(provider, dict):
            raise ValueError("selected model provider table is missing")
    mcp = (live.get("mcp_servers") or {}).get("psr_reliability_native")
    if not isinstance(mcp, dict):
        raise ValueError("psr_reliability_native MCP config is missing")

    lines = []
    for key in TOP_LEVEL_ALLOWLIST:
        if key in live:
            lines.append(f"{key} = {_toml_literal(live[key])}")
    lines.extend(["", "[features]", "plugins = false", "apps = false", "remote_plugin = false", "plugin_sharing = false"])
    if (live.get("features") or {}).get("fast_mode") is not None:
        lines.append(f"fast_mode = {_toml_literal(bool(live['features']['fast_mode']))}")
    if provider is not None:
        lines.extend(["", f"[model_providers.{provider_name}]"])
        for key, value in provider.items():
            lines.append(f"{key} = {_toml_literal(value)}")

    lines.extend(["", "[mcp_servers.psr_reliability_native]"])
    lines.append(f"command = {_toml_literal(mcp_path)}")
    lines.append(f"args = {_toml_literal(mcp.get('args', []))}")
    for key in ("startup_timeout_sec", "tool_timeout_sec", "enabled"):
        if key in mcp:
            lines.append(f"{key} = {_toml_literal(mcp[key])}")

    skill_states = {str(path): False for path in disabled_skill_paths}
    skill_states[str(skill_path)] = arm == "S"
    for path, enabled in sorted(skill_states.items(), key=lambda item: item[0].casefold()):
        lines.extend(["", "[[skills.config]]"])
        lines.append(f"path = {_toml_literal(path)}")
        lines.append(f"enabled = {_toml_literal(enabled)}")
    return "\n".join(lines).rstrip() + "\n"


def profile_receipt(live: dict, arm: str, config_sha256: str, mcp_sha256: str, skill_sha256: str) -> dict:
    provider_name = live.get("model_provider")
    provider = (live.get("model_providers") or {}).get(provider_name) or {}
    return {
        "schema_version": 1,
        "arm": arm,
        "model": live.get("model"),
        "provider": provider_name,
        "provider_base_url": provider.get("base_url"),
        "provider_wire_api": provider.get("wire_api"),
        "effort": live.get("model_reasoning_effort"),
        "approval_policy": live.get("approval_policy"),
        "sandbox_mode": live.get("sandbox_mode"),
        "config_sha256": config_sha256,
        "mcp_sha256": mcp_sha256,
        "skill_sha256": skill_sha256,
    }


def _flatten_prompt_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(filter(None, (_flatten_prompt_text(item) for item in value)))
    if isinstance(value, dict):
        parts = []
        if isinstance(value.get("text"), str):
            parts.append(value["text"])
        for key in ("content", "body", "message"):
            if key in value:
                parts.append(_flatten_prompt_text(value[key]))
        return "\n".join(filter(None, parts))
    return ""


_SKILL_LINE = re.compile(
    r"^-\s+([^:\r\n]+):.*?\(file:\s*([^\r\n)]+)\)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def parse_prompt_input_skills(payload) -> list[dict]:
    text = _flatten_prompt_text(payload)
    return [
        {"name": match.group(1).strip(), "path": match.group(2).strip()}
        for match in _SKILL_LINE.finditer(text)
    ]


def verify_arm_catalog(arm: str, skills: list[dict]) -> None:
    names = [str(item.get("name", "")).strip().casefold() for item in skills]
    psr_count = names.count("powershell-reliability")
    unrelated = [name for name in names if name and name != "powershell-reliability"]
    if arm == "S":
        if psr_count != 1:
            raise ValueError("S catalog must contain exactly one powershell-reliability Skill")
        if unrelated:
            raise ValueError(f"S catalog contains unrelated Skills: {unrelated}")
    elif arm == "M":
        if psr_count or unrelated:
            raise ValueError("M catalog must contain no Skills")
    else:
        raise ValueError("arm must be S or M")


def verify_mcp_profile(profile: dict) -> None:
    servers = profile.get("mcp_servers")
    if not isinstance(servers, dict) or set(servers) != {"psr_reliability_native"}:
        raise ValueError("profile must contain exactly one MCP server: psr_reliability_native")
    config = servers["psr_reliability_native"]
    if not isinstance(config, dict) or not config.get("command"):
        raise ValueError("psr_reliability_native MCP command is missing")
    if config.get("enabled") is False:
        raise ValueError("psr_reliability_native MCP must be enabled")


def verify_cli_identity(exe: pathlib.Path, expected_version: str, expected_sha256: str, runner=subprocess.run) -> dict:
    actual_hash = sha256_file(exe)
    if actual_hash.casefold() != expected_sha256.casefold():
        raise ValueError(f"CLI SHA256 mismatch: expected {expected_sha256}, got {actual_hash}")
    completed = runner([str(exe), "--version"], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise ValueError("CLI version probe failed")
    match = re.search(r"(?:codex-cli\s+)?([^\s]+)", (completed.stdout or "").strip())
    actual_version = match.group(1) if match else ""
    if actual_version != expected_version:
        raise ValueError(f"CLI version mismatch: expected {expected_version}, got {actual_version}")
    return {"version": actual_version, "sha256": actual_hash, "path": str(exe)}


def codex_argv(exe: pathlib.Path, workspace: pathlib.Path, model: str | None = None) -> list[str]:
    argv = [exe.as_posix(), "exec", "--ephemeral", "--json"]
    if model:
        argv.extend(["--model", model])
    argv.extend(["-C", workspace.as_posix(), "-"])
    return argv


def validate_profile_identity(profile: pathlib.Path, expected_identity) -> None:
    if not os.path.lexists(profile):
        raise RuntimeError("secret-bearing profile is missing")
    if _path_is_link_or_junction(profile):
        raise RuntimeError("secret-bearing profile filesystem identity changed")
    if _filesystem_object_identity(profile) != tuple(expected_identity):
        raise RuntimeError("secret-bearing profile filesystem identity changed")
    if not profile.is_dir():
        raise RuntimeError("secret-bearing profile is no longer a directory")


def remove_profile(profile: pathlib.Path, expected_identity=None) -> None:
    if not os.path.lexists(profile):
        return
    if expected_identity is not None:
        validate_profile_identity(profile, expected_identity)
        shutil.rmtree(profile)
        if os.path.lexists(profile):
            raise RuntimeError(f"secret-bearing profile cleanup failed: {profile}")
        return
    is_junction = getattr(profile, "is_junction", lambda: False)
    if profile.is_symlink():
        profile.unlink()
        if os.path.lexists(profile):
            raise RuntimeError(f"secret-bearing profile cleanup failed: {profile}")
        raise RuntimeError("secret-bearing profile became a symlink during cleanup")
    if is_junction():
        profile.rmdir()
        if os.path.lexists(profile):
            raise RuntimeError(f"secret-bearing profile cleanup failed: {profile}")
        raise RuntimeError("secret-bearing profile became a junction during cleanup")
    shutil.rmtree(profile)
    if os.path.lexists(profile):
        raise RuntimeError(f"secret-bearing profile cleanup failed: {profile}")


def _kill_process_tree_windows(process) -> None:
    subprocess.run(
        ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def run_codex_process(
    exe: pathlib.Path,
    workspace: pathlib.Path,
    profile: pathlib.Path,
    prompt_bytes: bytes,
    stdout_path: pathlib.Path,
    stderr_path: pathlib.Path,
    timeout_seconds: int,
    popen_factory=subprocess.Popen,
    tree_killer=_kill_process_tree_windows,
    clock=time.monotonic,
    model: str | None = None,
) -> dict:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(profile)
    env["CODEX_SQLITE_HOME"] = str(profile)
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    timed_out = False
    termination_reason = "process_exit"
    started_at = clock()
    with stdout_path.open("wb") as stdout_handle, stderr_path.open("wb") as stderr_handle:
        process = popen_factory(
            codex_argv(exe, workspace, model=model),
            stdin=subprocess.PIPE,
            stdout=stdout_handle,
            stderr=stderr_handle,
            env=env,
        )
        try:
            process.communicate(input=prompt_bytes, timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            termination_reason = "timeout"
            tree_killer(process)
            try:
                process.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired as exc:
                    raise RuntimeError("timed-out Codex process would not terminate") from exc
    task_wall_clock_ms = max(0, round((clock() - started_at) * 1000))
    return {
        "pid": process.pid,
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "termination_reason": termination_reason,
        "task_wall_clock_ms": task_wall_clock_ms,
        "stdout_path": str(stdout_path),
        "stderr_path": str(stderr_path),
    }


def restrict_profile_acl(
    profile: pathlib.Path,
    identity_runner=subprocess.run,
    icacls_runner=subprocess.run,
) -> str:
    if profile.exists() and any(profile.iterdir()):
        raise RuntimeError("temporary ACL restriction requires an empty profile directory")
    identity_probe = identity_runner(["whoami.exe"], capture_output=True, text=True, check=False)
    identity = (identity_probe.stdout or "").strip()
    if identity_probe.returncode != 0 or not identity:
        raise RuntimeError("could not resolve current Windows identity")
    grant = f"{identity}:(OI)(CI)F"
    applied = icacls_runner(
        ["icacls.exe", str(profile), "/inheritance:r", "/grant:r", grant],
        capture_output=True, text=True, check=False,
    )
    if applied.returncode != 0:
        raise RuntimeError("failed to restrict temporary profile ACL")
    verified = icacls_runner(["icacls.exe", str(profile)], capture_output=True, text=True, check=False)
    acl_text = (verified.stdout or "") + (verified.stderr or "")
    if verified.returncode != 0 or identity.casefold() not in acl_text.casefold() or "(I)" in acl_text:
        raise RuntimeError("temporary profile ACL verification failed")
    return identity


def run_with_profile_cleanup(profile: pathlib.Path, executor):
    try:
        return executor()
    finally:
        remove_profile(profile)


TOKEN_FIELDS = (
    "input_tokens",
    "cached_input_tokens",
    "cache_write_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


def _error_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("message", "error", "detail"):
            if isinstance(value.get(key), str):
                return value[key]
    return json.dumps(value, ensure_ascii=False, sort_keys=True) if value is not None else ""


def parse_cli_jsonl(path: pathlib.Path, allow_truncated_tail: bool = False) -> dict:
    thread_id = None
    turn_status = "unknown"
    commands_by_id = {}
    mcp_calls_by_id = {}
    command_started_ids = set()
    command_completed_ids = set()
    mcp_started_ids = set()
    mcp_completed_ids = set()
    errors = []
    final_message = None
    tokens = {name: None for name in TOKEN_FIELDS}
    event_count = 0
    truncated_jsonl_tail = False
    lines = path.read_text(encoding="utf-8").splitlines()
    nonempty_indexes = [index for index, raw in enumerate(lines) if raw.strip()]
    last_nonempty_index = nonempty_indexes[-1] if nonempty_indexes else None

    for zero_index, raw in enumerate(lines):
        line_number = zero_index + 1
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError as exc:
            if allow_truncated_tail and zero_index == last_nonempty_index:
                truncated_jsonl_tail = True
                break
            raise ValueError(f"malformed CLI JSONL line {line_number}") from exc
        if not isinstance(event, dict) or not isinstance(event.get("type"), str):
            raise ValueError(f"invalid CLI JSONL event at line {line_number}")
        event_count += 1
        kind = event["type"]
        if kind == "thread.started":
            thread_id = event.get("thread_id")
        elif kind in {"item.started", "item.completed"}:
            item = event.get("item") or {}
            if not isinstance(item, dict):
                raise ValueError(f"invalid CLI item at line {line_number}")
            item_kind = item.get("type")
            item_id = item.get("id")
            if item_kind in {"command_execution", "mcp_tool_call"}:
                if not isinstance(item_id, str) or not item_id:
                    raise ValueError(f"CLI tool/command item missing id at line {line_number}")
                target = commands_by_id if item_kind == "command_execution" else mcp_calls_by_id
                started_ids = command_started_ids if item_kind == "command_execution" else mcp_started_ids
                completed_ids = command_completed_ids if item_kind == "command_execution" else mcp_completed_ids
                if kind == "item.started":
                    summary = target.setdefault(item_id, {"id": item_id, "type": item_kind, "started_event_index": None, "completed_event_index": None})
                    started_ids.add(item_id)
                    if summary["started_event_index"] is None:
                        summary["started_event_index"] = event_count
                else:
                    summary = target.get(item_id)
                    if summary is None or item_id not in started_ids:
                        raise ValueError(f"CLI {item_kind} completion without matching start at line {line_number}")
                    completed_ids.add(item_id)
                    summary["completed_event_index"] = event_count
                    summary["terminal_status"] = item.get("status")
                if item_kind == "command_execution":
                    for field in ("command", "cwd", "workdir", "exit_code"):
                        value = item.get(field)
                        if field == "exit_code":
                            if field in item:
                                summary[field] = value
                        elif field == "command":
                            if kind == "item.started" and isinstance(value, str) and value:
                                summary.setdefault(field, value)
                        elif isinstance(value, str) and value:
                            summary.setdefault(field, value)
                else:
                    for field in ("server", "tool"):
                        if field in item:
                            summary[field] = item[field]
            elif kind == "item.completed" and item_kind == "agent_message" and isinstance(item.get("text"), str):
                final_message = item["text"]
        elif kind == "turn.completed":
            turn_status = "completed"
            usage = event.get("usage") or {}
            if not isinstance(usage, dict):
                raise ValueError(f"invalid CLI usage at line {line_number}")
            for name in TOKEN_FIELDS:
                value = usage.get(name)
                if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
                    raise ValueError(f"invalid CLI token field {name} at line {line_number}")
                tokens[name] = value
        elif kind == "turn.failed":
            turn_status = "failed"
            errors.append(_error_text(event.get("error")))
        elif kind == "error":
            errors.append(_error_text(event.get("error") or event.get("message") or event))

    commands = list(commands_by_id.values())
    mcp_calls = list(mcp_calls_by_id.values())
    return {
        "thread_id": thread_id,
        "turn_status": turn_status,
        "event_count": event_count,
        "truncated_jsonl_tail": truncated_jsonl_tail,
        "commands": commands,
        "mcp_calls": mcp_calls,
        "native_command_count": len(commands),
        "incomplete_native_command_count": len(command_started_ids - command_completed_ids),
        "mcp_call_count": len(mcp_calls),
        "incomplete_mcp_call_count": len(mcp_started_ids - mcp_completed_ids),
        "reliability_mcp_call_count": sum(call.get("server") == "psr_reliability_native" for call in mcp_calls),
        "tokens": tokens,
        "final_message": final_message,
        "errors": [item for item in errors if item],
    }


def validate_first_command_expectation(row: dict) -> str | None:
    expected = row.get("expected_first_command_fragment")
    if expected is None:
        return None
    if not isinstance(expected, str) or not expected.strip():
        raise ValueError("manifest first command expectation must be a non-empty string")
    return expected


def validate_expected_first_command(row: dict, parsed: dict) -> None:
    expected = validate_first_command_expectation(row)
    if expected is None:
        return
    commands = parsed.get("commands") or []
    if not commands or not isinstance(commands[0].get("command"), str):
        raise ValueError("manifest first command missing")
    actual = commands[0]["command"]
    if not routing_eval.trigger_eval.raw_command_fragment_matches(expected, actual):
        raise ValueError("manifest first command mismatch")


def _known_path_sha256(value: pathlib.Path | str) -> str:
    normalized = str(pathlib.PureWindowsPath(str(value))).replace("/", "\\").rstrip("\\").casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest().upper()


def _text_mentions_windows_path(text: str, path: pathlib.Path | str) -> bool:
    if not isinstance(text, str) or not text:
        return False
    normalized_text = text.replace("/", "\\").casefold()
    normalized_path = str(pathlib.PureWindowsPath(str(path))).replace("/", "\\").rstrip("\\").casefold()
    if not normalized_path:
        return False
    pattern = rf"(?<![A-Za-z0-9_.-]){re.escape(normalized_path)}(?![A-Za-z0-9_.-])"
    return re.search(pattern, normalized_text) is not None


def _command_mentions_known_path(command: dict, target: pathlib.Path | str) -> bool:
    absolute_fields = [command.get("command"), command.get("cwd"), command.get("workdir")]
    if any(_text_mentions_windows_path(value, target) for value in absolute_fields if isinstance(value, str)):
        return True
    command_text = command.get("command")
    if not isinstance(command_text, str) or not command_text:
        return False
    target_text = str(target)
    for base_value in (command.get("cwd"), command.get("workdir")):
        if not isinstance(base_value, str) or not base_value or not ntpath.isabs(base_value):
            continue
        try:
            relative = ntpath.relpath(target_text, start=base_value)
        except ValueError:
            continue
        if relative not in {"", "."} and _text_mentions_windows_path(command_text, relative):
            return True
    return False


def detect_campaign_contamination(
    parsed: dict,
    manifest_rows: list[dict],
    current_row: dict,
    coordinator_root: pathlib.Path,
) -> list[dict]:
    current_workspace = str(current_row.get("workspace") or "")
    current_key = _windows_path_key(current_workspace) if current_workspace else ""
    other_paths = []
    for row in manifest_rows:
        value = row.get("workspace")
        if not isinstance(value, str) or not value:
            continue
        if _windows_path_key(value) != current_key:
            other_paths.append(value)

    def target_aliases(kind: str, value: pathlib.Path | str):
        raw = pathlib.Path(value)
        resolved = raw.resolve(strict=False)
        canonical_hash = _known_path_sha256(resolved)
        candidates = []
        for candidate in (str(raw), str(resolved)):
            key = _windows_path_key(candidate)
            if key not in {_windows_path_key(item) for item in candidates}:
                candidates.append(candidate)
        return [(kind, candidate, canonical_hash) for candidate in candidates]

    targets = target_aliases("coordinator_access", coordinator_root)
    for value in other_paths:
        targets.extend(target_aliases("other_row_workspace_access", value))

    evidence = []
    seen = set()
    for command in parsed.get("commands") or []:
        command_id = command.get("id")
        for kind, target, path_sha256 in targets:
            if not _command_mentions_known_path(command, target):
                continue
            identity = (kind, command_id, path_sha256)
            if identity in seen:
                continue
            seen.add(identity)
            evidence.append({"kind": kind, "command_id": command_id, "path_sha256": path_sha256})
    return evidence


def validate_cli_terminal_state(process_result: dict, parsed: dict) -> None:
    if process_result.get("timed_out"):
        return
    if parsed.get("turn_status") not in {"completed", "failed"}:
        raise ValueError("CLI JSONL is missing a terminal turn event")


def evaluate_manifest_row(manifest_row: dict, workspace: pathlib.Path, runtime_boundary=None) -> dict:
    if runtime_boundary is not None:
        validate_runtime_workspace_boundary(manifest_row, workspace, expected=runtime_boundary)
    row = dict(manifest_row)
    row["workspace"] = str(workspace)
    rule = row.get("post_condition", {"kind": "none"})
    kind = rule.get("kind") if isinstance(rule, dict) else None
    if kind == "workspace_state":
        if _path_is_link_or_junction(workspace):
            raise ValueError("workspace root must not be a symlink or junction during post-condition evaluation")
        return routing_eval.evaluate_workspace_state(row)
    if kind == "none":
        return routing_eval.evaluate_post_condition([], row)
    raise ValueError("CLI automation supports only workspace_state/none post-conditions")


def _receipt_native_commands(commands) -> list[dict]:
    allowed = (
        "id", "type", "started_event_index", "completed_event_index",
        "terminal_status", "exit_code",
    )
    result = []
    for command in commands or []:
        if not isinstance(command, dict):
            continue
        result.append({key: command[key] for key in allowed if key in command})
    return result


def normalized_execution_receipt(
    manifest_row: dict,
    process_result: dict,
    parsed: dict,
    profile_meta: dict,
    skill_catalog: list[dict],
    post_condition: dict,
    profile_cleanup_ok: bool,
    workspace_cleanup_ok: bool,
    contamination_evidence=(),
) -> dict:
    receipt = {
        "schema_version": 1,
        "case_key": manifest_row.get("case_key"),
        "case_id": manifest_row.get("case_id"),
        "trial_id": manifest_row.get("trial_id"),
        "arm": manifest_row.get("arm"),
        "sequence": manifest_row.get("sequence"),
        "prompt_sha256": manifest_row.get("prompt_sha256"),
        "workspace_sha256": manifest_row.get("workspace_sha256"),
        "fixture_sha256": manifest_row.get("fixture_sha256"),
        "cli_version": profile_meta.get("cli_version"),
        "cli_sha256": profile_meta.get("cli_sha256"),
        "profile_fingerprint": profile_meta.get("profile_fingerprint"),
        "mcp_sha256": profile_meta.get("mcp_sha256"),
        "skill_sha256": profile_meta.get("skill_sha256"),
        "live_config_sha256": profile_meta.get("live_config_sha256"),
        "model": profile_meta.get("model"),
        "provider": profile_meta.get("provider"),
        "reasoning_effort": profile_meta.get("effort"),
        "approval_policy": profile_meta.get("approval_policy"),
        "sandbox_mode": profile_meta.get("sandbox_mode"),
        "campaign_identity_sha256": profile_meta.get("campaign_identity_sha256"),
        "harness_git_head": profile_meta.get("harness_git_head"),
        "public_main_sha": profile_meta.get("public_main_sha"),
        "process_exit_code": process_result.get("exit_code"),
        "timed_out": bool(process_result.get("timed_out")),
        "termination_reason": process_result.get("termination_reason"),
        "task_wall_clock_ms": process_result.get("task_wall_clock_ms"),
        "thread_id": parsed.get("thread_id"),
        "turn_status": parsed.get("turn_status"),
        "native_command_count": parsed.get("native_command_count", 0),
        "incomplete_native_command_count": parsed.get("incomplete_native_command_count", 0),
        "mcp_call_count": parsed.get("mcp_call_count", 0),
        "incomplete_mcp_call_count": parsed.get("incomplete_mcp_call_count", 0),
        "reliability_mcp_call_count": parsed.get("reliability_mcp_call_count", 0),
        "truncated_jsonl_tail": bool(parsed.get("truncated_jsonl_tail")),
        "native_commands": _receipt_native_commands(parsed.get("commands")),
        "mcp_calls": parsed.get("mcp_calls", []),
        "skill_catalog": sorted({str(item.get("name", "")).strip() for item in skill_catalog if item.get("name")}),
        "post_condition_passed": post_condition.get("passed"),
        "post_condition_source": post_condition.get("source"),
        "protocol_contamination": bool(contamination_evidence),
        "contamination_evidence": list(contamination_evidence),
        "profile_cleanup_ok": bool(profile_cleanup_ok),
        "workspace_cleanup_ok": bool(workspace_cleanup_ok),
        "cleanup_ok": bool(profile_cleanup_ok and workspace_cleanup_ok),
    }
    for name in TOKEN_FIELDS:
        receipt[name] = (parsed.get("tokens") or {}).get(name)
    return receipt


def _profile_env(profile: pathlib.Path) -> dict[str, str]:
    env = os.environ.copy()
    env["CODEX_HOME"] = str(profile)
    env["CODEX_SQLITE_HOME"] = str(profile)
    return env


def probe_skill_catalog(exe: pathlib.Path, profile: pathlib.Path, runner=subprocess.run) -> list[dict]:
    completed = runner(
        [exe.as_posix(), "debug", "prompt-input", "probe"],
        env=_profile_env(profile), capture_output=True, encoding="utf-8", errors="replace", check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Codex Skill catalog probe failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Codex Skill catalog probe returned malformed JSON") from exc
    return parse_prompt_input_skills(payload)


def probe_mcp_catalog(exe: pathlib.Path, profile: pathlib.Path, runner=subprocess.run) -> list[dict]:
    completed = runner(
        [exe.as_posix(), "mcp", "list", "--json"],
        env=_profile_env(profile), capture_output=True, encoding="utf-8", errors="replace", check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("Codex MCP catalog probe failed")
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError("Codex MCP catalog probe returned malformed JSON") from exc
    if not isinstance(payload, list) or len(payload) != 1:
        raise ValueError("Codex MCP catalog must contain exactly one server")
    server = payload[0]
    if not isinstance(server, dict) or server.get("name") != "psr_reliability_native" or server.get("enabled") is not True:
        raise ValueError("Codex MCP catalog must contain exactly one enabled psr_reliability_native server")
    return payload


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--arm", choices=("S", "M"), required=True)
    parser.add_argument("--live-config", type=pathlib.Path, required=True)
    parser.add_argument("--codex", type=pathlib.Path, required=True)
    parser.add_argument("--codex-version", required=True)
    parser.add_argument("--codex-sha256", required=True)
    parser.add_argument("--skill-path", type=pathlib.Path, required=True)
    parser.add_argument("--skill-sha256", required=True)
    parser.add_argument("--mcp-path", type=pathlib.Path, required=True)
    parser.add_argument("--mcp-sha256", required=True)
    parser.add_argument("--evidence-root", type=pathlib.Path, required=True)
    parser.add_argument("--identity-lock", type=pathlib.Path, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--public-main-sha", required=True)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Isolated Codex routing automation")
    subparsers = parser.add_subparsers(dest="command", required=True)
    profile = subparsers.add_parser("profile-check")
    _add_common_args(profile)
    profile.add_argument("--initialize-identity-lock", action="store_true")
    run_row = subparsers.add_parser("run-row")
    _add_common_args(run_row)
    run_row.add_argument("--manifest", type=pathlib.Path, required=True)
    run_row.add_argument("--sequence", type=int, required=True)
    run_row.add_argument("--timeout", type=int, required=True)
    return parser


def parse_args(argv=None):
    return build_arg_parser().parse_args(argv)


def _windows_path_key(value: str) -> str:
    return str(pathlib.PureWindowsPath(value)).replace("/", "\\").rstrip("\\").casefold()


def materialize_profile(
    live_config_path: pathlib.Path,
    arm: str,
    skill_path: pathlib.Path,
    mcp_path: pathlib.Path,
    codex_path: pathlib.Path,
    temp_parent: pathlib.Path | None = None,
    acl_func=restrict_profile_acl,
    skill_probe=probe_skill_catalog,
    mcp_probe=probe_mcp_catalog,
):
    live_hash_before = sha256_file(live_config_path)
    live = load_live_config(live_config_path)
    profile = pathlib.Path(tempfile.mkdtemp(prefix="psr-codex-profile-", dir=str(temp_parent) if temp_parent else None))
    profile_identity = None
    try:
        profile_identity = _filesystem_object_identity(profile)
        acl_func(profile)
        if live.get("model_provider") == "openai":
            shutil.copyfile(live_config_path.parent / "auth.json", profile / "auth.json")
        initial_text = build_profile_text(live, arm, skill_path.as_posix(), mcp_path.as_posix())
        config_path = profile / "config.toml"
        config_path.write_text(initial_text, encoding="utf-8", newline="\n")
        discovered = skill_probe(codex_path, profile)
        final_text = build_profile_text(
            live, arm, skill_path.as_posix(), mcp_path.as_posix(),
            disabled_skill_paths=[item["path"] for item in discovered],
        )
        config_path.write_text(final_text, encoding="utf-8", newline="\n")
        final_skills = skill_probe(codex_path, profile)
        verify_arm_catalog(arm, final_skills)
        profile_dict = tomllib.loads(final_text)
        verify_mcp_profile(profile_dict)
        mcp_catalog = mcp_probe(codex_path, profile)
        observed_command = (((mcp_catalog[0].get("transport") or {}).get("command")) if mcp_catalog else None)
        if not isinstance(observed_command, str) or _windows_path_key(observed_command) != _windows_path_key(str(mcp_path)):
            raise ValueError("observed Reliability MCP command does not match frozen MCP path")
        live_hash_after = sha256_file(live_config_path)
        if live_hash_after != live_hash_before:
            raise RuntimeError("live Codex config changed during isolated profile materialization")
        validate_profile_identity(profile, profile_identity)
        provider_name = live.get("model_provider")
        provider = (live.get("model_providers") or {}).get(provider_name) or {}
        meta = {
            "live_config_sha256": live_hash_before,
            "profile_fingerprint": sha256_file(config_path),
            "provider": provider_name,
            "provider_base_url": provider.get("base_url"),
            "provider_wire_api": provider.get("wire_api"),
            "model": live.get("model"),
            "effort": live.get("model_reasoning_effort"),
            "approval_policy": live.get("approval_policy"),
            "sandbox_mode": live.get("sandbox_mode"),
            "_profile_filesystem_identity": profile_identity,
        }
        return profile, meta, final_skills, mcp_catalog
    except Exception:
        if profile_identity is None:
            remove_profile(profile)
        else:
            remove_profile(profile, expected_identity=profile_identity)
        raise


_CASE_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_WINDOWS_RESERVED_BASENAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def validate_case_key(case_key: str) -> str:
    if not isinstance(case_key, str) or not _CASE_KEY_RE.fullmatch(case_key) or case_key.endswith((".", " ")):
        raise ValueError("manifest case_key must be a single safe Windows path component")
    basename = case_key.split(".", 1)[0].upper()
    if basename in _WINDOWS_RESERVED_BASENAMES:
        raise ValueError("manifest case_key uses a reserved Windows device name")
    return case_key


def _is_relative_to(child: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_runtime_topology(
    coordinator_root: pathlib.Path,
    runtime_root: pathlib.Path,
    workspace: pathlib.Path,
) -> None:
    if _path_is_link_or_junction(runtime_root) or _path_is_link_or_junction(workspace):
        raise ValueError("runtime root/workspace must not be a symlink or junction")
    coordinator_root = coordinator_root.resolve(strict=False)
    runtime_root = runtime_root.resolve(strict=False)
    workspace = workspace.resolve(strict=False)
    if _is_relative_to(runtime_root, coordinator_root) or _is_relative_to(coordinator_root, runtime_root):
        raise ValueError("coordinator and runtime roots must be disjoint")
    if workspace.parent != runtime_root:
        raise ValueError("workspace must be a direct child of the frozen runtime root")


def validate_manifest_row_paths(manifest_path: pathlib.Path, row: dict) -> None:
    coordinator_root = ensure_external_evidence_root(manifest_path.parent)
    case_key = row.get("case_key")
    arm = row.get("arm")
    if arm not in {"S", "M"}:
        raise ValueError("manifest row must contain a valid case_key and arm")
    validate_case_key(case_key)
    raw_prompt = pathlib.Path(row.get("prompt_path", ""))
    if _path_is_link_or_junction(raw_prompt) or _path_is_link_or_junction(raw_prompt.parent):
        raise ValueError("manifest prompt path must not be a symlink or junction")
    expected_prompt = (coordinator_root / "prompts" / f"{case_key}.txt").resolve(strict=False)
    actual_prompt = raw_prompt.resolve(strict=False)
    if actual_prompt != expected_prompt:
        raise ValueError("manifest prompt path must use the prepared coordinator layout")
    raw_fixture = pathlib.Path(row.get("fixture_path", ""))
    if _path_is_link_or_junction(raw_fixture) or _path_is_link_or_junction(raw_fixture.parent):
        raise ValueError("manifest fixture path must not be a symlink or junction")
    expected_fixture = (coordinator_root / "fixtures" / f"{case_key}.json").resolve(strict=False)
    actual_fixture = raw_fixture.resolve(strict=False)
    if actual_fixture != expected_fixture:
        raise ValueError("manifest fixture path must use the prepared coordinator layout")
    raw_runtime_root = pathlib.Path(row.get("runtime_root", ""))
    raw_workspace = pathlib.Path(row.get("workspace", ""))
    if _path_is_link_or_junction(raw_runtime_root) or _path_is_link_or_junction(raw_workspace):
        raise ValueError("manifest runtime root/workspace must not be a symlink or junction")
    runtime_root = raw_runtime_root.resolve(strict=False)
    workspace = raw_workspace.resolve(strict=False)
    if not routing_eval.OPAQUE_TOKEN_RE.fullmatch(runtime_root.name):
        raise ValueError("manifest runtime root must end in an opaque 32-hex token")
    if not routing_eval.OPAQUE_TOKEN_RE.fullmatch(workspace.name):
        raise ValueError("manifest workspace must use an opaque 32-hex row token")
    validate_runtime_topology(coordinator_root, runtime_root, workspace)
    if routing_eval.workspace_identity(str(runtime_root)) != row.get("runtime_root_sha256"):
        raise ValueError("runtime root identity mismatch")
    if routing_eval.workspace_identity(str(workspace)) != row.get("workspace_sha256"):
        raise ValueError("workspace identity mismatch")


def load_manifest_row(path: pathlib.Path, sequence: int) -> dict:
    matches = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, raw in enumerate(handle, 1):
            if not raw.strip():
                continue
            try:
                row = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed manifest JSONL line {line_number}") from exc
            if isinstance(row, dict) and row.get("sequence") == sequence:
                matches.append(row)
    if len(matches) != 1:
        raise ValueError(f"manifest sequence {sequence} must be unique and present")
    return matches[0]


def execute_profile_check(args, verify_cli=verify_cli_identity, materialize=materialize_profile) -> dict:
    args.evidence_root = ensure_external_evidence_root(args.evidence_root)
    cli_identity = verify_cli(args.codex, args.codex_version, args.codex_sha256)
    skill_hash = sha256_file(args.skill_path)
    mcp_hash = sha256_file(args.mcp_path)
    if skill_hash.casefold() != args.skill_sha256.casefold():
        raise ValueError("Skill SHA256 mismatch")
    if mcp_hash.casefold() != args.mcp_sha256.casefold():
        raise ValueError("Reliability MCP SHA256 mismatch")
    profile = None
    profile_identity = None
    cleanup_ok = False
    try:
        profile, meta, skills, mcp_catalog = materialize(
            args.live_config, args.arm, args.skill_path, args.mcp_path, args.codex,
        )
        observed_profile_identity = _filesystem_object_identity(profile)
        profile_identity = tuple(meta.get("_profile_filesystem_identity") or observed_profile_identity) if isinstance(meta, dict) else observed_profile_identity
        validate_profile_identity(profile, profile_identity)
        identity = campaign_identity_payload(cli_identity, args.skill_path, skill_hash, args.mcp_path, mcp_hash, meta, model=args.model, public_main_sha=args.public_main_sha)
        identity_sha = verify_or_create_campaign_identity_lock(
            args.identity_lock, identity, allow_create=bool(args.initialize_identity_lock)
        )
        result = {
            "schema_version": 1,
            "status": "PASS",
            "arm": args.arm,
            "cli_version": cli_identity["version"],
            "cli_sha256": cli_identity["sha256"],
            "model": args.model,
            "live_config_sha256": meta["live_config_sha256"],
            "profile_fingerprint": meta["profile_fingerprint"],
            "mcp_sha256": mcp_hash,
            "skill_sha256": skill_hash,
            "campaign_identity_sha256": identity_sha,
            "harness_git_head": identity["harness_git_head"],
            "public_main_sha": identity["public_main_sha"],
            "skill_catalog": sorted(item["name"] for item in skills),
            "mcp_catalog": [item["name"] for item in mcp_catalog],
        }
    finally:
        if profile is not None:
            remove_profile(profile, expected_identity=profile_identity)
            cleanup_ok = not os.path.lexists(profile)
    result["cleanup_ok"] = cleanup_ok
    args.evidence_root.mkdir(parents=True, exist_ok=True)
    output = args.evidence_root / f"profile-check-{args.arm}.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def execute_run_row(
    args,
    verify_cli=verify_cli_identity,
    materialize=materialize_profile,
    process_runner=run_codex_process,
    json_parser=parse_cli_jsonl,
) -> dict:
    args.evidence_root = ensure_external_evidence_root(args.evidence_root)
    skill_hash = sha256_file(args.skill_path)
    mcp_hash = sha256_file(args.mcp_path)
    if skill_hash.casefold() != args.skill_sha256.casefold():
        raise ValueError("Skill SHA256 mismatch")
    if mcp_hash.casefold() != args.mcp_sha256.casefold():
        raise ValueError("Reliability MCP SHA256 mismatch")
    row = load_manifest_row(args.manifest, args.sequence)
    validate_manifest_row_paths(args.manifest, row)
    validate_first_command_expectation(row)
    cli_identity = verify_cli(args.codex, args.codex_version, args.codex_sha256)
    if row.get("arm") != args.arm:
        raise ValueError("requested arm does not match manifest row")
    prompt_path = pathlib.Path(row["prompt_path"])
    prompt_bytes = prompt_path.read_bytes()
    actual_prompt_hash = hashlib.sha256(prompt_bytes).hexdigest().upper()
    if actual_prompt_hash != row.get("prompt_sha256"):
        raise ValueError("prompt hash mismatch")
    workspace = pathlib.Path(row["workspace"])
    ensure_evidence_outside_workspace(args.evidence_root, workspace)
    ensure_evidence_runtime_disjoint(args.evidence_root, pathlib.Path(row["runtime_root"]))
    output_dir = args.evidence_root / f"{args.sequence:04d}-{row['case_key']}-{args.arm}"
    if output_dir.exists():
        raise FileExistsError(f"row evidence already exists: {output_dir}")

    profile = None
    profile_identity = None
    workspace_materialized = False
    profile_cleanup_ok = False
    workspace_cleanup_ok = False
    runtime_boundary = None
    cleanup_errors = []
    try:
        workspace = materialize_row_workspace(row)
        workspace_materialized = True
        runtime_boundary = capture_runtime_workspace_boundary(row, workspace)
        try:
            profile, profile_meta, skills, _ = materialize(
                args.live_config, args.arm, args.skill_path, args.mcp_path, args.codex,
            )
            observed_profile_identity = _filesystem_object_identity(profile)
            profile_identity = tuple(profile_meta.get("_profile_filesystem_identity") or observed_profile_identity) if isinstance(profile_meta, dict) else observed_profile_identity
            validate_profile_identity(profile, profile_identity)
            identity = campaign_identity_payload(
                cli_identity, args.skill_path, skill_hash, args.mcp_path, mcp_hash,
                profile_meta, model=args.model, public_main_sha=args.public_main_sha,
            )
            identity_sha = verify_or_create_campaign_identity_lock(
                args.identity_lock, identity, allow_create=False
            )
            output_dir.mkdir(parents=True)
            validate_runtime_workspace_boundary(row, workspace, expected=runtime_boundary)
        except Exception:
            evaluate_manifest_row(row, workspace, runtime_boundary)
            raise
        try:
            process_result = process_runner(
                args.codex, workspace, profile, prompt_bytes,
                output_dir / "stdout.jsonl", output_dir / "stderr.log", args.timeout,
                model=args.model,
            )
        except Exception:
            evaluate_manifest_row(row, workspace, runtime_boundary)
            raise
        post_condition = evaluate_manifest_row(row, workspace, runtime_boundary)
        parsed = json_parser(
            output_dir / "stdout.jsonl",
            allow_truncated_tail=bool(process_result.get("timed_out")),
        )
        validate_cli_terminal_state(process_result, parsed)
        validate_expected_first_command(row, parsed)
        manifest_rows = routing_eval.trigger_eval.load_jsonl(args.manifest)
        contamination_evidence = detect_campaign_contamination(
            parsed, manifest_rows, row, args.manifest.parent
        )
    finally:
        if profile is not None:
            try:
                remove_profile(profile, expected_identity=profile_identity)
                profile_cleanup_ok = not os.path.lexists(profile)
                if not profile_cleanup_ok:
                    raise RuntimeError("secret-bearing profile cleanup left a residual filesystem entry")
            except Exception as exc:
                cleanup_errors.append(("profile", exc))
        if workspace_materialized:
            try:
                if runtime_boundary is None:
                    raise RuntimeError("runtime boundary capture unavailable; recursive workspace cleanup refused")
                validate_runtime_workspace_boundary(row, workspace, expected=runtime_boundary)
                remove_runtime_workspace(workspace)
                runtime_root, _ = validate_runtime_workspace_boundary(
                    row, workspace, expected=runtime_boundary, require_workspace=False
                )
                if any(runtime_root.iterdir()):
                    raise RuntimeError("runtime root must be empty after row cleanup")
                workspace_cleanup_ok = not os.path.lexists(workspace)
            except Exception as exc:
                cleanup_errors.append(("workspace", exc))
        if cleanup_errors:
            kinds = ", ".join(kind for kind, _ in cleanup_errors)
            raise RuntimeError(f"row cleanup failed: {kinds}") from cleanup_errors[0][1]

    if sha256_file(args.live_config) != profile_meta["live_config_sha256"]:
        raise RuntimeError("live Codex config changed during automated row")
    profile_meta = dict(profile_meta)
    profile_meta.update({
        "cli_version": cli_identity["version"],
        "cli_sha256": cli_identity["sha256"],
        "mcp_sha256": mcp_hash,
        "skill_sha256": skill_hash,
        "model": args.model,
        "campaign_identity_sha256": identity_sha,
        "harness_git_head": identity["harness_git_head"],
        "public_main_sha": identity["public_main_sha"],
    })
    receipt = normalized_execution_receipt(
        row, process_result, parsed, profile_meta, skills, post_condition,
        profile_cleanup_ok, workspace_cleanup_ok, contamination_evidence,
    )
    (output_dir / "receipt.json").write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if contamination_evidence:
        raise RuntimeError("protocol contamination detected; bounded receipt preserved")
    return receipt


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        if args.command == "profile-check":
            result = execute_profile_check(args)
        elif args.command == "run-row":
            result = execute_run_row(args)
        else:
            raise ValueError(f"unsupported command: {args.command}")
    except Exception as exc:
        error = {"status": "ERROR", "error_type": type(exc).__name__, "message": str(exc)}
        print(json.dumps(error, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
