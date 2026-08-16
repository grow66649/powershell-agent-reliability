# Minimal Environment Digest Contract

Purpose: expose only the execution-context identity needed to diagnose bounded drift, without returning the full machine environment.

## Inputs and local-only state

`inspect_environment` may receive only task-relevant values:

- an optional shell executable path or name;
- an optional cwd, otherwise the MCP process cwd;
- up to 16 task-declared critical executables;
- up to 32 task-supplied environment key/value deltas.

The implementation may inspect exact local paths, PATH contents, executable metadata, and supplied env-delta values while producing the digest. Those raw values are not returned in the default output.

## Exported digest

Each call computes a fresh digest containing:

- `schema_version` and observation timestamp;
- optional shell identity when `shell_executable` was supplied;
- OS family/build and process architecture;
- cwd existence plus SHA-256 of the normalized absolute cwd;
- SHA-256 of the current PATH value;
- bounded identity for each requested critical executable;
- each supplied env-delta key with SHA-256 of its value.

Raw cwd, raw PATH, resolved executable paths, and raw env-delta values are not exported.

## Shell identity semantics

The shell object reports:

- `family`, inferred from the requested/resolved executable filename: `powershell.exe` -> `WindowsPowerShell`, `pwsh.exe`/`pwsh` -> `PowerShell`, otherwise `Unknown`;
- `executable_file_version`, when Windows file/PE version metadata is available;
- executable architecture when detectable, otherwise `unknown`;
- resolution status and a SHA-256 identity for the resolved path when resolution succeeds.

`executable_file_version` is **not** the PowerShell engine version. The MCP does not launch PowerShell to query `$PSVersionTable` or infer engine capabilities. PowerShell engine family/version evidence used by diagnosis must come from caller-observed shell facts, as defined by the current MCP tool contract.

## Critical executable semantics

For each task-declared executable, the digest reports its requested display name, resolution status, source class (`explicit_path`, `path`, or `not_found`), resolved-path SHA-256 when found, optional executable file version, optional PE architecture, and an optional file SHA-256 when the resolved file is at most 64 MiB and can be read.

A missing version/hash/architecture remains missing; it must not be promoted to a PowerShell engine version or guessed from the executable name.

## Refresh behavior

The current implementation does not keep a digest cache or TTL. Each `inspect_environment` call recomputes the observable digest from the current process environment and requested inputs.

When a later diagnostic step needs to compare identity after a boundary change (for example cwd/PATH/executable resolution changed), call `inspect_environment` again and compare the bounded identities. Do not add broad environment collection merely to make comparison easier.
