# r4 Naturalistic Dataset and Desktop Campaign Design

Status: Owner-approved on 2026-08-14. Sealed validation, 12-turn non-scored timeout calibration, and the timeout freeze formula below are frozen for this campaign revision.

## Decision question

Given the accepted r4 S/M evaluator, which routing arm behaves better on natural Windows Codex Desktop tasks without overfitting to scorer internals?

- **S:** thin `powershell-reliability` companion Skill + the same Reliability MCP.
- **M:** companion Skill absent + the same Reliability MCP, established only by a supported reversible Desktop setup.

This campaign selects a routing shape. It does not by itself establish final product value; selected-arm shadow and the harder autonomous-Desktop-vs-Reliability recovery A/B remain downstream.

## Fixed authority and boundaries

The privacy-safe accepted baseline is `main@3ea553262d6d13462bde698a321b06d5db4d786c`.

The routing harness/contracts are accepted evaluator infrastructure. This slice does not change Rust product behavior, MCP schemas/descriptions, installed Skill behavior, Hook behavior, Codex security settings, release packaging, or scorer thresholds.

Codex Desktop/app-server remains the normal command/process/sandbox owner. Raw prompts, transcripts, full environments, credentials, and host-local evidence remain outside the repository.

## Dataset construction method

Use `naturalistic candidate pool -> human qualification -> provenance-cluster split -> seeded stratified freeze`.

Build about 48 candidates before scored trials: approximately 20 should-trigger, 20 should-not-trigger, and 8 boundary candidates. Taxonomy is a coverage audit, not a prompt-generation recipe. Do not derive prompts from scorer branches, Skill wording, MCP tool descriptions, historical S/M outcomes, or expected activation markers.

## Qualification and provenance isolation

Each candidate is reviewed before S/M outcome visibility. Reject only predeclared quality failures: ambiguous expected routing, flaky fixture, non-deterministic validation, unsafe setup, duplicate provenance, evaluator leakage, or broken privacy/sanitization.

A provenance cluster is the same root incident/template/fixture skeleton/error-marker family. Paraphrased or cosmetically varied siblings stay in one lane; they cannot cross train, validation, or holdout.

Freeze the 24-case core as:

- 10 `should_trigger`;
- 10 `should_not_trigger`;
- 4 `boundary`.

Freeze train=`6/6/2=14` and validation=`4/4/2=10`, with three fresh-thread repeats per arm. After all train-driven routing changes are frozen, create a fresh unseen holdout candidate pool and freeze holdout=`4/4/2=10`, also with three repeats per arm.

## Sealed validation firewall

Owner-approved policy: validation prompts, fixtures, expected routing, post-condition specifics, and provenance details remain sealed from any session allowed to modify Skill/MCP routing after train evidence until that routing revision is frozen.

The owner may review and approve validation before sealing. A train-driven routing session sees only train material. Validation results evaluate the frozen revision but may not tune that same revision. Any routing change after validation exposure requires a new isolated evaluation revision.

During train, the repository may contain train-visible artifacts only. Sealed validation content stays outside the train-visible repository surface under host-local evidence with a recorded hash. Sanitized validation/core material may be committed only after the validation evaluation is closed and publication of the cases cannot contaminate that evaluated revision.

Fresh holdout content remains outside the train/validation-visible repository surface until the candidate routing revision is frozen and the holdout is ready to run.

## Coverage matrix

Trigger coverage should include quoting/expansion, CWD/path identity, shell-version mismatch, native-process outcome, timeout/cancellation, post-condition mismatch, environment staleness, safe sandbox-boundary evidence when reproducible, UNKNOWN/insufficient-evidence behavior, and one frequency/risk-driven extra case.

If sandbox-boundary behavior cannot be reproduced safely without weakening protections, record a coverage gap rather than manufacturing the case.

No-trigger coverage mixes ordinary successful controls and controlled near-misses. Boundary cases are genuinely debatable routing situations and remain outside trigger-recall and no-trigger false-activation denominators.

## Case contract

Every scored case must be arm-neutral and compatible with `routing_eval.load_cases()` / `prepare_campaign()`.

Required harness-facing fields are `case_id`, `lane`, `group`, `prompt`, `boundary_detector`, optional `expected_first_command_fragment`, optional `files`, and `post_condition`.

Prompts describe the user's natural goal. They do not name Reliability, the Skill, the MCP, S/M arms, evaluator behavior, failure class labels, or expected activation.

Deterministic post-conditions validate observable requested world-state. They never use assistant prose or preferred repair steps as evidence. `tool_output_marker` pass/fail markers are distinct, frozen before execution, and unchanged by later model output.

Human-review metadata is kept in a separate review artifact so benchmark execution fields remain minimal. Review metadata includes provenance cluster, natural-task rationale, expected routing rationale, failure-family coverage, boundary rationale, deterministic success condition, leakage checks, safety/privacy checks, and reviewer decision.

## S/M setup canaries

Before any calibration or scored trial:

1. S canary proves the companion Skill is visible and the intended Reliability MCP is reachable on the exact target Desktop/runtime.
2. M canary proves the Skill is absent through a supported reversible configuration while the exact same Reliability MCP remains reachable.
3. Restore S and repeat the visibility/reachability check to prove reversibility.

