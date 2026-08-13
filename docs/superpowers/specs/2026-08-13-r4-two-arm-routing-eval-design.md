# r4 Two-Arm Routing Evaluation Design

Status: Draft for owner review. Design A approved on 2026-08-13; implementation is not yet approved.

## Decision question

For Windows Codex Desktop after an eligible PowerShell/native-command or explicit post-condition failure, which routing shape gives the better practical boundary between useful Reliability intervention and unnecessary context/tool cost?

- **S — thin companion Skill + MCP:** the `powershell-reliability` Skill is available and is expected to be selected only after an eligible boundary; Reliability MCP remains the bounded diagnosis/environment/verification backend.
- **M — MCP-only self-routing:** the companion Skill is not exposed; the same Reliability MCP remains available and Codex decides from MCP tool names/descriptions when to call it.

This r4 gate selects a routing shape. It does not by itself prove end-to-end product value; harder repeated autonomous-vs-Reliability Codex Desktop A/B remains downstream.

## Why Design A

Preserve `benchmarks/harness/trigger_eval.py` and `docs/contracts/skill-trigger-eval-contract-v0.2.md` as the existing Skill-selection compatibility/evidence layer. Add a separate `benchmarks/harness/routing_eval.py` for the broader S-vs-M temporal, token, latency, call, repair, completion, and post-condition comparison.

This avoids turning a validated Skill-selection collector into a mixed-purpose scorer, keeps historical trigger evidence reproducible, and lets r4 evolve without changing the meaning of the v0.2 trigger contract.

## Current architecture boundary

Arm H (`PostToolUse Hook + MCP`) is outside primary r4. Target Desktop Gate 0 did not admit reliable non-zero failure dispatch. Raw host evidence stays outside the repository; this design only records the resulting scope decision.

Codex Desktop/app-server remains the command/process/sandbox owner. The evaluation harness reads rollout evidence and deterministic fixture post-conditions; it does not inject commands, wrap every shell call, parse arbitrary transcripts into a replacement event stream, or become a second execution engine.

## Reuse boundary

`routing_eval.py` reuses the existing trigger collector as a library for common rollout facts where practical: case marker binding, session/runtime metadata, Skill reads, Reliability MCP call counts, first-command extraction, and environment fields. r4-specific parsing and scoring remain in `routing_eval.py`.

Do not refactor `trigger_eval.py` merely to make the new file aesthetically cleaner. A shared helper module is admitted only if TDD shows the same stable logic must otherwise be duplicated in both harnesses.

The existing 25-case trigger dataset remains unchanged as historical/compatibility data. r4 receives its own dataset contract so the 24-case core, split policy, arm metadata, and scoring semantics cannot silently change the old trigger benchmark.

## Arm isolation contract

The only intentional routing difference between matched S and M trials is companion-Skill exposure.

For both arms, keep the same normal Codex Desktop build, model, reasoning effort, approval policy, sandbox type, fixture definition, prompt text, Reliability MCP executable/tool schemas, and measurement policy. Each arm/trial gets its own fresh disposable workspace materialized from the same fixture definition/hash; never reuse a workspace after the paired arm has mutated it.

- S requires `powershell-reliability` to be present in the observed Skill catalog.
- M requires `powershell-reliability` to be absent from the observed Skill catalog.
- Both require the same Reliability MCP candidate to be available.

The harness does **not** mutate global Skill/config state to create an arm. Arm setup belongs to a disposable benchmark runbook. A trial whose observed catalog/runtime identity does not match its declared arm is invalid rather than repaired in-place. If normal Codex Desktop cannot establish M with the target Skill absent through an explicit, reversible, supported setup, the M campaign is blocked; the harness must not simulate MCP-only by hiding evidence after the fact or by weakening unrelated global configuration.

Before a campaign, one separate explicit MCP canary per arm proves that the intended candidate/tool surface is reachable. Those canaries are not scored as implicit routing trials and must not be mixed into recall or false-activation denominators.

## Temporal event model

Every valid trial is reduced to ordered observable events. The scorer must not infer a boundary from assistant prose when a tool/output or deterministic fixture oracle can establish it.

Required event classes:

1. `user_turn_start` — case/trial begins.
2. `first_attempt_start` — first task execution call for first-attempt cases.
3. `first_attempt_end` — corresponding shell/native result.
4. `eligible_boundary` — first observable event that makes Reliability eligible.
5. `skill_activation` — S only; first observed activation of the `powershell-reliability` companion Skill.
6. `mcp_intervention` — first Reliability MCP call.
7. `repair_action` — first bounded task-changing action after Reliability intervention, when observable.
8. `final_verification` — deterministic task post-condition check when the case requires one.
9. `turn_complete` — Desktop task completion event or end of rollout.

For command-level cases, `eligible_boundary` is the failed command result, timeout/cancellation result, parser/binding/command-resolution failure, or other manifest-declared observable command outcome.

For exit-zero/task-level mismatches, the case manifest supplies a bounded boundary detector tied to a deterministic validator/tool output. The harness must not discover post-condition failure by semantically interpreting arbitrary natural-language reasoning.

Boundary cases remain a separate reporting lane. They do not silently enter trigger recall or no-trigger false-activation denominators.

## Correct routing semantics

For an eligible first-attempt failure, neither arm may call Reliability MCP before `eligible_boundary`.

For S:
- a Skill read before the boundary is a premature Skill activation;
- correct Skill activation occurs after the boundary;
- MCP use without a prior Skill read is recorded as S protocol bypass, not hidden or reclassified as M;
- Skill selection without any later MCP call is recorded separately from actual intervention.

For M:
- there is no Skill activation event by construction;
- correct activation is the first Reliability MCP call after the boundary.

For deterministic no-trigger controls:
- S false activation means either a `powershell-reliability` Skill read or any Reliability MCP call;
- M false activation means any Reliability MCP call.

A successful first attempt whose required post-condition passes must have zero Reliability MCP calls. Any pre-boundary MCP call is a hard failure regardless of later task success.

## Trial validity versus task failure

Protocol breakage makes a trial invalid; agent/task failure does not.

Invalid examples include duplicate case/trial rollouts, wrong workspace/arm catalog, model/build/effort/approval/sandbox drift outside the declared arm difference, missing required case marker, or failure to execute a manifest-frozen first command. An agent that follows the protocol but fails to complete the task remains a valid negative outcome and must count against completion-related metrics.

## r4 trial record

Persist one bounded normalized record per valid or invalid trial. Keep raw rollout paths as evidence pointers; do not copy raw prompts, full transcripts, full PATH, full environment, credentials, or unrelated machine inventory into benchmark records.

Required fields include:

- schema/case/trial/arm identity and sequence;
- rollout path, session ID, originator, Codex build, model, effort, approval policy, sandbox type;
- prompt hash and workspace/fixture identity hash;
- observed S/M arm-catalog conformance and MCP-candidate conformance;
- first-attempt start/end indexes and observable command outcome when available;
- eligible-boundary kind/index/timestamp and detector result;
- Skill activation index/timestamp/count and premature flag;
- Reliability MCP call indexes/timestamps/count and pre-boundary count;
- first post-boundary MCP latency;
- other-Skill collisions;
- final deterministic post-condition truth when available;
- completion truth, repair/adjudication fields, false-completion field, and evidence reference;
- total/phase token measurements when exposed;
- turn/intervention latency measurements when exposed;
- invalid reason(s) and missing-measurement flags.

Missing host measurements remain null/missing. The scorer must never convert missing token, latency, completion, or adjudication evidence to zero.

## Token and latency model

The primary cost comparison is paired S-versus-M on the same case/trial identity.

Use the final host-exposed `token_count.total_token_usage` snapshot for total-turn token burden when present. Persist its input, cached-input, output, reasoning-output, and total components separately; do not reinterpret these fields as billing.

If cumulative token snapshots safely bracket a known event, `routing_eval.py` may compute monotonic phase deltas for:

- pre-boundary work;
- Skill/routing activation;
- Reliability intervention and recovery;
- final verification/completion.

Phase deltas are optional evidence. If snapshots do not bracket a phase cleanly, that phase remains missing rather than estimated from text length.

The frozen idle-cost gate is evaluated on valid matched known-good/no-trigger pairs as the median paired total-token delta of S relative to M. S must remain within `+2%` median idle-token delta for admission. Token-gate claims require at least 90% paired token-measurement coverage; otherwise cost admission is unresolved.

