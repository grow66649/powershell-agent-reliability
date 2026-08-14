# r4 Naturalistic Dataset and Desktop Campaign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a human-reviewable naturalistic S/M campaign package, prove real S/M canaries, calibrate one frozen timeout from 12 non-scored Desktop turns, and execute train -> sealed validation -> fresh holdout without leaking evaluation material or changing product behavior.

**Architecture:** Keep `routing_eval.py` as the accepted trial collector/scorer. Add one narrow dataset-side validator for split/review integrity and timeout calibration, keep train-visible artifacts in the repo, keep validation/holdout content sealed outside the train-visible repo until their evaluation boundary closes, and update the existing contract/runbook rather than creating a second runner.

**Tech Stack:** Python 3, `unittest`, JSON/JSONL, PowerShell 7, Git, Windows Codex Desktop, existing `routing_eval.py` harness.

## Global Constraints

- Base/spec HEAD: `db2919be3286011a19e6c98a0b891502ed498755` on `docs/r4-naturalistic-dataset-campaign-20260814`.
- Target runtime is Windows Codex Desktop; standalone Codex CLI is secondary only.
- S=`thin companion Skill + MCP`; M=`Skill absent + same MCP`, established only by a supported reversible setup.
- Validation is sealed from routing-modification sessions until the candidate routing revision is frozen.
- Calibration is exactly 3 task shapes x 2 arms x 2 repeats = 12 valid non-scored turns.
- Freeze `T = ceil_to_30_seconds(2 * max(valid_calibration_turn_duration))` before the first scored train turn.
- One natural user prompt per scored trial; no manual follow-up hint/retry; autonomous tool continuation may run until completion or T.
- Do not change Rust product behavior, MCP/Skill behavior, scorer thresholds, Hook behavior, security settings, or release packaging.
- Raw Desktop rollouts, validation/holdout source material, exact session paths, and private review notes stay host-local.
- Every mutable repo task follows RED -> minimal GREEN -> focused test -> repo verification -> commit.

---
## File Structure

- Create `benchmarks/harness/routing_dataset.py`: validate frozen train/validation packages, review metadata, provenance isolation, and compute the calibrated timeout from normalized records.
- Create `benchmarks/harness/test_routing_dataset.py`: RED/GREEN coverage for split quotas, review completeness, provenance leakage, and timeout math.
- Modify `scripts/verify-local.ps1`: include the new dataset-helper unit tests in the benchmark test gate and Python compile gate.
- Create `benchmarks/routing_eval/calibration_cases.json`: three sanitized non-scored calibration task shapes, distinct from core/holdout material.
- Create `benchmarks/routing_eval/train_cases.json`: only the owner-approved 14 train cases after the sealed split is frozen.
- Create `benchmarks/routing_eval/train_review.jsonl`: sanitized pre-run human-review rows for those 14 train cases.
- Modify `docs/contracts/routing-eval-contract-r4.md`: freeze sealed-validation, calibration exclusion, and timeout rules without changing routing thresholds.
- Modify `docs/runbooks/routing-eval-desktop.md`: add exact S/M canary, calibration, split-freeze, train, validation, holdout, retry, and review procedure.
- Host-local only: candidate pool/reviews, sealed validation cases/reviews, holdout cases/reviews, raw rollouts, adjudication, timeout evidence, and score reports.

### Task 1: Add the dataset integrity and timeout helper

**Files:**
- Create: `benchmarks/harness/routing_dataset.py`
- Create: `benchmarks/harness/test_routing_dataset.py`

**Interfaces:**
- Produces `validate_frozen_core(train_cases, train_reviews, validation_cases, validation_reviews) -> dict`.
- Produces `compute_timeout_seconds(records: list[dict]) -> int`.
- CLI commands: `validate-freeze` and `freeze-timeout`; both write bounded JSON summaries only.
- [ ] **Step 1: Write RED tests for exact split quotas and review completeness**

Add tests that require train=`6 trigger/6 no-trigger/2 boundary`, validation=`4/4/2`, unique `case_id`, one approved review row per case, and `outcome_visible_before_review=false`.

```python
with self.assertRaisesRegex(ValueError, "train quota"):
    routing_dataset.validate_frozen_core(bad_train, train_reviews, validation, validation_reviews)

with self.assertRaisesRegex(ValueError, "review coverage"):
    routing_dataset.validate_frozen_core(train, train_reviews[:-1], validation, validation_reviews)
```

