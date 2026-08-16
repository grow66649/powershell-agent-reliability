# Routing evaluation CLI automation

This runbook automates repetitive routing-evaluation rows with the Codex CLI bundled with Windows Codex Desktop. It is a screening and train-execution aid; Windows Codex Desktop remains the product-admission runtime.

The runner uses one fresh disposable `CODEX_HOME`, workspace, output namespace, and Codex process per row. Initial concurrency is 1. It does not mutate the live Codex configuration and it does not use the `codex` executable found on `PATH` unless that path is the separately frozen Desktop-bundled binary.

## Prerequisites

- Windows with the repository prerequisites installed.
- Codex Desktop installed and the exact bundled `codex.exe` path identified.
- The live Codex configuration already working with the intended model/provider.
- The exact Reliability MCP executable and companion Skill file available locally.
- A host-local evidence directory outside the repository. The runner rejects a repository-internal evidence root.
- One host-local campaign identity lock path outside the repository; both arms and every row use the same lock.

Keep provider tokens, authorization headers, raw JSONL, and temporary profiles outside the repository.

## Profile check

Run `profile-check` before model-bearing rows. It makes no model request. It verifies the exact CLI version/hash, Skill and MCP hashes, creates a temporary restricted profile, disables unrelated apps/plugins/Skills, and observes the final arm surface. Campaign lock creation is an explicit one-time initialization: the first profile check must include `--initialize-identity-lock`. Ordinary later profile checks omit that flag and fail closed if the lock is missing; every later profile check and row must match the same existing lock.

```powershell
pwsh.exe -NoProfile -File .\scripts\run-routing-automation.ps1 profile-check `
  --arm S `
  --live-config <live-config.toml> `
  --codex <codex-desktop-bundled.exe> `
  --codex-version 0.148.0-alpha.9 `
  --codex-sha256 <sha256> `
  --model gpt-5.6-luna `
  --public-main-sha <exact-public-main-sha> `
  --skill-path <powershell-reliability-SKILL.md> `
  --skill-sha256 <sha256> `
  --mcp-path <powershell-agent-reliability.exe> `
  --mcp-sha256 <sha256> `
  --evidence-root <host-evidence-root> `
  --identity-lock <campaign-root>\campaign-identity.json `
  --initialize-identity-lock
```

Run the same command with `--arm M` but omit `--initialize-identity-lock`; the existing lock is mandatory. S must expose only `powershell-reliability`; M must expose no Skills. Both arms must expose exactly the same `psr_reliability_native` MCP command. The shared lock binds the actual CLI path/version/hash, Skill and MCP hashes, live-config hash, model/provider/reasoning/approval/sandbox identity, harness Git HEAD, and the explicitly supplied public-main SHA; secret provider values are never stored in the lock. The runner does not require a local `main` ref, so shallow PR CI and detached checkouts can still exercise the automation tests.

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
  --model gpt-5.6-luna `
  --public-main-sha <exact-public-main-sha> `
  --skill-path <powershell-reliability-SKILL.md> `
  --skill-sha256 <sha256> `
  --mcp-path <powershell-agent-reliability.exe> `
  --mcp-sha256 <sha256> `
  --evidence-root <host-evidence-root> `
  --identity-lock <campaign-root>\campaign-identity.json
```

The runner requires the prepared campaign layout: `<campaign-root>/prompts/<case-key>.txt` and `<campaign-root>/workspaces/<arm>/<case-key>`, with the campaign root outside the repository. `case-key` must be one safe path component; traversal/escaped campaign paths are rejected. The prompt is read from the frozen manifest file and sent once through stdin. There is no follow-up steering. Immediately before profile/model execution, the runner re-hashes the actual UTF-8 text fixture tree and requires the manifest `fixture_sha256`; a stale or previously mutated workspace fails closed instead of being rerun. Raw CLI stdout JSONL and stderr stay under the host-local evidence root. The evidence root must not equal or descend from the row workspace, so runner output cannot mutate a fixture after its pre-model hash check. The temporary secret-bearing profile is deleted after the row.

The runner records command-process state separately from deterministic task outcome. Exit code 0 is not task success. A valid row with a failed workspace post-condition remains a task negative rather than an infrastructure retry.

## Parity before scored use

CLI automation does not replace Windows Codex Desktop evidence merely because the CLI version matches. Before CLI rows enter a scored train denominator, separately verify:

1. the frozen campaign identity lock matches model/provider/reasoning/approval/sandbox, exact bundled CLI, Skill, MCP, harness HEAD, and public-main anchor;
2. S/M Skill catalog conformance and identical Reliability MCP identity;
3. four fresh non-scored capability sessions: Desktop-S, Desktop-M, CLI-S, CLI-M;
4. four natural cases (`TC-A`, `TT-A`, `NG-B`, `NW-A`) across Desktop-S/M and CLI-S/M, for 16 fresh natural sessions;
5. deterministic post-condition, command-failure-boundary, MCP-order, false-activation, and safety semantics agree closely enough for the reviewed parity rule;
6. CLI JSONL preserves started/completed command and MCP identities, terminal outcomes, timeout partial evidence, and exact token fields without inventing missing metrics.

Capability canaries may directly ask whether the Skill is available and may explicitly call the MCP. Those sessions are non-scored and are never reused as natural-task trials. Natural parity prompts must not name the Skill, MCP, arm, evaluator, or expected activation. If actual Skill read/activation cannot be observed reliably, keep that metric explicitly missing/`INCONCLUSIVE` rather than inferring it from catalog presence.

## Evidence and cleanup

`--ephemeral` means the runner must capture stdout JSONL directly; it must not wait for a session rollout file. Command/MCP attempts are paired by item id: `item.started` establishes an attempt, `item.completed` records its terminal outcome, and terminal `failed`/`declined` items are complete rather than incomplete. A command/MCP `item.completed` without a matching prior `item.started` is protocol-invalid and fails closed; it is never counted as an invocation. A timed-out row may preserve a valid JSONL prefix when only the final non-empty record is truncated; non-timeout or mid-stream malformed JSONL still fails closed. A non-timeout row without a terminal `turn.completed`/`turn.failed` event fails closed. Missing token fields remain `null` and are not synthesized. Each row also records `task_wall_clock_ms` around the Codex process. Compare time only across matched S/M rows with balanced order; keep valid slow rows and report unstable timing as inconclusive rather than forcing a winner.

A cleanup failure blocks the campaign. Do not weaken ACLs, sandboxing, approval policy, PowerShell profiles, or global environment settings to force a run through.
