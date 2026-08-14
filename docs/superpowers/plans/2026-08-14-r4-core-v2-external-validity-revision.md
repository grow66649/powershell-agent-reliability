# r4 Core v2 External-Validity Revision Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unapproved v1 core proposal with a more realistic, anti-coaching 24-case v2 owner-review package without exposing S/M outcomes or starting the campaign.

**Architecture:** Keep the accepted routing harness and 24-case experiment size. Add narrow dataset-quality validation in `routing_dataset.py`, rebuild candidates host-locally from pre-outcome material plus research-backed Windows cases, then stop at owner review before any train-case commit or Desktop canary.

**Tech Stack:** Python 3.14 stdlib, existing routing dataset/eval harness, Windows PowerShell/native fixtures, host-local evidence, Git.

## Global Constraints

- Worktree base=`f608315c10bda7ca5dc0467bfa2ba6c152499511`; accepted product main=`3ea553262d6d13462bde698a321b06d5db4d786c`.
- Design=`docs/superpowers/specs/2026-08-14-r4-core-v2-external-validity-revision.md`.
- Core stays `10 should_trigger / 10 should_not_trigger / 4 boundary`; train=`6/6/2`, validation=`4/4/2`.
- Validation remains sealed from future train-driven routing modification.
- No S/M outcome may be read while constructing or qualifying v2 candidates.
- No Rust/MCP/Skill/scorer-threshold/Hook/security/release/publication change.
- Do not manufacture ACL/sandbox failures by weakening protections.
- Stop at owner review; no train-case commit, canary, calibration, or scored trial in this plan.

---
### Task 1: Enforce v2 external-validity rules in the dataset validator

**Files:**
- Modify: `benchmarks/harness/routing_dataset.py`
- Modify: `benchmarks/harness/test_routing_dataset.py`

**Produces:** `validate_external_validity(cases, reviews)` that rejects benchmark-coached prompts, missing required coverage, misclassified hard negatives, and unjustified `post_condition=none` rows.

- [ ] **Step 1: Add RED tests** for these failures: prompt contains `if it fails, recover`; no selected `command-resolution` trigger; no selected `native-semantic-nonzero` no-trigger; `pre-failure-mention` or `historical-failure-context` review is not `should_not_trigger`; `post_condition=none` lacks a non-empty `post_condition_rationale`.
- [ ] **Step 2: Run** `python -m unittest test_routing_dataset.ExternalValidityTests -v` from `benchmarks/harness`; expect RED because the API does not exist.
- [ ] **Step 3: Implement** a fixed lower-case coaching phrase tuple limited to workflow-leading phrases (`if it fails`, `recover conservatively`, `repair only`, `diagnose the local cause`, `verify before finishing`) and the coverage/review checks above. Do not reject ordinary words such as `check`, `verify`, or `report` by themselves.
- [ ] **Step 4: Make `validate_frozen_core()` call `validate_external_validity()`** after quota/review/provenance checks so the CLI freeze gate cannot bypass v2 quality checks.
- [ ] **Step 5: Run** `python -m unittest test_routing_dataset.py -v`; expect all tests PASS.
- [ ] **Step 6: Run** `git diff --check`; commit only the validator/tests as `test: enforce r4 core external validity`.

### Task 2: Build the v2 candidate pool host-locally without S/M outcomes

**Files:**
- Host-local create: `D:/Codex/evidence/ai-boundary-lab/r4-naturalistic-campaign-v2-20260814/build_candidate_pool_v2.py`
- Host-local outputs: candidate/review/core/train/validation JSON/JSONL and freeze summaries under the same root.
- Repo: no case-data commit in this task.

- [ ] **Step 1: Copy only pre-outcome v1 candidate definitions/reviews as source material.** Do not read rollout, score, adjudication, token, latency, S/M activation, or winner evidence.
- [ ] **Step 2: Set v2 seed=`2026081402` and rebuild the pool as 26 provenance clusters / 52 candidates:** 10 trigger clusters, 12 no-trigger clusters, 4 boundary clusters; two variants per cluster.
- [ ] **Step 3: Reclassify the `BP` pre-failure-mention and `BH` historical-failure clusters to `should_not_trigger`.** They are hard false-activation controls, not score-free boundaries.
- [ ] **Step 4: Keep `BT` task-vs-helper and a safety/domain `BS` cluster as boundaries; add `BX` explicit-diagnosis-after-observed-failure and `BC` intentional-cancel/no-recovery-request boundary clusters so four distinct boundary provenance clusters exist.
- [ ] **Step 5: Make direct command resolution mandatory:** retain the TE provenance family but make the selected variant `TE-B`-equivalent: the task invokes a supplied helper by name, it is absent from PATH, and the safe repair uses the local supplied helper without global PATH mutation. Review family=`command-resolution`.
- [ ] **Step 6: Replace one `NS` semantic-nonzero variant with real Robocopy semantics:** copy a small disposable `src` tree to `dst` using `robocopy`; a documented nonzero success status must remain `should_not_trigger`. Review family=`native-semantic-nonzero`. Do not use a custom wrapper whose only purpose is to return 1.
- [ ] **Step 7: Rewrite prompts to goal-only language.** For trigger fixtures, state the requested artifact/action and any genuinely user-supplied first command; remove instructions telling the agent to diagnose, recover, repair, call Reliability, or perform the intended workflow after failure.
- [ ] **Step 8: Add `post_condition_rationale` and `anti_coaching_check` to every review row.** `post_condition=none` is allowed only for explanation-only, diagnosis-only, or UNKNOWN/routing-only cases and the rationale must say which one.
- [ ] **Step 9: Keep sandbox/ACL coverage as an explicit gap.** Do not add a candidate that changes ACLs, sandbox policy, profiles, or global environment.
- [ ] **Step 10: Run the host-local builder and verify candidate counts, two variants per provenance cluster, zero S/M outcome fields, and no private host data in candidate content.**

