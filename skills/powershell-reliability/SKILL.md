---
name: powershell-reliability
description: Failure-only reliability workflow for Windows Codex Desktop using the local PowerShell Reliability MCP. Use after a PowerShell/native command fails, times out, has a parser/binding/resolution error, violates a declared shell/cwd/executable identity expectation, or when an explicit task post-condition disagrees with the command exit status. Also use to verify a repaired Windows task before claiming completion. Do not invoke on a known-good first attempt whose required post-condition already passes.
---

# PowerShell Reliability

Keep Codex Desktop/app-server as the command and process owner. Use the MCP only for bounded environment identity, diagnosis, and post-condition verification.

## Failure-only workflow

1. Leave the first execution attempt unchanged. If the command outcome and required post-condition both pass, do not call this MCP.
2. After an eligible failure, preserve the original exit code, timeout state, stdout/stderr facts, and post-condition truth separately.
3. Call `inspect_environment` only when shell identity, cwd, PATH resolution, or a task-declared critical executable may matter. Supply only the shell/cwd/executable names tied to the failure. Never request or reconstruct a full environment dump.
4. Call `diagnose_failure` with bounded structured facts. Keep stdout/stderr excerpts minimal; prefer explicit boolean/hash facts over large logs.
5. Treat the returned class as evidence, not permission to bypass safety. If it returns `UNKNOWN`, collect only the missing facts tied to the failed boundary and diagnose again rather than guessing.
6. Perform at most one evidence-backed repair step through Codex Desktop's normal tools. Do not turn the MCP into a command runner.
7. Call `verify_result` with explicit deterministic post-conditions before declaring completion. Report command success and task success independently when they differ.

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
