# PowerShell Reliability v0.2 Agent-Facing Contract Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing three-tool Reliability MCP self-describing and causally useful to Codex Desktop while reducing the Companion Skill to a thin failure-only routing policy.

**Architecture:** Keep the accepted stateless `rmcp 3.1.2` STDIO server and exactly three public tools. Fix JSON output discoverability, file-version semantics, diagnostic specificity, per-tool routing metadata, and Skill duplication without adding execution/orchestration capability. Codex Desktop remains command/process/sandbox owner.

**Tech Stack:** Rust 1.88+ / edition 2024, `rmcp = 3.1.2`, `schemars = 1.2`, Serde, Tokio, PowerShell 7.6.3 for local verification.

## Global Constraints

- Exact product base: `f8d7ced0fb22575d4f5f7b095c3e23f00706baaf`.
- Worktree: `<repo-worktree>`.
- Branch: `feat/v02-contract-writer-20260813`.
- Public tools remain exactly `inspect_environment`, `diagnose_failure`, `verify_result`.
- Do not add raw `cwd` to `diagnose_failure` in this slice.
- Do not add a generic verify-to-diagnose evidence object in this slice.
- Do not add a runner, repair engine, daemon, session manager, queue, semaphore, network transport, or security/global-environment mutation.
- Every behavior change follows RED -> observed expected failure -> minimum GREEN -> regression check.
- The Leader planning commit is local Writer history only and must not enter accepted product integration.

---
## File map

- `src/diagnosis.rs`: diagnosis input/output types and failure-class ordering.
- `src/environment.rs`: bounded environment identity types and executable metadata semantics.
- `src/verification.rs`: deterministic post-condition input/output types.
- `src/lib.rs`: MCP tool descriptions, annotations, server instructions, blocking boundaries.
- `tests/schema_contract.rs`: direct generated input/output JSON Schema contracts.
- `tests/lifecycle.rs`: actual STDIO `tools/list` declarations and structured call lifecycle.
- `tests/diagnose_failure.rs`: causal-priority and evidence-preservation behavior.
- `tests/inspect_environment.rs`: executable file-version naming/privacy behavior.
- `tests/workflow_contract.rs`: runtime/Skill common-path guardrails.
- `skills/powershell-reliability/SKILL.md`: trigger metadata plus thin failure-only routing policy.
- `skills/powershell-reliability/references/tool-usage.md`: delete after MCP schemas become self-describing.
- `docs/contracts/mcp-tool-contract-v0.2.md`: stable v0.2 public MCP contract.
- `docs/contracts/auto-on-failure-trigger-contract.md`: align trigger/non-trigger language with the thin Skill.

### Task 1: Make nested output schemas directly discoverable

**Files:**
- Modify: `tests/schema_contract.rs`
- Modify: `tests/lifecycle.rs`
- Modify: `src/diagnosis.rs`
- Modify: `src/environment.rs`
- Modify: `src/verification.rs`

**Produces:** Direct nested output shapes for all three public tools without `$ref`-only agent-facing fields.
- [ ] **Step 1: Add the direct output-schema RED test**

Add imports for `DiagnosisResult`, `EnvironmentDigest`, `VerificationResult`, and `rmcp::handler::server::tool::schema_for_output`, then add:

```rust
#[test]
fn tool_output_schema_inlines_nested_agent_results() {
    let diagnosis = serde_json::Value::Object(schema_for_output::<DiagnosisResult>().as_ref().clone());
    assert!(!diagnosis["properties"]["evidence"]["items"].to_string().contains("\"$ref\""));
    assert_eq!(diagnosis["properties"]["evidence"]["items"]["properties"]["code"]["type"], "string");
    assert!(!diagnosis["properties"]["next_action"].to_string().contains("\"$ref\""));

    let environment = serde_json::Value::Object(schema_for_output::<EnvironmentDigest>().as_ref().clone());
    assert!(!environment["properties"]["cwd"].to_string().contains("\"$ref\""));
    assert!(!environment["properties"]["critical_executables"]["items"].to_string().contains("\"$ref\""));

    let verification = serde_json::Value::Object(schema_for_output::<VerificationResult>().as_ref().clone());
    assert!(!verification["properties"]["checks"]["items"].to_string().contains("\"$ref\""));
    assert_eq!(verification["properties"]["checks"]["items"]["properties"]["passed"]["type"], "boolean");
}
```

