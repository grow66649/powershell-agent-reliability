# MCP Packaging Canary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove that a minimal Node/TypeScript local STDIO MCP server starts, handshakes, answers one deterministic canary tool, and exits cleanly on the target Windows Codex Desktop development machine before any reliability product logic is added.

**Architecture:** Use the already-installed Node 24 runtime and the official MCP SDK. Keep the canary isolated from product contracts: one `psr_ping` tool only, no shell execution, environment inspection, persistence, network, or background daemon. A C# comparison is not admitted now because no .NET SDK is installed; reopen it only if the TypeScript canary fails a packaging/runtime requirement or a native-binary distribution requirement becomes proven.

**Tech Stack:** Node.js 24, npm 11, TypeScript, official Model Context Protocol SDK, Node built-in test runner.

## Global Constraints

- Target Windows Codex Desktop; standalone CLI is not the acceptance authority.
- STDIO stdout is protocol-only; diagnostics go to stderr.
- No shell/process execution tools in this canary.
- No new global dependency or PATH/profile mutation.
- Pin the selected MCP SDK through `package-lock.json`.
- One purpose: packaging/lifecycle proof only.

---

### Task 1: Freeze the local package and canary test

**Files:**
- Create: `package.json`
- Create: `tsconfig.json`
- Create: `src/server.ts`
- Create: `test/server.test.ts`

**Interfaces:**
- Produces: an executable server exposing only tool `psr_ping` with no input fields and deterministic result text `psr-ok`.

- [ ] **Step 1: Resolve and pin the SDK version**

Run:
```powershell
npm view @modelcontextprotocol/sdk version --json
```
Record the returned stable version by installing it as an exact dependency; do not install globally.

- [ ] **Step 2: Write the failing test**

`test/server.test.ts` must spawn the compiled server over stdio, complete the MCP initialize/list-tools flow using the SDK client transport, assert the tool list equals `['psr_ping']`, call it, assert the text equals `psr-ok`, close the client, and assert the child exits within 2 seconds.

- [ ] **Step 3: Run RED**

Run:
```powershell
npm test
```
Expected: failure because the server implementation/build output does not yet exist.

- [ ] **Step 4: Implement the minimum server**

`src/server.ts` must create one MCP server, register only `psr_ping`, connect to STDIO transport, write no non-protocol stdout, and exit cleanly after transport close.

- [ ] **Step 5: Run GREEN and typecheck**

Run:
```powershell
npm test
npm run check
```
Expected: test passes and TypeScript emits no errors.

- [ ] **Step 6: Verify scope**

Run:
```powershell
git diff --check
git diff -- package.json package-lock.json tsconfig.json src/server.ts test/server.test.ts
```
Confirm there is no shell command execution, environment dump, file mutation, network access, daemon/background service, or product tool surface.

- [ ] **Step 7: Commit**

```powershell
git add package.json package-lock.json tsconfig.json src/server.ts test/server.test.ts
git commit -m "test: prove local stdio mcp packaging"
```

### Task 2: Codex Desktop local lifecycle smoke

**Files:**
- Create: `docs/research/mcp-canary-smoke.md`

**Interfaces:**
- Consumes: compiled canary from Task 1.
- Produces: sanitized compatibility evidence only; no machine-specific live state is committed.

- [ ] **Step 1: Create an isolated Codex Desktop MCP configuration entry**

Point it directly at the local Node executable plus compiled server file. Do not use `npx`, PowerShell wrappers, or global package installation.

- [ ] **Step 2: Start a fresh Desktop task and call `psr_ping` once**

Expected result: `psr-ok`.

- [ ] **Step 3: Close the test task/app session and inspect process cleanup**

Verify no unexpected duplicate canary server process set remains after the owning Codex session is closed. Record only counts/timing and sanitized behavior in external evidence.

- [ ] **Step 4: Write the stable compatibility conclusion**

Commit only a short conclusion such as supported/unsupported plus the tested transport/runtime contract. Keep PIDs, user paths, task IDs, raw logs, and one-time process lists outside the repo.

- [ ] **Step 5: Gate**

If handshake or lifecycle is unreliable, stop product implementation and diagnose the integration boundary. If the canary is clean, the next plan may implement the first real tool, `inspect_environment`, by TDD.

## Self-review

- Spec coverage: packaging, stdout protocol, deterministic tool, shutdown/lifecycle, Desktop smoke, and no-product-logic boundary are covered.
- Placeholder scan: no TODO/TBD/"similar to" steps remain.
- Type consistency: one tool name (`psr_ping`) and one expected value (`psr-ok`) are used throughout.
