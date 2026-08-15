# r4 Evaluator-Owned World-State and Core v3 Design

Status: Owner approved Approach A on 2026-08-14. This design replaces agent/task-owned post-condition markers for future artifact-scored r4 cases and revises the unapproved v2 core. It does not authorize S/M canaries or scored trials.

## Goal

Make task-completion scoring independent of Codex/task output by having the evaluation harness inspect the disposable workspace itself after the turn, while revising weak v2 cases and anti-coaching/provenance controls before a final 24-case owner freeze.

## Fixed boundaries

- Accepted product/harness baseline remains `main@3ea553262d6d13462bde698a321b06d5db4d786c`.
- Current isolated design worktree starts at `docs/r4-core-v2-revision-20260814@976a0c2bf47ed1ef22b5825b165f93c8194e73b5`.
- S=`thin companion Skill + same Reliability MCP`; M=`Skill absent + same Reliability MCP`; H remains excluded.
- Codex Desktop/app-server continues to own normal command/process/sandbox execution.
- The evaluator is an evidence reader/scorer, not a second shell runner and not a repair engine.
- This validation-exposed Leader may change dataset/evaluator validity only; it may never perform later train-driven Skill/MCP routing tuning.
- Keep the provisional core at `24 = 10 should_trigger / 10 should_not_trigger / 4 boundary`, train=`14`, sealed validation=`10` unless the owner later changes experiment size.
- Keep the approved 12-turn calibration shape and timeout rule unchanged.

## Decision: evaluator-owned workspace state

Future artifact-scored cases use `post_condition.kind="workspace_state"`. The frozen rule is stored outside the agent workspace in the campaign manifest. After a rollout is bound to its exact manifest row, `routing_eval.py` evaluates the rule directly against that trial's disposable workspace.

The agent, fixture, shell output, assistant prose, Reliability Skill, and Reliability MCP cannot declare the final task pass/fail bit. A script printing `PASS`, `READY`, `*_OK`, or any other marker is irrelevant unless the frozen evaluator-owned workspace rule independently matches the resulting world state.
## Workspace-state schema

The narrow declarative schema mirrors the already accepted `verify_result` file-state semantics instead of inventing a general assertion language:

```json
{
  "kind": "workspace_state",
  "mode": "all",
  "checks": [
    {"kind": "file_exists", "path": "result.txt"},
    {"kind": "file_sha256", "path": "result.txt", "expected_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}
  ]
}
```

Allowed `mode` values: `all`, `any`.

Allowed checks:
- `file_exists(path)`;
- `file_absent(path)`;
- `directory_exists(path)`;
- `file_sha256(path, expected_sha256)`;
- `file_size(path, min_bytes?, max_bytes?)`.

No arbitrary command, script, regex, Python expression, PowerShell expression, network request, registry read, process launch, environment dump, or plugin callback is allowed in a post-condition rule.

All post-condition paths must be non-empty relative paths under the exact trial workspace. Absolute paths, `..`, and NULs are rejected when the case is frozen. At grading time the evaluator resolves the workspace and target again and fails closed if the resolved target escapes the resolved workspace, including through links/reparse points. SHA-256 reads are capped at 64 MiB, matching the existing Rust verification boundary.
## Collection and normalized evidence

`prepare_campaign()` validates and freezes the declarative post-condition into the manifest before any Desktop turn. `collect_rollouts()` first binds rollout identity using the existing case/workspace hash rules, then evaluates workspace state from the manifest's workspace path.

For `workspace_state`, normalized evidence records:
- `post_condition_kind="workspace_state"`;
- `post_condition_passed=true|false`;
- `post_condition_evidence_source="evaluator_workspace"`;
- bounded per-check results: check index, kind, passed/status, hashed path identity, optional observed existence/type/size/SHA-256, and bounded error kind;
- rollout evidence index/timestamp remain `null` because final grading is out-of-band world-state evidence rather than an agent tool output.

Missing expected files, wrong hashes, wrong sizes, or wrong file/directory type are valid task failures, not protocol-invalid trials. Invalid post-condition schema, path escape, manifest/workspace identity failure, duplicate binding, or evaluator configuration corruption invalidate the trial. Ordinary filesystem access errors are preserved as bounded failed check evidence rather than silently converted to success.

`tool_output_marker` remains readable only for backward-compatible historical harness fixtures while the transition is tested; the revised dataset validator forbids it for every newly admitted core case. New core cases use `workspace_state` or `none`, so admission cannot depend on agent/task-owned pass/fail markers.

## Boundary detection stays separate from final grading

Eligible routing boundary and final task completion remain different facts. The evaluator-owned final workspace check is not retroactively treated as an earlier routing boundary.

`first_command_nonzero` remains valid for real observable command/native failure. `tool_output_contains` may be used only for a natural, sanitized runtime observation that the agent actually saw; it must not use evaluator labels such as `POST-CONDITION: FAIL`, taxonomy names, or hidden answer markers.

