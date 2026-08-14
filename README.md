# PowerShell Agent Reliability

PowerShell Agent Reliability is an experimental Windows Codex Desktop companion for diagnosing eligible PowerShell/native-command failures, exposing privacy-bounded environment identity, and checking deterministic task post-conditions. Codex Desktop/app-server remains the normal command, process, sandbox, and approval owner.

> **Experimental / pre-release.** The repository has accepted local harness/build evidence, but S-vs-M routing value, production shadow behavior, and harder end-to-end product value are still under evaluation. It is not a stable or production-ready release.

## Architecture

```text
Codex Desktop
  -> thin failure-only companion Skill
  -> local STDIO Reliability MCP
       -> inspect_environment
       -> diagnose_failure
       -> verify_result
```

The native Rust MCP exposes exactly three public tools:

- `inspect_environment`: returns privacy-bounded shell, cwd, PATH, and executable identity without returning raw cwd/PATH/resolved paths.
- `diagnose_failure`: classifies evidence against the approved failure taxonomy with an explicit `UNKNOWN` fallback and one conservative next action.
- `verify_result`: checks explicit file/directory/hash/size post-conditions while keeping command success separate from task success.

The companion Skill source is `skills/powershell-reliability/`. It is intentionally failure-only: Reliability should not intervene before a first eligible failure or a false explicit post-condition.

## Scope and non-goals

This project is a bounded reliability layer, not a replacement execution stack. It does **not** provide a generic shell/terminal/process runner, replacement sandbox, universal quoting engine, automatic ACL/security weakening, PowerShell profile/global-environment mutation, or broad machine telemetry.

## Prerequisites

The currently verified source-build path targets Windows and uses:

- Rust `1.88+`;
- Python `3.14` for the current benchmark harness;
- PowerShell 7 (`pwsh.exe`) for the documented verification command.

From the repository root:

```powershell
cargo build --release
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
```

The release executable is:

```text
target/release/powershell-agent-reliability.exe
```

## Local Codex Desktop use

Configure Codex Desktop through its supported MCP settings to launch the release executable as a local STDIO server. This repository does not install, rewrite, or silently mutate Codex configuration.

Make `skills/powershell-reliability/` available through the supported Codex Desktop Skill workflow. Keep the intended failure-only boundary: no Reliability intervention before a first eligible failure or a false explicit task post-condition.

For the bounded local acceptance procedure, see [`docs/runbooks/codex-desktop-acceptance.md`](docs/runbooks/codex-desktop-acceptance.md). Use your own local repository path rather than copying a maintainer-specific absolute path.

## Evidence and benchmark boundary

Synthetic fixtures, unit tests, local STDIO lifecycle checks, and the routing harness demonstrate component and evaluator behavior only. They do not by themselves prove that Reliability improves real Codex Desktop outcomes.

The project therefore separates:

- harness/build correctness;
- controlled S-vs-M routing evaluation;
- selected-arm normal-turn shadow behavior;
- harder repeated autonomous Desktop recovery A/B product-value evidence.

Public claims should stay within the evidence actually collected for the relevant stage.

## Privacy and safety boundary

The MCP intentionally avoids returning full PATH/environment dumps or unrelated machine inventory. Raw Codex Desktop rollouts, exact session paths, credentials, and host-local evidence stay outside the repository unless a separately reviewed sanitized artifact is required for reproducibility.

Do not weaken Windows ACLs, Codex sandboxing, approval policy, PowerShell profiles, or global environment settings merely to make a test pass.

## Contributing and security

See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the development workflow and [`SECURITY.md`](SECURITY.md) for conservative vulnerability-reporting guidance.

## License

Licensed under the [MIT License](LICENSE).