### Task 3: Deterministically select and validate the proposed v2 core

**Files:**
- Host-local modify: `build_candidate_pool_v2.py`
- Read-only repo validator: `benchmarks/harness/routing_dataset.py`

**Selection contract:** one variant per selected provenance cluster. All 10 trigger clusters are selected; all 4 boundary clusters are selected. For no-trigger, require `BP`, `BH`, `NS`, `NW`, `NG`, `NB`, `NA`, and `NV`, then choose exactly two of `NC`, `NE`, `NN`, `NI` using seed `2026081402`.

- [ ] **Step 1: Force the coverage-critical selected variants:** direct-resolution `TE-B` equivalent and Robocopy semantic-nonzero `NS` variant. All other selected cluster variants use the recorded seed without looking at outcomes.
- [ ] **Step 2: Assign train/validation by group with the same seed** to exact quotas train=`6/6/2`, validation=`4/4/2`; no provenance cluster may cross lanes.
- [ ] **Step 3: Write host-local `train_cases.json`, `train_review.jsonl`, sealed `validation_cases.json`, `validation_review.jsonl`, `core_selected_preview.json`, and freeze summary.**
- [ ] **Step 4: Run** `python benchmarks/harness/routing_dataset.py validate-freeze ... --seed 2026081402 ...`; expect PASS.
- [ ] **Step 5: Run an explicit coaching scan and coverage report** showing zero banned workflow-leading phrases in selected prompts, direct command-resolution present, Robocopy semantic-nonzero present, BP/BH hard negatives in false-activation scoring, four distinct boundary clusters, and every `post_condition=none` row justified.
- [ ] **Step 6: Re-run focused repo tests** `python -m unittest test_routing_dataset.py test_routing_eval.py -v`; expect PASS.
### Task 4: Produce the owner-review package and stop

**Files:**
- Host-local create: `owner-review-v2.md`
- Host-local create: `old-vs-v2-summary.md`
- Repo: no train/validation case-data commit.

- [ ] **Step 1: Generate `owner-review-v2.md`** with one plain-language row per proposed core case: what the user is asking, what hidden/visible condition makes it useful, why Reliability should/should not activate, and how success is checked.
- [ ] **Step 2: Generate `old-vs-v2-summary.md`** listing every v1 selected case as `keep`, `rewrite`, `replace`, `reclassify`, or `drop`, with the v2 case/family and evidence-based rationale.
- [ ] **Step 3: Record hashes** for candidate pool, selected core, train package, sealed validation package, both review files, and the builder script.
- [ ] **Step 4: Run** `git diff --check`, `git status --short`, and the focused dataset/routing tests. The repo diff in this plan may contain only the v2 spec/plan plus validator/test changes; host-local case data stays outside the repo.
- [ ] **Step 5: Commit the repo-only v2 design/validator slice** with one-purpose commits after tests pass. Do not commit train cases yet.
- [ ] **Step 6: STOP at owner review.** Do not expose validation to a routing-tuning worker, do not run S/M setup canaries, do not run the 12-turn calibration, and do not start scored trials.

## Self-review checklist

- [ ] The plan preserves 24-case controlled-core size and sealed-validation policy.
- [ ] Required direct command-resolution and real native semantic-nonzero cases are machine-checked.
- [ ] Hard negatives affect the false-activation denominator instead of being hidden in boundary.
- [ ] Prompt coaching is mechanically rejected using narrow phrases, not a broad word blacklist.
- [ ] No sandbox/ACL weakening is introduced.
- [ ] No S/M outcomes are used for candidate qualification or selection.
- [ ] No unfinished implementation step or fill-later instruction remains in the plan.
