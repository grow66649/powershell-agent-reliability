# r4 Two-Arm Routing Evaluation Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the approved Design A evaluation harness for matched S=`thin companion Skill + MCP` and M=`MCP-only` routing trials.

**Architecture:** Preserve the existing Skill-selection harness as the compatibility layer. Add a separate standard-library-only `routing_eval.py` that reads Codex Desktop rollout JSONL, normalizes bounded routing facts, measures timing/token cost, merges bounded adjudication, and scores frozen routing gates.

**Tech Stack:** Python 3 stdlib, existing Codex Desktop rollout JSONL, existing PowerShell verification script, Git.

## Global Constraints

- Approved design commit: `0a7970a5cd6494d9c19c5d3530613e4d95362fdc`.
- Planning/design worktree: <repo-worktree>.
- Preserve `benchmarks/harness/trigger_eval.py`, `benchmarks/harness/test_trigger_eval.py`, and `benchmarks/trigger_eval/cases.json` semantics; do not repurpose the old 25-case dataset.
- Primary r4 arms are only S=`thin companion Skill + MCP` and M=`MCP-only self-routing`; Hook Arm H stays out of implementation.
- Do not modify Rust product code, installed Skill content, Codex runtime settings, Hook settings, release packaging, or MCP tool behavior in this plan.
- Do not automate user-wide Skill/config switching. If M cannot be established through an explicit reversible supported setup, the campaign is blocked rather than simulated.
- All behavior changes follow RED -> observed expected failure -> minimum GREEN -> compatibility verification.
- Normalized records keep only bounded hashes/identities and evidence pointers; raw rollout content stays outside the repository.
- Command outcome and deterministic task post-condition remain separate fields.
- Missing token, timing, completion, or adjudication evidence remains `None`; never coerce missing evidence to zero.

## Scope Split

This plan implements the **harness, stable r4 contract, synthetic tests, runbook, and local verification integration**. It intentionally does not author the final 24-case naturalistic core, the unseen holdout, or execute the paid Desktop campaign.

The 24-case core and campaign are a separate follow-up implementation/execution plan after this harness is reviewed. That keeps the human-reviewed experimental dataset from being buried inside harness code work and preserves the approved train/validation/holdout discipline.

---

## File Map

- Create: `benchmarks/harness/routing_eval.py` — paired preparation, rollout collection, normalization, adjudication merge, scoring, CLI/reporting.
- Create: `benchmarks/harness/test_routing_eval.py` — focused TDD suite using synthetic rollout rows and temporary workspaces.
- Create: `docs/contracts/routing-eval-contract-r4.md` — stable machine/human record and scoring contract derived from the approved design.
- Create: `docs/runbooks/routing-eval-desktop.md` — normal Desktop arm setup/canary/campaign/collection procedure.
- Modify: `scripts/verify-local.ps1` — include routing-eval tests and Python compile checks.
- Read/reuse only: `benchmarks/harness/trigger_eval.py`, `benchmarks/harness/score_ab.py`, `docs/contracts/skill-trigger-eval-contract-v0.2.md`.
### Task 1: Prepare matched S/M trial manifests without contaminating prompts

**Files:**
- Create: `benchmarks/harness/routing_eval.py`
- Create: `benchmarks/harness/test_routing_eval.py`

**Produces:** One arm-neutral prompt per case/trial, two fresh fixture workspaces per pair, deterministic fixture/workspace hashes, and a randomized manifest whose only declared arm difference is Skill exposure.

- [ ] **Step 1: Add RED tests for paired preparation**

Start `test_routing_eval.py` with standard-library imports. Add a temporary two-arm case and assert that one case/trial produces exactly one S row and one M row, both rows have the same `prompt_sha256` and `fixture_sha256`, and the two rows have different `workspace_sha256` values.

Also assert:
- the rendered prompt contains the neutral `[CASE-ID: R01-T01]` marker;
- the prompt does not contain `powershell-reliability`, `Reliability MCP`, or an arm name;
- each workspace contains byte-identical fixture files;
- case prompts containing `{workspace}` are rejected, because embedding different workspace paths would destroy the matched-prompt invariant;
- preparation is deterministic for the same seed;
- within each repetition round, S-first versus M-first pair order differs by at most one case.
The test should exercise this public interface:

