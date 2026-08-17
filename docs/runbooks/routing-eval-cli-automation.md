# Routing evaluation CLI automation

This runbook automates repetitive routing-evaluation rows with the Codex CLI bundled with Windows Codex Desktop. It is a screening and train-execution aid; Windows Codex Desktop remains the product-admission runtime.

The runner uses one fresh disposable `CODEX_HOME`, one just-in-time opaque workspace, one output namespace, and one Codex process per row. Initial concurrency is 1. It does not mutate the live Codex configuration and it does not use the `codex` executable found on `PATH` unless that path is the separately frozen Desktop-bundled binary.

## Prerequisites

- Windows with the repository prerequisites installed.
- Codex Desktop installed and the exact bundled `codex.exe` path identified.
- The live Codex configuration already working with the intended model/provider.
- The exact Reliability MCP executable and companion Skill file available locally.
- A host-local coordinator/evidence directory outside the repository.
- A separate neutral runtime parent outside the coordinator/evidence ancestry. Its path must not encode S/M, case ids, routing labels, Skill/MCP names, or campaign purpose.
- One host-local campaign identity lock path outside the repository; both arms and every row use the same lock.

Keep provider tokens, authorization headers, raw JSONL, and temporary profiles outside the repository.

## Prepare an isolated campaign

For scored automation, pass an explicit neutral `--runtime-parent` instead of relying on the operating-system temporary-directory default:

```powershell
python .\benchmarks\harness\routing_eval.py prepare `
  --cases .\benchmarks\routing_eval\train_cases.json `
  --output-root <campaign-coordinator-root> `
  --runtime-parent <neutral-runtime-parent> `
  --trials 3 `
  --seed <frozen-seed>
```

Preparation writes `campaign.json`, `manifest.jsonl`, `prompts/`, and `fixtures/` under the coordinator root. It creates one empty opaque campaign runtime root under `--runtime-parent`, but it does **not** create any row workspace. The manifest binds each row to a unique 128-bit row token rendered as 32 lowercase hexadecimal characters. The model-visible workspace path therefore contains no arm, case, lane, evaluator, Skill/MCP, or campaign-purpose label.

Before the first row, verify the opaque runtime root is empty. While concurrency is 1, only the active row workspace may exist there.

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
  --identity-lock <campaign-coordinator-root>\campaign-identity.json `
  --initialize-identity-lock
```

Run the same command with `--arm M` but omit `--initialize-identity-lock`; the existing lock is mandatory. S must expose only `powershell-reliability`; M must expose no Skills. Both arms must expose exactly the same `psr_reliability_native` MCP command. The shared lock binds the actual CLI path/version/hash, Skill and MCP hashes, live-config hash, model/provider/reasoning/approval/sandbox identity, harness Git HEAD, and explicitly supplied public-main SHA; secret provider values are never stored in the lock.

A failed catalog, hash, ACL, config, or cleanup check blocks the run. Do not repair a profile in place and continue using it.

## Run one row

Execute one exact manifest row:

```powershell
pwsh.exe -NoProfile -File .\scripts\run-routing-automation.ps1 run-row `
  --arm M `
  --manifest <campaign-coordinator-root>\manifest.jsonl `
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
  --identity-lock <campaign-coordinator-root>\campaign-identity.json
```

The runner validates the coordinator prompt/fixture bindings and the frozen opaque runtime/workspace identities before model execution. The coordinator and runtime roots must be disjoint in both directions. The runtime root must be empty and the target workspace absent.

The runner then materializes only the current row from `fixtures/<case-key>.json`, verifies the exact UTF-8 fixture hash before Codex starts, creates the isolated arm profile, and runs Codex with `-C` set to the opaque row workspace. The prompt is read from the frozen manifest file and sent once through stdin; there is no follow-up steering.

After execution, deterministic workspace post-condition grading occurs **before** the row workspace is deleted. A task may fail its post-condition and still be a valid task-negative receipt. Profile cleanup and workspace cleanup are independent and both must pass; any cleanup failure blocks the campaign. On success, task failure, timeout, parser failure, or exception, the row workspace must be absent before another row begins and the runtime root must be empty again.

Raw CLI stdout JSONL and stderr remain under the host-local evidence root. Normalized receipts do not copy raw command/cwd/workdir strings. When already-emitted command metadata names the coordinator root or another frozen row workspace, the receipt sets `protocol_contamination=true` and stores only bounded `kind`, `command_id`, and `path_sha256` evidence. Such a row is protocol-invalid and the campaign stops for review.

## Non-scored leakage canary

Before any fresh scored CLI campaign or denominator, run one non-scored leakage canary through the exact automation path. This is required even when the row-isolation implementation is unchanged from the previous campaign. It must prove all of the following:

1. the model-visible cwd and its runtime ancestors contain no S/M, case, lane, Skill/MCP, evaluator, or campaign-purpose label;
2. the opaque runtime root contains exactly one active row during execution and is empty afterward;
3. no peer/future row workspace is pre-materialized;
4. coordinator manifest/prompts/fixtures/driver state/row evidence are outside runtime ancestry;
5. prompt, fixture, runtime identity, arm Skill catalog, and Reliability MCP identity checks pass;
6. `protocol_contamination=false`;
7. both `profile_cleanup_ok` and `workspace_cleanup_ok` are true.

The leakage canary is setup/protocol evidence only. Never include it in routing recall, false-activation, completion, token, latency, or S/M winner denominators. A failed canary blocks scored execution.

## Desktop confirmation boundary

Using the Desktop-bundled CLI for screening/train does not turn CLI evidence into Windows Codex Desktop product admission. Keep the exact bundled CLI/model/provider/reasoning/approval/sandbox identity frozen for a campaign, and require a fresh bounded Windows Codex Desktop confirmation after S/M selection before any default/recommended product claim.

## Evidence and cleanup

`--ephemeral` means the runner captures stdout JSONL directly; it does not wait for a session rollout file. Command/MCP attempts are paired by item id: `item.started` establishes an attempt and `item.completed` records its terminal outcome. A completion without a matching start is protocol-invalid. A timed-out row may preserve a valid JSONL prefix only when the final non-empty record is truncated; non-timeout or mid-stream malformed JSONL fails closed. Missing token fields remain `null` and are not synthesized. Each row also records `task_wall_clock_ms` around the Codex process.

At normal campaign completion or abort, verify the opaque runtime root is empty, remove that empty runtime root, and verify it is gone. Do not delete the coordinator/evidence root: its bounded receipts and raw evidence remain the campaign record.

Do not weaken ACLs, sandboxing, approval policy, PowerShell profiles, or global environment settings to force a run through.