- [ ] **Step 2: Write RED tests for provenance-cluster isolation**

```python
validation[0]["provenance_cluster"] = train[0]["provenance_cluster"]
with self.assertRaisesRegex(ValueError, "provenance cluster crosses lanes"):
    routing_dataset.validate_frozen_core(train, train_reviews, validation, validation_reviews)
```

- [ ] **Step 3: Write RED tests for the frozen timeout rule**

Use 12 valid records covering exactly three case IDs, two arms, and two trial IDs. Assert 74.0 seconds maximum -> 150 seconds; reject missing/invalid/non-positive duration or an incomplete S/M/repeat matrix.

```python
self.assertEqual(routing_dataset.compute_timeout_seconds(records), 150)
with self.assertRaisesRegex(ValueError, "12 valid calibration records"):
    routing_dataset.compute_timeout_seconds(records[:-1])
```
- [ ] **Step 4: Run the focused tests and confirm RED**

Run:

```powershell
Push-Location benchmarks/harness
python -m unittest test_routing_dataset.py -v
Pop-Location
```

Expected: FAIL because `routing_dataset.py`/functions do not exist yet.

- [ ] **Step 5: Implement the minimum validator and timeout math**

Core constants/functions must include:

```python
CORE_QUOTAS = {
    "train": {"should_trigger": 6, "should_not_trigger": 6, "boundary": 2},
    "validation": {"should_trigger": 4, "should_not_trigger": 4, "boundary": 2},
}
REVIEW_REQUIRED = {
    "case_id", "provenance_cluster", "natural_task_rationale",
    "expected_routing_rationale", "failure_family", "boundary_rationale",
    "deterministic_success_condition", "leakage_check", "safety_privacy_check",
    "outcome_visible_before_review", "decision",
}

def _validate_lane(cases: list[dict], lane: str) -> None:
    counts = collections.Counter(row["group"] for row in cases)
    if counts != collections.Counter(CORE_QUOTAS[lane]):
        raise ValueError(f"{lane} quota mismatch: {dict(counts)}")
    if any(row.get("lane") != lane for row in cases):
        raise ValueError(f"{lane} package contains another lane")

def validate_frozen_core(train_cases, train_reviews, validation_cases, validation_reviews) -> dict:
    _validate_lane(train_cases, "train")
    _validate_lane(validation_cases, "validation")
    cases = train_cases + validation_cases
    if len({row["case_id"] for row in cases}) != 24:
        raise ValueError("case_id values must be unique across the 24-case core")
    reviews = {row["case_id"]: row for row in train_reviews + validation_reviews}
    if set(reviews) != {row["case_id"] for row in cases}:
        raise ValueError("review coverage must equal the frozen core")
    for row in reviews.values():
        if not REVIEW_REQUIRED.issubset(row) or row["decision"] != "approved" or row["outcome_visible_before_review"] is not False:
            raise ValueError("review coverage contains an unapproved or post-outcome row")
    lane_by_cluster = {}
    for case in cases:
        cluster = reviews[case["case_id"]]["provenance_cluster"]
        prior = lane_by_cluster.setdefault(cluster, case["lane"])
        if prior != case["lane"]:
            raise ValueError("provenance cluster crosses lanes")
    return {"train_count": 14, "validation_count": 10}

def ceil_to_30_seconds(value: float) -> int:
    if value <= 0:
        raise ValueError("duration must be positive")
    return int(math.ceil(value / 30.0) * 30)

def compute_timeout_seconds(records: list[dict]) -> int:
    if len(records) != 12 or any(row.get("valid") is not True for row in records):
        raise ValueError("need exactly 12 valid calibration records")
    identities = {(r["case_id"], r["trial_id"], r["arm"]) for r in records}
    if len({r["case_id"] for r in records}) != 3 or len(identities) != 12:
        raise ValueError("calibration matrix must be 3 cases x 2 trials x S/M")
    durations = [r.get("turn_duration_ms") for r in records]
    if any(not isinstance(v, (int, float)) or v <= 0 for v in durations):
        raise ValueError("all calibration durations must be positive numbers")
    return ceil_to_30_seconds(2 * max(durations) / 1000.0)
```

