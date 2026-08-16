# r4 Row Isolation and Arm-Blinding Design

Status: Design A approved by the owner on 2026-08-17. This document freezes the design for review; implementation is not yet approved.

## Problem statement

The current routing campaign layout eagerly materializes every trial workspace under a campaign-local tree whose path includes the literal arm name. That creates two protocol defects:

1. the model-visible working directory exposes `S` or `M` and campaign purpose even though companion-Skill exposure is supposed to be the only intentional arm difference;
2. peer and future trial workspaces, plus coordinator/evidence artifacts, can become discoverable by walking to parent or sibling directories.

Observed exploratory runs demonstrated both failure modes. Those runs remain historical behavior evidence only and are not valid blinded S/M denominators.

This change repairs benchmark topology only. It does not change Reliability MCP behavior, Skill routing text, Codex sandboxing, approval policy, Windows ACL policy, model/provider selection, scorer thresholds, or product admission rules.

## Decision

Use **Design A: just-in-time single-row materialization in an opaque standalone runtime root**.

Campaign coordination data stays in a host-local coordinator root. The active Codex workspace is created only for the row being executed, under a separate runtime root whose model-visible path contains no arm, case, lane, campaign-purpose, or expected-routing label. The active workspace is graded and then removed before the next row is materialized.

## Required invariants

A scored row is valid only when all of these topology invariants hold:

- The runtime workspace path is opaque. No path component may encode the arm (`S`/`M`), case ID/title, lane, trigger group, campaign purpose, Skill name, MCP name, or expected outcome.
- S and M rows use the same opaque-path format and the same runtime-root policy.
- The runtime root is neither equal to, inside, nor an ancestor of the coordinator/evidence root.
- The coordinator root contains manifest, prompts, fixture definitions, driver state, analyzer state, receipts, and raw execution evidence; none of those artifacts are copied into the active runtime workspace or its parent.
- Campaign preparation does not create executable trial workspaces. Only the active row is materialized.
- Scored automation remains concurrency=1 for this campaign revision, so exactly one campaign workspace can exist at a time.
- While one row is executing, no peer or future row workspace from the same campaign exists under that row's runtime parent.
- The fixture is reconstructed from frozen coordinator metadata immediately before execution and must match the manifest-frozen fixture hash before Codex starts.
- The deterministic post-condition is evaluated before workspace cleanup.
- Runtime-workspace cleanup runs on success, task failure, timeout, parser failure, post-condition failure, and unexpected exception. Failure to remove the workspace is a campaign-blocking cleanup failure.
- Disposable `CODEX_HOME` cleanup remains independent and fail-closed; this design does not weaken or replace the existing profile-isolation checks.

These invariants remove experiment cues and local sibling leakage. They are not a filesystem security boundary against a process that has unrestricted host read access.

## Coordinator and runtime layout

The coordinator root remains host-local evidence outside the repository. It owns frozen campaign state and is never the Codex working directory.

Conceptually:

```text
<coordinator-root>/
  campaign.json
  manifest.jsonl
  prompts/
  fixtures/
  row-evidence/
  driver-state.json

<neutral-temp-parent>/
  <opaque-campaign-token>/
    <opaque-row-token>/   # only this row exists while it runs
```

The harness creates one neutral runtime root under the host temporary parent using a 128-bit random campaign token rendered as exactly 32 lowercase hexadecimal characters. The runtime root must pass a bidirectional disjointness check against the coordinator root, and its ancestors must not contain a known arm, case, lane, Skill/MCP, or campaign-purpose label supplied by the campaign.

Each manifest row receives a separate 128-bit random row token in the same 32-lowercase-hex format during campaign preparation. Tokens are frozen in coordinator metadata and are not derived from case, arm, lane, prompt, or expected outcome. The manifest binds the resulting workspace path and workspace identity hash, but preparation creates no row workspace.

The same frozen campaign token, row token, and runtime-root binding are used when the row executes so workspace-identity checks remain deterministic. Before a row starts the runtime root must be empty; while Codex runs it contains exactly the active row workspace; after verified cleanup it is empty again.

## Frozen row data and materialization

Preparation writes one coordinator-local `fixtures/<case_key>.json` payload for each case/trial pair. The payload is the frozen mapping of relative UTF-8 fixture paths to text content. Both S and M rows reference that same payload and the same frozen fixture hash; the payload is coordinator metadata, not an executable workspace.

Execution for one row follows this order:

1. load exactly one manifest row and validate its arm, prompt binding, fixture binding, runtime-root binding, and campaign identity;
2. verify that the target opaque workspace does not already exist and that no other campaign row workspace is present under the runtime parent;
3. create only the target workspace and reconstruct its frozen fixture;
4. recompute fixture identity and abort before Codex launch on any mismatch;
5. create and verify the disposable Codex profile using the existing S/M catalog rules;
6. launch the exact frozen Codex runtime with `-C` set to the opaque workspace;
7. parse execution evidence and evaluate the deterministic post-condition against that workspace;
8. write bounded row evidence to the coordinator/evidence root;
9. remove the runtime workspace and disposable profile, then verify both are gone before the row is considered complete.

