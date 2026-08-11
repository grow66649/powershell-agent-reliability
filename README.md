# PowerShell Agent Reliability

A Windows Codex Desktop reliability companion focused on diagnosing execution failures and verifying task outcomes without replacing Codex's own command runner.

## Product shape

- Core: local STDIO MCP server.
- Companion: thin Codex Skill that decides when to call the MCP.
- Distribution: plugin packaging only after the MCP + Skill workflow is proven.
- Default policy: first attempt stays native to Codex Desktop; reliability logic is failure-only.

## v0.1 scope

- Failure classification for quoting, cwd/path identity, shell/version mismatch, native outcome, timeout, post-condition mismatch, environment drift, and Desktop sandbox boundaries.
- Minimal environment identity, not full environment capture.
- Explicit task post-condition verification.
- Benchmarking Codex Desktop alone versus Codex Desktop + reliability assistance.

## Non-goals

- No replacement shell, terminal, sandbox, or generic process supervisor.
- No automatic ACL weakening, sandbox bypass, profile mutation, or global PowerShell changes.
- No generic provider/framework layer before a second real implementation needs one.
- No machine-specific task state, PR state, raw logs, or private evidence in this repository.

## Development state

This repository starts with contracts, sanitized fixtures, and design documents only. Product source code is admitted only after the benchmark and packaging gates are satisfied.