```python
rows = routing_eval.prepare_campaign(cases, output_root, trials=3, seed=20260813)
```

Each manifest row must contain at least `case_key`, `case_id`, `trial_id`, `lane`, `group`, `arm`, `sequence`, `prompt_path`, `prompt_sha256`, `workspace`, `workspace_sha256`, `fixture_sha256`, `expected_first_command_fragment`, and `boundary_detector`.

- [ ] **Step 2: Run the preparation tests and observe RED**

Run from `benchmarks/harness`:

```powershell
python -m unittest test_routing_eval.RoutingEvalPrepareTests -v
```

Expected: import/test failure because `routing_eval.py` does not exist yet.

- [ ] **Step 3: Implement the minimum paired preparation API**

Create constants and validators:

```python
VALID_ARMS = {"S", "M"}
VALID_LANES = {"train", "validation", "holdout"}
VALID_GROUPS = {"should_trigger", "should_not_trigger", "boundary"}
BOUNDARY_KINDS = {"none", "first_command_nonzero", "tool_output_contains"}
```

Import `trigger_eval` and reuse its JSONL writer/hash/command-normalization behavior rather than copying the old collector.Use a Windows-path identity helper so collection can match the same neutral marker to the correct arm workspace without persisting raw cwd in records:

```python
def workspace_identity(value: str) -> str:
    normalized = str(pathlib.PureWindowsPath(value)).replace("/", "\\").rstrip("\\").casefold()
    return trigger_eval._sha256_text(normalized)
```

Hash fixture definitions over sorted relative paths plus UTF-8 bytes. Write the same files separately under `workspaces/S/<case_key>/` and `workspaces/M/<case_key>/`.

Write one shared prompt file per case/trial under `prompts/<case_key>.txt`. The prompt references only the current workspace and case marker; it never embeds the arm or absolute workspace.

Generate sequence order by repetition round: shuffle case order with `random.Random(seed)`, then alternate which arm goes first within each case pair so pair order remains balanced and reproducible.
- [ ] **Step 4: Run preparation tests GREEN**

Run from `benchmarks/harness`:

```powershell
python -m unittest test_routing_eval.RoutingEvalPrepareTests -v
```

Expected: all preparation tests PASS.

- [ ] **Step 5: Run old campaign-preparation compatibility tests**

```powershell
python -m unittest test_trigger_eval.TriggerEvalCampaignTests test_trigger_eval.TriggerEvalCampaignOrderingTests -v
```

Expected: PASS with no change to old files.

- [ ] **Step 6: Commit Task 1**

Stage only the two routing harness files, run `git diff --cached --check`, and commit with message `feat: prepare paired routing trials`.
### Task 2: Normalize temporal routing events and arm conformance

**Files:**
- Modify: `benchmarks/harness/routing_eval.py`
- Modify: `benchmarks/harness/test_routing_eval.py`

**Produces:** One bounded normalized trial record with event indexes/timestamps for first attempt, eligible boundary, Skill activation, Reliability MCP intervention, and completion/verification evidence.

- [ ] **Step 1: Add synthetic rollout helpers and RED temporal tests**

Cover these cases:
- S: first command fails, Skill read occurs after failed output, MCP call follows -> valid/correct activation.
- S: Skill read occurs before the boundary -> `premature_skill_activation=True`.
- S: MCP call occurs after the boundary without a prior Skill read -> `s_protocol_bypass=True`.
- M: observed Skill catalog still contains `powershell-reliability` -> invalid with `arm_catalog_mismatch`.
- M: catalog omits the Skill and MCP call occurs after the boundary -> valid/correct activation.
- no-trigger S: Skill read with no MCP call -> false activation.
- no-trigger M: zero MCP calls -> no false activation.
- task-level mismatch: a deterministic output marker establishes `eligible_boundary` even when the first command exit is zero.
The tests exercise:

```python
record = routing_eval.extract_trial(rows, pathlib.Path("rollout.jsonl"), manifest_row)
```

The normalized record stores hashes and evidence pointers, not the full prompt or full command text.

- [ ] **Step 2: Run temporal tests and observe RED**

```powershell
python -m unittest test_routing_eval.RoutingEvalTemporalTests -v
```

Expected: failures because temporal extraction is not implemented.

- [ ] **Step 3: Reuse the old bounded collector facts, then scan r4 events separately**

Start `extract_trial` by calling:

```python
base = trigger_eval.extract_rollout(rows, rollout_path)
```

Reuse `base` for case/session/runtime metadata, Skill catalog presence, first-command outcome, Skill selection, other-Skill collisions, and prompt hash. Do not change `trigger_eval.extract_rollout` for r4 convenience.

Separately scan `response_item` rows for `custom_tool_call` / `custom_tool_call_output`, using `trigger_eval._skill_names`, `trigger_eval.PSR_MCP`, `trigger_eval.SHELL_CALL`, and `trigger_eval.EXIT_RE` so old and new harnesses share existing matching semantics.Define boundary handling narrowly from manifest-declared detectors:

```python
def find_eligible_boundary(rows, manifest_row, first_command):
    detector = manifest_row["boundary_detector"]
    if detector["kind"] == "none":
        return None
    if detector["kind"] == "first_command_nonzero":
        return boundary_from_first_command_output(rows, first_command)
    if detector["kind"] == "tool_output_contains":
        return boundary_from_output_marker(rows, detector["marker"])
    raise ValueError(f"unsupported boundary detector {detector['kind']!r}")
```

`first_command_nonzero` is eligible only when the observable shell result is non-zero. `tool_output_contains` matches an exact sanitized marker supplied by the case manifest; it must not interpret assistant prose.

Record at minimum:
- `first_attempt_start_index`, `first_attempt_end_index`, `first_command_exit_code`;
- `eligible_boundary_kind`, `eligible_boundary_index`, `eligible_boundary_timestamp`;
- `skill_activation_indexes`, `skill_activation_count`, `premature_skill_activation`;
- `mcp_intervention_indexes`, `mcp_intervention_count`, `pre_boundary_mcp_call_count`;
- `s_protocol_bypass`, `selected_other_skills`;
- `turn_complete_index`, `turn_complete_timestamp`;
- `valid`, `invalid_reasons`.

Parse timestamps with `datetime.fromisoformat(value.replace("Z", "+00:00"))`; keep the original ISO string in the record and use parsed values only for deltas.

Arm validity is deterministic: S requires catalog presence; M requires catalog absence. A missing observed catalog is `arm_catalog_unobserved`, not an assumed pass.
- [ ] **Step 4: Verify temporal tests GREEN**

```powershell
python -m unittest test_routing_eval.RoutingEvalTemporalTests -v
```

Expected: PASS.

- [ ] **Step 5: Add workspace-bound collection RED tests**

Create two synthetic rollout files with the same neutral case marker but different `turn_context.cwd` values matching S and M manifest workspaces. Assert `collect_rollouts()` returns exactly two records keyed by `(case_id, trial_id, arm)` rather than treating the shared marker as a duplicate.

Also assert:
- unrelated malformed rollout files are ignored when they contain no known marker;
- a second rollout matching the same case/trial/arm workspace raises `ValueError`;
- a marker with the wrong workspace is ignored rather than rebound to another arm.

- [ ] **Step 6: Implement workspace-bound collection**

Build a manifest index by `(case_key, workspace_sha256)`. Read the case marker and `turn_context.cwd`, hash cwd with `workspace_identity()`, and bind only exact pairs. Persist the rollout path as the raw-evidence pointer but remove raw cwd after hashing.

- [ ] **Step 7: Run all routing temporal/collection tests and old collector robustness tests**