No row may reuse a mutated workspace. A cleanup failure blocks later rows rather than allowing a second workspace to coexist with stale campaign state. On normal campaign completion or abort, the now-empty opaque runtime root is removed and its absence is verified.

## Arm blinding

The intentional arm difference remains exactly the one frozen by the r4 routing contract:

- S exposes the `powershell-reliability` companion Skill and the Reliability MCP;
- M exposes the same Reliability MCP but no Reliability Skill.

Everything else that the campaign controls remains matched: prompt bytes/hash, fixture bytes/hash, model, effort, provider, approval policy, sandbox mode, Codex build, MCP identity, measurement policy, timeout, originator policy, and runtime-path format.

The prompt and fixture remain arm-neutral. Arm, lane, case identity, campaign identity, and evaluator labels may exist in coordinator metadata, but must not be encoded into the model-visible runtime path.

A hashed or random-looking path is not treated as a security secret. Its purpose is to remove semantic cues, not to hide data cryptographically.

## Contamination handling

Topology checks are the primary defense. If existing bounded execution evidence directly establishes that Codex accessed campaign coordinator data, prior row evidence, or another row workspace, that row is invalid even if its task post-condition passed.

This slice does not add a filesystem monitor or host-wide access detector. It relies on the same bounded command/runtime evidence already retained for evaluation. A single proven cross-row/coordinator access invalidates the row; repeated occurrences after the new topology is active are a systemic protocol failure and stop the campaign for review.

Because the target runtime may run with broad read access, this design does not claim that arbitrary global host searches are impossible. If Codex independently performs a broad host search and finds campaign artifacts, that is evidence of contamination, not evidence that the benchmark remained blinded.

## Leakage canary before scored execution

After implementation is integrated, run a fresh non-scored canary before any new screen or train denominator.

The canary must establish all of the following on the exact automation path:

- cwd and its model-visible ancestors contain no arm/case/campaign-purpose labels;
- the runtime parent contains only the active opaque workspace during execution;
- no prepared peer/future workspace exists;
- coordinator manifest, prompts, driver/analyzer state, and prior row evidence are not colocated beneath the runtime parent;
- fixture hash, prompt hash, runtime identity, Skill/MCP catalog, post-condition evaluation, and both cleanup receipts still pass.

The canary is setup/protocol evidence only. It never enters routing recall, false-activation, completion, token, latency, or S/M winner denominators.

## TDD requirements

Implementation begins with focused RED tests. At minimum they must prove:

- campaign and row runtime tokens are exactly 32 lowercase hexadecimal characters and are not derived from arm/case/lane semantics;
- prepared manifest runtime workspace paths contain no literal arm segment and no semantic case/campaign label;
- campaign preparation creates coordinator metadata but creates no trial workspace;
- a run materializes exactly one frozen fixture into exactly one opaque workspace;
- a second peer/future workspace is absent while the row runner is active;
- coordinator and runtime roots are rejected when equal, nested in either direction, or otherwise violate the frozen layout contract;
- fixture identity is checked after JIT materialization and before Codex launch;
- workspace identity still binds the observed cwd to the intended manifest row;
- post-condition evaluation occurs before runtime-workspace deletion;
- runtime workspace cleanup is verified on success, task failure, timeout, parser failure, and exception;
- stale runtime workspaces fail closed rather than being reused or silently overwritten;
- existing disposable-profile cleanup, arm catalog, MCP identity, prompt hash, runtime identity, and CRLF fixture-hash tests continue to pass.

The smallest compatible implementation is preferred. No unrelated routing-evaluator refactor is part of this slice.

## Existing campaign treatment

Previously prepared campaigns using `<campaign>/workspaces/<arm>/<case>` remain historical/exploratory artifacts. They are not migrated in place, resumed, or mixed with new denominators.

After this fix is merged, a new public-main SHA, new harness identity, new campaign identity, new opaque runtime root, and fresh row receipts are required. Validation and holdout material remain sealed and unread during this repair and fresh train decision.

## Non-goals

This slice does not:

- add a second sandbox, Windows user, VM/container, generic shell runner, or host-wide access monitor;
- weaken or mutate Codex sandboxing, approval policy, ACLs, PowerShell profiles, or global environment settings;
- use `workspace-write` as a confidentiality mechanism;
- change Skill wording, MCP tools/descriptions, model/provider, experiment thresholds, or case adjudication rules;
- expose sealed validation/holdout content to train-visible sessions;
- reinterpret the aborted screen/train as valid blinded evidence;
- claim CLI automation alone is Windows Codex Desktop product admission.

## Acceptance boundary

The topology repair is ready for a Draft PR only when:

1. all new isolation/blinding tests pass from RED to GREEN;
2. focused automation/routing harness tests pass;
3. the repository verification command passes and `git diff --check` is clean;
4. an independent read-only review finds no unresolved protocol, safety, or scope defect;
5. the implementation preserves the exact product boundary and does not introduce a new security/execution subsystem.

After Leader integration, the first runtime action is the non-scored leakage canary. Only a passing canary permits a fresh S/M screen or train campaign. Final/default product recommendation remains downstream of a valid S/M selection and fresh representative Windows Codex Desktop confirmation.
