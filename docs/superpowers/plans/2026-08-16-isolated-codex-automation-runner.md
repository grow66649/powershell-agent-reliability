# Isolated Codex Automation Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Automate one routing-evaluation row with a fresh isolated Codex profile/workspace while preserving Desktop/Cockpit runtime identity and deterministic external scoring.

**Architecture:** Add one focused Python runner beside the existing routing harness. It materializes an allowlisted temporary `CODEX_HOME`, proves S/M Skill and MCP surface conformance, launches the exact Desktop-bundled `codex exec --ephemeral --json` through structured argv/stdin, captures raw JSONL host-locally, normalizes CLI events, evaluates the existing workspace post-condition, and deletes the secret-bearing profile. A thin PowerShell entrypoint only forwards typed arguments.

**Tech Stack:** Python 3 stdlib (`tomllib`, `subprocess`, `pathlib`, `json`, `hashlib`), PowerShell 7, existing `routing_eval.py` helpers, Windows `icacls`, Codex Desktop-bundled CLI `0.148.0-alpha.9`.

## Global Constraints

- Exact accepted base: public `main@099854caa5db95fc990b3765029684820fbc3a26` plus approved isolated-profile design commit.
- Use only the Desktop-bundled Codex CLI; reject a mismatching version/hash.
- Never persist provider tokens/headers in repo, receipts, stdout/stderr summaries, or command-line arguments.
- S and M use the same exact Reliability MCP; only `powershell-reliability` Skill exposure differs.
- Fresh `CODEX_HOME`, workspace, output namespace, and Codex process per row; initial concurrency is 1.
- Prompt bytes are sent through stdin exactly once. No follow-up steering.
- Deterministic workspace post-condition, not assistant prose or process exit 0, defines task completion.
- Record task wall-clock and exact token fields for each row. Correctness/routing/safety remain primary; timing is secondary paired evidence, and 360 seconds remains only the external stopping bound.
- No Rust product, Skill wording, train cases, validation content, or routing scorer semantics change.

---
### Task 1: Profile materializer and redacted identity

**Files:**
- Create: `benchmarks/harness/codex_automation.py`
- Create: `benchmarks/harness/test_codex_automation.py`

**Interfaces:**
- Produces: `load_live_config(path) -> dict`, `build_profile_text(live, arm, skill_path, mcp_path) -> str`, `profile_receipt(...) -> dict`.

- [ ] **Step 1: Write failing tests** for allowlisted top-level runtime keys, one provider table, exactly one MCP table, `plugins=false`, arm-specific `skills.config`, and secret-free receipts.
- [ ] **Step 2: Run** `python -m unittest benchmarks.harness.test_codex_automation.ProfileMaterializerTests -v`; expect failures because module/functions do not exist.
- [ ] **Step 3: Implement minimal TOML reader/serializer** using `tomllib` and a narrow TOML literal writer for strings/bools/numbers/lists/dicts used by current provider/MCP config.
- [ ] **Step 4: Implement allowlist** for model/provider/effort/summary/verbosity/approval/sandbox/service tier/response storage/fast mode, selected provider table, and exact Reliability MCP table only.
- [ ] **Step 5: Implement redacted receipt** containing hashes and non-secret identities only; no provider table values other than provider name/base URL/wire API and no bearer/header values.
- [ ] **Step 6: Re-run focused tests**; expect PASS.

### Task 2: Skill/MCP surface conformance

**Files:**
- Modify: `benchmarks/harness/codex_automation.py`
- Modify: `benchmarks/harness/test_codex_automation.py`

**Interfaces:**
- Produces: `parse_prompt_input_skills(payload) -> list[dict]`, `probe_skill_catalog(...) -> dict`, `verify_arm_catalog(arm, skills) -> None`, `verify_mcp_profile(profile_dict) -> None`.

- [ ] **Step 1: Write failing tests** for S catalog containing only `powershell-reliability`, M catalog containing none, rejection of unrelated Skills, and exactly one enabled `psr_reliability_native` MCP.
- [ ] **Step 2: Run focused tests** and verify RED for missing conformance functions.
- [ ] **Step 3: Implement prompt-input JSON parsing** without model calls and fail closed on malformed/unobservable catalogs.
- [ ] **Step 4: Implement conformance rules**: S must observe PSR and no unrelated non-system Skill; M must not observe PSR or any unrelated non-system Skill; both profiles contain only the Reliability MCP.
- [ ] **Step 5: Run focused tests**; expect PASS.
### Task 3: Exact CLI subprocess execution and cleanup

**Files:**
- Modify: `benchmarks/harness/codex_automation.py`
- Modify: `benchmarks/harness/test_codex_automation.py`

**Interfaces:**
- Produces: `verify_cli_identity(path, expected_version, expected_sha256)`, `run_codex_row(...) -> dict`, `restrict_profile_acl(path)`, `remove_profile(path)`.