```powershell
python -m unittest test_routing_eval.RoutingEvalTemporalTests test_routing_eval.RoutingEvalCollectionTests test_trigger_eval.TriggerEvalCollectorRobustnessTests -v
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

Stage only `routing_eval.py` and `test_routing_eval.py`, run cached diff check, and commit with message `feat: normalize routing event timelines`.
### Task 3: Measure token and latency cost conservatively

**Files:**
- Modify: `benchmarks/harness/routing_eval.py`
- Modify: `benchmarks/harness/test_routing_eval.py`

**Produces:** Host-exposed total token components, conservative optional phase deltas, rollout-timestamp latency metrics, and explicit missing-measurement coverage.

- [ ] **Step 1: Add RED tests using the observed Desktop token event shape**

Synthetic token events must use `event_msg -> payload.type=token_count -> payload.info.total_token_usage` with the fields `input_tokens`, `cached_input_tokens`, `cache_write_input_tokens`, `output_tokens`, `reasoning_output_tokens`, and `total_tokens`.

Test that the final snapshot is recorded component-by-component and that missing token events produce `None`, not zero.

Add timestamp tests for boundary-to-first-Skill latency on S, boundary-to-first-MCP latency on both arms, total turn duration, missing endpoints, and non-monotonic token snapshots.
- [ ] **Step 2: Run cost tests and observe RED**

```powershell
python -m unittest test_routing_eval.RoutingEvalCostTests -v
```

Expected: failures because cost extraction is absent.

- [ ] **Step 3: Implement total-token extraction and timestamp deltas**

Add a fixed field tuple:

```python
TOKEN_FIELDS = (
    "input_tokens", "cached_input_tokens", "cache_write_input_tokens",
    "output_tokens", "reasoning_output_tokens", "total_tokens",
)
```

`final_token_usage(rows)` returns the final observed cumulative snapshot only when all present values are non-negative integers. Do not reinterpret token fields as billing cost.

Use rollout timestamps only for latency. Return milliseconds for `turn_duration_ms`, `boundary_to_skill_ms`, and `boundary_to_mcp_ms`; return `None` whenever an endpoint is missing or ordered backwards.

For optional phase token deltas, emit a delta only when two monotonic cumulative snapshots safely bracket the requested event interval. If bracketing is ambiguous, leave that phase absent and increment a missing-measurement flag.

- [ ] **Step 4: Verify cost tests GREEN**

```powershell
python -m unittest test_routing_eval.RoutingEvalCostTests -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 3**

Stage only the two routing harness files, run cached diff check, and commit with message `feat: measure routing token and latency cost`.
### Task 4: Merge bounded adjudication and score the frozen r4 gates

**Files:**
- Modify: `benchmarks/harness/routing_eval.py`
- Modify: `benchmarks/harness/test_routing_eval.py`

**Produces:** Deterministic automatic routing metrics plus separate causal human labels, with PASS/FAIL/UNRESOLVED gate states and exact denominators.

- [ ] **Step 1: Add RED adjudication tests**

Define adjudication rows keyed by `(case_id, trial_id, arm)` and allow only bounded labels plus an evidence pointer. Test duplicate identities, unknown trial identities, invalid types, and missing causal labels.

The merge interface is:

```python
merged = routing_eval.merge_adjudication(records, adjudication_rows)
```

Required supported labels:
- `wrong_repair`;
- `reliability_caused_wrong_repair`;
- `completion_claimed`;
- `false_completion`;
- `reliability_caused_false_completion`;
- `evidence_ref`.

All booleans may be `None` when genuinely unadjudicated. A missing causal label must remain unresolved rather than becoming false.

- [ ] **Step 2: Add RED scorer tests for routing semantics**

Construct small validation/holdout records and assert:
- primary recall uses actual post-boundary `mcp_intervention_count > 0`, not Skill-read recall;
- S no-trigger false activation is Skill read **or** MCP use;
- M no-trigger false activation is MCP use;
- boundary records stay outside recall/false-activation denominators;
- invalid trials stay outside all performance denominators but are reported;
- any valid should-trigger trial with `pre_boundary_mcp_call_count > 0` fails the pre-failure MCP hard gate;
- S MCP use without prior Skill read increments protocol-bypass count.
Add paired idle-token gate tests keyed by `(case_id, trial_id)` for valid `should_not_trigger` validation/holdout rows. Compute paired percentage as `(S total tokens - M total tokens) / M total tokens * 100`.