Record paired trigger-case token deltas as descriptive evidence even though no fixed trigger-token threshold is predeclared.

Latency uses rollout timestamps only: total turn duration, boundary-to-first-activation delay, boundary-to-first-MCP delay, and intervention-to-final-verification duration when those endpoints exist. Missing endpoints remain missing.

## Automatic metrics and human adjudication

Automatic scoring covers facts available from rollout/tool evidence and deterministic fixture oracles. It must not pretend to know semantic repair quality from raw prose.

Report at minimum:

- arm-specific activation recall on `should_trigger`;
- actual Reliability MCP intervention recall on `should_trigger`;
- false-activation rate on `should_not_trigger`;
- pre-boundary Skill activation count for S;
- pre-boundary Reliability MCP-call count for both arms;
- per-case three-repeat activation stability;
- S protocol-bypass count (MCP without prior Skill read);
- other-Skill collision trials;
- first-command conformance and invalid-trial counts;
- matched token, latency, and MCP-call deltas;
- deterministic post-condition completion rate where mechanically checkable.

Wrong-repair count and assistant completion claims may require bounded human adjudication. Store those labels in a separate adjudication JSONL keyed by case/trial/arm with an evidence pointer and reviewer decision. The scorer merges adjudication without changing raw rollout-derived facts.

A `Reliability-caused wrong repair` requires an evidence pointer showing that a Reliability output/recommendation materially led to the task-changing action and that the action was wrong under the frozen task criteria. Ambiguous causality remains unadjudicated rather than silently counted as zero.

`false_completion` is true only when evidence establishes that Codex claimed task completion while the frozen deterministic post-condition was false. For the Reliability-caused hard gate, adjudication must also establish that the Reliability path materially contributed to the unsupported completion claim. Unreviewed or causally ambiguous claims remain unadjudicated, not false or true by guess.

## Controlled dataset and split

r4 uses a new 24-case naturalistic core, not a mutation of the existing 25-case Skill-trigger dataset:
- 10 `should_trigger` cases;
- 10 `should_not_trigger` near-miss/known-good cases;
- 4 `boundary` collision/ambiguity cases.

Freeze the core split before campaign execution:

- train: 14 cases = 6 trigger + 6 no-trigger + 2 boundary;
- validation: 10 cases = 4 trigger + 4 no-trigger + 2 boundary.

Each core case runs three fresh-thread repetitions **per arm**. That is 84 train trials and 60 validation trials across S and M, for 144 controlled core trials total.

After train-driven routing-description changes are frozen, create a fresh unseen 10-case holdout = 4 trigger + 4 no-trigger + 2 boundary. Each holdout case also runs three repetitions per arm, adding 60 trials. Holdout outcomes may not change routing descriptions, thresholds, or scorer semantics.

Prompts are arm-neutral and must not name the Reliability Skill, MCP, routing arm, evaluator, or expected activation. The same rendered prompt and disposable fixture are paired across S and M.

Randomization uses a recorded fixed seed and balances arm order within repetition rounds. Fresh Desktop threads are mandatory; no trial inherits conversational state from another trial.

## Passive base-rate and production-shadow lane

A separate, user-authorized lane evaluates at least 300 normal Codex Desktop turns using only bounded rollout facts needed for routing metrics; raw prompts are not persisted into benchmark records. This lane estimates how often **observable** eligible failure boundaries occur and does not substitute for controlled S/M trials. Command/tool failures can be counted from bounded runtime evidence; task-level post-condition failures are counted only when an explicit deterministic outcome is observable. The report must state this coverage limit rather than treating the lane as complete coverage of every task-level failure.

After a candidate arm is selected, production-shadow evidence must cover at least 300 normal turns under that candidate's real catalog/tool configuration before any always-on recommendation. Organic user-authorized turns may be used so the project does not create model work solely to inflate the shadow count.

Report false activations per 100 normal turns and base-rate-adjusted precision. A production-shadow false-activation rate above `1/100` fails the frozen gate.

Historical turns whose arm exposure cannot be proven are usable for failure-prevalence estimation only, not for candidate false-activation claims.

