# Tool usage reference

## `inspect_environment`

Use only after a relevant failure. Inputs are optional `shell_executable`, optional `cwd`, up to 16 `critical_executables`, and up to 32 task-supplied `task_env_delta` entries. The output exposes hashes/identity rather than raw cwd/PATH values.

## `diagnose_failure`

Supply observed facts such as `exit_code`, `timed_out`, `post_condition`, `native_process`, bounded stdout/stderr excerpts, explicit nested-command/literal-dollar facts, cwd hashes, shell requirement/observation, resolution-before/after hashes, or an explicit Desktop sandbox signal. Do not infer a hash change unless it was actually observed.

The output contains `failure_class`, `confidence`, bounded evidence codes, and one `next_action`. `UNKNOWN` is a valid result.

## `verify_result`

Supply optional `command_exit_code`, optional `cwd`, `mode` (`all` or `any`), and one or more explicit checks. Supported checks are `file_exists`, `file_absent`, `directory_exists`, `file_sha256`, and `file_size`. Paths are local inputs; outputs identify them only by hash.

A non-zero command can still have `task_succeeded=true`, and exit code zero can still have `task_succeeded=false`. Preserve both values.
