# PowerShell Agent Reliability Benchmark Contract

## Decision question

Does a failure-only PowerShell Reliability MCP materially improve Windows Codex Desktop diagnosis and task completion compared with Codex Desktop solving the same failures autonomously, while keeping normal successful work effectively unchanged?

The benchmark exists to falsify the product if the answer is no. Synthetic fixtures alone can never justify shipping or default activation.

## Compared paths

### A — Codex Desktop autonomous baseline
- Same Codex Desktop build, model family/effort, workspace, permissions, and task.
- No PowerShell Reliability MCP or companion Skill assistance.
- Codex may inspect and repair failures using its ordinary tools and reasoning.

### B — Codex Desktop + PowerShell Reliability
- First execution attempt is identical to A.
- Reliability intervention is allowed only after a bounded failure trigger or failed task post-condition.
- The companion Skill may call the MCP for diagnosis/environment identity/post-condition verification.
- A successful first attempt whose post-condition passes must not invoke reliability analysis.

## What the project can plausibly improve

The MCP does not make PowerShell intrinsically more correct and does not replace Codex reasoning. Its value hypothesis is narrower:
1. expose machine facts that are otherwise rediscovered through trial and error;
2. distinguish command success from task success;
3. classify common Windows/PowerShell failure boundaries consistently;
4. reduce wrong repair branches, repeated commands, and false-completion claims;
5. preserve an explicit `UNKNOWN` result instead of confident unsupported diagnosis.

## Two benchmark layers

### Layer 1 — diagnostic benchmark
Give A and B the same sanitized failure evidence and ask for root cause plus next action.
Measure classification accuracy, first-action correctness, tool calls, elapsed time, and unsupported-confidence rate.

### Layer 2 — end-to-end Codex Desktop benchmark
Replay representative local tasks from a clean disposable state.
Measure actual completion, repair turns, wrong repair attempts, wall time, tool calls, false completion, and intervention cost.
Only this layer can admit default or recommended use.

## Fixture runner contract

Each synthetic fixture runs in its own child process with an explicit shell binary, explicit cwd, bounded environment delta, bounded stdout/stderr capture, timeout, and cleanup validator.
A record must keep command outcome and task post-condition outcome separate.
Timeout handling terminates only the exact owned fixture process tree and verifies cleanup.
A monolithic long-lived fixture process is not an acceptance authority.

## Failure taxonomy

- `QUOTING_EXPANSION`
- `CWD_PATH_IDENTITY`
- `SHELL_VERSION_MISMATCH`
- `NATIVE_PROCESS_OUTCOME`
- `TIMEOUT_CANCELLATION`
- `POST_CONDITION_MISMATCH`
- `ENVIRONMENT_STALENESS`
- `DESKTOP_SANDBOX_BOUNDARY`
- `UNKNOWN`

Classification never overwrites the original exit code, stdout/stderr facts, timeout state, or post-condition truth.

## Primary metrics

Per run record when measurable:
- task/case ID and trial ID;
- path A/B;
- Codex Desktop build and selected shell identity;
- completion truth;
- expected and predicted failure class;
- first recommended action and whether it is valid;
- repair-turn count and wrong-repair count;
- post-condition truth and false-completion flag;
- wall time;
- model/tool-call count and intervention count;
- MCP startup/runtime overhead;
- context/token burden when the host exposes it.

Missing measurements remain missing; never coerce them to zero.

## Aggregate metrics

Report separately for eligible failures and known-good controls:
- task completion rate;
- median and distribution of repair turns;
- median time to first correct diagnosis/action;
- failure-class confusion matrix and `UNKNOWN` rate;
- wrong-repair rate;
- false-completion rate;
- post-condition accuracy;
- false-intervention rate;
- MCP process startup/memory/idle overhead;
- wall-time and tool-call deltas.

## Admission / kill gate

Do not promise an improvement percentage before repeated real Desktop A/B trials exist.
The project advances only if B shows a repeated, practically meaningful gain on at least one primary outcome — higher completion, fewer repair turns/wrong repairs, faster correct diagnosis, or fewer false completions — without a compensating regression in the others.

Hard guardrails:
- known-good first attempts with passing post-conditions: reliability intervention rate must be 0 in deterministic controls;
- no automatic sandbox/ACL weakening or global profile/environment mutation;
- no increase in false-completion rate;
- no persistent MCP process accumulation or unacceptable session idle resource cost;
- any claimed gain must reproduce across repeated trials, not one anecdotal case.

If end-to-end trials show no material gain, keep the work as a diagnostic research harness or stop the product rather than adding more abstractions.

## Expected effect size is a hypothesis, not a claim

For eligible failures, a useful system should often replace several exploratory repair attempts with one evidence-backed diagnosis. A reduction such as multiple repair turns to one or two is plausible, but it is not accepted as fact until measured. The benchmark must report the observed delta rather than backfilling a target percentage.

## Privacy

May record bounded shell/version/cwd identity, explicitly requested executable resolutions, allowlisted environment deltas, and sanitized task outcomes.
Must not persist full PATH, full environment, user prompts, credentials, tokens, cookies, browser storage, auth databases, or unrelated software inventory.

## Evidence ladder

1. Synthetic fixtures: prove runner/scorer correctness and reproducibility.
2. Local sanitized incidents: prove the failure classes occur in real work.
3. Public upstream/user reports: prioritize candidate classes; never substitute for local reproduction.
4. Repeated representative Codex Desktop A/B trials: determine real utility.
5. Only level 4 can admit a default companion Skill policy or plugin packaging recommendation.
