# r4 Evaluator-Owned World-State and Core v3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace agent/task-owned post-condition markers with evaluator-owned workspace-state grading, then rebuild the unapproved r4 core into a realistic 24-case v3 owner-review package.

**Architecture:** Keep `routing_eval.py` as the evidence reader/scorer and add a narrow declarative `workspace_state` post-condition evaluated directly against each bound disposable workspace. Keep routing boundary detection separate from final grading; then strengthen `routing_dataset.py` so only realistic, anti-coached, provenance-reviewed cases with independent completion evidence can enter the next owner freeze.

**Tech Stack:** Python 3.14 stdlib, existing r4 routing harness, Windows PowerShell/native fixtures, host-local campaign evidence, Git.

## Global Constraints

- Written design spec=`docs/superpowers/specs/2026-08-14-r4-evaluator-owned-world-state-design.md` at owner-approved commit `a289350251bb4dcf1c37f340485fd05203bd3cc5`.
- Work only in isolated worktree `D:/Work/powershell-agent-reliability/.worktrees/r4-core-v2-revision-20260814`, branch `docs/r4-core-v2-revision-20260814`.
- S=`thin companion Skill + same Reliability MCP`; M=`Skill absent + same Reliability MCP`; H remains excluded.
- Do not change Rust/MCP/Skill routing behavior, scorer thresholds, security/approval policy, release/publication state, or the approved 12-turn timeout calibration rule.
- This validation-exposed session may change evaluator/dataset validity only; it may never tune Skill/MCP routing after train evidence.
- Keep provisional core=`24 = 10 should_trigger / 10 should_not_trigger / 4 boundary`; train=`14`; sealed validation=`10`.
- No S/M canary, calibration, scored trial, shadow, or harder product A/B in this plan.

---### Task 1: Freeze and validate the `workspace_state` schema

**Files:**
- Modify: `benchmarks/harness/routing_eval.py:1-170`
- Modify: `benchmarks/harness/test_routing_eval.py:1-110,659-720`

**Interfaces:**
- Consumes: case `post_condition` objects from `load_cases()` / `prepare_campaign()`.
- Produces: `_post_condition_rule(case) -> dict`, `_workspace_relative_path(value) -> PurePosixPath`, and `_resolved_workspace_target(workspace, relative) -> Path`; accepts `none`, historical `tool_output_marker`, and new `workspace_state` rules; no pass/fail filesystem grading yet.

- [ ] **Step 1: Add RED tests for valid freezing and invalid schema/path input.**

Add tests named `test_prepare_freezes_workspace_state_rule`, `test_prepare_rejects_workspace_state_absolute_path`, `test_prepare_rejects_workspace_state_parent_escape`, `test_prepare_rejects_workspace_state_bad_sha256`, and `test_prepare_rejects_workspace_state_unknown_check`.

```python
def _workspace_state(self):
    return {"kind": "workspace_state", "mode": "all", "checks": [
        {"kind": "file_exists", "path": "result.txt"},
        {"kind": "file_size", "path": "result.txt", "min_bytes": 1, "max_bytes": 64},
    ]}
```

- [ ] **Step 2: Run the focused tests and confirm RED.**

Run: `python -m unittest test_routing_eval.RoutingEvalReviewPostConditionTests -v`
Expected: FAIL because `workspace_state` is not in `POST_CONDITION_KINDS` and no schema validation exists.
- [ ] **Step 3: Implement the narrow declarative schema.**

In `routing_eval.py`, add constants and lexical validation only:

```python
POST_CONDITION_KINDS = {"none", "tool_output_marker", "workspace_state"}
WORKSPACE_CHECK_KINDS = {"file_exists", "file_absent", "directory_exists", "file_sha256", "file_size"}
MAX_POST_CONDITION_CHECKS = 32
MAX_WORKSPACE_PATH_BYTES = 32_768
MAX_POST_CONDITION_HASH_BYTES = 64 * 1024 * 1024


def _workspace_relative_path(value: str) -> pathlib.PurePosixPath:
    if not isinstance(value, str) or not value or len(value.encode("utf-8")) > MAX_WORKSPACE_PATH_BYTES or "\0" in value:
        raise ValueError("workspace-state path must be non-empty, bounded, and NUL-free")
    windows = pathlib.PureWindowsPath(value)
    path = pathlib.PurePosixPath(value.replace("\\", "/"))
    if windows.drive or windows.is_absolute() or path.is_absolute() or ".." in path.parts:
        raise ValueError("workspace-state path must stay relative to the trial workspace")
    return path


def _resolved_workspace_target(workspace: pathlib.Path, relative: str) -> pathlib.Path:
    base = workspace.resolve()
    target = (base / _workspace_relative_path(relative)).resolve(strict=False)
    if target != base and base not in target.parents:
        raise ValueError("workspace-state path escapes trial workspace")
    return target
```

`workspace_state` requires `mode in {"all", "any"}`, 1..32 checks, only the five allowed kinds, valid bounded relative paths, 64-hex `expected_sha256`, and optional non-negative `file_size` bounds with `min_bytes <= max_bytes` when both exist. Like existing Rust `verify_result`, a `file_size` check with both bounds omitted still verifies that the target is a regular file. Reject booleans where an integer is required.

After `_write_fixture()` materializes each S/M workspace, `prepare_campaign()` must resolve every frozen workspace-state target against that exact workspace and reject any target already escaping through a fixture symlink/junction before writing the manifest. Task 2 repeats the same containment check at grading time to defend against agent-created redirects.

- [ ] **Step 4: Run post-condition prepare tests; expect GREEN.**

Run: `python -m unittest test_routing_eval.RoutingEvalReviewPostConditionTests -v`
Expected: all prepare/schema tests PASS while historical marker tests remain unchanged.

- [ ] **Step 5: Run `git diff --check` and commit Task 1.**

```powershell
git add benchmarks/harness/routing_eval.py benchmarks/harness/test_routing_eval.py
git commit -m "test: freeze evaluator workspace-state schema"
```
### Task 2: Grade bounded workspace state independently of rollout output

**Files:**
- Modify: `benchmarks/harness/routing_eval.py:241-365`
- Modify: `benchmarks/harness/test_routing_eval.py:659-777`

**Interfaces:**
- Produces: `evaluate_workspace_state(manifest_row: dict) -> dict` and extends `evaluate_post_condition(rows, manifest_row)`.
- Result keys: `passed`, `index`, `timestamp`, `invalid_reason`, `source`, `checks`.

- [ ] **Step 1: Add RED tests proving task-owned output cannot spoof success.**

Add `test_workspace_state_ignores_agent_pass_marker_when_file_is_wrong`:

```python
manifest["post_condition"] = {
    "kind": "workspace_state", "mode": "all",
    "checks": [{"kind": "file_sha256", "path": "result.txt", "expected_sha256": hashlib.sha256(b"READY\n").hexdigest()}],
}
(workspace / "result.txt").write_text("STALE\n", encoding="utf-8")
rows = _base_rollout("P06-T01", workspace, skill_visible=False) + [_output("x", "POST-CONDITION: PASS", "2026-08-14T00:00:05Z")]
record = routing_eval.extract_trial(rows, pathlib.Path("p06.jsonl"), manifest)
self.assertFalse(record["post_condition_passed"])
self.assertEqual(record["post_condition_evidence_source"], "evaluator_workspace")
```

Also add tests for file exists/absent/directory, hash match+mismatch, size bounds, `all` vs `any`, missing file => valid `False` rather than invalid trial, and a bounded-hash failure by temporarily lowering `MAX_POST_CONDITION_HASH_BYTES` in the test and restoring it in `finally`. Add `test_workspace_state_failure_does_not_create_boundary`: with `boundary_detector={"kind":"none"}` and a failing workspace rule, assert `eligible_boundary_index is None` while `post_condition_passed is False`.

