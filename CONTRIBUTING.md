# Contributing

PowerShell Agent Reliability targets Windows Codex Desktop. Normal repository contributions require only the public prerequisites below; they do not depend on maintainer-local orchestration tools or private evidence directories.

Read [`AGENTS.md`](AGENTS.md) for repository-local engineering and safety rules, and [`docs/README.md`](docs/README.md) for the documentation map.

## Development prerequisites

For the current repository verification path, use:

- Git;
- Rust `1.88+`;
- Python `3.14` for the benchmark/evaluation harness;
- PowerShell 7 (`pwsh.exe`).

Windows Codex Desktop is required only when a change needs real target-runtime acceptance. Standalone Codex CLI results can support compatibility work, but they do not replace Desktop acceptance.

## Change discipline

Keep each change one-purpose and reviewable. For behavior changes:

- reproduce the problem with a bounded test or fixture;
- check whether existing repository/platform behavior already solves it;
- use TDD where practical: failing regression first, then the smallest implementation;
- keep command outcome separate from the requested task post-condition;
- avoid adding a generic shell/process runner or weakening sandbox, ACL, approval, or profile behavior.

Documentation changes should preserve the experimental/pre-release boundary and distinguish current contracts/runbooks from dated development plans. Do not turn historical plans into current requirements.

## Before requesting review

Run the smallest focused checks for the files you changed, then run the repository verifier and Git whitespace check from the repository root:

```powershell
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
git diff --check
```

If a change affects Windows Codex Desktop integration, also follow the relevant current runbook under [`docs/runbooks/`](docs/runbooks/). Report failures as failures rather than changing security settings or acceptance criteria to make a check pass.

## Public-repository hygiene

Do not commit:

- credentials, tokens, cookies, or browser/session secrets;
- raw Codex Desktop sessions or host-local evidence;
- full PATH/environment dumps or unrelated machine inventory;
- maintainer-specific absolute paths or private task/orchestration state.

Sanitized reproducible fixtures, stable product contracts, tests, and implementation-facing documentation belong in the repository when they are part of the change.
