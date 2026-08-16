# Isolated Codex Experiment Automation Profile Design

Status: owner-approved isolated-profile design A; implementation is under review in Draft PR #1.

## Decision

Automated screening and train runs use a fresh disposable `CODEX_HOME` per row. The runner invokes the Codex CLI bundled with the installed Codex Desktop build, not whichever `codex` happens to appear first on `PATH`.

Windows Codex Desktop remains the product-admission runtime. CLI automation may replace repetitive manual execution only after an explicit Desktop-versus-CLI parity gate passes.

## Goals

- Keep the owner's live `~/.codex` state unchanged during experiments.
- Reuse the same Cockpit-backed model provider without putting credentials in the repository or command-line arguments.
- Give S and M identical runtime settings and the same Reliability MCP binary; companion-Skill exposure is the only intended routing difference.
- Exclude unrelated MCP servers, plugins, and Skills from automated runs.
- Use one fresh process, profile, workspace, and prompt submission per row.
- Preserve raw JSONL and deterministic post-condition evidence host-locally.
- Record exact token/tool-call fields and task wall-clock for each row; correctness/routing/safety remain primary, while timing is secondary paired evidence rather than a single-run winner metric.

## Non-goals

This slice does not build a generic shell runner, daemon, sandbox, provider manager, terminal, or general multi-agent framework. It does not change Reliability MCP behavior, Skill wording, train prompts, validation data, or the existing routing scorer semantics.
## Approaches considered

### A. Disposable full `CODEX_HOME` per row 鈥?selected

Create a minimal secret-bearing profile from an allowlisted snapshot of the live configuration, materialize an arm-specific Skill surface, configure only the frozen Reliability MCP, run one `codex exec --ephemeral --json`, then destroy the secret-bearing profile.

This is the selected design because it provides the strongest S/M isolation and does not mutate live Codex state.

### B. Global config plus per-invocation `-c` overrides 鈥?rejected

This leaves unrelated MCP servers, plugins, Skills, rules, and other user state visible unless every inherited surface is explicitly neutralized. It also tempts secret-bearing provider values onto the command line. The current host has already shown unrelated MCP/auth failures during unattended CLI probes.

### C. Native `--profile` overlay on the live base config 鈥?rejected for scored automation

A Codex profile layers configuration on top of the base user config. That is convenient for normal use but does not give a strong proof that inherited MCP/Skill/plugin surfaces were removed. It may remain useful for developer convenience, not for S/M evidence.

## Reuse boundary

The runner should reuse the existing Python benchmark/harness stack and the already prepared routing manifests/workspaces. PowerShell may remain a thin Windows launcher, but subprocess ownership, exact argv construction, timeout handling, JSONL capture, and record normalization belong in one focused Python runner.

The existing `routing_eval.py` remains the scorer/collector authority for routing semantics. Automation adds execution evidence; it does not become a second routing scorer.
## Profile construction

At campaign start, snapshot the live Codex configuration into an in-memory parsed representation. Copy only an explicit allowlist into a host-local base template:

- model and model provider identity;
- reasoning effort/summary and model verbosity when present;
- approval and sandbox policy;
- the active provider table needed for the Cockpit-backed Responses endpoint;
- only runtime flags that affect the frozen experiment, such as fast mode when explicitly present;
- exactly one `psr_reliability_native` MCP definition.

Do not copy history, desktop state, apps, marketplaces, memories, plugins, unrelated MCP servers, arbitrary hooks, or user automation state. Set plugin loading off in the experiment profile.

The provider table may contain credentials or credential-bearing headers. Those values are copied only from live config to the temporary profile on the same host. They are never printed, committed, passed through argv, embedded in normalized records, or copied into raw public evidence.

The secret-bearing base template and per-row profile directories must inherit or receive an ACL restricted to the current Windows user. Cleanup of the secret-bearing profile is an explicit post-condition. A cleanup failure blocks the campaign until the leftover profile is removed safely; the runner must not weaken ACLs to force cleanup.

A redacted profile manifest is preserved separately. It records non-secret runtime identity, source config hash, generated profile hash/fingerprint, Skill surface, MCP executable hash, and cleanup result. Before formal rows, `profile-check` creates or verifies one shared non-secret campaign identity lock binding the actual bundled CLI path/version/hash, Skill/MCP hashes, live-config hash, effective model/provider/reasoning/approval/sandbox identity, harness Git HEAD, and local public-main anchor. Every S/M row must match the same lock; provider credentials/headers are never stored in it.

