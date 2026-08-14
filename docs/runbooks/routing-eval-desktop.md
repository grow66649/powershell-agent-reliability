# r4 Codex Desktop Routing Evaluation Runbook

## Scope

Use this runbook only after the harness slice has been independently reviewed. It operates normal Windows Codex Desktop; it does not use standalone Codex CLI as the product acceptance surface.

The controlled comparison is S=`thin companion Skill + MCP` versus M=`MCP-only self-routing`. Arm H is excluded for the current Desktop build.

The harness never switches user-wide Skill or Codex settings automatically. Arm setup must be explicit, supported, reversible, and operator-controlled.

## 1. Freeze exact harness identity

Before any canary or scored turn, record:

- `git rev-parse HEAD` for the reviewed harness commit;
- SHA256 of `benchmarks/harness/routing_eval.py`;
- SHA256 of the candidate Reliability MCP executable;
- Codex Desktop build, model, reasoning effort, approval policy, and sandbox type;
- the fixed campaign seed and case-set hash.

Do not mix rows from different identities in one admission report.

## 2. Run the S canary

Use a fresh Desktop thread and disposable workspace. Confirm the observed Skill catalog contains `powershell-reliability` and the candidate Reliability MCP is reachable through its intended tool surface.

The S canary is explicit capability proof, not an implicit routing trial. Keep it out of recall and false-activation denominators.
## 3. Run the M canary

Establish M only through a supported reversible setup that removes `powershell-reliability` from the observed Skill catalog while leaving the same Reliability MCP candidate reachable.

Verify both facts from the fresh M thread before any scored turn. If supported reversible Skill exclusion is unavailable, M setup is BLOCKED rather than simulated.

Do not hide catalog evidence after collection, rename the arm, weaken unrelated global configuration, or infer MCP-only behavior from S rows.

## 4. Freeze the reviewed dataset

The future controlled core path is `benchmarks/routing_eval/core_cases.json`. That file is created and frozen only by the separate owner-reviewed dataset/campaign plan after this harness review.

Do not author or tune the 24-case core in this implementation slice. The later plan freezes train and validation before execution and creates the unseen holdout only after train-driven routing changes are frozen.

Prepare a campaign only from the reviewed frozen cases:

```powershell
python .\benchmarks\harness\routing_eval.py prepare `
  --cases .\benchmarks\routing_eval\core_cases.json `
  --output-root <host-local-evidence-root> `
  --trials 3 --seed <frozen-seed>
```

Record the generated manifest hash before running scored turns. If a case declares a deterministic post-condition, freeze its `post_condition` rule and exact pass/fail markers before execution; do not derive or revise those criteria from later model output.
## 4A. Review and seal the train/validation package

Before any scored execution, the owner reviews every core case row: natural-task rationale, provenance cluster, expected routing, fixture, boundary detector, deterministic post-condition, leakage checks, and safety/privacy checks. Only rows approved before S/M outcome visibility are eligible.

Keep the 14 train cases/reviews in the train-visible repository surface. Keep the 10 validation prompts, fixtures, provenance metadata, and reviews host-local and sealed by hash from any session allowed to modify routing after train evidence. Validation remains sealed until the candidate routing revision is frozen. Validation outcomes cannot tune that same revision.

Validation and holdout scheduled attempts are not discretionarily retried. A setup abort may be replaced only when detected before prompt submission. After prompt submission, a timeout, routing miss, wrong repair, or task failure is a valid outcome unless protocol evidence itself is invalid.

## 4B. Prove S/M canaries and reversibility

1. In a fresh S thread, verify the observed Skill catalog contains `powershell-reliability` and verify the intended Reliability MCP surface is reachable.
2. Establish M only through a supported reversible configuration. In a fresh M thread, verify the Skill catalog does not contain `powershell-reliability` while the exact same Reliability MCP candidate remains reachable.
3. Restore S and repeat the visibility/reachability proof.

If M cannot be established without renaming/moving Skill files, hiding catalog evidence, weakening unrelated security/global settings, or otherwise simulating absence, set campaign status to `BLOCKED` and stop.

## 4C. Run the 12-turn timeout calibration lane

Prepare the reviewed calibration set with two repeats per case:

```powershell
python .\benchmarks\harness\routing_eval.py prepare `
  --cases .\benchmarks\routing_eval\calibration_cases.json `
  --output-root <host-local-calibration-root> `
  --trials 2 --seed 20260814
```

Execute all 12 manifest rows in fresh threads/workspaces under the same Desktop build, model, effort, approval, sandbox, MCP executable, and measurement policy planned for scored trials. Canary/calibration prompts must not use validation or holdout material.

Collect normalized records, then freeze T:

```powershell
python .\benchmarks\harness\routing_dataset.py freeze-timeout `
  --records <host-local-calibration-records> `
  --output <host-local-timeout-freeze>
```

The helper requires exactly 3 task shapes x 2 arms x 2 repeats = 12 valid turns and computes `T = ceil_to_30_seconds(2 * max(valid_calibration_turn_duration))`. Record the 12 durations, record/hash, and T before the first scored train row. The same T applies to S and M through train and validation. A safety-ceiling hit or infrastructure fault blocks timeout freeze for review rather than silently shrinking the evidence set.

## 4D. Execute train before revealing validation

Prepare and run only the train package with three repeats per arm under the frozen runtime identity and T. Train may motivate a separately reviewed routing revision. If routing changes, freeze the new routing identity before validation is revealed.

Only after the candidate routing revision is frozen may the sealed validation package be opened to the evaluation runner/reviewer. After validation closes, create the fresh unseen holdout pool; holdout remains evaluation-only and cannot tune the same revision. Case-level post-run human review is required before selecting S or M.

## 5. Execute manifest rows in normal Desktop

For every manifest row:

1. Apply the declared S or M setup and re-check its catalog invariant.
2. Start a fresh Codex Desktop thread; do not reuse conversational state.
3. Use exactly the manifest workspace. Never reuse the paired arm's mutated workspace.
4. Submit the generated prompt file unchanged. Do not add arm names, Skill hints, MCP hints, expected failures, or evaluator instructions.
5. Allow Codex Desktop/app-server to own normal command/process execution.
6. Preserve the resulting rollout JSONL under the host-local evidence root.

Raw rollout evidence stays host-local. Do not copy full transcripts, credentials, full PATH/environment, or unrelated machine state into the repository.

## 6. Collect after each bounded batch

Run collection against the actual Desktop sessions root:

```powershell
python .\benchmarks\harness\routing_eval.py collect `
  --manifest <host-local-evidence-root>\manifest.jsonl `
  --sessions-root <codex-desktop-sessions-root> `
  --output <host-local-evidence-root>\records.jsonl `
  --report <host-local-evidence-root>\collect-report.json
```

Review expected, collected, invalid, and remaining counts plus the next prompt/workspace pointers. Wrong workspace, duplicate identity, prompt drift, or arm-catalog mismatch is not repaired in place; preserve evidence and stop the affected batch.
## 7. Stop on hard guardrails

Stop the affected frozen revision immediately if a valid trial shows any pre-boundary Reliability MCP use, a Reliability-caused wrong repair, or a Reliability-caused false completion. Preserve the evidence; do not patch validation/holdout behavior and continue under the same identity.

Train is the only lane that may motivate a later separately reviewed routing-description revision. Validation and holdout are evaluation-only.

Do not claim a rate from an incomplete planned denominator after an early stop.

## 8. Adjudicate and score

Keep causal human labels in a separate bounded adjudication JSONL with evidence references. Unreviewed or ambiguous causality stays null.

```powershell
python .\benchmarks\harness\routing_eval.py score `
  --records <host-local-evidence-root>\records.jsonl `
  --adjudication <host-local-evidence-root>\adjudication.jsonl `
  --report <host-local-evidence-root>\score-report.json
```

Review case-level S/M outcomes and missing-measurement coverage, not only aggregate gates. Harness success does not establish product value.

## 9. Production shadow and downstream A/B

The controlled harness does not infer production-shadow evidence. The later user-authorized lane covers at least 300 normal turns under the selected real configuration and applies the frozen production-shadow threshold.

Only after the owner selects S or M and the shadow gate is satisfied may the selected routing shape proceed to the harder repeated autonomous-Desktop versus Reliability recovery A/B.

Main merge, release packaging, plugin/default recommendation, and always-on recommendation remain blocked until those downstream gates and explicit owner admission pass.

## Review-fix operator constraints

For each matched `(case_id, trial_id)` pair, preserve the same prompt/fixture identity, model, effort, approval policy, sandbox type, Desktop/CLI runtime identity, and Desktop originator. If collection shows missing identity evidence or cross-arm drift, treat that pair as invalid evidence; do not include either arm in performance denominators.

For cases with a frozen `post_condition.kind=tool_output_marker`, only the declared deterministic validator's matching tool-output marker is eligible evidence. Assistant prose or a self-reported completion claim never establishes the task post-condition. Keep the frozen pass/fail markers unchanged after the campaign starts.

When reviewing the score report, inspect ordinary `wrong_repair` and `false_completion` counts and review coverage separately from `reliability_caused_wrong_repair` and `reliability_caused_false_completion`. Causal attribution requires its own bounded human decision and evidence reference.
