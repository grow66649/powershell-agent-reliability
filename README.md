# PowerShell Agent Reliability

A failure-only Windows Codex Desktop reliability companion. It adds bounded environment identity, conservative failure classification, and deterministic task-result verification without replacing Codex Desktop's command runner.

## Product shape

```text
Codex Desktop
  -> thin companion Skill
  -> local STDIO PowerShell Reliability MCP
       -> inspect_environment
       -> diagnose_failure
       -> verify_result
```

Codex Desktop/app-server remains the command/process/sandbox/approval owner. Plugin packaging remains a later distribution decision after repeated Desktop A/B evidence proves net value.

## Current implementation

The native Rust MCP uses the official Model Context Protocol Rust SDK (`rmcp = 3.1.2`) and exposes exactly three public tools:

- `inspect_environment`: privacy-bounded shell/cwd/PATH/executable identity; raw cwd/PATH/resolved paths are not returned.
- `diagnose_failure`: structured classification across the approved failure taxonomy with explicit `UNKNOWN` fallback and one conservative next action.
- `verify_result`: explicit file/directory/hash/size post-condition checks with command success kept separate from task success.
The companion Skill source lives at `skills/powershell-reliability/` and enforces failure-only invocation: successful first attempts with passing post-conditions receive no reliability intervention.

## Build and test

```powershell
cargo test
cargo check
cargo build --release
cargo test --release --test lifecycle -- --nocapture
```

The release server is `target/release/powershell-agent-reliability.exe` on Windows. Build artifacts remain ignored and are not committed.

The repository intentionally does not install or mutate Codex configuration automatically. Desktop integration is an explicit acceptance step after local build/test gates pass.

## Benchmark harness

- `benchmarks/harness/run_baseline.py`: reproduces the sanitized synthetic failure fixtures.
- `benchmarks/harness/measure_stdio_mcp.ps1`: measures local STDIO initialize/list readiness, idle process memory, and owned-process cleanup.
- `benchmarks/harness/snapshot_mcp_processes.ps1`: takes a read-only exact-executable process/memory snapshot for Desktop lifecycle observation.
- `benchmarks/harness/score_ab.py`: scores user-supplied A/B JSONL run records while preserving missing metrics as missing.

Synthetic/local evidence proves components only. Product admission still requires repeated representative Windows Codex Desktop A/B trials under `docs/contracts/benchmark-contract.md`.

## Non-goals

No replacement shell/terminal/sandbox, generic process executor, automatic ACL/security weakening, profile/global-environment mutation, universal quoting engine, or broad machine telemetry.
