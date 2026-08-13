# r4 Codex Desktop Routing Evaluation Runbook

## Scope

Use this runbook only after the harness slice has been independently reviewed. It operates normal Windows Codex Desktop; it does not use standalone Codex CLI as the product acceptance surface.

The controlled comparison is S=`thin companion Skill + MCP` versus M=`MCP-only self-routing`. Arm H is excluded for the current Desktop build.

The harness never switches user-wide Skill or Codex settings automatically. Arm setup must be explicit, supported, reversible, and operator-controlled.

## 1. Freeze exact harness identity

Before any canary or scored turn, record:

- `git rev-parse HEAD` for the reviewed harness commit;
- SHA256 of `benchmarks/harness/routing_eval.py`;
- SHA256 of the candidate Reliability MCP executable;
- Codex Desktop build, model, reasoning effort, approval policy, and sandbox type;
- the fixed campaign seed and case-set hash.

Do not mix rows from different identities in one admission report.

## 2. Run the S canary

Use a fresh Desktop thread and disposable workspace. Confirm the observed Skill catalog contains `powershell-reliability` and the candidate Reliability MCP is reachable through its intended tool surface.

The S canary is explicit capability proof, not an implicit routing trial. Keep it out of recall and false-activation denominators.
## 3. Run the M canary

Establish M only through a supported reversible setup that removes `powershell-reliability` from the observed Skill catalog while leaving the same Reliability MCP candidate reachable.

Verify both facts from the fresh M thread before any scored turn. If supported reversible Skill exclusion is unavailable, M setup is BLOCKED rather than simulated.

Do not hide catalog evidence after collection, rename the arm, weaken unrelated global configuration, or infer MCP-only behavior from S rows.

## 4. Freeze the reviewed dataset

The future controlled core path is `benchmarks/routing_eval/core_cases.json`. That file is created and frozen only by the separate owner-reviewed dataset/campaign plan after this harness review.

Do not author or tune the 24-case core in this implementation slice. The later plan freezes train and validation before execution and creates the unseen holdout only after train-driven routing changes are frozen.

Prepare a campaign only from the reviewed frozen cases:

```powershell
python .\benchmarks\harness\routing_eval.py prepare `
  --cases .\benchmarks\routing_eval\core_cases.json `
  --output-root <host-local-evidence-root> `
  --trials 3 --seed <frozen-seed>
```

Record the generated manifest hash before running scored turns.
## 5. Execute manifest rows in normal Desktop

For every manifest row:

1. Apply the declared S or M setup and re-check its catalog invariant.
2. Start a fresh Codex Desktop thread; do not reuse conversational state.
3. Use exactly the manifest workspace. Never reuse the paired arm's mutated workspace.
4. Submit the generated prompt file unchanged. Do not add arm names, Skill hints, MCP hints, expected failures, or evaluator instructions.
5. Allow Codex Desktop/app-server to own normal command/process execution.
6. Preserve the resulting rollout JSONL under the host-local evidence root.

Raw rollout evidence stays host-local. Do not copy full transcripts, credentials, full PATH/environment, or unrelated machine state into the repository.

## 6. Collect after each bounded batch

Run collection against the actual Desktop sessions root:

```powershell
python .\benchmarks\harness\routing_eval.py collect `
  --manifest <host-local-evidence-root>\manifest.jsonl `
  --sessions-root <codex-desktop-sessions-root> `
  --output <host-local-evidence-root>\records.jsonl `
  --report <host-local-evidence-root>\collect-report.json
```

Review expected, collected, invalid, and remaining counts plus the next prompt/workspace pointers. Wrong workspace, duplicate identity, prompt drift, or arm-catalog mismatch is not repaired in place; preserve evidence and stop the affected batch.
## 7. Stop on hard guardrails

Stop the affected frozen revision immediately if a valid trial shows any pre-boundary Reliability MCP use, a Reliability-caused wrong repair, or a Reliability-caused false completion. Preserve the evidence; do not patch validation/holdout behavior and continue under the same identity.

Train is the only lane that may motivate a later separately reviewed routing-description revision. Validation and holdout are evaluation-only.

Do not claim a rate from an incomplete planned denominator after an early stop.

## 8. Adjudicate and score

Keep causal human labels in a separate bounded adjudication JSONL with evidence references. Unreviewed or ambiguous causality stays null.

```powershell
python .\benchmarks\harness\routing_eval.py score `
  --records <host-local-evidence-root>\records.jsonl `
  --adjudication <host-local-evidence-root>\adjudication.jsonl `
  --report <host-local-evidence-root>\score-report.json
```

Review case-level S/M outcomes and missing-measurement coverage, not only aggregate gates. Harness success does not establish product value.

## 9. Production shadow and downstream A/B

The controlled harness does not infer production-shadow evidence. The later user-authorized lane covers at least 300 normal turns under the selected real configuration and applies the frozen production-shadow threshold.

Only after the owner selects S or M and the shadow gate is satisfied may the selected routing shape proceed to the harder repeated autonomous-Desktop versus Reliability recovery A/B.

Main merge, release packaging, plugin/default recommendation, and always-on recommendation remain blocked until those downstream gates and explicit owner admission pass.