The CLI may serialize only bounded counts/hashes/seed/T; it must not copy raw prompts, host paths, or rollout contents into repo artifacts.
- [ ] **Step 6: Run focused tests and confirm GREEN**

```powershell
Push-Location benchmarks/harness
python -m unittest test_routing_dataset.py -v
Pop-Location
```

Expected: all dataset-helper tests PASS.

- [ ] **Step 7: Commit Task 1**

```powershell
git add benchmarks/harness/routing_dataset.py benchmarks/harness/test_routing_dataset.py
git commit -m "test: enforce r4 dataset freeze rules"
```

### Task 2: Put the new helper under the normal verification gate

**Files:**
- Modify: `scripts/verify-local.ps1`

**Interfaces:**
- Existing verifier remains the single local gate.
- Adds `test_routing_dataset.py` to benchmark tests and `routing_dataset.py`/test file to Python compilation.

- [ ] **Step 1: Edit the benchmark test command**

Change the unittest invocation to:

```powershell
& python -m unittest test_score_ab.py test_trigger_eval.py test_routing_eval.py test_routing_dataset.py
```
- [ ] **Step 2: Edit the Python compile command**

Include both new files:

```powershell
& python -m py_compile score_ab.py test_score_ab.py trigger_eval.py test_trigger_eval.py routing_eval.py test_routing_eval.py routing_dataset.py test_routing_dataset.py run_baseline.py fixture_worker.py
```

- [ ] **Step 3: Run the full local verifier**

```powershell
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
```

Expected: PASS; benchmark scorer count increases by the exact number of new helper tests.

- [ ] **Step 4: Commit Task 2**

```powershell
git add scripts/verify-local.ps1
git commit -m "test: include r4 dataset validation"
```

### Task 3: Freeze the campaign contract and Desktop procedure

**Files:**
- Modify: `docs/contracts/routing-eval-contract-r4.md`
- Modify: `docs/runbooks/routing-eval-desktop.md`

**Interfaces:**
- Contract freezes what counts as valid campaign evidence.
- Runbook gives the operator the exact canary/calibration/train/validation/holdout sequence.
- [ ] **Step 1: Add sealed-validation rules to the contract**

State explicitly that validation prompts/fixtures/review metadata remain outside the train-visible repo until the routing revision is frozen; validation outcomes cannot tune that same revision; holdout remains fresh and unseen until after train-driven changes freeze.

- [ ] **Step 2: Add calibration exclusion and timeout rules to the contract**

Freeze exactly:

```text
3 calibration task shapes x 2 arms x 2 repeats = 12 valid turns
T = ceil_to_30_seconds(2 * max(valid_calibration_turn_duration))
```

State that calibration/canary evidence never enters recall/FPR/token/completion/winner denominators.

- [ ] **Step 3: Expand the runbook before the existing scored execution section**

Add operator sections for: S canary -> M canary -> restore S -> prepare three calibration cases with `--trials 2` -> collect normalized records -> run `routing_dataset.py freeze-timeout` -> record T/hash -> freeze train/validation package -> execute train -> freeze routing revision -> reveal validation -> later create fresh holdout.

- [ ] **Step 4: Add no-retry and owner-review checkpoints**

The runbook must say setup aborts occur only before prompt submission; validation/holdout scheduled attempts are not discretionarily retried; owner pre-run review occurs before validation sealing; case-level post-run review is required before arm selection.

- [ ] **Step 5: Verify docs against the approved spec**

Run:

```powershell
git diff --check
git grep -n -E "12 valid|ceil_to_30|sealed validation|BLOCKED" -- docs/contracts/routing-eval-contract-r4.md docs/runbooks/routing-eval-desktop.md
```

Expected: all four campaign controls are present and `git diff --check` is clean.
- [ ] **Step 6: Commit Task 3**

```powershell
git add docs/contracts/routing-eval-contract-r4.md docs/runbooks/routing-eval-desktop.md
git commit -m "docs: freeze r4 campaign controls"
```

### Task 4: Author the non-scored calibration set

**Files:**
- Create: `benchmarks/routing_eval/calibration_cases.json`

**Interfaces:**
- Exactly three sanitized cases compatible with `routing_eval.py prepare`.
- They are not members or paraphrases of train/validation/holdout provenance clusters.
- Their only purpose is measuring realistic Desktop duration under both arms.

- [ ] **Step 1: Author the three case shapes**

The file must contain exactly:

1. one ordinary no-trigger task with deterministic success;
2. one eligible failure/repair task with a deterministic boundary and post-condition;
3. one deliberately slower build/test-or-verification task that remains safe and disposable.

Each case must use neutral prompts, relative fixture files only, and deterministic `boundary_detector`/`post_condition` values accepted by `routing_eval.load_cases()`.

- [ ] **Step 2: Validate preparation produces 12 rows**

```powershell
python ./benchmarks/harness/routing_eval.py prepare `
  --cases ./benchmarks/routing_eval/calibration_cases.json `
  --output-root $env:TEMP/psr-r4-calibration-prepare `
  --trials 2 --seed 20260814
```

Expected: `case_count=3`, `pair_count=6`, `trial_row_count=12`.
- [ ] **Step 3: Run the existing loader and focused helper tests**

```powershell
Push-Location benchmarks/harness
python -m unittest test_routing_eval.py test_routing_dataset.py -v
Pop-Location
```

Expected: PASS; calibration cases remain outside any admission denominator.

- [ ] **Step 4: Commit Task 4**

```powershell
git add benchmarks/routing_eval/calibration_cases.json
git commit -m "test: add r4 timeout calibration cases"
```

### Task 5: Build, review, and seal the naturalistic core

**Files:**
- Create after owner freeze: `benchmarks/routing_eval/train_cases.json`
- Create after owner freeze: `benchmarks/routing_eval/train_review.jsonl`
- Host-local only: `candidate_pool.json`, `candidate_review.jsonl`, `validation_cases.json`, `validation_review.jsonl`, `freeze-summary.json`.

**Interfaces:**
- Candidate pool target: about 48 rows, approximately 20 trigger / 20 no-trigger / 8 boundary.
- Frozen core: 24 cases; train=14 (`6/6/2`), validation=10 (`4/4/2`).
- Review row required fields: `case_id`, `provenance_cluster`, `natural_task_rationale`, `expected_routing_rationale`, `failure_family`, `boundary_rationale`, `deterministic_success_condition`, `leakage_check`, `safety_privacy_check`, `outcome_visible_before_review`, `decision`.

- [ ] **Step 1: Build the candidate pool before any S/M outcome is visible**

Source candidate ideas from real project failure families and ordinary Windows/Codex tasks, not scorer/Skill/MCP wording. Keep prompts natural, fixtures disposable, and deterministic validation independent from assistant prose.
- [ ] **Step 2: Perform pre-run human qualification**

Reject only the frozen reasons: ambiguous expected routing, flaky fixture, non-deterministic validator, unsafe setup, duplicate provenance, evaluator leakage, or privacy/sanitization failure. Set every reviewed row to `outcome_visible_before_review=false`.

- [ ] **Step 3: Freeze the train/validation split with a recorded seed**

Use a recorded seed to order the qualified pool within each group, then select the 24-case core while preserving exact group quotas and never placing one provenance cluster in both lanes. Record the seed and both package hashes in host-local `freeze-summary.json`.

- [ ] **Step 4: Validate the sealed freeze**

Run the new helper against repo-visible train material and host-local validation material:

Before running it, set `PSR_R4_VALIDATION_CASES`, `PSR_R4_VALIDATION_REVIEW`, and `PSR_R4_FREEZE_SUMMARY` to host-local paths outside the repository.

```powershell
python ./benchmarks/harness/routing_dataset.py validate-freeze `
  --train-cases ./benchmarks/routing_eval/train_cases.json `
  --train-review ./benchmarks/routing_eval/train_review.jsonl `
  --validation-cases $env:PSR_R4_VALIDATION_CASES `
  --validation-review $env:PSR_R4_VALIDATION_REVIEW `
  --seed 20260814 `
  --output $env:PSR_R4_FREEZE_SUMMARY
