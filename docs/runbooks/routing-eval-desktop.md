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

## 4. Use the reviewed train-visible and sealed datasets

The checked-in train-visible package is `benchmarks/routing_eval/train_cases.json` with its review metadata in `benchmarks/routing_eval/train_review.jsonl`. The timeout-calibration cases are in `benchmarks/routing_eval/calibration_cases.json`.

The sealed validation package is intentionally host-local and is not checked into this repository. There is no current `benchmarks/routing_eval/core_cases.json`; do not create or require that path for the current campaign. The unseen holdout is created only after train-driven routing changes are frozen, as required by the r4 contract.

Prepare scored train rows from the reviewed train-visible cases:

```powershell
python .\benchmarks\harness\routing_eval.py prepare `
  --cases .\benchmarks\routing_eval\train_cases.json `
  --output-root <host-local-train-evidence-root> `
  --runtime-parent <neutral-runtime-parent> `
  --trials 3 --seed <frozen-seed>
```

Record the generated manifest hash before running scored turns. Preparation creates one empty opaque campaign runtime root under the separate neutral runtime parent and creates **no row workspace**. The manifest freezes one opaque row path per S/M row plus coordinator-local prompt/fixture payloads. New artifact cases freeze an evaluator-owned `workspace_state` rule before execution. Those rules use only the five bounded file-state checks defined by the contract and relative paths under the exact trial workspace; do not derive or revise completion criteria from later model output.
## 4A. Review and seal the train/validation package

Before any scored execution, the owner reviews every scored train/validation case row: natural-task rationale, provenance cluster, expected routing, fixture, boundary detector, deterministic post-condition, leakage checks, and safety/privacy checks. Only rows approved before S/M outcome visibility are eligible.

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
  --runtime-parent <neutral-runtime-parent> `
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

For every manifest row, keep the runtime root single-row and opaque:

1. Apply the declared S or M setup and re-check its catalog invariant.
2. Verify the manifest runtime root is empty. Validate the manifest bindings and recompute the exact prompt-byte SHA-256 against `prompt_sha256` before Desktop sees the prompt. Then materialize **only** the current row from its frozen `fixture_path`; do not create any peer/future workspace.
3. Start a fresh Codex Desktop thread; do not reuse conversational state.
4. Open exactly the manifest workspace. Its model-visible path must contain only the neutral runtime parent, opaque campaign token, and opaque row token; it must not encode S/M, case/lane, Skill/MCP identity, evaluator labels, or campaign purpose.
5. Submit the generated prompt file unchanged. Do not add arm names, Skill hints, MCP hints, expected failures, or evaluator instructions.
6. Allow Codex Desktop/app-server to own normal command/process execution.
7. Preserve the resulting rollout JSONL under host-local evidence, grade/collect the current row while its workspace still exists, then delete that row workspace and verify the runtime root is empty before starting the next row.

From the repository root, materialize exactly one row with the reviewed helper:

```powershell
python -c "import hashlib,pathlib,sys; sys.path.insert(0,str(pathlib.Path('benchmarks/harness').resolve())); import codex_automation; m=pathlib.Path(r'<campaign-root>\manifest.jsonl'); r=codex_automation.load_manifest_row(m,<sequence>); codex_automation.validate_manifest_row_paths(m,r); p=pathlib.Path(r['prompt_path']); assert hashlib.sha256(p.read_bytes()).hexdigest().upper()==r['prompt_sha256'], 'prompt hash mismatch'; print(codex_automation.materialize_row_workspace(r))"
```

Do this immediately before the Desktop row. Do not use this helper to pre-create a batch.

Raw rollout evidence stays host-local. Do not copy full transcripts, credentials, full PATH/environment, or unrelated machine state into the repository.

## 6. Grade and collect each row before workspace cleanup

`workspace_state` is evaluator-owned final state, so collection must occur while the active row workspace still exists. Do not defer grading until after several row workspaces have been deleted.

For the just-completed Desktop thread, copy only that row's rollout JSONL into a host-local per-row collection directory and collect against the full frozen manifest:

```powershell
python .\benchmarks\harness\routing_eval.py collect `
  --manifest <campaign-root>\manifest.jsonl `
  --sessions-root <host-local-current-row-session-dir> `
  --output <host-local-current-row-record.jsonl> `
  --report <host-local-current-row-collect-report.json>
```

The per-row report must contain exactly the intended row and no invalid record before cleanup. Collection binds the rollout to its exact opaque workspace first and evaluates the deterministic post-condition directly from that workspace; it does not run a verifier command and does not ask the agent to self-report pass/fail.

After the current row record is preserved, remove the row workspace and verify the runtime root is empty:

```powershell
python -c "import pathlib,sys; sys.path.insert(0,str(pathlib.Path('benchmarks/harness').resolve())); import codex_automation; m=pathlib.Path(r'<campaign-root>\manifest.jsonl'); r=codex_automation.load_manifest_row(m,<sequence>); w=pathlib.Path(r['workspace']); codex_automation.remove_runtime_workspace(w); assert not w.exists(); assert list(pathlib.Path(r['runtime_root']).iterdir()) == []"
```

Wrong workspace, duplicate identity, prompt drift, arm-catalog mismatch, coordinator/other-row contamination, stale runtime entries, or failed cleanup is protocol failure. Preserve evidence and stop the affected batch; do not repair the row in place. At campaign completion or abort, remove the now-empty opaque runtime root and verify it is gone while retaining coordinator/raw evidence.

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

For new core artifact cases, `workspace_state` is the only admitted deterministic completion mechanism. The evaluator reads bounded final file state from the already-bound disposable workspace; assistant prose or a self-reported completion claim never establishes the task post-condition. `tool_output_marker is legacy-only` for historical campaign compatibility and is not eligible for new-core artifact admission. Final completion grading stays separate from routing evidence: final grading does not create an earlier routing boundary.

When reviewing the score report, inspect ordinary `wrong_repair` and `false_completion` counts and review coverage separately from `reliability_caused_wrong_repair` and `reliability_caused_false_completion`. Causal attribution requires its own bounded human decision and evidence reference.
