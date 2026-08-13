# AUTO_ON_FAILURE Candidate Trigger Contract

This is a benchmark policy, not yet a production admission.

## First attempt

The first attempt uses the same plain shell/native path as baseline A. No reliability wrapper is inserted merely because the task runs on Windows.

## Candidate triggers

Reliability analysis may activate after one of these observable boundaries:
- non-zero shell/native exit;
- shell parser / parameter-binding / command-resolution failure;
- bounded timeout or cancellation ambiguity;
- task-supplied post-condition is false, including exit code 0;
- a declared critical executable resolves differently after a workspace/environment/install boundary;
- a task declares a shell capability requirement that the selected shell/version cannot satisfy.

## Non-triggers

Do not activate solely because:
- stderr is non-empty while exit/post-condition are successful;
- Codex reports PowerShell shell-snapshot unsupported;
- a Gateway/RDC/MCP transport/backend is unavailable;
- an unrelated analyzer/tool fails;
- the command is complex but has not failed;
- the machine has both Windows PowerShell and pwsh installed.

Component-routing failures must be classified at their actual boundary before PowerShell reliability is considered.

## Routing after activation

- A pure command/post-condition disagreement goes directly to `diagnose_failure`; environment inspection is not a default intermediate step.
- `inspect_environment` is used only when shell, cwd, PATH resolution, or task-declared executable identity can causally matter to the observed failure.
- A high-confidence diagnosis does not justify unrelated exploratory probes.
- `UNKNOWN` permits collection of only the explicitly missing bounded fact before at most one re-diagnosis.

## Success-path invariant

If the first attempt returns its expected command outcome and the required observable post-condition passes, `AUTO_ON_FAILURE` records zero intervention. Any measurable overhead on such controls counts against the candidate.

## Repair boundary

Reliability may guide at most one evidence-backed repair from facts tied to the failed boundary. Freeze deterministic task criteria before repair and perform exactly one final `verify_result` after repair. Never weaken criteria or derive expected values from repaired candidate output. Reliability must not silently rewrite arbitrary user commands, alter global profiles/configuration, install dependencies, or broaden permissions.