```

Expected: PASS with exact `14/10` split, `10/10/4` group totals, no cross-lane provenance cluster, complete review coverage, and bounded hashes only.

- [ ] **Step 5: Owner checkpoint before train execution**

Present all 24 pre-run review rows to the owner. After approval, keep validation prompt/fixture/review files sealed from any session that may modify routing; expose only `train_cases.json` and `train_review.jsonl` to the train writer/runtime.

- [ ] **Step 6: Commit only train-visible artifacts**

```powershell
git add benchmarks/routing_eval/train_cases.json benchmarks/routing_eval/train_review.jsonl
git commit -m "test: freeze r4 naturalistic train set"
```
### Task 6: Prove S/M canaries and freeze the scored timeout

**Files:**
- No scored data is committed.
- Host-local only: canary evidence, calibration manifest/records/report, `timeout-freeze.json`.

**Interfaces:**
- S canary: Skill visible + intended Reliability MCP reachable.
- M canary: Skill absent via supported reversible setup + identical Reliability MCP reachable.
- Restore-S canary: proves the M setup is reversible.
- Timeout output: one integer T in seconds, common to both arms.

- [ ] **Step 1: Freeze runtime identity before canaries**

Record exact harness HEAD, `routing_eval.py` SHA256, MCP executable SHA256, Desktop build, model, effort, approval policy, sandbox type, and campaign seed in host-local evidence.

- [ ] **Step 2: Run the S canary in a fresh Desktop thread**

Verify the observed Skill catalog contains `powershell-reliability`; explicitly call/list the intended Reliability MCP surface to prove reachability. Preserve bounded evidence only.

- [ ] **Step 3: Run the M canary**

Use only a supported reversible Skill-exclusion mechanism. Verify the observed catalog does not contain `powershell-reliability` while the exact same MCP candidate remains reachable. If this cannot be established, stop with campaign=`BLOCKED`; do not simulate M.

- [ ] **Step 4: Restore S and re-run the visibility/reachability canary**

Expected: original S state is restored without changing sandbox, approval policy, ACLs, PowerShell profile, or unrelated global settings.
- [ ] **Step 5: Prepare and execute the 12 non-scored calibration turns**

Prepare the three public calibration cases with two trials per case, then execute every S/M manifest row in a fresh thread/workspace under the frozen runtime identity. No validation/holdout material is opened.

- [ ] **Step 6: Collect calibration records and freeze T**

```powershell
python ./benchmarks/harness/routing_eval.py collect `
  --manifest $CalibrationManifest `
  --sessions-root $DesktopSessionsRoot `
  --output $CalibrationRecords `
  --report $CalibrationCollectReport

python ./benchmarks/harness/routing_dataset.py freeze-timeout `
  --records $CalibrationRecords `
  --output $TimeoutFreeze
```

Expected: 12 valid rows, complete 3-case x 2-trial x S/M matrix, all durations positive, and T equals the approved `2 * max` rule rounded up to 30 seconds.

- [ ] **Step 7: Leader records the durable timeout value**

Write only the measured T, runtime identity hashes, and evidence pointers to the canonical task. Keep raw calibration rollouts and exact session paths outside the repo.

### Task 7: Execute train without exposing validation

**Files:**
- Repo-visible input: `benchmarks/routing_eval/train_cases.json`.
- Host-local only: prepared manifest/workspaces, Desktop rollouts, normalized records, adjudication, score report.

- [ ] **Step 1: Prepare train with three repeats and the frozen seed**

```powershell
python ./benchmarks/harness/routing_eval.py prepare `
  --cases ./benchmarks/routing_eval/train_cases.json `
  --output-root $TrainEvidenceRoot `
  --trials 3 --seed 20260814
```
Expected: 84 train rows = 14 cases x 3 repeats x 2 arms; manifest hash recorded before execution.

- [ ] **Step 2: Execute rows in manifest order with frozen T**

For every row: apply the declared arm setup, verify catalog invariant, start a fresh Desktop thread, use the exact generated workspace/prompt, provide no manual follow-up, and stop only on natural completion, T, or a frozen hard guardrail.

- [ ] **Step 3: Collect after bounded batches and fail closed on protocol drift**

```powershell
python ./benchmarks/harness/routing_eval.py collect `
  --manifest $TrainManifest `
  --sessions-root $DesktopSessionsRoot `
  --output $TrainRecords `
  --report $TrainCollectReport
```

Wrong workspace, duplicate rollout, catalog mismatch, runtime drift, or ambiguous post-condition evidence is INVALID; task/routing failure after a valid prompt submission remains a scored negative outcome.

- [ ] **Step 4: Complete bounded human adjudication and score train**

```powershell
python ./benchmarks/harness/routing_eval.py score `
  --records $TrainRecords `
  --adjudication $TrainAdjudication `
  --report $TrainScoreReport
