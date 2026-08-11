# Benchmark Run Record v1

Use newline-delimited JSON (JSONL), one record per Codex Desktop trial. Raw prompts, full logs, credentials, full PATH/environment, and unrelated machine state stay outside the record.

## Required fields

- `case_id`: stable sanitized case identifier string.
- `trial_id`: stable trial identifier string.
- `path`: `A` for autonomous Codex Desktop or `B` for the same Desktop workflow with failure-only Reliability assistance.
- `eligible_failure`: boolean. `false` identifies a known-good control where Reliability should not intervene.

## Optional measured fields

Leave a field absent when it was not measured. Never substitute zero for missing data.

- `completion`: boolean task completion truth.
- `expected_class`: expected failure taxonomy class.
- `predicted_class`: observed diagnosis class.
- `first_action_correct`: boolean.
- `repair_turns`: non-negative number.
- `wrong_repairs`: non-negative number.
- `post_condition_correct`: boolean.
- `false_completion`: boolean.
- `wall_ms`: non-negative number.
- `tool_calls`: non-negative number.
- `intervention_count`: non-negative number.
- `mcp_startup_ms`: non-negative number when exposed.
- `mcp_idle_mb`: non-negative number when measured.
