# AGENTS.md

## Scope

These instructions apply to code agents working in this repository. Keep repository changes portable and reviewable; do not depend on maintainer-local task systems, private orchestration tools, or host-specific evidence paths.

## Product boundary

- Target runtime: Windows Codex Desktop.
- Codex Desktop/app-server remains the normal command, process, sandbox, and approval owner.
- Standalone Codex CLI is supporting compatibility/evaluation evidence only unless a task explicitly concerns CLI behavior; it does not replace Desktop product acceptance.
- The product is a thin failure-only companion Skill plus a local STDIO Reliability MCP.
- Do not add a generic shell executor, terminal, second sandbox, process manager, universal quoting engine, daemon, or broad telemetry layer without a demonstrated product gap.
- Reliability is for bounded failure diagnosis, minimal environment identity, deterministic post-condition verification, and conservative recovery guidance.

## Engineering rules

- Reuse existing repository and platform capabilities before adding code or dependencies.
- Keep changes one-purpose and reviewable.
- Use TDD for behavior changes where practical; preserve a regression test for fixed behavior.
- Keep command outcome and requested task outcome separate.
- Every completion claim should have an observable post-condition when the task defines one.
- Prefer structured arguments and typed fields over nested shell command-string concatenation.
- Do not create a universal Windows/PowerShell escaping function. Add only narrow handling for a reproduced boundary.

## Safety and privacy

- Never weaken Codex sandboxing, Windows ACLs, approval policy, PowerShell profiles, or global environment settings as an automatic recovery step.
- Never persist credentials, tokens, cookies, browser storage, full PATH, complete environment dumps, or unrelated software inventory.
- Test mutations must use disposable locations and verify cleanup.
- Treat `EPERM`, `Access denied`, Windows sandbox-helper errors, and ACL/setup failures as environment-boundary evidence until proven otherwise.

## Repository and documentation hygiene

- Keep raw machine evidence and private maintainer state outside the repository.
- Commit only stable product docs, sanitized reproducible fixtures, tests, and implementation needed by the public project.
- Use [`docs/README.md`](docs/README.md) to distinguish current contracts/runbooks from historical plans.
- Do not rewrite a dated development plan to make it look like a current product contract.
- Keep `.worktrees/` ignored before creating linked worktrees.

## Acceptance

Before commit or PR, run the smallest focused checks for the change, then:

```powershell
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
git diff --check
```

For Desktop-facing changes, use the applicable current runbook and preserve actual Desktop evidence. Do not simulate Desktop acceptance with standalone CLI output.