```

Owner/Leader reviews all 14 cases side-by-side across S1/S2/S3 and M1/M2/M3. Train alone may motivate a separately reviewed routing revision; validation remains sealed.

- [ ] **Step 5: Freeze routing revision before validation reveal**

Record exact Skill/MCP/tool-schema/harness hashes. If train motivates a routing change, implement/review it in a separate branch, rerun train under a new campaign revision, and do not reveal validation until that revision is frozen.

### Task 8: Execute sealed validation, then fresh unseen holdout

**Files:**
- Validation/holdout source remains host-local until each evaluation boundary closes.
- Optional post-evaluation reproducibility commit may add sanitized `benchmarks/routing_eval/core_cases.json` only after validation is closed.
- [ ] **Step 1: Reveal validation only to the evaluation runner/reviewer**

Confirm the frozen validation package hash still matches `freeze-summary.json`. Do not expose validation prompts/fixtures to any session allowed to change routing under this revision.

- [ ] **Step 2: Prepare and run the 60 validation rows**

Use the same frozen T, runtime identity, seed policy, fresh thread/workspace rule, and no-follow-up interaction budget. Do not discretionarily retry invalid/missing validation attempts; report UNRESOLVED coverage when evidence is insufficient.

- [ ] **Step 3: Adjudicate and score validation without tuning**

Any hard-gate violation fails this frozen revision. Do not patch Skill/MCP/scorer/thresholds and continue under the same validation identity.

- [ ] **Step 4: Build a fresh holdout candidate pool after train-driven changes are frozen**

Create new host-local candidates with no train/validation provenance clusters, qualify them before S/M outcome visibility, and freeze holdout=`4 trigger/4 no-trigger/2 boundary` with three repeats per arm.

- [ ] **Step 5: Run the 60 holdout rows once**

Use the same T and runtime identity. No discretionary retries, no tuning, and no threshold changes. Preserve per-case 0/3..3/3 stability and bounded human adjudication.

- [ ] **Step 6: Produce the owner review package**

Present validation and holdout separately plus combined frozen gates. For every case show S1/S2/S3 versus M1/M2/M3 validity, boundary, Skill/MCP use, pre-boundary MCP, deterministic task completion, wrong repair, false completion, tokens, latency, call counts, evidence refs, and anomalies.

### Task 9: Final repository verification and handoff

- [ ] **Step 1: Run focused Python suites**

```powershell
Push-Location benchmarks/harness
python -m unittest test_routing_dataset.py test_routing_eval.py test_trigger_eval.py test_score_ab.py -v
Pop-Location
```

Expected: PASS.
- [ ] **Step 2: Run the full local verifier**

```powershell
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
```

Expected: PASS.

- [ ] **Step 3: Check scope and whitespace**

```powershell
git diff --check
git status --short
git diff --name-only db2919be3286011a19e6c98a0b891502ed498755..HEAD
```

Expected repo changes are limited to the dataset helper/tests, verifier registration, calibration/train artifacts, r4 contract/runbook, and approved spec/plan docs. No `src/`, Rust product behavior, installed Skill, Hook, Codex config, release/tag, validation source, holdout source, or raw rollout files may appear.

- [ ] **Step 4: Commit any final documentation-only handoff**

```powershell
git add docs/contracts/routing-eval-contract-r4.md docs/runbooks/routing-eval-desktop.md
git commit -m "docs: finalize r4 campaign runbook"
```

Skip this commit if those files are already clean/committed; do not create an empty commit.

- [ ] **Step 5: Leader independent review before campaign admission**

Reviewer verifies exact HEAD, clean status, test evidence, split/review integrity, sealed-validation proof, M-canary proof, timeout-freeze evidence, and absence of validation/holdout leakage. Only then may the canonical task advance from campaign preparation to scored evaluation.

## Self-Review Checklist

- Spec coverage: dataset construction, provenance isolation, sealed validation, 12-turn calibration, timeout rule, canaries, interaction budget, retries, adjudication, train/validation/holdout, owner review, and evidence hygiene each map to a task above.
- Placeholder scan: angle-bracket strings appear only where the existing public runbook deliberately denotes a host-local runtime path; implementation commands should bind those paths to local PowerShell variables before execution.
- Type consistency: dataset helper consumes existing routing case/normalized record fields; it does not change `routing_eval.py` record schema or scorer thresholds.
- Scope: no product Rust/MCP/Skill behavior change is required by this plan.