## Skill isolation

`CODEX_HOME` isolation alone is insufficient: Codex can still discover Skills from external roots such as Mirasim. The runner therefore treats Skill visibility as an observed surface, not an assumption.

Profile bootstrap uses `codex debug prompt-input` without a model call to materialize built-in Skill files and enumerate the actual model-visible Skill catalog. The final profile writes explicit `[[skills.config]]` entries disabling every observed Skill.
For S, the final profile explicitly enables only `powershell-reliability`; the conformance probe must observe that Skill and no unrelated non-required Skills. For M, the same path is explicitly disabled; the conformance probe must observe no `powershell-reliability` Skill.

The profile is invalid if observed Skill visibility differs from the declared arm. Do not repair a row in place and continue scoring it.

Host-local design probes established the required mechanism before implementation: an empty isolated `CODEX_HOME` still exposed the Mirasim Skill root; an explicit disabled `skills.config` entry removed `powershell-reliability`; explicit enable restored it. After bootstrap, explicit disables also reduced the isolated S catalog to the Reliability Skill only and the isolated M catalog to zero Skills. These probes are design evidence, not product-effect evidence.

## MCP isolation

The final profile contains exactly one experiment MCP server: `psr_reliability_native`. Its executable path and SHA-256 are frozen at campaign preparation time. S and M must reference the same exact binary and tool schema.

Before a row is admitted, configuration inspection must show no unrelated MCP server in the temporary profile. A separate non-scored canary proves that the native Reliability server starts and exposes the expected diagnosis/environment/verification tools.

Do not copy OAuth state for unrelated connectors. Do not start or authenticate unrelated MCPs merely because they exist in the owner's normal Desktop configuration.

## Per-row execution

Each manifest row must resolve to the prepared external campaign layout (`prompts/<case-key>.txt` and `workspaces/<arm>/<case-key>` under the manifest directory); `case-key` must be one bounded ASCII Windows-safe component, rejecting reserved device names, reserved characters, control characters, trailing dot/space, and traversal/arbitrary prompt/workspace paths. Each admitted row receives:

1. a fresh disposable workspace materialized from its frozen fixture, with the actual pre-run UTF-8 text tree re-hashed against the manifest fixture identity before any profile/model call;
2. a fresh disposable `CODEX_HOME` cloned from the campaign base template;
3. an arm patch for S or M followed by a prompt-input conformance probe;
4. one fresh Desktop-bundled CLI process;
5. one exact prompt submitted once through redirected stdin;
6. raw stdout JSONL, stderr, exit code, timeout state, task wall-clock, and final message captured host-locally;
7. deterministic post-condition evaluation independent of assistant prose;
8. profile cleanup in a `finally` path.
The exact CLI command is constructed as an argument array, never one nested command string. The implementation must pin the bundled CLI path and verify its version/hash before campaign execution. Prompt bytes are redirected through stdin so shell quoting cannot change the manifest-frozen prompt.

The runner uses `--ephemeral --json`, the frozen workspace via `-C`, and the arm profile through `CODEX_HOME`. It must not use `--dangerously-bypass-approvals-and-sandbox`; the experiment preserves the frozen approval/sandbox policy from configuration.

The existing 360-second campaign timeout remains the external kill boundary for both arms. Timeout handling terminates the Windows process tree, then uses a bounded settle period and a final parent-kill fallback rather than waiting indefinitely. The runner records task wall-clock around the Codex process itself. Timing is secondary paired evidence: valid slow rows are retained, S/M order is balanced, and unstable timing is reported as inconclusive rather than forced into an arm-selection claim.

## Evidence and cleanup

Raw CLI stdout JSONL, stderr, final deterministic fixture state, and normalized routing records stay under a host-local evidence root outside the repository; the runner rejects repo-internal evidence roots and any evidence root equal to or below the row workspace so runner output cannot mutate a fixture after its pre-model hash check. Secret-bearing `CODEX_HOME` contents are not evidence artifacts.