- [ ] **Step 2: Run only the new test and observe RED**

Run: `cargo test --test schema_contract tool_output_schema_inlines_nested_agent_results -- --exact --nocapture`
Expected: FAIL because nested result schemas currently contain `$ref`.
- [ ] **Step 3: Inline only agent-facing nested output structs**

Add `#[schemars(inline)]` to:

```rust
DiagnosisEvidence
DiagnosisAction
ShellIdentity
OsIdentity
CwdIdentity
ExecutableIdentity
EnvDeltaDigest
VerificationCheckResult
```

Do not inline unrelated root request/result structs.

- [ ] **Step 4: Verify the focused schema test GREEN**

Run: `cargo test --test schema_contract tool_output_schema_inlines_nested_agent_results -- --exact --nocapture`
Expected: PASS.

- [ ] **Step 5: Extend actual STDIO lifecycle assertions**

In `tests/lifecycle.rs`, after `list_all_tools()`, assert each tool has `output_schema` and the same nested paths contain direct `properties` rather than `$ref`. This test must inspect the serialized tool declarations returned by the running MCP server.

- [ ] **Step 6: Run lifecycle and schema suites**

Run: `cargo test --test schema_contract --test lifecycle -- --nocapture`
Expected: PASS.

- [ ] **Step 7: Commit Task 1**

Run: `git add src tests && git commit -m "fix: expose nested MCP output schemas"`
### Task 2: Correct executable file-version semantics

**Files:**
- Modify: `tests/inspect_environment.rs`
- Modify: `tests/schema_contract.rs`
- Modify: `src/environment.rs`

**Produces:** Public environment output that never presents PE/file metadata as a PowerShell engine version.

- [ ] **Step 1: Write the semantic RED test**

Replace the current `shell.version.is_some()` assertion with JSON-field assertions:

```rust
let json = serde_json::to_value(&digest).expect("serialize digest");
let shell = json["shell"].as_object().expect("shell object");
assert!(shell.contains_key("executable_file_version"));
assert!(!shell.contains_key("version"));
let executable = json["critical_executables"][0].as_object().expect("executable object");
assert!(executable.contains_key("executable_file_version"));
assert!(!executable.contains_key("version"));
```

Also assert the output schema exposes `executable_file_version` for both nested identity structs.

- [ ] **Step 2: Run the focused test and observe RED**

Run: `cargo test --test inspect_environment digest_is_privacy_bounded_and_resolves_explicit_executable -- --exact --nocapture`
Expected: FAIL because the current JSON field is `version`.
- [ ] **Step 3: Rename only the public metadata fields**

Change the structs and constructors to:

```rust
pub struct ShellIdentity {
    pub family: String,
    pub executable_file_version: Option<String>,
    pub architecture: String,
    pub resolution_status: String,
    pub resolved_path_sha256: Option<String>,
}

pub struct ExecutableIdentity {
    pub name: String,
    pub resolution_status: String,
    pub source_class: String,
    pub resolved_path_sha256: Option<String>,
    pub executable_file_version: Option<String>,
    pub file_sha256: Option<String>,
    pub architecture: Option<String>,
}
```

Keep the existing private `file_version(path)` helper; it already computes executable file metadata. Do not execute PowerShell to populate engine version.

- [ ] **Step 4: Run inspect + schema tests GREEN**

Run: `cargo test --test inspect_environment --test schema_contract -- --nocapture`
Expected: PASS.

- [ ] **Step 5: Commit Task 2**

Run: `git add src/environment.rs tests/inspect_environment.rs tests/schema_contract.rs && git commit -m "fix: name executable version metadata precisely"`
### Task 3: Make specific causal diagnosis outrank generic outcome mismatch

**Files:**
- Modify: `tests/diagnose_failure.rs`
- Modify: `src/diagnosis.rs`

**Produces:** Specific failure classes when causal evidence exists, while preserving command/task disagreement as evidence.

- [ ] **Step 1: Add RED cases for specific evidence plus outcome disagreement**

Add a helper assertion and representative cases:

```rust
fn assert_specific_with_mismatch(request: DiagnoseFailureRequest, expected: &str) {
    let diagnosis = diagnose_failure(request).expect("specific diagnosis");
    assert_eq!(diagnosis.failure_class, expected);
    assert!(diagnosis.evidence.iter().any(|item| item.code == "command_task_outcome_disagree"));
}
```

Use it for at least:
- resolution before=`a*64`, after=`b*64`, exit=0, post_condition=false -> `ENVIRONMENT_STALENESS`;
- expected cwd=`c*64`, actual cwd=`d*64`, exit=0, post_condition=false -> `CWD_PATH_IDENTITY`;
- required PowerShell 7, observed WindowsPowerShell 5.1, exit=0, post_condition=false -> `SHELL_VERSION_MISMATCH`;
- parser/binding+nested+literal-dollar, exit=0, post_condition=false -> `QUOTING_EXPANSION`;
- native_process=true, exit=7, post_condition=true -> `NATIVE_PROCESS_OUTCOME`.

- [ ] **Step 2: Run the new tests and observe RED**

Run: `cargo test --test diagnose_failure specific -- --nocapture`
Expected: at least one FAIL because generic `POST_CONDITION_MISMATCH` currently returns before the specific classes.
- [ ] **Step 3: Reorder classification without expanding the taxonomy**

Compute the disagreement once:

```rust
fn command_task_outcome_disagree(request: &DiagnoseFailureRequest) -> bool {
    matches!((request.exit_code, request.post_condition), (Some(code), Some(post)) if (code == 0) != post)
}
```

Evaluate explicit sandbox and timeout first, then resolution drift, cwd mismatch, shell mismatch, quoting, stderr sandbox pattern, and native non-zero outcome. Evaluate generic `POST_CONDITION_MISMATCH` only after those specific branches and before `UNKNOWN`.

Before returning a specific diagnosis, append this evidence when the helper is true and the class is not `POST_CONDITION_MISMATCH`:

```rust
diagnosis.evidence.push(DiagnosisEvidence {
    code: "command_task_outcome_disagree".to_owned(),
    detail: "Command exit status and the explicit task post-condition disagree.".to_owned(),
});
```

Do not duplicate that evidence in the generic mismatch result.

- [ ] **Step 4: Run the full diagnosis suite GREEN**

Run: `cargo test --test diagnose_failure -- --nocapture`
Expected: PASS, including existing `UNKNOWN`, privacy, and fail-closed validation tests.

- [ ] **Step 5: Commit Task 3**

Run: `git add src/diagnosis.rs tests/diagnose_failure.rs && git commit -m "fix: prefer causal failure evidence"`
### Task 4: Make each public tool self-route through descriptions and annotations

**Files:**
- Modify: `tests/lifecycle.rs`
- Modify: `src/lib.rs`

**Produces:** Tool declarations that tell Codex when to use and not use each read-only closed-world tool.

- [ ] **Step 1: Add lifecycle RED assertions**

For each tool returned by `list_all_tools()`, assert:

```rust
assert_eq!(tool.annotations.as_ref().and_then(|a| a.read_only_hint), Some(true));
assert_eq!(tool.annotations.as_ref().and_then(|a| a.open_world_hint), Some(false));
```

Also assert descriptions contain these stable routing phrases:

```text
inspect_environment: "only when shell, cwd, PATH, or executable identity can causally matter"
inspect_environment: "Do not call for a pure command/post-condition disagreement"
diagnose_failure: "Does not inspect the environment"
verify_result: "final deterministic post-condition verification"
```

- [ ] **Step 2: Run lifecycle and observe RED**

Run: `cargo test --test lifecycle -- --nocapture`
Expected: FAIL because annotations and negative-routing descriptions are not present.

- [ ] **Step 3: Add truthful rmcp annotations and descriptions**
Use the rmcp macro shape already proven by local `rmcp 3.1.2` tests:

```rust
#[tool(
    name = "inspect_environment",
    description = "Use after a failed Windows task only when shell, cwd, PATH, or executable identity can causally matter. Do not call for a pure command/post-condition disagreement or known-good success. Return privacy-bounded identity only.",
    annotations(title = "Inspect Windows execution identity", read_only_hint = true, open_world_hint = false)
)]
```

