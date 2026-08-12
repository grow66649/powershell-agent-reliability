# PowerShell Reliability MCP Tool Contract v0.1

This contract defines the bounded structured surface of the local STDIO server. Codex Desktop/app-server remains the command/process/sandbox owner.

## Common invariants

- Server identity: `powershell-agent-reliability`.
- Transport: local STDIO.
- Public tools: `inspect_environment`, `diagnose_failure`, `verify_result` only.
- Tool outputs are structured JSON.
- Unknown input fields are rejected rather than silently ignored; collection/text/hash bounds are exposed in JSON Schema where practical and are also enforced at runtime.
- No tool is a generic shell/process runner.
- No tool mutates profiles, global environment, ACLs, sandbox settings, approvals, registry, services, or unrelated files.
- Command outcome and task post-condition remain separate facts.
- Missing evidence stays missing; `UNKNOWN` is valid.

### Same-process concurrency

- One STDIO server process may have multiple in-flight `tools/call` requests.
- Request IDs/results must remain correctly paired; concurrent requests must not share mutable request state.
- Failure or invalid input in one request must not corrupt, cancel, or change another request's result.
- Bounded file hashing/metadata work in `inspect_environment` or `verify_result` must not starve an unrelated `diagnose_failure` request.
- Concurrency does not authorize a session manager, daemon, global queue/cache, generic worker pool, or a wider public tool surface.

## `inspect_environment`

Use after a failure when shell/cwd/executable-resolution identity matters.

Inputs:
- `shell_executable` (optional): explicit shell path or executable name already relevant to the task.
- `cwd` (optional): execution cwd already relevant to the task; defaults to the MCP process cwd if absent.
- `critical_executables` (0-16): task-declared executable names/paths only.
- `task_env_delta` (0-32): task-supplied environment key/value pairs only.

Outputs never include raw cwd, raw PATH, resolved executable paths, or raw env-delta values. They include stable SHA-256 identities, shell family/version/architecture when resolvable, OS family/build, PATH fingerprint, and bounded executable identity.
## `diagnose_failure`

Use bounded facts from the failed boundary. Inputs may include:
- `exit_code`, `timed_out`, `post_condition`, and `native_process`;
- bounded `stdout_excerpt` / `stderr_excerpt` (maximum 4096 bytes each);
- explicit parser/binding, nested-command, literal-dollar, or Desktop-sandbox signals;
- expected/actual cwd SHA-256 identities;
- required/observed shell family and major/minor version;
- before/after executable-resolution SHA-256 identities.

Supported output classes:
- `QUOTING_EXPANSION`
- `CWD_PATH_IDENTITY`
- `SHELL_VERSION_MISMATCH`
- `NATIVE_PROCESS_OUTCOME`
- `TIMEOUT_CANCELLATION`
- `POST_CONDITION_MISMATCH`
- `ENVIRONMENT_STALENESS`
- `DESKTOP_SANDBOX_BOUNDARY`
- `UNKNOWN`

Output includes `confidence`, bounded evidence codes/details, and one conservative `next_action`. It does not echo supplied stdout/stderr excerpts.

## `verify_result`

Evaluate explicit deterministic post-conditions independently from `command_exit_code`.
Inputs:
- optional `command_exit_code`;
- optional `cwd` used only to resolve explicit relative check paths;
- `mode`: `all` (default) or `any`;
- 1-32 `checks`.

Supported check kinds:
- `file_exists`
- `file_absent`
- `directory_exists`
- `file_sha256`
- `file_size` with optional minimum/maximum byte bounds.

Outputs include `command_succeeded` (when an exit code was supplied), independent `task_succeeded`, and one result per check. Raw paths are not echoed; check results carry only a path SHA-256 plus bounded metadata/hash facts.

## Failure-only calling policy

A known-good first attempt with a passing required post-condition receives zero reliability intervention. The companion Skill may call these tools only after an eligible failure/failed post-condition or when verifying a repair before completion.

No structured tool result authorizes automatic privilege expansion or security weakening.