If M cannot be established without renaming/moving Skill files, hiding catalog evidence, weakening unrelated security/global settings, or otherwise simulating absence, campaign status is `BLOCKED`.

Canaries are setup evidence only and never enter routing-performance denominators.

## Timeout calibration

Do not guess the scored timeout. After setup canaries, run a non-scored calibration set distinct from train/validation/holdout.

**Frozen calibration shape:** use three representative task shapes: ordinary no-trigger, eligible failure/repair, and a deliberately slower build/test-or-verification path. Run S and M with two fresh repeats each: 3 shapes x 2 arms x 2 repeats = 12 valid completed calibration turns.

Calibration uses the same Desktop build/model/effort/approval/sandbox/runtime identity planned for scored trials. A generous operational safety ceiling may stop hangs, but that ceiling is not the scored timeout and any hit blocks timeout freeze for review.

**Frozen timeout rule:** after 12 valid completed turns, freeze `T = ceil_to_30_seconds(2 * max(valid_calibration_turn_duration))`. Record all 12 durations and T before the first scored trial. The same T applies to S and M through train and validation.

If train later shows T structurally censors valid tasks, stop and create a new campaign revision. Never change T mid-validation or retroactively rescore prior trials.

## Scored trial interaction budget

Each scored trial gets exactly one natural user prompt. No manual follow-up hint, correction, steering message, or retry prompt is allowed. Codex Desktop may continue autonomous tool calls until natural completion or T. Tool-call count is measured as cost evidence; no separate arbitrary tool-call cap is introduced in this revision.

Every row uses a fresh Desktop thread and fresh disposable workspace. Matched S/M rows keep prompt hash, fixture hash, model, reasoning effort, approval policy, sandbox type, runtime identity, and originator consistent. Arm order is balanced using a recorded fixed seed.

## Validity, retries, and stopping

Setup failure detected before prompt submission is a setup abort, not a scored trial. After prompt submission, a routing miss, wrong repair, task failure, or timeout under the frozen policy is a valid outcome unless protocol evidence itself is corrupt.

Invalid examples include catalog mismatch/unobserved catalog, runtime identity drift, workspace/prompt mismatch, duplicate rollout identity, broken frozen first-command contract, or ambiguous deterministic post-condition evidence.

Validation and holdout scheduled attempts are not discretionarily retried. Missing valid evidence yields UNRESOLVED rather than selective resampling. Train diagnostic replays are allowed only when clearly marked non-scored.

Stop the frozen revision immediately on any valid pre-boundary Reliability MCP call, Reliability-caused wrong repair, Reliability-caused false completion, impossible M setup, systemic runtime-identity drift, or systemic collection/workspace/catalog mismatch. Do not performance-early-stop merely because recall or false activation looks poor; complete the frozen lane when safe so the case pattern remains inspectable.

## Human adjudication and owner review

Review occurs in two layers: outcome validity first, causal attribution second. Ambiguous causal attribution remains null/unresolved.

The owner reviews every core and holdout case, not just aggregate metrics. Pre-run review covers natural-task rationale, provenance cluster, expected routing, fixture, boundary detector, deterministic post-condition, leakage, safety/privacy, and reviewer decision. Post-run review presents S1/S2/S3 beside M1/M2/M3 validity, routing, task outcome, wrong repair, false completion, tokens/latency/calls, evidence pointers, anomalies, and case-level interpretation.

Three repeats of one case are stability evidence, not three independent problem types.

## Frozen gates and evidence boundary

Existing r4 gates remain unchanged: pre-failure MCP=`0`; Reliability-caused wrong repair=`0`; Reliability-caused false completion=`0`; validation+holdout eligible MCP-intervention recall `>=90%`; controlled near-miss false activation `<=5%`; production shadow false activation `<=1/100`; known-good/no-trigger median paired S idle-token delta versus M `<=+2%` with at least 90% paired token coverage.

Canary/calibration turns never enter recall, false-activation, token-cost, completion, or routing-winner denominators. Boundary cases remain descriptive/review-only for the frozen routing gates.

## Repository and sealed-evidence shape

During train authoring/evaluation, repository-visible additions are limited to sanitized train cases plus stable review/runbook artifacts. Validation and holdout prompts/fixtures stay sealed outside the train-visible repository until their evaluation boundary closes.

After validation closes, sanitized core material may be assembled at `benchmarks/routing_eval/core_cases.json` for reproducibility. Holdout material may be committed only after holdout scoring closes.

Raw Desktop rollout JSONL, exact session paths, runtime logs, private review notes, and calibration evidence remain host-local.

## Non-goals

- changing product Rust/MCP/Skill behavior in the dataset slice;
- tuning scorer thresholds from validation/holdout;
- hiding or simulating M-arm absence;
- using synthetic harness correctness as product-value evidence;
- replacing case-level owner review with one aggregate score;
- manufacturing sandbox failures by weakening protections.

## Acceptance

This design is implemented only after a task-by-task plan is reviewed. Dataset authoring is accepted when the frozen split/provenance rules, human review artifacts, canary/calibration procedure, and sealed-validation controls are demonstrably enforceable without leaking validation/holdout material.

Scored S/M execution starts only after S/M canaries pass, 12 valid calibration turns freeze T, the train/validation identities are recorded, and the owner confirms the sealed validation package remains uncontaminated.