Use equivalent annotations for `diagnose_failure` and `verify_result`. Their descriptions must state that diagnosis consumes supplied evidence without environment inspection, and verification is the final deterministic post-condition check rather than an exploratory retry loop.

Do not add destructive/idempotent hints merely for completeness; the tools are read-only.

- [ ] **Step 4: Run lifecycle GREEN**

Run: `cargo test --test lifecycle -- --nocapture`
Expected: PASS and actual STDIO `tools/list` contains the annotations/descriptions.

- [ ] **Step 5: Run product-boundary tests**

Run: `cargo test --test product_boundary -- --nocapture`
Expected: PASS, proving the metadata change did not grow execution/network surface.

- [ ] **Step 6: Commit Task 4**

Run: `git add src/lib.rs tests/lifecycle.rs && git commit -m "fix: make reliability tools self-routing"`

### Task 5: Thin the Companion Skill after the MCP becomes self-describing

**Files:**
- Modify: `skills/powershell-reliability/SKILL.md`
- Delete: `skills/powershell-reliability/references/tool-usage.md`
- Modify: `tests/schema_contract.rs`
- Modify: `tests/workflow_contract.rs`
**Produces:** A two-file Skill package whose `SKILL.md` contains trigger boundaries, common routing, stop rules, and safety invariants without duplicating MCP JSON schema.

- [ ] **Step 1: Change workflow/schema tests to the target package contract and observe RED**

Remove `skill_reference_documents_exact_nested_tool_shapes`. Add a package-shape test that asserts the duplicated reference is gone:

```rust
#[test]
fn companion_skill_does_not_duplicate_mcp_schema_reference() {
    let root = std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("skills")
        .join("powershell-reliability");
    assert!(root.join("SKILL.md").is_file());
    assert!(root.join("agents/openai.yaml").is_file());
    assert!(!root.join("references/tool-usage.md").exists());
}
```

Update `workflow_contract.rs` to assert the `SKILL.md` itself contains the routing invariants and no longer reads the reference.

Run: `cargo test --test schema_contract --test workflow_contract -- --nocapture`
Expected: FAIL because `tool-usage.md` still exists and tests still expect duplicated text.

- [ ] **Step 2: Replace the frontmatter description with the frozen trigger boundary**

Use this exact candidate unless a validator rejects its length/format:

```yaml
description: Use this skill after a Windows Codex Desktop PowerShell or native-command failure: non-zero exit, timeout/cancellation ambiguity, parser/binding/command-resolution failure, declared shell/cwd/executable identity mismatch, or an explicit task post-condition that is false even when exit code is 0. Do not use before the first attempt, for known-good successful work, for ordinary PowerShell explanation/code-writing, for unrelated MCP/connector/backend failures, for stderr-only warnings when the required task outcome passed, or merely because multiple PowerShell versions are installed.
```
- [ ] **Step 3: Rewrite SKILL.md as a compact common-path router**

Keep these rules in `SKILL.md` itself:

```text
1. Before the first execution attempt: no Reliability intervention.
2. If command outcome and required post-condition both pass: stop with zero MCP calls.
3. Pure command/post-condition disagreement: call diagnose_failure directly; do not inspect environment.
4. Call inspect_environment only when shell/cwd/PATH/executable identity can causally matter.
5. After a high-confidence diagnosis: do not add unrelated probes.
6. UNKNOWN: collect only one explicitly missing fact, then at most one re-diagnosis.
7. Freeze deterministic task criteria before repair; at most one evidence-backed repair.
8. After repair: exactly one verify_result against frozen criteria.
9. Never weaken criteria or derive expected values from repaired candidate output.
10. Keep Desktop as command/process owner; never weaken sandbox/ACL/approvals/profiles/global environment.
```

Keep the existing privacy limits and MCP-unavailable fallback. Remove the detailed per-class repair taxonomy if the MCP `next_action` now carries that guidance; retain only a rule that `next_action` is evidence, not permission to bypass safety.

- [ ] **Step 4: Delete duplicated tool-usage.md**

Run: `git rm skills/powershell-reliability/references/tool-usage.md`
Do not create replacement references, scripts, or assets in this slice.

