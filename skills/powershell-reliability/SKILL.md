---
name: powershell-reliability
description: Use this skill after a Windows Codex Desktop PowerShell or native-command failure: non-zero exit, timeout/cancellation ambiguity, parser/binding/command-resolution failure, declared shell/cwd/executable identity mismatch, or an explicit task post-condition that is false even when exit code is 0. Do not use before the first attempt, for known-good successful work, for ordinary PowerShell explanation/code-writing, for unrelated MCP/connector/backend failures, for stderr-only warnings when the required task outcome passed, or merely because multiple PowerShell versions are installed.
---

# PowerShell Reliability

Keep Codex Desktop/app-server as the command and process owner. Use Reliability only after an eligible failed execution boundary; the MCP supplies bounded observation, diagnosis, and deterministic verification, not a second shell or repair engine.

## Common path

1. Before the first execution attempt, make no Reliability intervention.
2. If the command outcome and required post-condition both pass, stop with zero MCP calls.
3. Freeze the deterministic task criteria before diagnosis or repair. Expected hashes, sizes, names, and other target values must come from the user/task or declared target, never from repaired candidate output.
4. Pure command/post-condition disagreement: call `diagnose_failure` directly; do not call `inspect_environment`.
5. Call `inspect_environment` only when shell, cwd, PATH resolution, or executable identity can causally matter to the observed failure.
6. Keep probe/helper failures separate from the original task failure unless the probe is itself the failed task boundary.
7. Call `diagnose_failure` once per failure boundary with bounded structured facts. After a high-confidence diagnosis, do not add unrelated probes.
8. If diagnosis is `UNKNOWN`, collect only one missing fact tied to the failed boundary, then make at most one re-diagnosis.
9. Perform at most one evidence-backed repair through Codex Desktop's normal tools. If the frozen criteria still fail, stop and report failure; do not perform a second repair in the same Reliability intervention.
10. After repair, perform exactly one `verify_result` against the frozen criteria before claiming completion.
11. Never weaken criteria after a failed verification. Never derive expected values from repaired candidate output. Keep command success and task success separate.

## Safety and scope

Treat MCP `next_action` as evidence-backed guidance, not permission to bypass security or task constraints. Never weaken Codex sandboxing, Windows ACLs, approval policy, PowerShell profiles, or global environment settings automatically.
Never send or persist full PATH, complete environment variables, credentials, tokens, cookies, browser state, command history, unrelated software inventory, or broad machine logs. Exact local paths may be supplied to a tool only when required for the current task; tool outputs should remain hashed or otherwise bounded.

If the Reliability MCP is unavailable, continue with ordinary Codex reasoning and tools. Do not modify global configuration merely to make Reliability available during an unrelated task.
