# OSS Publication Hygiene Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prepare the privacy-safe experimental baseline for a truthful first public GitHub push with MIT licensing, useful public documentation, minimal Windows CI, and bounded privacy cleanup, without changing product behavior or benchmark evidence.

**Architecture:** Keep the first-publication surface deliberately small: documentation + license + one CI workflow + two host-path cleanups. Reuse `scripts/verify-local.ps1` as the source-build/test gate and keep GitHub creation/push/release/application actions outside this implementation slice.

**Tech Stack:** Markdown, MIT License, GitHub Actions on `windows-latest`, `actions/checkout@v6`, `actions/setup-python@v6`, Rust 1.88.0, Python 3.14, PowerShell 7, existing Rust/Python test harness.

## Global Constraints

- Base/spec HEAD: `a62284917b4f9d487c4030af3d0efd25f9365c86` on `docs/oss-publication-hygiene-20260814`.
- License is MIT, copyright `2026 jh06`.
- Repository status must be explicit: `Experimental / pre-release`.
- Target is Windows Codex Desktop; Codex Desktop/app-server remains command/process/sandbox/approval owner.
- No Rust product behavior, MCP/Skill semantics, benchmark dataset/results/history, scorer threshold, Hook, Git history/ref, tag/release, or OpenAI application change.
- Do not claim users, downloads, dependents, production maturity, security audit, broad adoption, or an upstream Codex fix.
- Do not add telemetry, hosted service, installer, release upload, CLA, issue/PR bureaucracy, or marketing-only badges.
- First push remains a later explicit owner gate and must publish reviewed `main` only.
- Every task ends with `git diff --check`; final acceptance requires full `verify-local.ps1 -SkipBaseline` and independent publication review.

---
## File Structure

- Create `LICENSE`: standard MIT text.
- Rewrite `README.md`: public-facing project overview, status, scope, source-build/use/evidence/privacy boundaries.
- Create `CONTRIBUTING.md`: small executable contribution workflow.
- Create `SECURITY.md`: conservative private-reporting guidance and experimental scope.
- Create `.github/workflows/windows-ci.yml`: one source-build/test job only.
- Modify `docs/superpowers/plans/2026-08-13-r4-two-arm-routing-eval.md`: replace the one public-facing absolute worktree path with `<repo-worktree>` and repair the existing line break if needed.
- Modify `docs/superpowers/plans/2026-08-13-v02-agent-facing-contract.md`: replace the one public-facing absolute worktree path with `<repo-worktree>`.

### Task 1: Add the MIT License

**Files:**
- Create: `LICENSE`

- [ ] **Step 1: Create the exact MIT text**

Use the standard MIT License beginning:

```text
MIT License

Copyright (c) 2026 jh06

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
```
Continue exactly with:

```text
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 2: Verify the file and whitespace**

```powershell
Get-Content ./LICENSE
git diff --check
```

Expected: holder/year are exactly `2026 jh06`; no extra restrictions or custom clauses.

- [ ] **Step 3: Commit Task 1**

```powershell
git add LICENSE
git commit -m "docs: add MIT license"
```

### Task 2: Rewrite README for an unfamiliar maintainer

**Files:**
- Modify: `README.md`

**Interfaces:**
- README is the public entry point; internal plans remain supporting detail.
- All commands must work from the repository root without machine-specific absolute paths.
- [ ] **Step 1: Replace the opening with target + status**

Use this meaning, without stronger claims:

```markdown
# PowerShell Agent Reliability

PowerShell Agent Reliability is an experimental Windows Codex Desktop companion for diagnosing eligible PowerShell/native-command failures, exposing privacy-bounded environment identity, and checking deterministic task post-conditions. Codex Desktop/app-server remains the normal command, process, sandbox, and approval owner.

> **Experimental / pre-release.** The repository has accepted local harness/build evidence, but S-vs-M routing value, production shadow behavior, and harder end-to-end product value are still under evaluation. It is not a stable or production-ready release.
```

- [ ] **Step 2: Add the architecture and scope sections**

Keep this architecture block:

```text
Codex Desktop
  -> thin failure-only companion Skill
  -> local STDIO Reliability MCP
       -> inspect_environment
       -> diagnose_failure
       -> verify_result
