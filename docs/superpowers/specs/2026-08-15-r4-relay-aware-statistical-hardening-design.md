# r4 Relay-Aware Statistical Hardening Design

## Goal

Harden the S=`Skill+MCP` versus M=`MCP-only` evaluation against stochastic latency introduced by the user's Codex API relay, upstream queueing, network variation, and model-service variation without changing product routing behavior or the already frozen natural-task dataset.

This design changes measurement and interpretation only. It does not change the Rust MCP, Skill trigger text, case prompts, fixtures, validation seal, failure taxonomy, or safety boundaries.

## Fixed experimental facts

- Scored train remains 14 cases x 3 repeats x 2 arms = 84 turns.
- The prepared schedule remains 42 adjacent matched S/M pairs.
- First-arm order remains exactly balanced: 21 S-first and 21 M-first pairs.
- Frozen safety timeout remains T=360 seconds and is only a common stopping bound.
- Valid slow/tail observations are retained; no discretionary outlier deletion is allowed.
- Validation remains sealed from any train-driven routing writer until a candidate routing revision is frozen.

## Capability proof is separate from routing evaluation

Capability canaries and scored natural-task trials are separate Desktop sessions by construction. A capability session may directly ask whether `powershell-reliability` is available and require an actual Skill read plus an actual Reliability MCP call. A scored session never receives that question, the canary transcript, an arm label, a Skill hint, an MCP hint, or expected-routing guidance.

Capability self-report is corroborating evidence only. Positive S capability requires catalog presence, actual Skill read, and actual MCP call evidence. M capability requires catalog absence plus the same MCP surface remaining callable. Canary rows never enter scored denominators.

## Outcome hierarchy

Primary product conclusions use outcomes that the relay cannot plausibly manufacture by merely delaying a response:

1. deterministic task completion/post-condition truth;
2. Reliability-caused wrong repair and false completion hard gates;
3. routing recall and false activation;
4. repair/tool-call burden;
5. paired token overhead.

End-to-end wall-clock latency is secondary. It can strengthen or weaken a recommendation, but it cannot override a correctness or safety failure.

## Paired latency estimand

For each valid matched `(case_id, trial_id)` pair, compute:

`d_ij = log(T_S / T_M)`

where `T_S` and `T_M` are end-to-end turn durations from rollout timestamps. Negative values favor S; positive values favor M. Log ratios are used because relay jitter is naturally multiplicative and because a 2x slowdown and a 2x speedup become symmetric around zero.

The three repeat-level values for each case are collapsed to one case-level value using their median. The primary latency point estimate is the median of the 14 case-level medians, transformed back to a multiplicative S/M ratio for reporting.

Raw arithmetic arm means remain descriptive only. They are never the latency winner criterion.

## Uncertainty and heavy-tail handling

Uncertainty is computed at the case cluster, not by pretending the three repeats are 42 independent tasks.

- Cluster bootstrap: resample the 14 case IDs with replacement, keeping all three repeats of a sampled case together; recompute the case medians and overall median for each resample.
- Freeze bootstrap seed and 20,000 resamples before scored row 1.
- Report the percentile 95% interval for the median log-ratio and its transformed S/M ratio.
- Also report the number of case-level medians below, equal to, and above zero and an exact two-sided sign-test probability over non-tied case directions as a robustness diagnostic.

No valid observation is removed merely for being slow. A genuinely malformed rollout or protocol-invalid trial remains excluded under the existing validity rules, not a new latency-specific trimming rule.

## Order and time diagnostics

The existing adjacent-pair schedule is preserved because it minimizes temporal distance between S and M observations. Report repeat-level `d_ij` separately for S-first and M-first pairs.

Latency is marked `INCONCLUSIVE` if the order-stratified medians have opposite signs, or if the case-cluster 95% interval includes zero. A directional latency finding requires both order strata to have the same sign as the overall estimate and the 95% interval to exclude zero. The exact sign test is reported but is not a standalone gate.

This rule deliberately prefers an inconclusive timing result over attributing relay or queue jitter to the product arm.

## Non-scored A/A relay-noise sentinel

Before scored train, run 12 matched M/M pairs (24 turns) using one reviewed neutral no-trigger task while the Skill is absent and the same MCP is configured, fresh workspaces, and fresh Desktop threads. Split them into three time blocks of four pairs so the observation is not confined to one short provider/relay condition.

The A/A sentinel never enters S/M product denominators and cannot tune Skill/MCP routing. It estimates ambient relay/runtime jitter only. Report `abs(log(T_1/T_2))` p50 and p90, block-level medians, and the signed first-minus-second log ratio to reveal period effects.

Do not subtract A/A latency from scored S/M latency. It is a diagnostic context for whether observed timing effects are large relative to ambient variation.

## Token and tool-call treatment

Tokens and tool calls remain separate paired outcomes. Do not regress end-to-end latency on output/reasoning tokens in the primary analysis because fewer tokens or calls may be a real mechanism by which one routing arm helps.

For scorable matched pairs, report median relative token delta and median tool-call delta. The existing validation+holdout idle-token gate remains unchanged: median S-vs-M idle-token overhead <= +2% with >=90% pair coverage.

## Relay identity and claim boundary

The runtime freeze records the existing Desktop/model/effort/approval/sandbox/MCP identities plus a privacy-safe relay-route fingerprint if one can be derived without credentials, tokens, raw authorization headers, or endpoint secrets. Otherwise record `UNKNOWN`.

Any latency conclusion is explicitly conditional on the observed relay-mediated runtime. It is not a universal claim about OpenAI-hosted Codex latency.

## Rejected alternatives

- Raw S mean versus raw M mean: rejected because relay/model-service tail latency can dominate the mean and grouped timing can create order bias.
- Deleting slow runs or winsorizing after seeing outcomes: rejected because it creates analyst discretion and can erase real user-visible tails.
- Token-adjusted primary latency regression: rejected because tokens/tool calls can be treatment mechanisms rather than pure nuisance variables.
- A large mixed-effects model as the primary analysis: deferred. With only 14 independent case clusters, a simpler paired case-level analysis is easier to audit and less assumption-heavy. A mixed model may be exploratory after the frozen analysis closes, never a gate-changing rescue analysis.

## Required harness/report changes

The scorer should add a descriptive `paired_latency` section without changing existing admission thresholds. It must expose pair coverage, case coverage, case-level medians, overall median ratio, cluster-bootstrap interval, sign counts/test, S-first versus M-first medians, and a `DIRECTIONAL|INCONCLUSIVE|UNRESOLVED` interpretation field. Missing durations remain missing.

The A/A sentinel can use a small separate host-local helper or bounded scorer mode; it must not require product-code changes or persist raw relay credentials.

## Tests

Add deterministic unit tests for log-ratio pairing, repeat-to-case aggregation, fixed-seed cluster bootstrap reproducibility, order-sign disagreement => `INCONCLUSIVE`, missing latency coverage, no outlier trimming, and A/A diagnostic summaries. Keep existing 102 harness tests green and run the repository verifier plus `git diff --check` before integration.

## Scope boundary

This slice is analysis infrastructure only. No product routing behavior, MCP schema, Skill trigger wording, frozen train prompts/fixtures, validation content, T=360s, or arm definition may change.
