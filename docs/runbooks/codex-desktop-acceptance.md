# Codex Desktop Acceptance Runbook

Use this only after the local Rust build/test gates pass. It validates the target runtime without letting a standalone CLI substitute for Windows Codex Desktop.

## Preconditions

- Build `target/release/powershell-agent-reliability.exe` from the exact candidate commit.
- `cargo test`, `cargo check`, release build, lifecycle integration test, and `git diff --check` pass.
- The companion Skill and MCP tool contract match the candidate commit.
- Do not merge or claim product admission before this runbook is complete.

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
- `diagnose_failure`: use a synthetic fact `timed_out=true`; expected class is `TIMEOUT_CANCELLATION`.
- `verify_result`: check that the current workspace directory exists; expected `task_succeeded=true`.

Any unavailable tool, protocol error, malformed structured result, raw privacy leak, or simulated answer fails the functional gate.

## Lifecycle/resource acceptance

Before opening the test thread, take a read-only process snapshot with `benchmarks/harness/snapshot_mcp_processes.ps1` for the exact native executable.

After functional calls:
- record process count and per-process private/working-set memory;
- close the owning test thread normally;
- snapshot immediately after close and again after a short observation interval;
- repeat with at least three fresh threads.

Do not kill candidate processes during the observation period. A test harness may clean up only processes it started itself.
## Decision

- **PASS native runtime gate** when real Desktop discovery/calls work, resource cost is acceptable, and repeated thread lifecycle does not create unacceptable accumulation.
- If Desktop retains one native process per historical thread but the native idle cost is negligible, record it as an upstream lifecycle limitation and decide against adding a second daemon unless end-to-end evidence shows the retained cost is still material.
- If native process accumulation remains materially harmful, test an isolated self-idle/respawn experiment next. Do not implement or enable it without proving Codex Desktop can transparently respawn the STDIO server.
- Consider a shared Streamable HTTP service only if native STDIO remains unacceptable after those tests; that changes lifecycle/security ownership and requires a separate architecture gate.

Only after this runtime gate passes should the candidate be treated as ready for repeated end-to-end A/B admission trials.