The normalized execution receipt records at least: case/trial/arm, sequence, campaign-identity-lock hash, public-main and harness-Git anchors, CLI version/hash, redacted profile fingerprint, live-config/model/provider/reasoning/approval/sandbox identity, Skill/MCP hashes, prompt hash, workspace/fixture identity, process exit/timeout state, task wall-clock, ordered command/MCP attempt summaries with started/completed/terminal outcome evidence, post-condition truth, tool/Skill observations exposed by the rollout, token fields when present, and cleanup result.

A command exit of zero does not imply task success. The deterministic post-condition remains authoritative. Conversely, an agent/task failure under a valid protocol remains a scored negative rather than an invalid row.

If the process times out, the runner terminates only that row's process tree, records timeout separately from task/post-condition truth, performs cleanup, and stops the campaign if cleanup or arm-conformance cannot be proven.
## Desktop-versus-CLI parity gate

Parity is established in layers before CLI automation can replace manual train execution.

1. **Runtime identity:** bundled CLI version/hash, model, provider, reasoning effort, approval policy, sandbox policy, prompt bytes, workspace fixture, and Reliability MCP executable/hash match the frozen campaign identity.
2. **Surface identity:** S exposes the Reliability Skill and M does not; both expose the same Reliability MCP tools; no unexpected MCP/plugin surface is present in the isolated profile.
3. **Capability sessions:** run exactly four fresh non-scored capability sessions: Desktop-S, Desktop-M, CLI-S, and CLI-M. They may explicitly ask whether `powershell-reliability` is available/readable and may perform an explicit Reliability MCP canary. Self-report alone is insufficient; these sessions are separate from natural-task trials and cannot be reused as scored threads.
4. **Behavioral canaries:** run four train-visible natural cases (`TC-A`, `TT-A`, `NG-B`, `NW-A`) across Desktop-S/M and CLI-S/M for 16 fresh natural sessions with byte-equivalent prompts/fixtures. Natural prompts do not name the Skill, MCP, arm, evaluator, or expected activation. Deterministic post-condition truth plus command-failure-boundary, MCP-order, false-activation, and safety direction must satisfy the reviewed parity rule. A valid mismatch may repeat the entire four-cell case bundle once; persistent runtime-specific divergence fails parity and unstable evidence remains inconclusive.
5. **Evidence compatibility:** automated JSONL contains enough bounded facts for the existing collector/scorer or an explicitly reviewed adapter to produce the same trial semantics as Desktop rollout evidence. `item.started` establishes an attempt, `item.completed` records terminal outcome (including failed/declined completion), and started-only attempts remain visible. A timed-out row may preserve a valid prefix when only the final non-empty JSONL record is truncated; non-timeout or mid-stream corruption fails closed, and non-timeout output must contain a terminal turn event.

Until all applicable parity layers pass, CLI runs are screening/engineering evidence only. Even after parity, final product admission retains a bounded fresh Desktop confirmation sample.

## Screening versus formal evidence

The first automated workload is intentionally a small train-visible Skill-necessity screen. Its minimal isolated catalog is useful for estimating the direct marginal effect of adding the thin Reliability Skill to an otherwise identical Reliability-MCP surface.

That minimal catalog is **not** automatically evidence about competition with the owner's full personal Skill/plugin catalog. If the project later needs claims about collision/selection behavior in a realistic catalog, freeze a separate Desktop-equivalent catalog profile and re-run the relevant gate. Do not silently generalize the minimal-screen result.
## Concurrency policy

Initial campaign concurrency is `1`. This avoids turning Cockpit/account-pool scheduling, provider queueing, and host resource contention into hidden experiment variables while the automation boundary is being validated.

Concurrency may later increase only after a separate non-product contention check shows isolated profiles/workspaces remain independent and the relay/provider remains stable. If enabled, independent rows receive distinct `CODEX_HOME`, workspace, output, and process-tree identities. No concurrent rows may share a mutable arm toggle or secret-bearing profile directory.

S/M pairing order remains the manifest order. Parallel execution must never regroup all S rows and all M rows or change frozen sequence semantics merely for throughput.

## Failure classification

The runner separates at least these outcomes:

- profile/bootstrap invalidity;
- arm-surface conformance failure;
- provider/MCP startup failure;
- Codex process non-zero exit;
- external timeout/cancellation;
- protocol invalidity such as prompt/workspace mismatch;
- valid agent/task failure;
- deterministic post-condition failure;
- cleanup failure.

