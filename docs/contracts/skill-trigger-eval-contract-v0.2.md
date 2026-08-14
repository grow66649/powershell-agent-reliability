# PowerShell Reliability Skill Trigger Evaluation Contract v0.2

## Decision question

Does the installed `powershell-reliability` Skill get selected after eligible Windows Codex Desktop failures, stay unselected on adjacent/non-trigger work, and avoid pre-first-attempt intervention?

This gate measures Skill selection and routing only. It does not by itself prove diagnosis quality, repair quality, or product value.

## Authority

Final evidence comes from real Windows Codex Desktop rollout JSONL, not model self-report.
The rollout must originate from Codex Desktop and expose the same installed Skill catalog and Reliability MCP candidate used for product acceptance.

A selected Skill is observed when the agent actually reads the installed `powershell-reliability/SKILL.md` during the turn. Catalog presence alone is not selection.
Reliability MCP calls are recorded separately from Skill selection.

## Dataset

The repository contains 25 sanitized implicit-trigger cases:

- 10 `should_trigger` cases covering eligible failure boundaries;
- 10 `should_not_trigger` cases covering known-good, explanation/code-writing, warning-only, and unrelated work;
- 5 `boundary` cases for ambiguous timing or mixed outcomes.

Each case is repeated at least three times for admission claims.

## Implicit-lane hygiene

Implicit prompts must not name the Skill, tell Codex to load a Skill, or describe the MCP workflow.
A neutral `[CASE-ID: ...]` marker is allowed only so the local collector can bind a rollout to a sanitized case/trial identity.

Use a fresh Desktop thread for every trial. Keep model, effort, approval/sandbox settings, installed Skill, candidate binary, and available-Skill catalog stable across the campaign.
Randomize case/trial order with a fixed recorded seed.

If a case declares an exact first command, the collector records whether the first shell call matched it. A mismatch makes the trial unsuitable for automatic trigger interpretation until manually reviewed.

## Selection timing

For eligible execution-failure cases, correct timing is:

1. no Skill read and no Reliability MCP call before the first command;
2. observe the failed command/task boundary;
3. select/read the Skill if the boundary matches its description;
4. follow the failure-only workflow.

Any Skill read or Reliability MCP call before the first command is a timing violation for first-attempt cases.

For `should_not_trigger` cases, any Skill selection is a false positive even if no MCP call follows.

## Automated record contract

`benchmarks/harness/trigger_eval.py` performs four bounded jobs:

- `prepare`: render randomized trial prompts and disposable workspaces from `benchmarks/trigger_eval/cases.json`;
- `collect`: scan Codex Desktop rollout JSONL for known case markers and extract bounded selection/tool metadata;
- `score`: compute selection recall, false-positive rate, timing violations, collisions, case stability, and environment consistency;
- collection is idempotent over the same unique case/trial set and rejects duplicate rollouts for one case/trial.

The collector must not inject prompts into Codex Desktop, alter the Skill/MCP, or create a second command runner. It only reads the rollout evidence Codex Desktop already produced.

Persisted trigger records omit the raw user prompt and raw first-command text. They retain hashes, case/trial identity, bounded runtime metadata, observed selection, MCP-call counts, and the raw rollout path as the evidence pointer.

## Metrics

Report at minimum:

- selection recall on `should_trigger`;
- false-positive rate on `should_not_trigger`;
- per-case selection stability across repetitions;
- pre-first-attempt Skill-selection violations;
- pre-first-attempt Reliability MCP-call violations;
- other-Skill collision trials;
- Reliability MCP calls on non-trigger cases;
- first-command conformance where the case freezes one;
- environment consistency for model, effort, Codex build, approval policy, sandbox type, and Skill catalog presence.

## Screening gate

The following are project screening rules, not a universal OpenAI Skill standard:

- deterministic `should_not_trigger` controls target zero false positives;
- first-attempt cases target zero pre-first-attempt Skill/MCP intervention;
- environment/catalog drift must be zero before aggregate rates are trusted;
- `should_trigger` cases should select consistently across repeated trials; any repeated false negative must be reviewed before product admission;
- boundary cases are reported separately and are never silently folded into recall or false-positive denominators.

No aggregate percentage overrides human review. The user reviews the case-family table and representative false positives/false negatives before default/recommended activation.

## Explicit invocation lane

Explicit `$powershell-reliability` invocation is measured separately. Explicit trials verify that an intentional selection still obeys first-attempt, one-repair, and final-verification guards.
Explicit results must never be mixed into implicit recall or false-positive metrics.

## Campaign workflow

Prepare one three-repeat campaign. Set both variables to host-local operator paths; they are not repository paths:

```powershell
$EvidenceRoot = '<evidence-root>'
$SessionsRoot = '<codex-desktop-sessions-root>'

python .\benchmarks\harness\trigger_eval.py prepare `
  --cases .\benchmarks\trigger_eval\cases.json `
  --output-root $EvidenceRoot `
  --trials 3 --seed 20260813
```
After running fresh Desktop threads from the generated prompts, collect and score:

```powershell
python .\benchmarks\harness\trigger_eval.py collect `
  --manifest (Join-Path $EvidenceRoot 'manifest.jsonl') `
  --sessions-root $SessionsRoot `
  --output (Join-Path $EvidenceRoot 'records.jsonl') `
  --report (Join-Path $EvidenceRoot 'report.json')
```

The collector reports the next uncollected prompt path, so the campaign can be resumed without manual bookkeeping.

## Evidence interpretation

A rollout-derived trigger record is executed evidence. A case definition is proposed/expected behavior until a real Desktop rollout exists.
Static Skill audits and synthetic parser tests do not substitute for trigger trials.
Harder end-to-end A/B remains a later product-value gate after trigger usability is acceptable.
