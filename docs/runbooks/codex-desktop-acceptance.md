# Codex Desktop Acceptance Runbook

Use this after the local Rust build/test gates pass. It validates the target Windows Codex Desktop runtime; standalone CLI output cannot substitute for this run.

## Preconditions

- Build `target/release/powershell-agent-reliability.exe` from the exact candidate commit.
- `cargo test`, `cargo check`, release build, lifecycle integration test, and `git diff --check` pass.
- The companion Skill and current MCP tool contract match the candidate commit.
- Record the exact candidate commit and release-binary SHA-256 before Desktop testing.
- Do not merge or make a runtime-readiness claim from this runbook until the required observations are complete.

## Temporary MCP configuration

Add a distinct test server entry to the user's Codex MCP config. Use the absolute release-binary path from the candidate worktree; do not overwrite another MCP entry.

```toml
[mcp_servers.psr_reliability_native]
command = "<ABSOLUTE_PATH_TO_RELEASE_EXE>"
args = []
```

Restart Codex Desktop normally if the running app does not reload MCP configuration dynamically. Do not change sandbox, ACL, approval, PowerShell profile, or global environment settings.

## Functional acceptance

In a fresh Codex Desktop thread, require real MCP tool discovery and calls. Shell/file simulation of expected responses is not evidence.

Verify all three tools are exposed:

1. `inspect_environment`
2. `diagnose_failure`
3. `verify_result`

Then call them with bounded deterministic inputs:

- `inspect_environment`: identify `powershell.exe` and the current workspace cwd; confirm the response is structured and does not expose raw PATH/cwd/resolved executable paths.
- `diagnose_failure`: use the synthetic fact `timed_out=true`; expected class is `TIMEOUT_CANCELLATION`.
- `verify_result`: check that the current workspace directory exists; expected `task_succeeded=true`.

Any unavailable tool, protocol error, malformed structured result, raw privacy leak, or simulated answer fails the functional gate.

## Lifecycle/resource observation

The repository currently has **no frozen numerical pass threshold** for retained-process count or memory. This section therefore defines a reproducible measurement sequence, not an invented acceptable-cost number.

Before starting, record an observation interval for post-close snapshots and keep that interval unchanged for the run. Also record the exact executable path used by every snapshot.

Use `benchmarks/harness/snapshot_mcp_processes.ps1 -ExecutablePath <ABSOLUTE_PATH_TO_RELEASE_EXE>` and preserve each JSON result. For at least three fresh Desktop threads:

1. capture a baseline snapshot before opening the thread;
2. open a fresh thread and complete the functional calls;
3. capture a snapshot while that thread owns the configured MCP;
4. close the thread normally without killing the candidate process;
5. capture an immediate post-close snapshot;
6. wait the pre-recorded observation interval, then capture the final snapshot.

For every snapshot, compare `count`, `aggregate_private_mb`, `aggregate_working_set_mb`, and the per-process PID/parent PID/start-time rows. A harness may clean up only processes it started itself; do not hide retained Desktop-owned processes during the observation sequence.

## Decision and reporting

- **Functional gate PASS:** real Windows Codex Desktop discovery and all three deterministic calls satisfy the checks above with no privacy leak or protocol failure.
- **Lifecycle evidence complete:** the full baseline/in-thread/immediate/final snapshot sequence exists for at least three fresh threads, uses one exact executable identity, and was not altered by manual process killing.
- **Resource threshold:** not frozen in this runbook. Report the measured count/memory deltas and retained-process pattern as observations. Do not translate "small", "acceptable", "material", or "negligible" into PASS/FAIL without a separately predeclared criterion.

If repeated final snapshots retain additional native processes relative to their baselines, report the accumulation pattern with the measured deltas. If a later review decides the cost needs an experiment, test a bounded self-idle/respawn design only after proving Codex Desktop can transparently recreate the STDIO server. Do not add a daemon or change transport merely to make the process count look cleaner.

A shared Streamable HTTP service would change lifecycle and security ownership and requires a separate architecture decision.

Only real Windows Codex Desktop evidence from the exact candidate can satisfy this runbook. Product-value claims still require the separate repeated end-to-end A/B evidence defined by the benchmark contracts.
