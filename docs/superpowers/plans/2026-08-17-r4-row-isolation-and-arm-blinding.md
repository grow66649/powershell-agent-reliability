# r4 Row Isolation and Arm-Blinding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace campaign-local S/M workspaces with opaque just-in-time single-row runtime workspaces so Skill exposure is the only intentional S/M routing difference.

**Architecture:** `routing_eval.py` freezes prompt/fixture/coordinator metadata plus 128-bit opaque campaign/row tokens, but does not materialize row workspaces. `codex_automation.py` validates coordinator/runtime separation, materializes exactly one fixture immediately before execution, verifies it, runs Codex, evaluates the post-condition, records bounded contamination evidence, and removes the row workspace on every exit path.

**Tech Stack:** Python 3.14 standard library (`pathlib`, `secrets`, `tempfile`, `json`, `shutil`), `unittest`, existing Codex CLI automation and routing harness.

## Global Constraints

- Exact implementation base is the approved planning branch descendant of public main `7455cfc306024b8a0d8b26ca688b8f63652affe7`.
- Runtime path tokens are 128-bit random values rendered as exactly 32 lowercase hexadecimal characters.
- Coordinator and runtime roots must be disjoint in both directions; no arm/case/lane/Skill/MCP/campaign-purpose label may be encoded into the model-visible runtime path.
- Campaign preparation creates coordinator metadata and fixture payloads only; it creates no row workspace.
- Concurrency remains `1`; while a row runs, its runtime root contains exactly one active row workspace.
- Fixture identity is verified before Codex launch; deterministic post-condition evaluation happens before workspace cleanup.
- Workspace and disposable-profile cleanup are fail-closed on success, task failure, timeout, parser failure, and unexpected exception.
- Do not add a second sandbox, ACL mutation, generic runner, global setting change, new dependency, or host-wide telemetry.
- Validation and holdout remain sealed; aborted screen/train rows remain exploratory only.

---## File structure

- `benchmarks/harness/routing_eval.py`: campaign preparation, opaque token generation, frozen prompt/fixture metadata, runtime-path bindings.
- `benchmarks/harness/test_routing_eval.py`: RED/GREEN coverage for prepare-time arm blinding, fixture payload freezing, token/path invariants, and no eager workspaces.
- `benchmarks/harness/codex_automation.py`: row topology validation, JIT materialization, execution ordering, bounded contamination evidence, and fail-closed cleanup.
- `benchmarks/harness/test_codex_automation.py`: RED/GREEN coverage for topology rejection, one-row runtime lifecycle, failure paths, and receipt fields.
- `docs/contracts/routing-eval-contract-r4.md`: stable row-isolation/arm-blinding contract.
- `docs/runbooks/routing-eval-cli-automation.md`: operator steps for neutral runtime parent, JIT row execution, cleanup, and leakage canary.
- `docs/runbooks/routing-eval-desktop.md`: align Desktop campaign preparation language with the new no-eager-workspace contract.

### Task 1: Freeze opaque campaign metadata without creating row workspaces

**Files:**
- Modify: `benchmarks/harness/routing_eval.py:1-230,1120-1145`
- Modify/Test: `benchmarks/harness/test_routing_eval.py:34-90`

**Interfaces:**
- Produces: `prepare_campaign(cases, output_root, trials, seed, runtime_parent=None, token_factory=None) -> list[dict]`.
- Produces manifest fields: `fixture_path`, `runtime_root`, `runtime_root_sha256`, `workspace`, `workspace_sha256`, with `workspace` equal to `<runtime_root>/<32hex-row-token>`.
- Produces `fixtures/<case_key>.json`, shared by matched S/M rows.
- [ ] **Step 1: Replace the eager-workspace preparation assertion with RED isolation assertions**

```python
rows = routing_eval.prepare_campaign(
    [_case()], coordinator, trials=1, seed=7,
    runtime_parent=runtime_parent,
    token_factory=iter(["1" * 32, "2" * 32, "3" * 32]).__next__,
)
self.assertTrue((coordinator / "fixtures" / "R01-T01.json").is_file())
self.assertFalse(pathlib.Path(rows[0]["workspace"]).exists())
self.assertFalse(pathlib.Path(rows[1]["workspace"]).exists())
self.assertEqual(pathlib.Path(rows[0]["workspace"]).parent, runtime_parent / ("1" * 32))
self.assertRegex(pathlib.Path(rows[0]["workspace"]).name, r"^[0-9a-f]{32}$")
self.assertNotIn(rows[0]["arm"], pathlib.Path(rows[0]["workspace"]).parts)
```