- [ ] **Step 1: Write failing tests** for refusing a mismatched CLI version/hash, structured argv, stdin prompt bytes, per-row CODEX_HOME, monotonic task wall-clock, timeout classification, and cleanup failure blocking the row.
- [ ] **Step 2: Run focused tests** and verify RED.
- [ ] **Step 3: Implement CLI identity verification** with SHA-256 plus `codex --version`; never use PATH fallback.
- [ ] **Step 4: Implement Windows profile ACL restriction** using the current `whoami` identity and `icacls`; fail closed before the model call if restriction cannot be verified.
- [ ] **Step 5: Implement subprocess launch** with `--ephemeral --json -C <workspace> -`, `CODEX_HOME`/`CODEX_SQLITE_HOME` in the child environment, prompt on stdin, raw stdout/stderr files, and timeout process-tree termination.
- [ ] **Step 6: Implement `finally` cleanup** and distinct infrastructure/task/timeout/cleanup states.
- [ ] **Step 7: Run focused tests**; expect PASS.

### Task 4: CLI JSONL adapter and deterministic result

**Files:**
- Modify: `benchmarks/harness/codex_automation.py`
- Modify: `benchmarks/harness/test_codex_automation.py`
- Reuse: `benchmarks/harness/routing_eval.py`

**Interfaces:**
- Produces: `parse_cli_jsonl(path) -> dict`, `evaluate_manifest_row(row, workspace) -> dict`, `normalized_execution_receipt(...) -> dict`.

- [ ] **Step 1: Write failing fixtures/tests** for command execution items, MCP call items, turn completion/error, token usage, malformed/truncated JSONL, and missing token fields remaining `None` rather than synthesized.
- [ ] **Step 2: Run focused tests** and verify RED.
- [ ] **Step 3: Implement event adapter** that counts native commands, all MCP calls, Reliability MCP calls, and captures exact token fields when present.
- [ ] **Step 4: Reuse `routing_eval._evaluate_workspace_post_condition` or the narrow existing helper** to read final workspace truth independently of final prose/process exit.
- [ ] **Step 5: Emit one normalized execution receipt** with process state, post-condition truth, prompt/workspace/profile/MCP/CLI hashes, observed Skill catalog, tool counts, token fields, and cleanup result.
- [ ] **Step 6: Run focused tests**; expect PASS.
### Task 5: Operator entrypoint and runbook

**Files:**
- Create: `scripts/run-routing-automation.ps1`
- Create: `docs/runbooks/routing-eval-cli-automation.md`
- Modify: `benchmarks/harness/codex_automation.py`
- Modify: `benchmarks/harness/test_codex_automation.py`

**Interfaces:**
- Produces CLI subcommands `profile-check` and `run-row` with typed arguments.

- [ ] **Step 1: Write failing CLI parser tests** covering required manifest row, arm, live config, exact Codex path/hash/version, MCP path/hash, evidence root, and timeout.
- [ ] **Step 2: Run focused tests** and verify RED.
- [ ] **Step 3: Implement argparse entrypoint**; `profile-check` does no model call; `run-row` performs one complete isolated row.
- [ ] **Step 4: Write thin PowerShell launcher** that resolves repo-relative Python script and forwards arguments without experiment logic or command-string nesting.
- [ ] **Step 5: Write runbook** for prerequisites, profile-check, one-row dry smoke, parity gate, evidence/cleanup, and explicit rule that CLI does not replace Desktop admission until parity passes.
- [ ] **Step 6: Run focused tests**; expect PASS.

### Task 6: Host smoke, regression suite, and review-ready commit

**Files:**
- All files from Tasks 1-5.

- [ ] **Step 1: Run non-model S profile-check** against the real Cockpit config and exact Desktop-bundled CLI; require observed PSR-only catalog, one MCP, no live-config hash change, and secret-profile cleanup.
- [ ] **Step 2: Run non-model M profile-check**; require zero Skills, the same one MCP, no live-config hash change, and cleanup.
- [ ] **Step 3: Run** `python -m unittest discover -s benchmarks/harness -p 'test_*.py'` and require all routing/automation tests PASS.
- [ ] **Step 4: Run** `pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline` from the worktree root and require PASS.
- [ ] **Step 5: Run** `git diff --check`, private-path/secret scans over changed files, and `git status --short`; require no unexpected files.
- [ ] **Step 6: Commit the implementation** in one purpose-focused commit after all verification is fresh.

## Self-review

- Spec coverage: profile isolation, exact CLI, secret boundary, S/M catalog, one MCP, stdin prompt, JSONL, deterministic post-condition, timeout/cleanup, token/tool accounting, serial execution, parity runbook are each mapped to a task.
- No product/Skill/routing dataset/validation changes are in scope.
- No latency comparison or generic orchestration framework is introduced.
