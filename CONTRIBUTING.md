# Contributing

This project targets Windows Codex Desktop. Read `AGENTS.md` before making repository changes.

Keep changes one-purpose and reviewable. Use TDD for behavior changes, preserve command outcome separately from task post-condition, and do not add a generic shell/process runner or weaken sandbox/ACL/security behavior.

Before requesting review, run the smallest focused tests, then:

```powershell
pwsh.exe -NoProfile -File ./scripts/verify-local.ps1 -SkipBaseline
git diff --check
```

Do not commit credentials, raw Codex Desktop sessions, full PATH/environment dumps, unrelated machine inventory, or host-local evidence.