- [ ] **Step 2: Run the prepare tests and verify RED**

Run: `python -m unittest benchmarks.harness.test_routing_eval.RoutingEvalPrepareTests -v`
Expected: FAIL because `prepare_campaign` has no `runtime_parent`/`token_factory`, still writes `workspaces/<arm>/<case>`, and creates fixtures eagerly.

- [ ] **Step 3: Implement the minimum frozen-metadata preparation path**

```python
import secrets
import tempfile

OPAQUE_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")

def _opaque_token(token_factory=None):
    value = (token_factory or (lambda: secrets.token_hex(16)))()
    if not isinstance(value, str) or not OPAQUE_TOKEN_RE.fullmatch(value):
        raise ValueError("opaque runtime token must be exactly 32 lowercase hex characters")
    return value
```
Use one campaign token per prepared campaign and one row token per manifest row. Freeze fixture content as JSON using `json.dumps(files, ensure_ascii=False, sort_keys=True)` and keep `_fixture_sha256(files)` as the semantic fixture identity. Add `--runtime-parent` to the `prepare` CLI, defaulting to `pathlib.Path(tempfile.gettempdir())` only when the caller omits it. Create the opaque campaign runtime root itself as an empty directory, but never create any row workspace during preparation.

- [ ] **Step 4: Add deterministic negative tests for bad/semantic tokens and reused non-empty runtime roots**

```python
with self.assertRaisesRegex(ValueError, "32 lowercase hex"):
    routing_eval.prepare_campaign([_case()], coordinator, 1, 7, runtime_parent, token_factory=lambda: "S-arm")

runtime_root = runtime_parent / ("a" * 32)
runtime_root.mkdir(parents=True)
(runtime_root / "stale").mkdir()
with self.assertRaisesRegex(ValueError, "runtime root.*empty"):
    routing_eval.prepare_campaign([_case()], coordinator, 1, 7, runtime_parent, token_factory=iter(["a" * 32, "b" * 32, "c" * 32]).__next__)
```

- [ ] **Step 5: Run focused prepare tests GREEN**

Run: `python -m unittest benchmarks.harness.test_routing_eval.RoutingEvalPrepareTests -v`
Expected: PASS; no row workspace exists after preparation.

- [ ] **Step 6: Commit Task 1**

```powershell
git add benchmarks/harness/routing_eval.py benchmarks/harness/test_routing_eval.py
git commit -m "test: freeze opaque routing workspace metadata"
```

### Task 2: Validate coordinator/runtime separation and JIT fixture materialization

**Files:**
- Modify: `benchmarks/harness/codex_automation.py:700-923`
- Modify/Test: `benchmarks/harness/test_codex_automation.py:502-739`

**Interfaces:**
- Produces: `validate_manifest_row_paths(manifest_path, row) -> None` for the new coordinator/runtime layout.
- Produces: `validate_runtime_topology(coordinator_root, runtime_root, workspace) -> None`.
- Produces: `materialize_row_workspace(row) -> pathlib.Path` and `remove_runtime_workspace(workspace) -> None`.
- [ ] **Step 1: Write RED topology tests for bidirectional root nesting and stale/peer workspaces**

```python
row = prepared_row(runtime_parent, coordinator)
codex_automation.validate_manifest_row_paths(coordinator / "manifest.jsonl", row)

for bad_runtime in (coordinator, coordinator / "runtime", coordinator.parent):
    bad = dict(row, runtime_root=str(bad_runtime), workspace=str(bad_runtime / ("b" * 32)))
    with self.assertRaisesRegex(ValueError, "disjoint"):
        codex_automation.validate_manifest_row_paths(coordinator / "manifest.jsonl", bad)

runtime_root = pathlib.Path(row["runtime_root"])
(runtime_root / ("f" * 32)).mkdir()
with self.assertRaisesRegex(RuntimeError, "runtime root.*empty"):
    codex_automation.materialize_row_workspace(row)
```

- [ ] **Step 2: Run topology tests and verify RED**