Infrastructure/protocol invalidity does not become a task negative. A valid task failure does not become an infrastructure retry. Failed scheduled validation/holdout attempts are never discretionarily retried.

## Security boundary

The runner never logs provider tokens, authorization headers, cookies, full environment dumps, or unrelated configuration. It records hashes and redacted identities instead.

Temporary profile ACLs must be applied using the current Windows identity, not an assumed short username. The implementation verifies the ACL before starting Codex and verifies profile removal afterward.

No automation step weakens Windows ACLs, Codex sandboxing, approval policy, PowerShell profiles, or global environment settings. Live `~/.codex` is read as source input only and remains byte-for-byte unchanged by a run.
## Host design probes completed before implementation

Read-only/disposable probes on the owner host established the feasibility assumptions behind this design:

- the admitted Desktop-bundled CLI is `0.148.0-alpha.9`; the older PATH CLI remains excluded;
- a minimal temporary profile loaded the intended model/provider, reported exactly one configured MCP, passed MCP configuration checks, and reached the Cockpit-backed provider;
- `CODEX_HOME` alone did not hide externally discovered Mirasim Skills;
- explicit `skills.config` disable removed the Reliability Skill from the observed prompt catalog and explicit enable restored it;
- after bootstrap and explicit disables, S exposed exactly one Skill (`powershell-reliability`) while M exposed zero Skills;
- the secret-bearing provider probe directory was removed successfully;
- the live Codex config hash was unchanged before/after the probes.

Raw probe evidence and host-specific paths remain outside the repository and are referenced from the canonical project task.

## Proposed implementation shape

Keep the implementation narrow:

- `benchmarks/harness/codex_automation.py` 鈥?deterministic profile builder, arm-conformance probe, exact CLI subprocess execution, timeout/process-tree cleanup, and bounded execution receipt;
- `benchmarks/harness/test_codex_automation.py` 鈥?TDD fixtures for allowlisting, secret redaction, Skill/MCP isolation, argv construction, timeout classification, and cleanup;
- `scripts/run-routing-automation.ps1` 鈥?thin Windows entrypoint that locates Python and forwards typed arguments; no experiment logic;
- `docs/runbooks/routing-eval-cli-automation.md` 鈥?operator procedure, parity gate, evidence locations, cleanup, and manual Desktop confirmation steps.

Do not modify Rust product code, Skill wording, routing cases, sealed validation content, or the existing S/M scorer in this slice unless a focused compatibility test proves an adapter is necessary.
## Test and acceptance boundary

Implementation begins with RED tests for:

- refusing the PATH CLI when it does not match the frozen Desktop-bundled identity;
- copying only allowlisted config keys/sections and never emitting secret values into receipts/logs;
- producing exactly one Reliability MCP in the generated profile;
- S catalog conformance and M catalog conformance from `debug prompt-input` output;
- prompt delivery through stdin without byte drift;
- one shared campaign identity lock across S/M rows, with runtime drift rejected before model execution;
- one fresh `CODEX_HOME`/workspace/output namespace per row;
- strict Windows-safe `case-key` validation and evidence-root/workspace separation;
- started/completed command/MCP identity pairing, failed/declined terminal outcomes, and timeout final-line truncation handling;
- timeout versus process failure versus valid task failure classification;
- deterministic post-condition truth remaining independent from process exit/final prose;
- cleanup success and fail-closed handling of leftover secret-bearing profiles;
- the normal Windows verifier actually executing and compiling the automation runner/test module.

The slice is accepted only when focused automation tests pass, existing routing scorer tests remain green, repo-wide verification passes, `git diff --check` is clean, exact-head Windows CI runs the automation suite, and a fresh independent implementation review accepts the exact head. Model-bearing parity starts only after that merge/verification gate.

Model-bearing parity canaries may run only after the automation PR is accepted, merged, and the merged public main is reverified. The automated Skill-necessity screen and any scored train rows remain blocked until parity passes.

## Owner decision already fixed

The owner selected design A: disposable isolated profiles. No further choice between A/B/C is required. Implementation remains in Draft PR #1 until the current review blockers close, exact-head Windows CI covers the automation suite, and a fresh independent rereview accepts the head.