Assert:
- median paired S-minus-M percentage `<= 2.0` passes when token coverage is at least 90%;
- coverage below 90% yields `UNRESOLVED` even if measured pairs look cheap;
- a missing S or M token snapshot remains missing;
- an M total of zero is unscorable.

Add hard causal gate tests:
- any `reliability_caused_wrong_repair=True` -> FAIL;
- any `reliability_caused_false_completion=True` -> FAIL;
- if an intervention trial that requires review still has causal label `None`, the corresponding causal hard gate is `UNRESOLVED`;
- all required reviewed labels false -> PASS.
- [ ] **Step 3: Run scorer tests and observe RED**

```powershell
python -m unittest test_routing_eval.RoutingEvalAdjudicationTests test_routing_eval.RoutingEvalScoringTests -v
```

Expected: failures because merge/scoring is not implemented.

- [ ] **Step 4: Implement explicit metrics and gate states**

Use stdlib `statistics.median` for paired deltas. Keep three gate states only: `PASS`, `FAIL`, and `UNRESOLVED`.

`score_records(records)` must report, per arm and admission lane:
- valid/invalid trial counts and invalid reasons;
- MCP intervention recall on `should_trigger`;
- Skill-read recall for S as diagnostic only;
- false activation on `should_not_trigger`;
- pre-boundary Skill/MCP violations;
- S protocol bypass;
- other-Skill collision trials;
- case-level three-repeat stability;
- paired token coverage and median deltas;
- latency and MCP-call distributions when measured;
- deterministic post-condition completion rate when available;
- adjudication coverage and causal hard-gate state.

Admission recall and near-miss false activation use validation + holdout only and also report each lane separately. Train remains descriptive/tuning evidence and cannot rescue an admission failure.The scorer encodes the frozen gates exactly:

```text
pre-failure Reliability MCP calls = 0
Reliability-caused wrong repair = 0
Reliability-caused false completion = 0
validation+holdout MCP intervention recall >= 90%
validation+holdout should_not_trigger false activation <= 5%
known-good/no-trigger median paired S idle-token delta vs M <= +2%
token-pair measurement coverage >= 90% before the token gate can resolve
```

Production-shadow `<=1/100 normal turns` is not inferred from controlled rows; it remains a separate downstream lane and appears in the report as `NOT_MEASURED` until shadow evidence is supplied by the campaign plan.

- [ ] **Step 5: Verify adjudication/scoring tests GREEN**

```powershell
python -m unittest test_routing_eval.RoutingEvalAdjudicationTests test_routing_eval.RoutingEvalScoringTests -v
```

Expected: PASS.

- [ ] **Step 6: Run old A/B scorer tests to protect shared scoring conventions**

```powershell
python -m unittest test_score_ab.py -v
```

Expected: PASS unchanged.

- [ ] **Step 7: Commit Task 4**

Stage only the routing harness files, run cached diff check, and commit with message `feat: score routing admission gates`.
### Task 5: Expose a deterministic prepare/collect/score CLI

**Files:**
- Modify: `benchmarks/harness/routing_eval.py`
- Modify: `benchmarks/harness/test_routing_eval.py`

**Produces:** A small CLI that can drive the future real Desktop campaign without hand-editing benchmark records.

- [ ] **Step 1: Add RED CLI/status tests**

Required subcommands are `prepare`, `collect`, and `score`.

`prepare` takes cases, output root, trial count, and seed. `collect` takes manifest, Desktop sessions root, output records, and optional report path. `score` takes normalized records, optional adjudication JSONL, and optional report path.

`collect` status must report expected, collected, invalid, and remaining trial counts plus the next manifest row's prompt/workspace pointers. Operator paths may appear in status; normalized records remain bounded.

Test malformed input returns process exit code 2 with a JSON error and no partial success report.
- [ ] **Step 2: Run CLI tests and observe RED**

```powershell
python -m unittest test_routing_eval.RoutingEvalCliTests -v
```

Expected: failures because argparse/status wiring is incomplete.