Run: `python -m unittest benchmarks.harness.test_codex_automation.ManifestTopologyTests -v`
Expected: FAIL because validation still requires `<campaign>/workspaces/<arm>/<case>` and no JIT materializer exists.

- [ ] **Step 3: Implement strict path validation and fixture loading**

```python
def _is_relative_to(child: pathlib.Path, parent: pathlib.Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False

def validate_runtime_topology(coordinator_root, runtime_root, workspace):
    coordinator_root = coordinator_root.resolve(strict=False)
    runtime_root = runtime_root.resolve(strict=False)
    workspace = workspace.resolve(strict=False)
    if (_is_relative_to(runtime_root, coordinator_root)
            or _is_relative_to(coordinator_root, runtime_root)):
        raise ValueError("coordinator and runtime roots must be disjoint")
    if workspace.parent != runtime_root:
        raise ValueError("workspace must be a direct child of the frozen runtime root")
```

Validate `prompt_path == coordinator/prompts/<case_key>.txt`, `fixture_path == coordinator/fixtures/<case_key>.json`, the 32-hex campaign/row path components, and the frozen workspace identity. Reject symlink/junction runtime/workspace roots.
- [ ] **Step 4: Implement JIT materialization and verified deletion**

```python
def materialize_row_workspace(row):
    runtime_root = pathlib.Path(row["runtime_root"])
    workspace = pathlib.Path(row["workspace"])
    if workspace.exists() or any(runtime_root.iterdir()):
        raise RuntimeError("runtime root must be empty before row materialization")
    files = json.loads(pathlib.Path(row["fixture_path"]).read_text(encoding="utf-8"))
    routing_eval._write_fixture(workspace, files)
    if workspace_fixture_sha256(workspace) != row["fixture_sha256"]:
        remove_runtime_workspace(workspace)
        raise ValueError("workspace fixture SHA256 mismatch")
    return workspace

def remove_runtime_workspace(workspace):
    if workspace.exists():
        shutil.rmtree(workspace)
    if workspace.exists():
        raise RuntimeError("runtime workspace cleanup failed")
```

- [ ] **Step 5: Test CRLF fixture preservation through JSON payload -> JIT workspace**

Use a fixture containing `"@echo off\r\nexit /b 0\r\n"`, materialize it, and assert `workspace_fixture_sha256(workspace) == row["fixture_sha256"]`. This guards the integrated CRLF identity fix.

- [ ] **Step 6: Run focused topology/materialization tests GREEN**

Run: `python -m unittest benchmarks.harness.test_codex_automation.ManifestTopologyTests benchmarks.harness.test_codex_automation.RunRowWorkflowTests -v`
Expected: PASS for new topology tests; existing run-row tests may still need Task 3 lifecycle updates but fixture/hash helpers remain GREEN.

- [ ] **Step 7: Commit Task 2**

```powershell
git add benchmarks/harness/codex_automation.py benchmarks/harness/test_codex_automation.py
git commit -m "feat: materialize isolated routing rows just in time"
```

### Task 3: Make row execution order and cleanup fail closed

**Files:**
- Modify: `benchmarks/harness/codex_automation.py:830-923`
- Modify/Test: `benchmarks/harness/test_codex_automation.py:615-739`

**Interfaces:**
- `execute_run_row()` must order: validate -> materialize -> verify fixture -> profile/identity -> execute -> parse -> post-condition -> evidence -> cleanup.
- Receipt adds `workspace_cleanup_ok` while retaining `cleanup_ok` as the conjunction of workspace and profile cleanup.
- [ ] **Step 1: Write RED ordering/cleanup tests for success, task failure, timeout, parser failure, and exception**

Use a fake `process_runner` that asserts the runtime root contains exactly the active workspace while it runs. Use a fake `json_parser`/`evaluate_manifest_row` that records ordering. For every exit path, assert `workspace.exists()` is false and the secret profile is removed.

```python
events = []
def process_runner(*args, **kwargs):
    workspace = args[1]
    self.assertEqual([p for p in workspace.parent.iterdir()], [workspace])
    events.append("process")
    return {"exit_code": 0, "timed_out": False, "termination_reason": "process_exit"}

with mock.patch.object(codex_automation, "evaluate_manifest_row", side_effect=lambda row, ws: events.append("post") or {"passed": True, "source": "evaluator_workspace"}):
    receipt = codex_automation.execute_run_row(...)
self.assertLess(events.index("process"), events.index("post"))
self.assertFalse(pathlib.Path(row["workspace"]).exists())
self.assertTrue(receipt["workspace_cleanup_ok"])
```