- [ ] **Step 5: Run Skill/workflow tests GREEN**

Run: `cargo test --test schema_contract --test workflow_contract -- --nocapture`
Expected: PASS.
- [ ] **Step 6: Commit Task 5**

Run: `git add skills tests && git commit -m "fix: thin reliability companion skill"`

### Task 6: Freeze the stable v0.2 contract docs

**Files:**
- Create: `docs/contracts/mcp-tool-contract-v0.2.md`
- Modify: `docs/contracts/auto-on-failure-trigger-contract.md`
- Do not delete: `docs/contracts/mcp-tool-contract-v0.1.md`

**Produces:** Stable public behavior documentation without live task state or host evidence paths.

- [ ] **Step 1: Create v0.2 MCP contract from the frozen decisions**

The v0.2 contract must state:
- local STDIO, exactly three public tools, no generic runner;
- direct structured input and output schemas suitable for model/tool consumers;
- `inspect_environment` positive/negative trigger boundary;
- executable metadata field means executable file version, not PowerShell engine version;
- caller-observed `ShellObservation.major/minor` represents engine/capability evidence;
- specific causal diagnosis outranks generic command/post-condition disagreement;
- `verify_result` remains deterministic and independent of command exit;
- read-only/closed-world annotations are hints, not authorization;
- all existing privacy/security/concurrency non-goals remain.

- [ ] **Step 2: Align the trigger contract**

Add pure post-condition mismatch as a direct-diagnose path and explicitly state that environment inspection is not a default intermediate step. Preserve all existing non-triggers.

- [ ] **Step 3: Run documentation-linked contract tests**

Run: `cargo test --test workflow_contract --test product_boundary -- --nocapture`
Expected: PASS.

- [ ] **Step 4: Commit Task 6**

Run: `git add docs tests && git commit -m "docs: define reliability v0.2 contract"`
### Task 7: Run full local acceptance and prepare a read-only handoff

**Files:**
- No product changes unless a failing acceptance check reveals a real regression; if so, return to RED before repair.

- [ ] **Step 1: Run the complete repository-defined verifier**

Run from the Writer worktree:

```powershell
pwsh.exe -NoProfile -File .\scripts\verify-local.ps1
```

Expected: every step PASS, including cargo test/check, release build, release lifecycle, benchmark scorer tests, sanitized fixture baseline, Python compile, and `git diff --check`.

If any PowerShell/native command fails, load `$powershell-reliability` immediately and follow its failure-only workflow before one evidence-backed repair.

- [ ] **Step 2: Verify exact public surface and clean worktree**

Run:

```powershell
git rev-parse HEAD
git status --short
git diff f8d7ced0fb22575d4f5f7b095c3e23f00706baaf..HEAD --stat
git diff f8d7ced0fb22575d4f5f7b095c3e23f00706baaf..HEAD --check
```

Expected: status empty; diff check exit 0; no fourth tool or runner/network surface.

- [ ] **Step 3: Record implementation handoff**

Return exact HEAD, ordered commit list after the Leader planning commit, tests/verification result, changed files, any unresolved concern, and confirmation that no config/installed Skill/canonical task/runtime state was modified.

Do not merge. Do not modify main. Do not stage the candidate into Codex Desktop; Leader owns product-side staging and acceptance.

## Self-review checklist

- [ ] Every production behavior change has a test that was observed RED first.
- [ ] Nested output directness is tested both with `schema_for_output` and actual STDIO `tools/list`.
- [ ] No public field still implies executable file version is PowerShell engine version.
- [ ] Generic `POST_CONDITION_MISMATCH` no longer masks stronger supported causal evidence.
- [ ] The three public tools remain exactly the same names.
- [ ] `tool-usage.md` is deleted and no replacement reference/script/asset was added.
- [ ] Tool annotations are truthful read-only/closed-world hints only.
- [ ] No raw host evidence, live task state, credentials, PATH, or environment dump entered repo docs.
- [ ] Full `verify-local.ps1` and `git diff --check` pass.

## Integration note

This plan file is Leader planning history. Do not include its commit in the accepted product integration/cherry-pick set. Accepted product changes begin with the Writer's first RED/GREEN product commit after this plan.