- [ ] **Step 2: Run the new workspace evaluator tests; expect RED.**

Run: `python -m unittest test_routing_eval.RoutingEvalReviewPostConditionTests -v`
Expected: FAIL because workspace-state evaluation/record fields do not exist.
- [ ] **Step 3: Implement evaluator-owned bounded filesystem checks.**

Reuse Task 1 `_resolved_workspace_target()` at grading time so an agent-created symlink/junction cannot redirect a relative rule outside the trial workspace. Re-resolve every target immediately before each check; do not trust the prepare-time path result.

Implement bounded hashing with 64 KiB chunks and fail closed if the file is over 64 MiB. For each check return only bounded evidence: `index`, `kind`, `passed`, `status`, `path_sha256`, optional `observed_exists`, `observed_is_directory`, `observed_size_bytes`, `observed_sha256`, `error_kind`. Hash normalized resolved path text for `path_sha256`; never store the raw absolute path in normalized records.

`all` passes only if every check passes; `any` passes if at least one check passes. Missing/wrong artifact/type/hash/size is a normal failed check. Ordinary filesystem access errors (including permission/read failures or the 64 MiB hash cap) become bounded failed-check evidence with `error_kind`; they do not silently become success and do not invalidate an otherwise well-formed trial. Schema corruption or path escape is `invalid_reason="post_condition_invalid"`.

- [ ] **Step 4: Extend normalized trial evidence.**

Add fields in `extract_trial()`:

```python
"post_condition_evidence_source": post_condition.get("source"),
"post_condition_checks": post_condition.get("checks") or [],
```

For `workspace_state`, `index` and `timestamp` stay `None`. For legacy `tool_output_marker`, set `source="tool_output_legacy"`; for `none`, source is `None`.

- [ ] **Step 5: Run workspace/post-condition tests; expect GREEN.**

Run: `python -m unittest test_routing_eval.RoutingEvalReviewPostConditionTests -v`
Expected: all workspace and historical compatibility tests PASS.

- [ ] **Step 6: Commit Task 2.**

```powershell
git add benchmarks/harness/routing_eval.py benchmarks/harness/test_routing_eval.py
git commit -m "feat: grade routing tasks from workspace state"
```
### Task 3: Prove collection/scoring uses workspace state, not emitted markers

**Files:**
- Modify: `benchmarks/harness/test_routing_eval.py:720-777`
- Modify: `benchmarks/harness/routing_eval.py:367-430` only if the RED end-to-end test exposes an integration bug.

**Interfaces:**
- Consumes: manifest rows already bound by `(case_key, workspace_sha256)` in `collect_rollouts()`.
- Produces: end-to-end evidence that matched S/M workspaces are graded independently after rollout binding.

- [ ] **Step 1: Replace the marker-based end-to-end test with a workspace-state test.**

Create `test_prepare_collect_score_uses_evaluator_workspace_state` with one validation case whose frozen rule hashes `result.txt`. For both S and M rollouts, append the same fake tool output text `POST-CONDITION: PASS`; write correct bytes only to S workspace and stale bytes to M workspace.

Expected assertions:

```python
self.assertEqual({row["arm"]: row["post_condition_passed"] for row in records}, {"S": True, "M": False})
self.assertTrue(all(row["post_condition_evidence_source"] == "evaluator_workspace" for row in records))
self.assertEqual(report["arms"]["S"]["lanes"]["admission"]["deterministic_post_condition_completion_rate"], 1.0)
self.assertEqual(report["arms"]["M"]["lanes"]["admission"]["deterministic_post_condition_completion_rate"], 0.0)
```

- [ ] **Step 2: Run the end-to-end class and confirm RED only if integration is incomplete.**

