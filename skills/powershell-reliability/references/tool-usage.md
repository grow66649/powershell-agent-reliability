# Tool usage reference

## `inspect_environment`

Use only after a relevant failure. Inputs are optional `shell_executable`, optional `cwd`, up to 16 `critical_executables`, and up to 32 task-supplied `task_env_delta` entries. The output exposes hashes/identity rather than raw cwd/PATH values.

## `diagnose_failure`

Supply observed facts such as `exit_code`, `timed_out`, `post_condition`, `native_process`, bounded stdout/stderr excerpts, explicit nested-command/literal-dollar facts, cwd hashes, shell requirement/observation, resolution-before/after hashes, or an explicit Desktop sandbox signal. Do not infer a hash change unless it was actually observed.

For a command/post-condition disagreement, keep the call minimal:

```json
{"exit_code": 0, "timed_out": false, "post_condition": false}
```

When shell evidence is actually relevant, `required_shell` and `observed_shell` are objects, never strings:

```json
{"required_shell": {"family": "PowerShell", "minimum_major": 7, "minimum_minor": 6}, "observed_shell": {"family": "PowerShell", "major": 7, "minor": 6}}
```

Omit shell fields when the failure does not depend on shell identity or version. The output contains `failure_class`, `confidence`, bounded evidence codes, and one `next_action`. `UNKNOWN` is a valid result.

## `verify_result`
Supply optional `command_exit_code`, optional `cwd`, `mode` (`all` or `any`), and one or more explicit checks. Every check uses `kind` as its discriminator.

Exact check shapes:

```json
{"kind": "file_exists", "path": "output.txt"}
{"kind": "file_absent", "path": "artifact.tmp"}
{"kind": "directory_exists", "path": "build"}
{"kind": "file_sha256", "path": "output.txt", "expected_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}
{"kind": "file_size", "path": "output.txt", "min_bytes": 5, "max_bytes": 5}
```

For `file_size`, use `min_bytes` and/or `max_bytes`; there is no `size` field. For `file_sha256`, use `expected_sha256`; there is no `sha256` field. Use `kind`, not `type`.

A typical deterministic verification request is:

```json
{"command_exit_code": 0, "cwd": "D:/work/task", "mode": "all", "checks": [{"kind": "file_sha256", "path": "output.txt", "expected_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"}]}
```

A non-zero command can still have `task_succeeded=true`, and exit code zero can still have `task_succeeded=false`. Preserve both values.
