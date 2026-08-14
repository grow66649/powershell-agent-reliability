# OSS Publication Hygiene Design

Status: Draft for owner review. MIT license choice is approved; no GitHub repository has been created or pushed.

## Goal

Prepare the privacy-safe reviewed experimental baseline for a truthful first public GitHub push without changing product behavior, benchmark results, or development history.

The source baseline is `main@2d9716655ccf8a034c307af21e499ea5a3ad9660` with public Git identity `jh06 <315192398+grow66649@users.noreply.github.com>`.

## Publication boundary

`main` means the current independently reviewed experimental public-maintenance baseline. It does not mean stable release, production maturity, recommended always-on activation, or proven product value.

This slice is public-surface hygiene only. It must not modify Rust product behavior, MCP schema/semantics, installed Skill behavior, routing datasets/results, scorer thresholds, Git history/refs, release tags, or application claims.

No public remote, push, release, or OpenAI application submission occurs in this slice.

## License

Use the standard MIT License with copyright holder `jh06` and year `2026`.

The repository README and contributing/security docs may refer to MIT licensing but must not add extra restrictions that conflict with the license text.

## README information architecture

The README must let an unfamiliar Windows maintainer understand the project before reading internal plans.
README sections, in order:

1. one-paragraph problem/target statement;
2. explicit `Experimental / pre-release` status;
3. architecture shape: `Codex Desktop -> thin failure-only Skill -> local STDIO Reliability MCP`;
4. supported scope and non-goals;
5. prerequisites for Windows source build;
6. build and local verification commands;
7. local MCP setup and companion-Skill usage at a high level without machine-specific paths;
8. evidence/benchmark boundary: harness correctness is not product-value proof;
9. privacy/safety boundary;
10. contribution and security-reporting pointers;
11. license.

README claims must be supported by current code/contracts. Do not claim users, downloads, dependents, production maturity, a security audit, broad adoption, or that this repository fixes upstream Codex bugs.

## CONTRIBUTING.md

Keep contribution guidance small and executable:

- target Windows Codex Desktop;
- read `AGENTS.md` for repo-local rules;
- one-purpose branches/changes;
- behavior changes require TDD;
- run focused tests plus `pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline` and `git diff --check`;
- preserve command-outcome vs task-post-condition separation;
- do not weaken sandbox/ACL/security settings or add a generic runner;
- do not include raw host evidence, secrets, full environment dumps, or unrelated machine data.

Do not require a CLA or contributor bureaucracy in the first-publication slice.
## SECURITY.md

State the supported security-reporting boundary conservatively:

- do not publish exploit details in a normal issue;
- use GitHub private vulnerability reporting / Security Advisories when the public repository supports it;
- if no private channel is available, open only a minimal non-sensitive issue requesting a private contact path;
- do not claim the project has undergone a security audit;
- disclose the experimental/pre-release status and Windows Codex Desktop scope.

The publication checklist should enable private vulnerability reporting if GitHub exposes that repository setting.

## Windows CI

Add one minimal GitHub Actions workflow on `windows-latest`.

The workflow checks out the repository, installs a stable Rust toolchain and a current supported Python 3, then runs:

`pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline`

The workflow must not upload raw environment snapshots, Codex Desktop sessions, benchmark rollouts, credentials, or host-local evidence. It is source-build/test evidence only and must not be described as a real Desktop end-to-end test.

No release/upload/package-publish job belongs in this first workflow.

## Host-path and privacy cleanup

Replace the two known public-facing `D:/Work/...` literals in historical planning documents with portable placeholders such as `<repo-worktree>` while preserving the historical technical meaning.

Repeat a tracked-content and reachable-history privacy scan after the hygiene changes. The scan must cover the old private email/name strings, `C:\Users\GrowU`, host-specific `D:/Work/` literals, likely credential/token patterns, and accidental raw evidence/session paths.
## GitHub metadata and first-push policy

Repository name remains `powershell-agent-reliability` unless the owner changes it at the later publication gate.

Recommended description: experimental Windows Codex Desktop reliability companion for failure diagnosis and deterministic post-condition verification.

Recommended topics: `windows`, `powershell`, `codex`, `mcp`, `rust`, `developer-tools`, `reliability`.

First push is explicitly owner-gated and pushes only the reviewed privacy-safe `main`. Do not use `--all` or `--mirror`, and do not publish old worker/canary/history/backup refs or unapproved tags.

## First release policy

The first public push may have no release. Prove public CI and clean source-build/install instructions first.

A later first release, if owner-approved, should be clearly pre-release/experimental (for example `v0.x.y-alpha.1`). Do not backfill fake historical releases.

## Deferred items

Issue templates are optional until real issue traffic appears. PR templates, branch protection, CHANGELOG, packaging/binary distribution, and release automation are deferred until the public source workflow proves it needs them.

Do not add telemetry, hosted services, installers, badges with unverified status, or marketing claims solely for launch optics.

## Acceptance

The hygiene implementation passes only when exact changed paths stay within the approved public surface, full local verification passes, CI configuration is reviewable, privacy/path scans are clean or explicitly documented, README claims match current code/contracts, and an independent publication reviewer finds no blocker.

Only after that acceptance does the owner decide public repository creation, visibility, description/topics, private vulnerability-reporting setting, and first push.