Run: `python -m unittest test_routing_eval.RoutingEvalReviewPostConditionEndToEndTests -v`
Expected after Task 2: PASS. If RED, fix only manifest binding/evaluation integration; do not change scoring denominators.

- [ ] **Step 3: Run all routing evaluator tests.**

Run: `python -m unittest test_routing_eval.py -v`
Expected: existing temporal/pair/cost/adjudication/scoring behavior stays GREEN.

- [ ] **Step 4: Commit Task 3 test migration.**

```powershell
git add benchmarks/harness/test_routing_eval.py benchmarks/harness/routing_eval.py
git commit -m "test: prove evaluator-owned post-condition collection"
```
### Task 4: Freeze evaluator-owned semantics in contract and runbook

**Files:**
- Modify: `docs/contracts/routing-eval-contract-r4.md`
- Modify: `docs/runbooks/routing-eval-desktop.md`
- Modify: `benchmarks/harness/test_routing_eval.py:580-610`

**Interfaces:**
- Produces: repository contract/runbook language matching the implemented `workspace_state` semantics and legacy-only marker boundary.

- [ ] **Step 1: Add RED repository-contract assertions.**

Update `test_repository_contract_and_runbook_freeze_r4_invariants` to require these phrases in the combined docs:

```python
required = (
    "workspace_state",
    "evaluator-owned",
    "relative paths under the exact trial workspace",
    "tool_output_marker is legacy-only",
    "final grading does not create an earlier routing boundary",
)
```

Also assert the contract no longer says new deterministic post-conditions are limited to only `none` or `tool_output_marker`.

- [ ] **Step 2: Run the repository-contract test; expect RED.**

Run: `python -m unittest test_routing_eval.RoutingEvalRepositoryContractTests -v`
Expected: FAIL because docs still freeze marker-based post-condition semantics.

- [ ] **Step 3: Update contract/runbook.**

Contract must state: new core artifact tasks use `workspace_state`; allowed five checks; relative-contained paths; bounded evidence; legacy marker compatibility is not eligible for new-core admission; boundary detection and final grading are separate. Runbook must tell operators that collection reads final workspace state after exact rollout binding and never runs a verifier command or asks the agent to self-report pass/fail.

- [ ] **Step 4: Re-run repository-contract test and all routing tests.**

Run: `python -m unittest test_routing_eval.RoutingEvalRepositoryContractTests -v`
Run: `python -m unittest test_routing_eval.py -v`
Expected: PASS.

- [ ] **Step 5: Commit Task 4.**

```powershell
git add docs/contracts/routing-eval-contract-r4.md docs/runbooks/routing-eval-desktop.md benchmarks/harness/test_routing_eval.py
git commit -m "docs: freeze evaluator-owned routing completion"
```
### Task 5: Enforce v3 dataset quality and anti-coaching rules

**Files:**
- Modify: `benchmarks/harness/routing_dataset.py:1-120`
- Modify: `benchmarks/harness/test_routing_dataset.py:1-190`

**Interfaces:**
- Consumes: selected cases plus pre-outcome review rows.
- Produces: `validate_external_validity(cases, reviews)` that rejects legacy completion markers, weak `none` rationales, missing research-critical failure families, incomplete visible-surface anti-coaching, and missing provenance basis.

- [ ] **Step 1: Add the new required review metadata and RED tests.**

Extend `REVIEW_REQUIRED` with:

```python
"provenance_basis",
"post_condition_category",
"first_failure_preview",
```

Use exactly these allowed `post_condition_category` values:

```python
POST_CONDITION_NONE_CATEGORIES = {
    "explanation_only", "diagnosis_only", "intentional_cancel_no_recovery", "unknown_routing_only"
}
POST_CONDITION_CATEGORIES = POST_CONDITION_NONE_CATEGORIES | {"mechanical_workspace_state"}
```