- [ ] **Step 2: Run `RunRowWorkflowTests` and verify RED**

Run: `python -m unittest benchmarks.harness.test_codex_automation.RunRowWorkflowTests -v`
Expected: FAIL because current execution expects an already-materialized workspace and only cleans `CODEX_HOME`.

- [ ] **Step 3: Refactor `execute_run_row()` into one bounded lifecycle with two independent cleanup flags**

Keep `profile = None`, `workspace = None`, `profile_cleanup_ok = False`, and `workspace_cleanup_ok = False`. Materialize the workspace before profile creation. Evaluate post-condition before cleanup. In `finally`, remove profile and workspace independently; if either verified cleanup fails, surface the cleanup failure rather than reporting success.

- [ ] **Step 4: Preserve task failure as a receipt, but not protocol/setup failure**

A completed Codex turn whose deterministic post-condition is false remains a normal receipt with `post_condition_passed=false`. Identity drift, fixture mismatch, stale runtime root, parser corruption, or cleanup failure remains an exception/error path and must not be converted to task success.

- [ ] **Step 5: Run `RunRowWorkflowTests` GREEN**

Run: `python -m unittest benchmarks.harness.test_codex_automation.RunRowWorkflowTests -v`
Expected: PASS, including timeout/parser/exception cleanup cases.

- [ ] **Step 6: Commit Task 3**

```powershell
git add benchmarks/harness/codex_automation.py benchmarks/harness/test_codex_automation.py
git commit -m "fix: clean isolated routing rows on every exit path"
```
### Task 4: Preserve bounded contamination evidence without adding host-wide telemetry

**Files:**
- Modify: `benchmarks/harness/codex_automation.py:260-430,560-650`
- Modify/Test: `benchmarks/harness/test_codex_automation.py:251-360,615-739`

**Interfaces:**
- `parse_cli_jsonl()` preserves bounded command fields already emitted by Codex: `command` plus optional `cwd`/`workdir` when present.
- Produces: `detect_campaign_contamination(parsed, manifest_rows, current_row, coordinator_root) -> list[dict]`.
- Receipt adds `protocol_contamination` and `contamination_evidence`; it never copies command output or unrelated host paths.

- [ ] **Step 1: Write RED parser test for preserving only bounded command path evidence**

```python
rows = [
    {"type": "item.started", "item": {"id": "c1", "type": "command_execution", "command": "Get-ChildItem D:\\coord", "cwd": "D:\\runtime\\abc"}},
    {"type": "item.completed", "item": {"id": "c1", "type": "command_execution", "command": "Get-ChildItem D:\\coord", "cwd": "D:\\runtime\\abc", "exit_code": 0, "status": "completed"}},
    {"type": "turn.completed", "usage": {}},
]
parsed = codex_automation.parse_cli_jsonl(self._write_jsonl(temp_dir, rows))
self.assertEqual(parsed["commands"][0]["command"], "Get-ChildItem D:\\coord")
self.assertEqual(parsed["commands"][0]["cwd"], "D:\\runtime\\abc")
```

- [ ] **Step 2: Write RED contamination test**

Build two manifest rows with opaque sibling workspace paths. A command referencing the coordinator root or the other row's frozen workspace must produce one bounded evidence item; references to the current workspace must not.

- [ ] **Step 3: Implement narrow detection**

Normalize Windows paths case-insensitively. Compare only command/cwd/workdir strings against the known coordinator root and known *other* row workspace bindings. Store only `{kind, command_id, path_sha256}`; do not store arbitrary command output or scanned host inventory.

- [ ] **Step 4: Run parser and run-row tests GREEN**

Run: `python -m unittest benchmarks.harness.test_codex_automation.CliJsonAdapterTests benchmarks.harness.test_codex_automation.RunRowWorkflowTests -v`
Expected: PASS and no existing token/MCP accounting regressions.

- [ ] **Step 5: Commit Task 4**

