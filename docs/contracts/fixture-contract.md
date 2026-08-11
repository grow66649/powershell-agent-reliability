# PowerShell Agent Reliability v0.1 Fixture Contract

Purpose: freeze harmless, repeatable Windows fixtures before any reliability-layer implementation.

## Taxonomy

| ID | Class | Baseline failure | Reliability property |
|---|---|---|---|
| PSR-001 | QUOTING_EXPANSION | Outer PowerShell expands `$` intended for nested shell | Preserve intended argument/script bytes or classify construction failure |
| PSR-002 | CWD_PATH_IDENTITY | Relative path resolves from unexpected cwd | Bind cwd explicitly and report resolved identity |
| PSR-003 | SHELL_VERSION_MISMATCH | A pwsh 7 command surface is assumed under Windows PowerShell 5.1 | Report shell/version capability mismatch before retry loops |
| PSR-004 | NATIVE_PROCESS_OUTCOME | Native process emits stdout+stderr and exits non-zero | Capture exit/stdout/stderr separately and classify outcome |
| PSR-005 | TIMEOUT_CANCELLATION | Child exceeds bounded runtime | Kill only owned process and verify termination |
| PSR-006 | POST_CONDITION_FALSE_POSITIVE | Command exits 0 but required artifact/state is absent | Completion remains false |
| PSR-007 | POST_CONDITION_FALSE_NEGATIVE | Command exits non-zero after producing required artifact/state | Report command failure and post-condition truth separately |
| PSR-008 | ENVIRONMENT_STALENESS | Same executable name resolves to a different path after environment change | Digest invalidates on critical resolution change |

## Safety

- All mutable fixtures use a disposable `%TEMP%` subtree.
- No registry, service, scheduled-task, profile, credential, browser, network, or global environment mutation.
- No user prompts, raw Codex conversations, tokens, cookies, complete PATH, or complete environment are recorded.
- A fixture is accepted only if it reproduces consistently under at least one installed PowerShell and its cleanup post-condition passes.

## Benchmark comparison

A = plain shell/native invocation.
B = future reliability-assisted path.

Measure per fixture: completion truth, repair attempts, failure-class correctness, post-condition correctness, wall time, intervention count, and false intervention on known-good controls.

Do not admit B because it catches synthetic fixtures alone. Admission requires representative real-task replays and repeated net benefit.