- [ ] **Step 3: Implement CLI wiring with existing JSON helpers**

Reuse `trigger_eval.load_jsonl`, `trigger_eval.write_jsonl`, and the existing JSON report style. Keep function APIs independently callable so tests do not need subprocesses for business logic.

The `collect` path must:
1. load and validate the manifest;
2. scan only rollouts carrying known case markers;
3. bind by marker + workspace hash;
4. normalize each matched trial;
5. write records in manifest sequence order;
6. report missing/invalid trials without fabricating rows.

The `score` path optionally merges adjudication before scoring, but writes the merged/scored report separately from raw normalized records.

- [ ] **Step 4: Verify CLI tests GREEN and run a synthetic end-to-end smoke**

Prepare a two-case temporary campaign, materialize synthetic S/M rollout JSONL, collect four records, score them, and assert the report has both arms and deterministic gate states.

Run:

```powershell
python -m unittest test_routing_eval.RoutingEvalCliTests test_routing_eval.RoutingEvalEndToEndTests -v
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Stage only the routing harness files, run cached diff check, and commit with message `feat: expose routing evaluation cli`.
### Task 6: Freeze the r4 contract/runbook and wire local verification

**Files:**
- Create: `docs/contracts/routing-eval-contract-r4.md`
- Create: `docs/runbooks/routing-eval-desktop.md`
- Modify: `scripts/verify-local.ps1`
- Modify: `benchmarks/harness/test_routing_eval.py`

**Produces:** Stable record/scoring semantics, a safe normal-Desktop operator procedure, and repo verification that always covers the new harness.

- [ ] **Step 1: Add RED repository-contract tests**

In `test_routing_eval.py`, add a repository test that reads the new contract/runbook paths and checks for the stable phrases/values that must not silently drift:
- S=`thin companion Skill + MCP` and M=`MCP-only self-routing`;
- Arm H excluded for the current Desktop build;
- `pre-failure MCP = 0`;
- `MCP intervention recall >= 90%`;
- controlled false activation `<= 5%`;
- production shadow `<= 1/100`;
- paired idle-token delta `<= +2%` and token coverage `>= 90%`;
- missing measurements remain missing;
- M setup is blocked rather than simulated when supported reversible Skill exclusion is unavailable;
- raw rollout evidence stays host-local.

The test should initially fail because the two docs do not exist.

- [ ] **Step 2: Run the doc-contract test and observe RED**

```powershell
python -m unittest test_routing_eval.RoutingEvalRepositoryContractTests -v
```

Expected: file-not-found or required-phrase assertion failure.
- [ ] **Step 3: Write `routing-eval-contract-r4.md` from the approved design**

The contract must define arm invariants, manifest identity `(case_id, trial_id, arm)`, neutral prompt pairing, boundary-detector kinds, normalized record fields, valid-trial versus valid-negative semantics, automatic metric denominators, adjudication fields, token/latency measurement rules, frozen admission gates, and train/validation/holdout immutability.

Do not copy the 254-line design verbatim. The contract is the concise stable interface that future code and campaign artifacts must satisfy.

- [ ] **Step 4: Write `routing-eval-desktop.md` as an operator runbook**

The runbook must require exact harness identity, explicit S and M canaries, fresh Desktop threads/workspaces, unchanged arm-neutral prompts, bounded collection after each batch, immediate stop on hard guardrail failure, and host-local raw rollout retention.The S canary must prove `powershell-reliability` is visible and the candidate MCP is reachable. The M canary must prove the Skill is absent while the same MCP candidate remains reachable. If a supported reversible M setup cannot be established, the runbook marks the campaign BLOCKED.

The runbook may reference the future `benchmarks/routing_eval/core_cases.json` path, but must state that the file is created and frozen only by the separate dataset/campaign plan after owner review.

- [ ] **Step 5: Update `scripts/verify-local.ps1` to cover the new harness**

Extend the existing Python unittest invocation to include `test_routing_eval.py`. Extend the existing `py_compile` invocation to include `routing_eval.py` and `test_routing_eval.py`. Do not weaken or remove any existing Rust/build/lifecycle/diff checks.
- [ ] **Step 6: Run doc-contract and focused compatibility tests GREEN**

```powershell
python -m unittest test_routing_eval.RoutingEvalRepositoryContractTests -v
python -m unittest test_routing_eval.py test_trigger_eval.py -v
```

Expected: PASS.

- [ ] **Step 7: Run repository local verification**

From repo root:

```powershell
pwsh.exe -NoProfile -File .\scripts\verify-local.ps1 -SkipBaseline
```

Expected: all existing Rust/Python/local checks pass, including the newly wired routing harness tests and compile checks.

- [ ] **Step 8: Commit Task 6**

Stage the two docs, `scripts/verify-local.ps1`, and any test-only repository contract assertions; run cached diff check; commit with message `docs: freeze r4 routing evaluation contract`.
### Task 7: Run the final compatibility/scope gate and hand off one-purpose review

**Files:**
- Verify only; no new feature files are introduced in this task.

**Produces:** Fresh evidence that the harness slice is complete, backward-compatible with the old trigger evaluator, and contains no product-runtime drift.

- [ ] **Step 1: Run focused routing tests from a clean process**

```powershell
Set-Location .\benchmarks\harness
python -m unittest test_routing_eval.py -v
```

Expected: PASS with zero failures/errors.

- [ ] **Step 2: Run compatibility scorers from a clean process**

```powershell
python -m unittest test_trigger_eval.py test_score_ab.py -v
```

Expected: PASS unchanged.

- [ ] **Step 3: Run full local verification again from repo root**

```powershell
Set-Location ..\..
pwsh.exe -NoProfile -File .\scripts\verify-local.ps1 -SkipBaseline
```

Expected: PASS.
- [ ] **Step 4: Verify scope and hygiene**

Use the exact implementation-base SHA supplied in the worker handoff and recorded in the canonical task. Inspect:

```powershell
git diff --check
git status --short --branch
if ([string]::IsNullOrWhiteSpace($env:PSR_IMPLEMENTATION_BASE_SHA)) { throw 'PSR_IMPLEMENTATION_BASE_SHA must be supplied by the Leader handoff' }
$base = $env:PSR_IMPLEMENTATION_BASE_SHA
git diff --name-only "$base..HEAD"
git log --oneline "$base..HEAD"
```

The changed-path list must be limited to:

```text
benchmarks/harness/routing_eval.py
benchmarks/harness/test_routing_eval.py
docs/contracts/routing-eval-contract-r4.md
docs/runbooks/routing-eval-desktop.md
scripts/verify-local.ps1
```

No `src/`, Rust tests, installed Skill, Hook, Codex settings, or release files may appear. `benchmarks/routing_eval/core_cases.json` must also be absent from this implementation slice.

- [ ] **Step 5: Prepare the review handoff**

Summarize exact base/HEAD, commits, changed files, focused/full verification outputs, and any residual missing-measurement limitations. Do not claim S or M product value; this slice proves harness behavior only.

Open/hand off one Draft PR for the harness slice if the repository's normal authenticated PR path is available under the project workflow. Workers do not merge.

---

## Execution Preconditions

Before Task 1 begins, the Leader must recover the canonical task again and record the exact approved plan commit as the implementation base. Use an isolated exact-SHA worktree/branch via the project's worktree workflow. Verify branch, `git rev-parse HEAD`, and clean status before the first RED test.

The implementation worker must read repo `AGENTS.md`, this plan, the approved design spec, and `docs/contracts/skill-trigger-eval-contract-v0.2.md`. Do not broaden into product runtime changes when a harness limitation is discovered; preserve evidence and return the limitation to the Leader.

## Follow-up Boundary

After this harness plan is implemented and independently reviewed, create a separate owner-reviewed plan for the 24-case naturalistic core, S/M canaries, controlled train/validation/holdout campaign, and passive/shadow evidence. The unseen holdout remains outside the train-visible repository surface until train-driven changes are frozen.

Only after the user selects S or M from that evidence does the project proceed to the harder repeated real Codex Desktop autonomous-vs-Reliability recovery A/B.