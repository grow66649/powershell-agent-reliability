# OSS Publication Review-Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the independent publication review's two Important current-tree findings without rewriting Git history, changing product behavior, or publishing anything.

**Architecture:** Apply a docs-only portability/reference repair on an isolated descendant of blocked hygiene HEAD `d9eaa6bb3c13da0263d90e73f05c9cf1a920de6c`. Replace host-specific command examples with explicit local placeholders and remap stale pre-rewrite SHA references to equivalent commits reachable from the intended public lineage, then rerun the full publication review gates.

**Tech Stack:** Markdown, Git, PowerShell 7, existing repo verifier.

## Global Constraints

- Worktree=`<repo-worktree>`.
- Branch=`fix/oss-publication-review-20260814`; base=`d9eaa6bb3c13da0263d90e73f05c9cf1a920de6c`.
- Current main stays `3ea553262d6d13462bde698a321b06d5db4d786c` until independent reviewer PASS.
- No history rewrite, rebase, filter-repo, main fast-forward, remote, push, tag, release, or application action in this plan.
- No Rust/MCP/Skill/benchmark-data/scorer-threshold behavior change.
- Review findings are exact: five host-local evidence/session path lines and seven references to four pre-rewrite/non-public SHAs.

---
### Task 1: Make the trigger-eval campaign example host-portable

**Files:**
- Modify: `docs/contracts/skill-trigger-eval-contract-v0.2.md`

- [ ] **Step 1: Capture the RED review condition** with the host-local dual-form privacy scan (rendered + source-escaped patterns supplied from private evidence); record the five contract hits without copying those host-specific prefixes into this tracked plan.
- [ ] **Step 2: Replace the absolute examples with quoted PowerShell placeholders** defined immediately before the commands:

```powershell
$EvidenceRoot = '<evidence-root>'
$SessionsRoot = '<codex-desktop-sessions-root>'
```

Use `Join-Path $EvidenceRoot ...` for manifest/output/report arguments. Keep the commands illustrative and state that both values are host-local operator paths, not repository paths.
- [ ] **Step 3: Re-run the dual-form host-local scan** across tracked current-tree files; expect zero hits in both rendered and source-escaped representations.
- [ ] **Step 4: Check README/AGENTS consistency**: the contract must not imply raw sessions/evidence belong in the repo.
- [ ] **Step 5: Run** `git diff --check`; commit Task 1 as `docs: make trigger evaluation paths portable`.

### Task 2: Remap stale public SHA references

**Files:**
- Modify: `docs/superpowers/specs/2026-08-14-oss-publication-hygiene-design.md`
- Modify: `docs/superpowers/plans/2026-08-14-oss-publication-hygiene.md`
- Modify: `docs/superpowers/plans/2026-08-13-r4-two-arm-routing-eval.md`
- Modify: `docs/superpowers/plans/2026-08-13-v02-agent-facing-contract.md`

**Reachable replacement identities:**
- `fix: close r4 routing review gaps` -> `3ea553262d6d13462bde698a321b06d5db4d786c`.
- `docs: record publication privacy blocker` -> `a62284917b4f9d487c4030af3d0efd25f9365c86`.
- `docs: define r4 two-arm routing evaluation` -> `0a7970a5cd6494d9c19c5d3530613e4d95362fdc`.
- `fix: bound failure-only reliability workflow` -> `5cd67a80a8a7fb63f1704aa996f31ee47e7b54ed`.
The four pre-rewrite full SHA strings come from the reviewer handoff and are used only as search inputs during execution; they are not retained in the final public-facing plan text.
- [ ] **Step 1: Verify every mapped target is reachable from the blocked hygiene HEAD** with `git merge-base --is-ancestor <new-sha> HEAD`; all four must return exit 0 before editing.
- [ ] **Step 2: Replace only the seven identified textual references** using the mappings above. Preserve the surrounding historical meaning and commands; do not rewrite commit history.
- [ ] **Step 3: Scan the current tree for the four pre-rewrite full SHAs supplied by the reviewer handoff**; expect zero hits and do not add those values to new public-facing documentation.
- [ ] **Step 4: Scan tracked Markdown for full 40-hex tokens.** For each token, run `git cat-file -e <sha>^{commit}` and `git merge-base --is-ancestor <sha> HEAD`. Any non-reachable commit reference is a blocker unless the text explicitly labels it as a non-public historical identifier approved by the owner; no such exception is planned for this fix.
- [ ] **Step 5: Run** `git diff --check`; commit Task 2 as `docs: remap public history references`.

### Task 3: Re-run publication gates and hand off independent review

**Files:**
- Verify only; no new production files.

- [ ] **Step 1: Run the current-tree host-path/privacy scan** using the reviewer-reported absolute evidence/session prefixes and the four private-literal patterns from host-local evidence. Also scan for concrete maintainer worktree paths. Expected: no prohibited current-tree hits; generic documentation explaining how to scan for host paths is not itself a private host path.
- [ ] **Step 2: Run the intended-history private-identity/path scan** used after the second privacy rewrite. This checks privacy literals only; generic historical host-layout strings are not a third-history-rewrite gate under the owner's current decision.
- [ ] **Step 3: Run the unreachable-full-SHA scan** from Task 2 across tracked Markdown; expected zero unapproved non-reachable SHA references.
- [ ] **Step 4: Run** `pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline`; expect PASS.
- [ ] **Step 5: Run** `git diff --check`, `git status --short --branch`, `git diff --name-only d9eaa6bb3c13da0263d90e73f05c9cf1a920de6c..HEAD`, and confirm changes are limited to this plan plus the five approved documentation files.
- [ ] **Step 6: Prepare an independent read-only reviewer handoff** with exact base/HEAD, commits, changed files, full verifier result, host-path scan result, stale-SHA scan result, and confirmation that no history/main/remote/publication action occurred.
- [ ] **Step 7: STOP.** Do not fast-forward main. Reviewer PASS is required first.

## Self-review checklist

- [ ] Both Important findings are addressed directly.
- [ ] No third history rewrite was performed or implied.
- [ ] All four replacement SHAs are reachable from the candidate public lineage.
- [ ] Current public docs contain no host-specific evidence/session path examples.
- [ ] No unapproved unreachable full-SHA reference remains in tracked Markdown.
- [ ] No product/benchmark behavior changed.
- [ ] No unfinished implementation step remains; `<evidence-root>` and `<codex-desktop-sessions-root>` are intentional literal public path tokens.