```powershell
git add benchmarks/harness/codex_automation.py benchmarks/harness/test_codex_automation.py
git commit -m "feat: record bounded routing contamination evidence"
```
### Task 5: Align stable contract/runbooks and verify the whole slice

**Files:**
- Modify: `docs/contracts/routing-eval-contract-r4.md`
- Modify: `docs/runbooks/routing-eval-cli-automation.md`
- Modify: `docs/runbooks/routing-eval-desktop.md`
- Modify/Test: `benchmarks/harness/test_codex_automation.py:OperatorArtifactTests`

**Interfaces:**
- Contract freezes opaque 128-bit path tokens, coordinator/runtime disjointness, JIT single-row materialization, and contamination invalidation.
- CLI runbook requires an explicit neutral runtime parent for scored automation and a non-scored leakage canary before fresh denominators.
- Desktop runbook no longer implies that `prepare` creates executable row workspaces.

- [ ] **Step 1: Add RED documentation assertions**

```python
runbook_text = runbook.read_text(encoding="utf-8")
for phrase in ("--runtime-parent", "opaque", "leakage canary", "concurrency is 1"):
    self.assertIn(phrase, runbook_text)
```

- [ ] **Step 2: Update contract and runbooks with the exact implemented behavior**

Document that prepared fixtures live under coordinator `fixtures/`, runtime workspaces use opaque 32-hex components outside coordinator/evidence ancestry, only the active row is materialized, task post-condition is checked before deletion, cleanup failure blocks the campaign, and contamination evidence invalidates the row. Keep CLI evidence explicitly secondary to Windows Codex Desktop product admission.

- [ ] **Step 3: Run all harness tests**

Run: `python -m unittest discover -s benchmarks/harness -p "test_*.py" -v`
Expected: PASS; previous baseline was 147 tests, and the total must increase with the new isolation tests.

- [ ] **Step 4: Run repository acceptance checks**

```powershell
pwsh.exe -NoProfile -File .\scripts\verify-local.ps1 -SkipBaseline
git diff --check
git status --short
```

Expected: verifier PASS, Python harness suite PASS, diff check clean, and only intended files modified.

- [ ] **Step 5: Perform scope/security self-review**

Confirm no new dependency, no ACL/sandbox/global-config change, no host-wide telemetry, no validation/holdout material, no raw evidence, and no product Rust/MCP/Skill behavior change entered the diff.

- [ ] **Step 6: Commit docs/acceptance alignment**

```powershell
git add docs/contracts/routing-eval-contract-r4.md docs/runbooks/routing-eval-cli-automation.md docs/runbooks/routing-eval-desktop.md benchmarks/harness/test_codex_automation.py
git commit -m "docs: freeze blinded routing row lifecycle"
```

### Task 6: Independent review, Draft PR, integration gate, then leakage canary

**Files:**
- No product files should change during read-only review.

- [ ] **Step 1: Request independent read-only review of the exact implementation HEAD**

Review must check arm/campaign cue removal, no eager peer/future workspaces, coordinator/runtime ancestry, profile+workspace cleanup on every exit path, CRLF fixture identity, bounded contamination evidence, and unchanged product/sandbox boundaries.

- [ ] **Step 2: Fix only validated review findings with new RED tests first**

For any behavior defect, add a failing regression test before the minimal fix; rerun focused and full verification.

- [ ] **Step 3: Open one-purpose Draft PR**

PR base must be the then-current public `main`; record exact base/head SHAs. Do not merge from a worker context.

- [ ] **Step 4: Leader independently verifies CI/local evidence and integrates**

Use the fixed noreply Git identity for local commits/merge operations. Update canonical task only after durable integration state changes.

- [ ] **Step 5: Freeze a fresh campaign identity and run the non-scored leakage canary**

Canary passes only if cwd/ancestors are semantically neutral, the runtime parent contains only the active opaque row during execution, no peer/future workspace is pre-created, coordinator/evidence is outside runtime ancestry, fixture/prompt/runtime/catalog identities pass, and both cleanup receipts pass. Do not score or reuse canary rows.

- [ ] **Step 6: Resume fresh S/M evaluation only after canary PASS**

Create a new denominator on the integrated public main. Never resume or combine the aborted `skill-necessity-cli-train-7455cfc-20260816-v1` rows. Validation/holdout remain sealed.
