# Routing evaluation CLI automation

This runbook automates repetitive routing-evaluation rows with the Codex CLI bundled with Windows Codex Desktop. It is a screening and train-execution aid; Windows Codex Desktop remains the product-admission runtime.

The runner uses one fresh disposable `CODEX_HOME`, workspace, output namespace, and Codex process per row. Initial concurrency is 1. It does not mutate the live Codex configuration and it does not use the `codex` executable found on `PATH` unless that path is the separately frozen Desktop-bundled binary.

## Prerequisites

- Windows with the repository prerequisites installed.
- Codex Desktop installed and the exact bundled `codex.exe` path identified.
- The live Codex configuration already working with the intended model/provider.
- The exact Reliability MCP executable and companion Skill file available locally.
- A host-local evidence directory outside the repository.

Keep provider tokens, authorization headers, raw JSONL, and temporary profiles outside the repository.

## Profile check

Run `profile-check` before model-bearing rows. It makes no model request. It verifies the exact CLI version/hash, Skill and MCP hashes, creates a temporary restricted profile, disables unrelated apps/plugins/Skills, and observes the final arm surface.

```powershell
pwsh.exe -NoProfile -File .\scripts\run-routing-automation.ps1 profile-check `
  --arm S `
  --live-config <live-config.toml> `
  --codex <codex-desktop-bundled.exe> `
  --codex-version 0.148.0-alpha.9 `
  --codex-sha256 <sha256> `
  --skill-path <powershell-reliability-SKILL.md> `
  --skill-sha256 <sha256> `
  --mcp-path <powershell-agent-reliability.exe> `
  --mcp-sha256 <sha256> `
  --evidence-root <host-evidence-root>
```

Run the same command with `--arm M`. S must expose only `powershell-reliability`; M must expose no Skills. Both arms must expose exactly the same `psr_reliability_native` MCP command.

A failed catalog, hash, ACL, config, or cleanup check blocks the run. Do not repair a profile in place and continue using it.

## Run one row

Prepare the campaign with the existing routing harness, then execute one exact manifest row:

```powershell
pwsh.exe -NoProfile -File .\scripts\run-routing-automation.ps1 run-row `
  --arm M `
  --manifest <campaign-root>\manifest.jsonl `
  --sequence 1 `
  --timeout 360 `
  --live-config <live-config.toml> `
  --codex <codex-desktop-bundled.exe> `
  --codex-version 0.148.0-alpha.9 `
  --codex-sha256 <sha256> `
  --skill-path <powershell-reliability-SKILL.md> `
  --skill-sha256 <sha256> `
  --mcp-path <powershell-agent-reliability.exe> `
  --mcp-sha256 <sha256> `
  --evidence-root <host-evidence-root>
```

The prompt is read from the frozen manifest file and sent once through stdin. There is no follow-up steering. Immediately before profile/model execution, the runner re-hashes the actual UTF-8 text fixture tree and requires the manifest `fixture_sha256`; a stale or previously mutated workspace fails closed instead of being rerun. Raw CLI stdout JSONL and bounded stderr stay under the host-local evidence root. The temporary secret-bearing profile is deleted after the row.

The runner records command-process state separately from deterministic task outcome. Exit code 0 is not task success. A valid row with a failed workspace post-condition remains a task negative rather than an infrastructure retry.

## Parity before scored use

CLI automation does not replace Windows Codex Desktop evidence merely because the CLI version matches. Before CLI rows enter a scored train denominator, separately verify:

1. model/provider/reasoning/approval/sandbox identity;
2. S/M Skill catalog conformance and identical Reliability MCP identity;
3. one should-trigger and one no-trigger/known-good shape in both Desktop and CLI;
4. deterministic post-condition semantics;
5. CLI JSONL fields used for command, MCP, and token accounting.

Capability canaries may directly ask whether the Skill is available and may explicitly call the MCP. Those sessions are non-scored and are never reused as natural-task trials.

## Evidence and cleanup

`--ephemeral` means the runner must capture stdout JSONL directly; it must not wait for a session rollout file. Missing token fields remain `null` and are not synthesized. Each row also records `task_wall_clock_ms` around the Codex process. Compare time only across matched S/M rows with balanced order; keep valid slow rows and report unstable timing as inconclusive rather than forcing a winner.

A cleanup failure blocks the campaign. Do not weaken ACLs, sandboxing, approval policy, PowerShell profiles, or global environment settings to force a run through.