## Frozen admission gates

The following are fixed before validation/holdout:

- pre-failure Reliability MCP calls = `0`;
- Reliability-caused wrong repair = `0`;
- Reliability-caused false completion = `0`;
- validation + holdout eligible **MCP intervention recall** target = `>=90%` over all valid `should_trigger` trials in those two lanes; report validation and holdout separately as well. For S, Skill-read recall is diagnostic and cannot substitute for MCP-intervention recall;
- controlled near-miss false activation = `<=5%` over all valid `should_not_trigger` trials in validation + holdout; report each lane separately as well;
- production shadow false activation = `<=1/100` normal turns;
- known-good/no-trigger median paired S idle-token delta versus M = `<=+2%`.

Boundary cases are reviewed separately and do not rescue a failed hard gate. Aggregate percentages never override a protocol violation, missing environment proof, or human review of repeated false positives/false negatives.

## Campaign stopping rules

Train is the only lane that may justify a later revision to Skill wording, MCP descriptions, or routing fixtures. Such product-facing edits are **not** part of the harness implementation slice: they require their own reviewed change, new hashes/identity, and a newly frozen train revision. If a hard guardrail is violated during train, stop the affected experiment, preserve evidence, diagnose, and restart only after the revised train identity is frozen.

Validation and holdout are evaluation-only. If either produces a hard-gate violation, the evaluated candidate fails that frozen revision; do not patch and continue under the same validation/holdout identity.

A campaign may stop early after a decisive hard failure to avoid unnecessary token spend, but then no incomplete rate may be presented as if the planned denominator was completed.

## Proposed repository shape

Design A adds only r4 evaluation assets:

- `benchmarks/harness/routing_eval.py` — prepare/collect/merge-adjudication/score/report for S versus M;
- `benchmarks/harness/test_routing_eval.py` — focused RED/GREEN tests;
- `benchmarks/routing_eval/core_cases.json` — frozen 24-case core after dataset review;
- `docs/contracts/routing-eval-contract-r4.md` — stable machine/human evaluation contract derived from this approved design;
- `docs/runbooks/routing-eval-desktop.md` — arm setup, canaries, fresh-thread campaign, collection, and cleanup procedure.

Fresh unseen holdout content is frozen only after train-driven changes are complete. Until the holdout campaign closes, its source stays outside the train-visible repository surface; the campaign stores its hash/identity in external evidence. Sanitized holdout fixtures may be committed after scoring for reproducibility.

No production Rust/MCP behavior, installed Skill, global Codex configuration, Hook configuration, or release packaging changes belong in this implementation slice.

## TDD and verification boundary

Implementation begins with RED tests for temporal ordering, premature activation, M/S arm conformance, missing measurements, paired token math, invalid-versus-negative trials, boundary separation, adjudication merge, and frozen-gate scoring. Only then add the minimum `routing_eval.py` behavior needed to turn each RED test GREEN.

The implementation slice is complete only when focused r4 tests pass, the existing `test_trigger_eval.py` suite still passes unchanged, repo verification passes, and `git diff --check` is clean. This proves harness compatibility, not product value.

Before the real campaign, run deterministic synthetic rollout fixtures plus explicit S/M canaries. Real normal Codex Desktop rollout JSONL remains the authority for routing observations.

## Non-goals

- repairing Codex Desktop Hook dispatch;
- building a Hook/native gate;
- changing Reliability MCP product behavior during harness work;
- changing the installed companion Skill during validation/holdout;
- universal transcript parsing or command rewriting;
- using the harness itself to alter user-wide Skill or Codex settings when switching arms;
- replacing final human case-level review with one aggregate score;
- using synthetic harness success as evidence for release/default activation.

## Acceptance and handoff

After controlled train/validation/holdout and production-shadow evidence are complete, present S and M side by side with case-level failures, stability, timing, token/latency/call costs, wrong-repair/false-completion adjudication, and missing-measurement coverage.

The project owner selects S or M. Only the selected arm proceeds to the harder repeated real Desktop recovery A/B against autonomous Codex Desktop. Main merge, release packaging, plugin/default recommendation, and recommended always-on activation remain blocked until that downstream product-value gate and explicit human admission pass.