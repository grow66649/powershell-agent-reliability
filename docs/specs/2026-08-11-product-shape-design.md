# PowerShell Agent Reliability Product Shape Design

Status: Approved by project owner on 2026-08-11.

## Problem

Windows Codex Desktop can already execute commands through its own app-server/command runner. The remaining reliability gap is not "how to launch a process" but how to identify execution-context mistakes quickly, avoid incorrect repair branches, and verify that the requested task actually completed.

## Product shape

The product is MCP-first:

```text
Codex Desktop
  -> Companion Skill (failure-only calling policy)
  -> local STDIO PowerShell Reliability MCP
       -> inspect_environment
       -> diagnose_failure
       -> verify_result
```

Plugin packaging is a later distribution layer after real A/B evidence proves value. The exact package form (Skill plus MCP server versus Skill plus app/app template) must be revalidated against the then-current Codex plugin format before release.

## Ownership boundary

Codex Desktop/app-server owns command execution, process lifecycle, sandboxing, approvals, and normal task orchestration.
PowerShell Reliability owns only bounded reliability evidence and interpretation: failure classification, minimal environment identity, task post-condition verification, and recovery guidance.

The MCP must not duplicate a generic command runner in v0.1. A future execution helper is admitted only when an end-to-end benchmark proves a specific app-server gap that cannot be handled through existing Codex execution.

## v0.1 MCP surface

### `inspect_environment`
Return a minimal, privacy-bounded execution identity needed to detect shell/cwd/executable-resolution drift. Do not return the full environment or full PATH.

### `diagnose_failure`
Consume structured observed facts and return a bounded classification, supporting evidence, confidence, and next diagnostic/recovery action. Return `UNKNOWN` when evidence is insufficient.

### `verify_result`
Evaluate an explicit task-supplied post-condition or a small set of deterministic validators and return task outcome independently of command exit status.

## Explicit non-goals

- universal quoting/escaping engine;
- replacement PowerShell or terminal;
- replacement Codex sandbox/approval layer;
- automatic ACL/security changes;
- global PowerShell profile/environment mutation;
- generic plugin framework/provider registry;
- broad machine inventory or telemetry collection.

## Quoting strategy

Do not create a universal `escapePowerShellCommand()` function.
Prefer structured executable + argv for native programs. For actual PowerShell code, prefer an explicit script boundary over nested `-Command` string construction. Treat cmd/batch and other application parsers as separate boundaries. Add a narrow quoting adapter only when a reproducible fixture proves a specific boundary needs one.

## Desktop sandbox boundary

`EPERM`, `Access denied`, Windows sandbox helper failures, `CreateProcessAsUserW` failures, protected WindowsApps ACL failures, and similar evidence are classified as Desktop/environment boundaries until proven otherwise. The MCP must not "fix" them by weakening the sandbox or security configuration.

## Failure-only policy

The first Codex Desktop attempt remains unchanged. Reliability analysis is invoked only after a bounded failure trigger or failed post-condition. Known-good successful first attempts must receive no reliability intervention.

## Reuse strategy

Reuse Codex app-server execution semantics rather than duplicating them. Use standard platform APIs for hashes/path identity and structured process argument representations. Evaluate official MCP SDKs for the server implementation. Consider CliWrap only if a later benchmark proves an independent process-launch fallback is required. Use PSScriptAnalyzer only as optional static preflight for actual PowerShell script content; it is not a runtime diagnosis engine.

## Distribution path

1. Local STDIO MCP prototype.
2. Thin Codex companion Skill that teaches failure-only use.
3. Real Codex Desktop repeated A/B benchmark.
4. If admitted, package MCP + Skill as a plugin/distribution unit.

## Acceptance authority

Synthetic fixtures prove components, not product value. Product value is accepted only by repeated Codex Desktop A/B evidence defined in `docs/contracts/benchmark-contract.md`.
