---
name: powershell-reliability
description: Failure-only reliability workflow for Windows Codex Desktop using the local PowerShell Reliability MCP. Use after a PowerShell/native command fails, times out, has a parser/binding/resolution error, violates a declared shell/cwd/executable identity expectation, or when an explicit task post-condition disagrees with the command exit status. Also use to verify a repaired Windows task before claiming completion. Do not invoke on a known-good first attempt whose required post-condition already passes.
---

# PowerShell Reliability

Keep Codex Desktop/app-server as the command and process owner. Use the MCP only for bounded environment identity, diagnosis, and post-condition verification.

## Failure-only workflow

1. Leave the first execution attempt unchanged. If the command outcome and required post-condition both pass, do not call this MCP.
2. After an eligible failure, preserve the original exit code, timeout state, stdout/stderr facts, and post-condition truth separately. Freeze the task post-condition before diagnosis or repair. Expected hashes, sizes, or other target values must come from the user/task or be derived from the declared target before observing repaired candidate output.
3. Keep probe/helper failures separate: probe/helper errors are not evidence about the original task failure unless that probe is itself the task boundary. Call `inspect_environment` only when shell identity, cwd, PATH resolution, or a task-declared critical executable may matter.
4. Call diagnose_failure once per failure boundary with bounded structured facts. Call it again only after `UNKNOWN` with newly collected missing facts, or after a genuinely new failure boundary.
5. Treat the returned class as evidence, not permission to bypass safety. Do not add unrelated probes after a high-confidence diagnosis.
6. Perform at most one evidence-backed repair step through Codex Desktop's normal tools. If that repair fails the frozen post-condition, stop and report failure; do not perform a second repair in the same Reliability intervention.
7. Call `verify_result` once after repair against the frozen deterministic post-condition before declaring completion. Never weaken checks after a failed verification. Never use observed candidate output as the expected verification value. Report command success and task success independently when they differ.

## Repair rules

- `QUOTING_EXPANSION`: prefer structured executable + argv for native tools or an explicit PowerShell script/file boundary. Never invent a universal escaping function.
- `CWD_PATH_IDENTITY`: bind the intended cwd explicitly before searching, moving, or retrying relative paths.
- `SHELL_VERSION_MISMATCH`: select a compatible shell or compatible syntax; do not retry unchanged across shell families.
- `NATIVE_PROCESS_OUTCOME`: preserve exit code, stdout, stderr, and post-condition separately before interpreting the native program's failure.
- `TIMEOUT_CANCELLATION`: identify the timeout owner and verify the owned process state before retrying.
- `POST_CONDITION_MISMATCH`: trust the explicit post-condition as a separate fact; exit code alone never proves task completion.
- `ENVIRONMENT_STALENESS`: refresh the bounded environment digest after install/workspace/environment boundaries.
- `DESKTOP_SANDBOX_BOUNDARY`: keep attribution at the Desktop/security boundary until proven otherwise. Never weaken the sandbox, ACLs, approvals, profiles, or global environment automatically.
- `UNKNOWN`: reduce uncertainty with the smallest relevant observation; do not fabricate a root cause.

## Privacy and scope

Never send or persist full PATH, complete environment variables, credentials, tokens, cookies, browser state, command history, unrelated software inventory, or broad machine logs. Exact local paths may be supplied to a tool only when required for the current task; tool outputs should remain hashed/bounded.

If the MCP is unavailable, continue with ordinary Codex reasoning and tools. Do not modify global configuration merely to make the reliability layer available during an unrelated task.

Read `references/tool-usage.md` only when constructing tool arguments or interpreting structured results.