Add RED tests that reject: selected `tool_output_marker`; `none` with category outside that set; missing `provenance_basis`; missing `environment-staleness`, `native-child-status`, `real-timeout-cancellation`, or successful-native no-trigger coverage; and taxonomy-shaped leakage in prompt/filename/fixture/first-failure preview.

- [ ] **Step 2: Run dataset tests and confirm RED.**

Run: `python -m unittest test_routing_dataset.ExternalValidityTests -v`
Expected: failures for the new requirements because the validator does not implement them yet.
- [ ] **Step 3: Implement full visible-surface anti-coaching and coverage checks.**

Build the machine-scanned visible text from prompt + relative filenames + fixture text + frozen first command + boundary marker + sanitized pre-outcome `first_failure_preview`. Scan only narrow workflow-leading phrases plus taxonomy-shaped labels such as `CWD_FAIL`, `EXPORT_MISSING`, `PROBE_TIMEOUT`, `POST-CONDITION: PASS`, and `POST-CONDITION: FAIL`; do not ban generic words like `error`, `check`, `verify`, or `timeout`.

Require these selected-core families by group and construct the scanned visible surface explicitly:

```python
required_trigger = {"command-resolution", "environment-staleness", "native-child-status", "real-timeout-cancellation"}
required_no_trigger = {"native-semantic-nonzero", "native-success", "pre-failure-mention", "historical-failure-context"}
TAXONOMY_SHAPED_LABELS = ("cwd_fail", "export_missing", "probe_timeout", "post-condition: pass", "post-condition: fail")

def _visible_surface(case: dict, review: dict) -> str:
    files = case.get("files") or {}
    detector = case.get("boundary_detector") or {}
    parts = [case.get("prompt", ""), case.get("expected_first_command_fragment", ""), detector.get("marker", ""), review.get("first_failure_preview", "")]
    for relative, content in sorted(files.items()):
        parts.extend((relative, content))
    return "\n".join(part for part in parts if isinstance(part, str)).casefold()
```

For every non-`none` selected case require `post_condition.kind == "workspace_state"` and `post_condition_category == "mechanical_workspace_state"`. For `none`, require one of the four allowed semantic categories plus a nonempty rationale. The machine gate validates the explicit category; the owner/reviewer, not string heuristics, decides whether the rationale really matches that category.

- [ ] **Step 4: Keep provenance validation honest.**

Require nonempty `provenance_cluster` and `provenance_basis`, continue forbidding cross-lane cluster reuse, but do not infer semantic correctness from matching cluster names. Implement only the structural guard:

```python
for review in reviews:
    if not isinstance(review.get("provenance_basis"), str) or not review["provenance_basis"].strip():
        raise ValueError(f"provenance_basis required for case {review.get('case_id')}")
```

Owner/reviewer decides whether the stated basis is truly same-root provenance.

- [ ] **Step 5: Update test fixtures to use `workspace_state` and complete v3 metadata.**

For generic test artifact cases use a minimal rule such as:

```python
{"kind": "workspace_state", "mode": "all", "checks": [{"kind": "file_exists", "path": "result.txt"}]}
```

Use `post_condition_category="mechanical_workspace_state"`; explanation/UNKNOWN fixtures use `none` with one of the four allowed categories.

- [ ] **Step 6: Run dataset and combined routing tests.**

