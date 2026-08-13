# r4 Two-Arm Routing Evaluation Contract

## Purpose

This contract freezes the machine and human interface for evaluating two Windows Codex Desktop routing shapes. It proves harness behavior only; product-value admission still requires the later repeated Desktop recovery A/B.

Primary arms:

- S=`thin companion Skill + MCP`.
- M=`MCP-only self-routing`.
- Arm H is excluded for the current Desktop build.

Codex Desktop/app-server remains the normal command, process, sandbox, and approval owner. The harness is an evidence reader/scorer, not a command wrapper or second execution stack.

## Arm invariants

Matched S/M trials keep the same Desktop build, model, reasoning effort, approval policy, sandbox type, Reliability MCP candidate/tool schemas, fixture definition, prompt text, and measurement policy. The only declared routing difference is companion-Skill exposure.

S requires `powershell-reliability` to be observed in the Skill catalog. M requires it to be observed absent. A missing catalog is unresolved arm evidence and invalidates the trial.

If supported reversible Skill exclusion cannot establish M while leaving the same MCP candidate reachable, M setup is BLOCKED rather than simulated.

## Trial identity and pairing

One normalized trial is keyed by `(case_id, trial_id, arm)`. One matched pair is keyed by `(case_id, trial_id)` and contains one S row plus one M row.
The prompt is arm-neutral and contains only the neutral `[CASE-ID: ...]` marker plus task content. It must not name the Skill, Reliability MCP, routing arm, evaluator, or expected activation. `{workspace}` is forbidden because absolute per-arm paths would destroy prompt matching.

Each arm gets a fresh disposable workspace materialized from the same fixture definition. `fixture_sha256` must match across the pair; `workspace_sha256` must differ. Prompt and fixture hashes are deterministic identities, not substitutes for raw evidence.

## Boundary detectors

Supported `boundary_detector.kind` values are:

- `none` for deterministic no-trigger controls;
- `first_command_nonzero` for an observable non-zero first shell/native result;
- `tool_output_contains` for an exact sanitized marker in tool output.

The harness never infers an eligible boundary from assistant prose. Command outcome and deterministic task post-condition remain separate facts.

## Normalized record

Schema version 1 stores bounded evidence only. Required identity and environment fields include case/trial/arm, lane/group, sequence, rollout evidence pointer, session/build/model/effort/approval/sandbox identity, prompt/workspace/fixture hashes, and observed arm-catalog conformance.

Temporal fields include first-attempt start/end indexes, first command exit code, eligible-boundary kind/index/timestamp, Skill activation indexes/count, MCP intervention indexes/count, pre-boundary MCP count, S protocol bypass, and turn-complete index/timestamp.

Cost fields include the final host-exposed token snapshot when valid, optional monotonic phase-token deltas, total turn latency, boundary-to-Skill latency, and boundary-to-MCP latency.

Missing measurements remain missing. Missing token, latency, completion, or adjudication evidence is never coerced to zero.
## Validity versus negative outcome

Protocol breakage invalidates a trial; task failure does not. Examples of invalidity include duplicate trial identity, prompt/workspace mismatch, wrong or unobserved arm catalog, and failure to execute a manifest-frozen first command.

A protocol-conforming trial that fails to complete the task remains a valid negative outcome. Invalid trials are reported with reasons and stay outside routing-performance denominators.

For S, a pre-boundary Skill read is premature activation. An MCP intervention without any prior Skill read is S protocol bypass. For M, no Skill activation exists by construction.

For a no-trigger control, S false activation is any `powershell-reliability` Skill read or Reliability MCP use. M false activation is any Reliability MCP use.
## Automatic scoring denominators

Trigger recall uses actual post-boundary MCP intervention on valid `should_trigger` rows. S Skill-read recall is diagnostic only and cannot substitute for MCP intervention recall.

False activation uses valid `should_not_trigger` rows. `boundary` rows are reported separately and never enter recall or false-activation denominators.

Admission rates combine validation + holdout and also report validation and holdout separately. Train is descriptive/tuning evidence only and cannot rescue a failed admission gate.

Case stability reports repeated activation behavior without changing denominators. Invalid trials, missing measurements, collisions, latency distributions, MCP-call counts, and deterministic post-condition completion are reported separately.

## Human adjudication

Adjudication JSONL is keyed by `(case_id, trial_id, arm)` and may contain bounded repair/completion labels plus `evidence_ref`.
Boolean adjudication labels may be `null` when genuinely unreviewed or causally ambiguous. A missing causal label remains unresolved; it is never treated as `false`.

## Token and latency rules

The total token burden is the final valid Desktop `token_count.info.total_token_usage` snapshot. Token components remain host counters and are not reinterpreted as billing cost.

A phase-token delta is emitted only when valid cumulative snapshots safely bracket the phase and every component is monotonic. Otherwise the phase remains missing.

Latency is computed only from rollout timestamps. Negative, missing, or unparsable endpoints remain missing.

The paired idle-token population is valid matched validation/holdout `should_not_trigger` pairs. A pair is scorable only when both arms expose total tokens and M total tokens is greater than zero.
## Frozen gates

The frozen candidate gates are:

- pre-failure MCP = 0;
- Reliability-caused wrong repair = 0;
- Reliability-caused false completion = 0;
- MCP intervention recall >= 90% on validation + holdout valid trigger trials;
- controlled false activation <= 5% on validation + holdout valid no-trigger trials;
- production shadow <= 1/100 normal turns;
- paired idle-token delta <= +2% median S versus M;
- token coverage >= 90% before the paired token gate can resolve.
Gate states are `PASS`, `FAIL`, and `UNRESOLVED`. Production shadow remains `NOT_MEASURED` until the separate user-authorized normal-turn lane supplies evidence.

## Train, validation, and holdout immutability

Train may inform a later separately reviewed routing-description revision. Validation and holdout are evaluation-only; their outcomes cannot change routing descriptions, thresholds, or scorer semantics under the same frozen identity.

The future 24-case core is frozen only by the separate dataset/campaign plan. The unseen holdout stays outside the train-visible repository surface until train-driven changes are frozen.

## Evidence hygiene

Normalized records retain bounded hashes, identities, counters, and evidence pointers only. Raw prompts, transcripts, full PATH/environment, credentials, and unrelated machine inventory are not copied into the repository.

Raw rollout evidence stays host-local. The repository may contain only sanitized reproducible fixtures, stable contracts, tests, and bounded normalized records approved by the later campaign workflow.

Contract rule: missing measurements remain missing.
Evidence rule: raw rollout evidence stays host-local.
