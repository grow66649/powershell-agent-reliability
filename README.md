# PowerShell Agent Reliability

PowerShell Agent Reliability is an experimental companion for maintainers and operators using **Windows Codex Desktop** on PowerShell or native-command tasks. It adds bounded failure diagnosis, privacy-limited environment identity, and deterministic post-condition checks after an eligible failure. Codex Desktop/app-server remains the command, process, sandbox, and approval owner.

> **Experimental / pre-release.** This repository is not a stable or production-ready release. The MCP and evaluation harness have automated test coverage, but the practical S-vs-M routing choice and repeated end-to-end Codex Desktop value are still under evaluation.

The project is intentionally narrow. It does not provide a replacement terminal, generic process runner, second sandbox, universal quoting engine, automatic ACL/security weakening, PowerShell profile mutation, or broad machine telemetry.

## What it provides

```text
Windows Codex Desktop
  -> thin failure-only companion Skill
  -> local STDIO Reliability MCP
       -> inspect_environment
       -> diagnose_failure
       -> verify_result
```

The Rust MCP exposes exactly three public tools:

- `inspect_environment`: returns bounded shell/cwd/PATH/executable identity without returning raw cwd, raw PATH, or resolved executable paths.
- `diagnose_failure`: classifies bounded failure evidence with an explicit `UNKNOWN` fallback and one conservative next action.
- `verify_result`: checks explicit file/directory/hash/size post-conditions independently from command exit status.

The companion Skill source is [`skills/powershell-reliability/`](skills/powershell-reliability/). Its policy is failure-only: no Reliability intervention before the first eligible failure or a false explicit task post-condition.

## Prerequisites

The currently supported source-build path is for Windows and requires:

- Git;
- Rust `1.88+`;
- Python `3.14` for the current benchmark/evaluation harness;
- PowerShell 7 (`pwsh.exe`) for repository verification;
- Windows Codex Desktop for product-runtime acceptance.

There is no packaged installer or release artifact yet. Build the executable from source.

## Build and test from source

```powershell
git clone https://github.com/grow66649/powershell-agent-reliability.git
cd powershell-agent-reliability
cargo build --release
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
```

A successful release build produces:

```text
target/release/powershell-agent-reliability.exe
```

## Configure the local MCP

Codex reads local MCP configuration from the user's Codex `config.toml`. Add a distinct entry for this executable; do not overwrite an unrelated server entry.

First print the absolute path you just built:

```powershell
$binary = (Resolve-Path .\target\release\powershell-agent-reliability.exe).Path
$binary
```

Then add this table to `$HOME\.codex\config.toml`, replacing the placeholder with that absolute path. A TOML literal string avoids double-escaping Windows backslashes:

```toml
[mcp_servers.psr_reliability_native]
command = '<ABSOLUTE_PATH_TO_RELEASE_EXE>'
args = []
```

The repository does not modify Codex configuration automatically. Restart Codex Desktop if the running app does not pick up the configuration change.

## Install the companion Skill locally

For a user-local installation, copy the checked-in Skill directory into Codex's user Skill location:

```powershell
$skillParent = Join-Path $HOME '.agents\skills'
$skillSource = Join-Path (Get-Location) 'skills\powershell-reliability'
$skillDest = Join-Path $skillParent 'powershell-reliability'
New-Item -ItemType Directory -Force -Path $skillParent | Out-Null
if (Test-Path -LiteralPath $skillDest) {
    throw "Skill destination already exists: $skillDest"
}
Copy-Item -Recurse -LiteralPath $skillSource -Destination $skillDest
```

This copies only the repository's `powershell-reliability` Skill. If Codex Desktop does not show the new Skill immediately, restart it.

## Verify in Windows Codex Desktop

Use a fresh Desktop thread. Verify that:

1. the observed Skill catalog contains `powershell-reliability`;
2. the configured MCP exposes exactly `inspect_environment`, `diagnose_failure`, and `verify_result`;
3. real MCP calls, not shell/file simulations, satisfy the deterministic checks in [`docs/runbooks/codex-desktop-acceptance.md`](docs/runbooks/codex-desktop-acceptance.md).

Standalone Codex CLI behavior is supporting compatibility evidence only. It does not replace Windows Codex Desktop acceptance.

## Remove the local setup

To remove the MCP, delete only the `[mcp_servers.psr_reliability_native]` table that you added to `$HOME\.codex\config.toml`.

If you used the copy command above, remove only that copied Skill directory:

```powershell
$skillDest = Join-Path $HOME '.agents\skills\powershell-reliability'
Remove-Item -Recurse -Force -LiteralPath $skillDest
```
Restart Codex Desktop after removing configuration or Skill files.

## Documentation

Start with [`docs/README.md`](docs/README.md) for the map of current contracts, runbooks, and historical development plans.

For runtime setup and acceptance, see [`docs/runbooks/codex-desktop-acceptance.md`](docs/runbooks/codex-desktop-acceptance.md). For controlled routing evaluation, see [`docs/runbooks/routing-eval-desktop.md`](docs/runbooks/routing-eval-desktop.md).

## Evidence boundary

Synthetic fixtures, unit tests, local STDIO lifecycle checks, and the routing harness demonstrate component and evaluator behavior. They do not by themselves prove that Reliability improves real Codex Desktop outcomes.

The evaluation work therefore keeps these questions separate:

- build and harness correctness;
- controlled S-vs-M routing behavior;
- selected-arm normal-turn shadow behavior;
- repeated autonomous Desktop recovery versus Reliability-assisted recovery.

Public claims should stay within evidence collected for the relevant stage.

## Privacy and safety

The MCP intentionally avoids returning full PATH/environment dumps or unrelated machine inventory. Raw Codex Desktop rollouts, exact session paths, credentials, and host-local evidence stay outside the repository unless a separately reviewed sanitized artifact is required for reproducibility.

Do not weaken Windows ACLs, Codex sandboxing, approval policy, PowerShell profiles, or global environment settings merely to make a test pass.

## Contributing and security

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the public contribution workflow and [`SECURITY.md`](SECURITY.md) for vulnerability-reporting guidance.

## License

Licensed under the [MIT License](LICENSE).
