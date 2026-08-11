# Minimal Environment Digest Contract

Purpose: detect execution-context drift without sending the full machine environment to an agent.

## Local-only state

The reliability layer may inspect locally, only when needed:
- exact shell executable path and file identity;
- exact cwd;
- PATH and selected environment variables required to resolve explicitly named executables;
- file metadata/version for those explicitly named executables.

These raw values are not the default exported digest.

## Exported digest

A default digest should contain only:
- shell family (`WindowsPowerShell` / `PowerShell`), semantic version and process architecture;
- OS family/build identifier needed to explain shell behavior;
- cwd existence plus a stable hash of the normalized absolute cwd, not the raw path;
- PATH fingerprint hash, not PATH contents;
- for each task-declared critical executable: name, resolution status, source class, resolved-path hash and version/hash when cheap and relevant;
- explicit task env-delta key names with value hashes only when the task itself supplied those values;
- digest timestamp and schema version.

Do not include complete environment variables, usernames from paths, tokens, credentials, browser state, unrelated software inventory, or command history.

## Invalidation

Recompute when any observable execution boundary changes: shell executable/version, cwd, PATH fingerprint, declared env delta, critical executable resolution, worktree/workspace switch, or a dependency/install operation that can change resolution.

Do not rely on a long fixed TTL as the primary correctness mechanism. Event/boundary invalidation is authoritative; time-based refresh is only a fallback if later evidence proves it useful.
