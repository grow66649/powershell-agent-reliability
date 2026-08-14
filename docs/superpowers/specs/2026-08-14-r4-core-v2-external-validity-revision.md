# r4 Core v2 External-Validity Revision Design

Status: Owner-approved direction on 2026-08-14. This revision replaces the unapproved v1 24-case freeze; it does not authorize S/M canaries or scored trials.

## Goal

Revise the naturalistic controlled core so it tests real Windows/Codex reliability behavior rather than benchmark-shaped prompts, while preserving the approved 24-case scale, sealed validation, provenance isolation, and S/M comparison contract.

## Evidence basis

The revision applies four external-validity lessons: realistic end-to-end tasks with execution-based checks; explicit checks for broken/ambiguous tasks and scorer shortcuts; equivalent harness/budget across compared systems; and repeated trials as reliability evidence rather than independent task count.

PowerShell case families must be grounded in documented Windows/PowerShell behavior or reproducible local fixtures. Current examples include command/PATH resolution, PowerShell 5.1 vs 7 behavior, wildcard/LiteralPath semantics, native exit-code semantics, timeout/cancellation, cwd identity, parser/binding failures, and deterministic post-condition disagreement.

## Fixed boundaries

- Final accepted harness/main base: `3ea553262d6d13462bde698a321b06d5db4d786c`.
- Dataset implementation parent: `f608315c10bda7ca5dc0467bfa2ba6c152499511`.
- S=`thin companion Skill + same Reliability MCP`; M=`Skill absent + same Reliability MCP`.
- No Rust/MCP/Skill behavior, scorer threshold, Hook, Codex security setting, release, or publication change in this revision.
- Validation remains sealed from any later train-driven routing-modification session.
- This Leader/research session has seen validation and may revise dataset validity only; it may not tune Skill/MCP routing after train evidence.

## v2 case-quality requirements

1. Keep the controlled core at `24 = 10 should_trigger / 10 should_not_trigger / 4 boundary` unless a later owner decision changes the experiment size.
2. Every scored prompt states the user goal and necessary constraints, not the desired agent workflow. Remove coaching such as `if it fails, recover`, `repair only`, `diagnose`, or `verify before finishing` unless that wording is itself the natural user request being tested.
3. The selected trigger set must contain a direct command/PATH-resolution failure. Process-local environment state alone does not satisfy this requirement.
4. The selected no-trigger set must contain a real native/domain non-zero-success convention. Prefer documented Robocopy semantics over a custom wrapper that returns an artificial success code.
5. At least one successful first-attempt task containing prior/conditional failure language and one historical-failure/no-current-execution task must be scored as hard `should_not_trigger` controls so premature Reliability activation affects false-activation results.
6. Artifact-producing tasks require a mechanical post-condition whenever practical. `post_condition=none` is limited to explanation, diagnosis-only, or UNKNOWN cases and requires an explicit review rationale.
7. Do not manufacture sandbox/ACL failures by weakening security. If a safe reproducible Desktop sandbox case is unavailable, record the gap.
8. A selected sibling represents one parser/binding subtype only; do not claim both parser and binding coverage from one case.

## Candidate and provenance rules

Start from the existing pre-outcome 48-candidate pool as source material, not as an approved dataset. Reword benchmark-shaped prompts and add or replace only candidates needed to satisfy the requirements above. New/revised cases must be reviewed before any S/M result is visible.

Keep provenance clusters intact across train/validation/holdout. Selection must be deterministic from a recorded integer seed and must satisfy group quotas plus required coverage. If candidate revisions change group membership, the selection procedure must solve quotas explicitly rather than silently assuming one fixed group per cluster.

The owner-review artifact must show, for every proposed core case: plain-language purpose, natural-task rationale, provenance cluster, group/lane, failure family, fixture summary, expected first command when frozen, boundary detector, mechanical post-condition or reason none is valid, anti-coaching check, leakage check, and safety/privacy check.

## Metric placement

`should_trigger` and `should_not_trigger` remain the primary routing denominators. Boundary rows stay descriptive/review-only only when the expected activation is genuinely debatable. A difficult negative must not be moved to `boundary` merely to avoid penalizing false activation.

Three repeats remain stability evidence. Report case-level 0/3..3/3 behavior and do not treat the repeats as three independent problem types.

Train can motivate a separately reviewed routing revision. Validation evaluates only the frozen revision. Fresh holdout remains unseen until train-driven changes freeze. The selected-arm >=300-turn shadow and later harder autonomous Desktop A/B remain the breadth/product-value layers; the controlled core should prioritize quality over quantity.

## v2 owner gate

This revision may create a new host-local candidate pool and proposed 24-case review package, but must stop before committing train cases, revealing validation to a routing-modification worker, or running S/M canaries. The owner approves/rejects the v2 24-case package after seeing a plain-language old-vs-new change summary.

## Acceptance

The v2 proposal is ready for owner review only when machine checks confirm quotas, provenance isolation, review completeness, anti-coaching rules, required direct command-resolution and semantic-nonzero coverage, hard-negative placement, deterministic post-condition policy, and zero S/M outcome visibility during candidate qualification.