```

Explain the three current tools and retain the non-goals: no replacement shell/terminal/sandbox, generic process runner, automatic ACL/security weakening, profile/global-environment mutation, universal quoting engine, or broad telemetry.

- [ ] **Step 3: Add prerequisites and source-build commands**

State Windows, Rust `1.88+`, Python `3.14` for the current verified harness, and PowerShell 7 for the documented verifier command. Show:

```powershell
cargo build --release
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
```
- [ ] **Step 4: Add local MCP and Skill usage without machine paths**

State that the release executable is `target/release/powershell-agent-reliability.exe`. Explain that Codex Desktop should be configured, through its supported MCP settings, to launch that executable as a local STDIO server; the repository does not mutate Codex configuration automatically.

State that the companion Skill source is `skills/powershell-reliability/` and should be made available through the user's supported Codex Desktop Skill workflow. Emphasize failure-only use: no Reliability intervention before a first eligible failure/false post-condition.

Point readers to `docs/runbooks/codex-desktop-acceptance.md` for the bounded local acceptance procedure instead of embedding a developer's absolute path.

- [ ] **Step 5: Add evidence, privacy, contribution, security, and license sections**

Evidence text must distinguish synthetic/local harness correctness from real product-value admission. Privacy text must say the product intentionally avoids returning full PATH/environment dumps and raw evidence stays local. End with links to `CONTRIBUTING.md`, `SECURITY.md`, and MIT `LICENSE`.

- [ ] **Step 6: Run README claim checks**

```powershell
git grep -n -i -E "production.ready|security audited|fix(es|ed)? (an )?upstream|users|downloads|dependents" -- README.md
```

Expected: no unsupported positive claim. Legitimate negations such as "not production-ready" are acceptable and should be manually inspected.

- [ ] **Step 7: Run the documented commands**

```powershell
cargo build --release
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```powershell
git add README.md
git commit -m "docs: prepare experimental project readme"
```
### Task 3: Add contribution and security guidance

**Files:**
- Create: `CONTRIBUTING.md`
- Create: `SECURITY.md`

- [ ] **Step 1: Create concise CONTRIBUTING.md**

It must state:

```markdown
# Contributing

This project targets Windows Codex Desktop. Read `AGENTS.md` before making repository changes.

Keep changes one-purpose and reviewable. Use TDD for behavior changes, preserve command outcome separately from task post-condition, and do not add a generic shell/process runner or weaken sandbox/ACL/security behavior.

Before requesting review, run the smallest focused tests, then:

```powershell
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
git diff --check
```

Do not commit credentials, raw Codex Desktop sessions, full PATH/environment dumps, unrelated machine inventory, or host-local evidence.
```
- [ ] **Step 2: Create conservative SECURITY.md**

Use this policy:

```markdown
# Security Policy

PowerShell Agent Reliability is experimental/pre-release software targeting Windows Codex Desktop. It has not undergone a formal security audit.

Please do not publish exploit details, credentials, private logs, or sensitive reproduction material in a normal public issue.

When the public GitHub repository has private vulnerability reporting enabled, use **Security -> Report a vulnerability**. If no private reporting channel is available, open only a minimal non-sensitive issue asking the maintainer to establish a private contact path; do not include exploit details in that issue.

Security reports should identify the affected revision/version, the security boundary involved, reproduction prerequisites, and the minimum evidence needed to reproduce safely. Never weaken Windows ACLs, Codex sandboxing, approval policy, PowerShell profiles, or global environment settings merely to demonstrate a report.
```

- [ ] **Step 3: Verify both files are executable guidance, not policy theater**

```powershell
git diff --check
git grep -n -E "verify-local|git diff --check|Report a vulnerability|formal security audit" -- CONTRIBUTING.md SECURITY.md
```

Expected: contribution verification and conservative private-reporting language are both present.

- [ ] **Step 4: Commit Task 3**

```powershell
git add CONTRIBUTING.md SECURITY.md
git commit -m "docs: add contribution and security guidance"
```