For exit-zero false-completion cases, routing eligibility must come from an ordinary mismatch the agent actually sees during the turn, such as natural task output reporting the wrong artifact state or an observation explicitly required by the user goal. The hidden evaluator check may grade final completion but must not manufacture an earlier routing boundary retroactively.
## Revised case-quality rules

The next proposed core keeps the strong v2 controls and adds the independent review corrections:

1. Replace `TT-A` with a real bounded process wait/timeout/cancellation fixture. The fixture must terminate/clean up the child and prove no orphan process remains; no fake `PROBE_TIMEOUT` label may stand in for elapsed-time behavior.
2. Replace `TA-A` with a safe process-local environment-staleness/executable-identity fixture. A supplied script may alter only its own process environment to resolve a bundled stale helper before the intended helper. No global PATH/profile/ACL/sandbox mutation is allowed.
3. Keep `TE-B` as command/PATH-resolution coverage but do not label it environment staleness.
4. Replace `TN-B` with a real native child-status propagation case, such as a supplied PowerShell wrapper invoking a native Windows child that genuinely fails and propagating the real child status.
5. Keep `NS-B` as the real Robocopy semantic-nonzero no-trigger control.
6. Add/retain a successful native-execution no-trigger control so native process presence alone does not imply Reliability eligibility.
7. Mechanically verifiable checksum/version/artifact tasks must use `workspace_state`; rewrite the task to leave a checkable artifact when necessary rather than using `post_condition=none` for convenience.
8. `post_condition=none` is limited to explanation-only, diagnosis-only, intentional-cancel/no-recovery, or UNKNOWN/routing-only tasks, with an explicit semantic rationale matching one of those categories.

## Anti-coaching and provenance

Anti-coaching review covers the whole agent-visible surface, not prompt text alone: prompt, relative filenames, fixture file contents, frozen first command, boundary marker text, and a pre-outcome preview of deterministic first-failure stdout/stderr when the fixture can be safely probed.

Machine checks reject known workflow-leading phrases and taxonomy-shaped answer labels. Human review still decides whether ordinary wording or fixture structure indirectly reveals the intended diagnosis. Runtime probe previews are generated before S/M outcome visibility and stay with host-local candidate-review evidence.

`provenance_cluster` means true shared root incident/template/fixture lineage, not merely similar failure mechanism. Every review row must state a concise `provenance_basis`. The validator can enforce lane isolation and review completeness; it must not claim semantic provenance correctness solely from matching strings. Human owner/reviewer acceptance remains authoritative for true-root grouping.
## Data flow and isolation

1. Candidate authoring/review freezes prompt, fixture, group/lane, boundary detector, workspace-state rule, provenance basis, and anti-coaching evidence before S/M outcomes exist.
2. `prepare_campaign()` validates relative/bounded workspace checks and writes matched S/M manifest rows outside trial workspaces.
3. Codex Desktop executes the unchanged natural user prompt in its disposable workspace; neither arm receives evaluator instructions.
4. Collection binds the exact rollout to `(case_id, trial_id, arm, workspace_sha256)` and evaluates the frozen workspace-state rule directly from disk.
5. Scoring consumes only normalized bounded evidence. Raw rollouts, raw prompts beyond the sanitized case surface, and host-local evidence remain outside the repository.
6. Train may motivate a later routing revision only in a fresh train-only session. Validation remains sealed until that routing identity is frozen.

The evaluator never repairs, reruns, or mutates the workspace during grading. It only reads bounded filesystem state. A failed check is evidence, not an instruction to fix anything.

## TDD and regression requirements

Implementation must begin with RED tests proving that an agent/task-owned `PASS` marker cannot make a failing workspace pass. Additional RED coverage must include path traversal/absolute-path rejection, file existence/absence/type, SHA-256 mismatch/match, size bounds, `all` versus `any`, missing artifact as valid failure, and preservation of bounded error evidence.

Existing routing temporal, pair identity, token/latency, adjudication, timeout-calibration, and scoring behavior must stay green. Repository contract/runbook tests must be updated to freeze evaluator-owned world-state semantics and to mark `tool_output_marker` as legacy-only for new core admission.

Dataset tests must RED/GREEN the revised quality rules: real-timeout metadata, environment-staleness distinct from command resolution, native-child-status evidence, full visible-surface anti-coaching review, provenance basis, and semantic restrictions on `post_condition=none`.

Full acceptance before a new core freeze requires focused Python tests, `git diff --check`, and the repository-wide `scripts/verify-local.ps1 -SkipBaseline`.

## Stop and owner gates

This design authorizes only a written spec after owner approval. After the spec is committed and owner-reviewed, a separate implementation plan is required before code changes.

Implementation may rebuild a host-local proposed 24-case package, but it must stop again for owner case-level review. No train-case publication, S/M setup canary, real 12-turn calibration, scored train/validation/holdout, shadow, or harder product-value A/B is authorized merely by implementing this design.