Run: `python -m unittest test_routing_dataset.py -v`
Run: `python -m unittest test_routing_dataset.py test_routing_eval.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit Task 5.**

```powershell
git add benchmarks/harness/routing_dataset.py benchmarks/harness/test_routing_dataset.py
git commit -m "test: enforce r4 core v3 evidence quality"
```
### Task 6: Execute the sealed host-local core-v3 revision

**Files:**
- Read only in this validation-exposed Leader: `D:/Codex/evidence/ai-boundary-lab/r4-naturalistic-campaign-v3-20260814/private-case-revision-plan.md`
- Host-local outputs stay under: `D:/Codex/evidence/ai-boundary-lab/r4-naturalistic-campaign-v3-20260814/`
- Repo: no train/validation case data, exact prompt/fixture details, first-failure previews, or validation provenance are committed.

**Interfaces:**
- Consumes: the completed evaluator/dataset-quality implementation from Tasks 1-5 plus the sealed host-local case-revision plan.
- Produces: one pre-outcome proposed core with exact quotas `24 = 10 should_trigger / 10 should_not_trigger / 4 boundary`, train=`14`, validation=`10`, and host-local owner-review evidence.

- [ ] **Step 1: Confirm the validation firewall before opening private case material.**

The executor must be this already validation-exposed dataset/evaluator Leader or another explicitly validation-exposed read/write dataset session. A future train-only routing-modification worker must not read the private plan or any sealed validation file.

- [ ] **Step 2: Execute the private case-revision plan exactly.**

Use `D:/Codex/evidence/ai-boundary-lab/r4-naturalistic-campaign-v3-20260814/private-case-revision-plan.md`. That host-local plan contains the exact case replacements, prompts, fixtures, first-failure qualification commands, provenance mapping, post-condition rules, deterministic seed, and evidence-hash list intentionally omitted here.

- [ ] **Step 3: Run the frozen-core validator without copying validation into the repository.**

Run the exact `routing_dataset.py validate-freeze` command from the private plan. Expected: core=`24`, train=`14`, validation=`10`, required external-validity families present, no legacy marker completion in selected artifact cases, complete review metadata, and no provenance cluster crossing lanes.

- [ ] **Step 4: Preserve only bounded references in the canonical task.**

Write back the exact repo HEAD, host-local evidence root, and SHA-256 hashes for the candidate/core/train/sealed-validation/review artifacts. Do not copy raw validation prompts, fixtures, first-failure previews, or post-condition specifics into the canonical task or repo docs.

### Task 7: Run final verification and stop at owner review

**Files:**
- Repo changes from Tasks 1-5 only.
- Host-local owner-review/hashes from Task 6 only.

- [ ] **Step 1: Run focused routing tests.**

Run: `python -m unittest discover -s .\benchmarks\harness -p 'test_routing_*.py' -v`
Expected: PASS with zero failures.

- [ ] **Step 2: Run repository-wide verification.**

Run: `pwsh.exe -NoProfile -File .\scripts\verify-local.ps1 -SkipBaseline`
Expected: PASS for cargo test/check, release build/lifecycle, benchmark scorer tests, Python compile, and diff check.

- [ ] **Step 3: Verify Git hygiene.**

Run: `git diff --check` and `git status --short`. Expected: clean after all one-purpose commits; no case-data or validation files tracked.

- [ ] **Step 4: STOP.**

Update the single canonical task to `r4-core-v3-proposed-awaiting-owner-review`. Do not commit train cases, reveal sealed validation to a routing-tuning worker, run S/M setup canaries, run the 12 real calibration turns, start scored trials, shadow, or harder product A/B.

## Self-review checklist

- [ ] Every spec requirement maps to Tasks 1-7 or the sealed private case-revision plan.
- [ ] New core artifact completion cannot be established by agent/task-owned output markers.
- [ ] Workspace checks are bounded, relative, contained, read-only, and revalidated at collection time.
- [ ] Boundary detection remains separate from final grading.
- [ ] `tool_output_marker` remains historical compatibility only and cannot admit a new artifact-scored core row.
- [ ] Dataset quality checks cover full visible-surface anti-coaching, required real failure families, semantic `none` categories, and provenance basis.
- [ ] Exact future validation prompts/fixtures/post-condition specifics never enter the train-visible repository plan.
- [ ] No Skill/MCP routing behavior, scorer threshold, security setting, release/publication state, or approved timeout rule changes in this plan.
- [ ] No S/M outcome is used in candidate construction or qualification.
- [ ] Execution stops at owner case review.