### Task 4: Add one minimal Windows CI workflow

**Files:**
- Create: `.github/workflows/windows-ci.yml`
- [ ] **Step 1: Create the workflow exactly as a source-build/test gate**

```yaml
name: windows-ci

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  verify:
    runs-on: windows-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v6
      - uses: actions/setup-python@v6
        with:
          python-version: "3.14"
      - name: Install Rust 1.88.0
        shell: pwsh
        run: |
          rustup toolchain install 1.88.0 --profile minimal --no-self-update
          rustup default 1.88.0
      - name: Verify source tree
        shell: pwsh
        run: pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
```
- [ ] **Step 2: Review workflow boundaries**

```powershell
Get-Content ./.github/workflows/windows-ci.yml
git grep -n -i -E "upload|release|artifact|codex.*session|environment dump|token" -- .github/workflows/windows-ci.yml
```

Expected: no upload/release/publish/raw-evidence step; the only job checks out, installs Python/Rust, and runs the existing verifier.

- [ ] **Step 3: Re-run the workflow command locally**

```powershell
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
```

Expected: PASS.

- [ ] **Step 4: Commit Task 4**

```powershell
git add .github/workflows/windows-ci.yml
git commit -m "ci: verify windows source build"
```

### Task 5: Sanitize current-tree host-specific fixtures and plan paths

**Files:**
- Modify: `benchmarks/harness/test_trigger_eval.py`
- Modify: `docs/superpowers/plans/2026-08-13-r4-two-arm-routing-eval.md`
- Modify: `docs/superpowers/plans/2026-08-13-v02-agent-facing-contract.md`

- [ ] **Step 1: Capture the privacy regression before editing**

The current privacy-safe `main` still contains three source-escaped private Windows user-profile Skill-path fixtures in `test_trigger_eval.py` plus two `D:/Work/...` planning-worktree literals. Record the exact hit count with private values supplied from host-local migration evidence; do not paste the private username/email into repo files.

- [ ] **Step 2: Replace the three test-fixture user-profile literals**

Use the neutral form already established in `test_routing_eval.py`:

```python
"Get-Content C:\\\\Users\\\\u\\\\.codex\\\\skills\\\\powershell-reliability\\\\SKILL.md -Raw"
```

Apply the same neutral user segment to the `concise-planning` fixture. Do not change call IDs, Skill names, event structure, or expected assertions.

- [ ] **Step 3: Run the trigger/routing regression suites**

```powershell
Push-Location benchmarks/harness
python -m unittest test_trigger_eval.py test_routing_eval.py -v
Pop-Location
```

Expected: PASS; fixture semantics are unchanged.

- [ ] **Step 4: Replace only the two absolute planning-worktree values**

In the r4 plan, replace the planning/design worktree with `<repo-worktree>` and put the following preserve-rule sentence on its own line. In the v0.2 plan, replace the writer worktree with `<repo-worktree>`.

- [ ] **Step 5: Verify the current tree**

```powershell
git grep -n -F "D:/Work/" -- . ":(exclude)docs/superpowers/specs/2026-08-14-oss-publication-hygiene-design.md" ":(exclude)docs/superpowers/plans/2026-08-14-oss-publication-hygiene.md"
```

Expected: no current-tree host-worktree hit outside the hygiene design/plan's generic scan description. The private user-profile scan is run with the host-local pattern in Task 6.

- [ ] **Step 6: Commit Task 5**

```powershell
git add benchmarks/harness/test_trigger_eval.py docs/superpowers/plans/2026-08-13-r4-two-arm-routing-eval.md docs/superpowers/plans/2026-08-13-v02-agent-facing-contract.md
git commit -m "test: sanitize host-specific fixtures"
```

### Task 6: Run current-tree and history privacy gates

**Files:**
- No new repo file; scan output remains host-local.

- [ ] **Step 1: Bind private search patterns outside the repo**

Set host-local environment variables from the private migration evidence: `PSR_PRIVATE_GIT_NAME`, `PSR_PRIVATE_GIT_EMAIL`, and `PSR_PRIVATE_USER_PATH_SOURCE`. The last value is the source-escaped private user-profile path fragment as it appears in Python source. Never write these values into public docs.

