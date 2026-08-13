# PowerShell Reliability MCP Tool Contract v0.2

This contract defines the bounded agent-facing surface of the local STDIO Reliability server. Codex Desktop/app-server remains the command, process, sandbox, and approval owner.

## Common invariants

- Server identity: `powershell-agent-reliability`.
- Transport: local STDIO.
- Public tools remain exactly `inspect_environment`, `diagnose_failure`, and `verify_result`.
- Input and output JSON Schemas expose agent-facing nested structures directly rather than relying on unresolved nested references.
- Tool outputs use structured content and reject unknown input fields.
- No tool is a generic shell/process runner, repair engine, daemon, session manager, or network transport.
- No tool mutates profiles, global environment, ACLs, sandbox settings, approvals, registry, services, or unrelated files.
- Command outcome and task post-condition remain separate facts.
- Missing evidence stays missing; `UNKNOWN` is valid.
- Tool annotations are advisory metadata, not authorization or security enforcement.

### Same-process concurrency

The accepted v0.1 concurrency boundary remains unchanged: stateless per-request handling, correctly paired request IDs/results, and bounded blocking filesystem work for inspection/verification without starving synchronous diagnosis. Concurrency does not authorize new orchestration infrastructure.

## `inspect_environment`

Use only after an observed failure when shell, cwd, PATH resolution, or a task-declared executable identity can causally matter. Do not call for known-good success or a pure command/post-condition disagreement that has no identity uncertainty.

Inputs remain bounded to the task-relevant shell executable, cwd, critical executables, and task env delta. Outputs remain privacy-bounded: no raw PATH, resolved executable paths, raw cwd, or raw env-delta values are returned.

Executable metadata fields use `executable_file_version` to mean the executable file/PE metadata version. This field is not a PowerShell engine version. Actual PowerShell engine/capability evidence is caller-observed and supplied to diagnosis through `ShellObservation.family`, `major`, and `minor`; the MCP does not spawn PowerShell to discover engine version.

## `diagnose_failure`

Diagnosis consumes only bounded facts already observed at the failed boundary. It does not inspect the environment itself and does not accept a raw cwd in this contract.

Supported classes remain unchanged:
- `QUOTING_EXPANSION`
- `CWD_PATH_IDENTITY`
- `SHELL_VERSION_MISMATCH`
- `NATIVE_PROCESS_OUTCOME`
- `TIMEOUT_CANCELLATION`
- `POST_CONDITION_MISMATCH`
- `ENVIRONMENT_STALENESS`
- `DESKTOP_SANDBOX_BOUNDARY`
- `UNKNOWN`

Specific supported causal evidence outranks generic command/task outcome disagreement. Explicit sandbox/timeout, resolution drift, cwd mismatch, shell mismatch, quoting evidence, or native non-zero outcome determines the class when present. If command exit status and the explicit task post-condition also disagree, that disagreement remains additional evidence. `POST_CONDITION_MISMATCH` is the fallback only when no stronger supported causal signal exists.

Output includes confidence, bounded evidence, and one conservative `next_action`. It never echoes supplied stdout/stderr excerpts.

## `verify_result`

`verify_result` is final deterministic post-condition verification, not an exploratory retry loop. It evaluates 1-32 explicit checks independently from optional `command_exit_code`; supported check kinds and the 64 MiB `file_sha256` bound remain unchanged from v0.1.

Raw check paths are not echoed. Each result reports only bounded metadata such as path SHA-256, existence/type, size, hash, status, and error kind where applicable.

## Tool routing metadata

All three public tools are declared read-only and closed-world with truthful hints:
- `readOnlyHint=true`
- `openWorldHint=false`

Descriptions state both positive and important negative triggers. In particular, environment inspection is not a default intermediate step for pure post-condition mismatch.

## Failure-only calling policy

- Before the first execution attempt: zero Reliability intervention.
- Known-good command outcome plus passing task post-condition: zero Reliability intervention.
- Pure command/post-condition disagreement: diagnose directly; do not inspect environment unless identity evidence can causally matter.
- At most one evidence-backed repair is permitted in one Reliability intervention.
- After repair, run one deterministic final `verify_result` against criteria frozen before repair.
- Never weaken verification criteria or derive expected values from repaired candidate output.

No structured result or annotation authorizes privilege expansion, security weakening, global configuration mutation, or a second command/process ownership layer.
