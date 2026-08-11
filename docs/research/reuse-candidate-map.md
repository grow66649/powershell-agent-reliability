# Reuse Candidate Map

Research snapshot: 2026-08-11. Re-evaluate candidates only when a concrete implementation gap appears; do not add dependencies because they exist.

| Candidate | Decision | Reuse target | Re-evaluate when |
|---|---|---|---|
| OpenAI Codex Desktop/app-server command execution | REUSE BOUNDARY | Keep normal execution/process lifecycle owned by Codex | Only if a required reliability fact is unavailable from the existing path |
| Official MCP SDKs | EVALUATE FIRST | Local STDIO MCP transport/server | Packaging spike before implementation language freeze |
| .NET structured process arguments / `ArgumentList` | REUSE IF C# | Avoid string-concatenated argv | C# packaging spike wins |
| Node standard process APIs | REUSE IF TS | Minimal server/runtime plumbing | TS packaging spike wins |
| CliWrap | CONDITIONAL | Independent structured process fallback | Only if benchmarks prove Codex/app-server cannot provide a required execution behavior |
| PSScriptAnalyzer | OPTIONAL | Static preflight for actual PowerShell script content | Repeated script-level syntax/style failures justify preflight |
| Pester | ADAPT/OPTIONAL | Assertion vocabulary and deterministic post-condition patterns | Validator surface needs richer PowerShell-native assertions |
| PowerShell Crescendo | DESIGN REFERENCE | Native-command wrapping concepts | Never as core dependency without renewed maintenance/admission review |
| Strands Shell | DESIGN REFERENCE | Agent shell mediation, limits, bounded output | Architecture review only |
| Desktop Commander | DEVELOPMENT TOOL | Windows host/file/process/test evidence | Never product runtime dependency |
| GrowUp Gateway | DEVELOPMENT CONTROL PLANE | Canonical task governance, receipts, optional dev routing | Never product runtime dependency |
| CodeGraph / Serena | DEVELOPMENT ADVISORY | Symbols, references, blast radius | Exact current worktree/index only |
| Ponytail | DEVELOPMENT POLICY | Reuse/YAGNI check before nontrivial slices | Optional pull; never acceptance authority |

## Reuse rule

For each implementation slice use this order:
1. remove/narrow the requirement;
2. reuse existing repo code;
3. use platform/standard library capability;
4. use an already-admitted dependency;
5. evaluate mature external software;
6. write the smallest new code that satisfies the benchmarked need.

## Important exclusions

Do not build another generic Windows shell MCP merely because similar projects exist. Do not fork Codex to gain reliability behavior that can remain an external diagnostic/verification companion. Do not copy external project architecture wholesale; borrow only the proven capability that closes a measured gap.

## Windows Codex Desktop issue families to keep in the pain corpus

Current public reports include sandbox spawn/ACL failures, cwd/path binding and WSL path translation failures, native Git credential/network behavior inside the sandbox, MCP process lifecycle accumulation, and destructive-command scope mistakes. These reports are prioritization signals; each product requirement still needs local reproduction or a deterministic contract before implementation.