- [ ] **Step 2: Scan the current tree**

```powershell
$patterns = @($env:PSR_PRIVATE_GIT_NAME, $env:PSR_PRIVATE_GIT_EMAIL, $env:PSR_PRIVATE_USER_PATH_SOURCE)
if ($patterns | Where-Object { [string]::IsNullOrWhiteSpace($_) }) { throw "private scan patterns are not configured" }
foreach ($pattern in $patterns) {
  git grep -n -I -F -- $pattern HEAD -- .
  if ($LASTEXITCODE -eq 0) { throw "private literal remains in current tree" }
}
```

Expected: zero private-identity/user-profile hits in the current tree.

- [ ] **Step 3: Scan for credential/raw-evidence patterns**

```powershell
git grep -n -i -E "(api[_-]?key|access[_-]?token|refresh[_-]?token|authorization: bearer|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|codex.*sessions|<host-evidence-root>)" -- .
```

Inspect every hit manually. Documentation may discuss evidence concepts, but no live token, credential, session path, or private evidence path is allowed.

- [ ] **Step 4: Scan every public-reachable historical commit**

```powershell
$historyHits = @()
foreach ($commit in (git rev-list HEAD)) {
  foreach ($pattern in $patterns) {
    $hits = git grep -n -I -F -- $pattern $commit -- . 2>$null
    if ($LASTEXITCODE -eq 0) { $historyHits += $hits }
  }
}
$historyHits | Set-Content -Encoding utf8 $env:PSR_PUBLIC_HISTORY_PRIVACY_REPORT
if ($historyHits.Count -gt 0) { throw "public-reachable history still contains private literals" }
```

Under the currently observed pre-correction history this check is expected to fail because the private user-profile fixture existed in earlier commits. Treat that as a **publication blocker**, not as permission to weaken the scan.

- [ ] **Step 5: Hand off the history blocker to a separate owner-gated privacy rewrite**

Do not rewrite history inside this hygiene branch. Leader must create a separate content-history privacy plan that replaces only the proven private user-profile fixture/path literals across public-reachable commits, preserves technical semantics, remaps authoritative SHAs again, reruns full verification, and requires explicit owner approval before ref changes.

### Task 7: Verify the hygiene HEAD and prepare independent review

- [ ] **Step 1: Run the full local gate**

```powershell
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
```

Expected: PASS.

- [ ] **Step 2: Check scope and whitespace**

```powershell
git diff --check
git status --short
git diff --name-only a62284917b4f9d487c4030af3d0efd25f9365c86..HEAD
```

Expected changes only: approved hygiene spec/plan, `LICENSE`, `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `.github/workflows/windows-ci.yml`, three sanitized test-fixture literals in `test_trigger_eval.py`, and the two bounded planning-path edits.

- [ ] **Step 3: Independent publication review**

Reviewer checks exact HEAD, MIT text, README claims, SECURITY reporting boundary, CI workflow, full test evidence, current-tree privacy scan, and the history privacy report. A clean current tree with historical private hits is **not** public-ready; status must remain `BLOCKED_ON_HISTORY_PRIVACY` until the separate rewrite passes.

- [ ] **Step 4: Leader handoff**

Update `OPENAI-OSS-PRO-001` with the exact hygiene HEAD, verification evidence, current-tree scan result, and history-blocker evidence. Do not create a GitHub repo, remote, push, tag, release, or application submission from this plan.

## Self-Review Checklist

- Spec coverage: MIT, README, contribution/security docs, Windows CI, current-tree host/privacy cleanup, privacy/secret scan, first-push boundary, and independent review are mapped above.
- Privacy correction: source-escaped Windows paths are scanned in addition to rendered paths; the previous false negative cannot recur by searching only one representation.
- Placeholder scan: `<repo-worktree>` is intentional public replacement text, not unfinished work. Private search values are runtime environment variables sourced from private evidence.
- Scope: history rewrite is deliberately excluded from this plan and remains a separate owner-gated operation because it changes public-reachable commit identities again.