# AGENTS.md

## Scope

This repository contains the product-facing contracts, sanitized benchmarks, tests, and implementation for PowerShell Agent Reliability. Live project state belongs in the canonical task, not here.

## Development control plane

- Development is orchestrated from the ChatGPT Business web Project, which directly invokes Gateway MCP and RDC MCP.
- Gateway MCP owns canonical-task governance/CAS/receipts and governed development inspection/policy.
- RDC MCP owns ordinary Windows filesystem, workspace, shell, process, Git, build, test, log, and post-condition work.
- Windows Codex Desktop is the product target runtime and real acceptance surface only; it is not this project's development control plane.
- Standalone Codex CLI is not the development control plane and is only secondary compatibility evidence.

## Core product boundary

- Target runtime: Windows Codex Desktop.
- In the product runtime, Codex Desktop/app-server remains the command/process owner.
- Do not build a second generic shell executor, terminal, sandbox, or process manager unless a benchmark-approved gap proves it necessary.
- Product value is failure diagnosis, minimal environment identity, post-condition verification, and failure-only recovery guidance.

## Engineering rules

- Reuse-first: existing repo code -> standard/platform capability -> existing dependency -> mature OSS -> minimum new code.
- Use TDD for behavior changes. Preserve RED evidence for regressions.
- Keep changes one-purpose and reviewable.
- Every success claim requires an observable post-condition, not only exit code 0.
- Keep command outcome and task outcome separate.
- Prefer structured argv/typed fields over shell command-string concatenation.
- Do not create a universal Windows/PowerShell escape function. Add a narrow adapter only for a proven boundary with fixtures.

## Safety and privacy

- Never weaken Codex sandbox, Windows ACLs, security policy, or approval behavior as an automatic recovery step.
- Never mutate the user's PowerShell profile or global environment as a default action.
- Never persist credentials, tokens, cookies, browser storage, full PATH, complete environment dumps, or unrelated software inventory.
- Test mutations must use disposable locations and verify cleanup.
- Treat `EPERM`, `Access denied`, Windows sandbox helper errors, and ACL/setup failures as environment-boundary evidence until proven otherwise.

## Repository hygiene

- Do not write canonical-task stage, next action, worker assignment, PR/CI state, one-time analyzer results, or host-specific evidence paths into product files.
- Raw machine evidence stays outside the repository.
- Stable product contracts and sanitized reproducible fixtures may be committed.
- `.worktrees/` must remain ignored before linked worktrees are created.

## Development tools

- ChatGPT Business web is the controlling development surface; it calls Gateway and RDC according to the ownership split above.
- Do not route ordinary RDC-native host work through Gateway merely for uniformity.
- CodeGraph/Serena are advisory for symbol/reference/blast-radius inspection and must operate on the exact current worktree/index.
- Ponytail/reuse-YAGNI policy may be pulled before nontrivial implementation slices; it never overrides validation, security, recovery, or required compatibility.

## Acceptance

Before commit/PR for implementation work, run the smallest focused regression check plus the repo-wide check/build commands defined once a tech stack is selected, and always run `git diff --check`.
