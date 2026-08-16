# Documentation map

This directory contains current product contracts and runbooks alongside dated design/research history. Use this page to avoid treating an old implementation plan as a current requirement.

## Start here

1. Read the repository [`README.md`](../README.md) for scope, source build, local setup, verification, and removal.
2. Read [`contracts/mcp-tool-contract-v0.2.md`](contracts/mcp-tool-contract-v0.2.md) for the current agent-facing MCP surface.
3. Read [`runbooks/codex-desktop-acceptance.md`](runbooks/codex-desktop-acceptance.md) before claiming Windows Codex Desktop runtime acceptance.
4. If you are working on routing evaluation, read [`contracts/routing-eval-contract-r4.md`](contracts/routing-eval-contract-r4.md) and [`runbooks/routing-eval-desktop.md`](runbooks/routing-eval-desktop.md) together.

When behavior documentation disagrees, prefer the newest applicable versioned contract plus current source/tests. Dated plans explain how a change was developed; they are not installation instructions or current product guarantees.

## Current contracts

The files under [`contracts/`](contracts/) define bounded product/evaluation behavior. In particular:

- [`mcp-tool-contract-v0.2.md`](contracts/mcp-tool-contract-v0.2.md): current public MCP tool surface and failure-only calling policy.
- [`environment-digest-contract.md`](contracts/environment-digest-contract.md): privacy-bounded environment identity exported by `inspect_environment`.
- [`auto-on-failure-trigger-contract.md`](contracts/auto-on-failure-trigger-contract.md): failure-only trigger boundary.
- [`benchmark-contract.md`](contracts/benchmark-contract.md), [`fixture-contract.md`](contracts/fixture-contract.md), and [`benchmark-run-record-v1.md`](contracts/benchmark-run-record-v1.md): benchmark/evidence structure.
- [`routing-eval-contract-r4.md`](contracts/routing-eval-contract-r4.md): current S-vs-M routing evaluation contract.
- [`skill-trigger-eval-contract-v0.2.md`](contracts/skill-trigger-eval-contract-v0.2.md): current companion-Skill trigger evaluation contract.

[`mcp-tool-contract-v0.1.md`](contracts/mcp-tool-contract-v0.1.md) is retained as a historical contract and is superseded for current agent-facing behavior by v0.2.

## Current runbooks

- [`runbooks/codex-desktop-acceptance.md`](runbooks/codex-desktop-acceptance.md): target-runtime discovery, functional checks, and lifecycle/resource observation.
- [`runbooks/routing-eval-desktop.md`](runbooks/routing-eval-desktop.md): controlled routing evaluation in Windows Codex Desktop.
- [`runbooks/routing-eval-cli-automation.md`](runbooks/routing-eval-cli-automation.md): supporting CLI automation only. It does not make CLI output a substitute for Desktop acceptance, and any campaign using it must satisfy its own CLI/Desktop parity requirements first.

## Historical design and development material

- [`specs/`](specs/) contains dated design/specification snapshots. Use current contracts and source/tests for present behavior.
- [`research/`](research/) contains background research and reuse analysis, not runtime requirements.
- [`superpowers/plans/`](superpowers/plans/) contains dated implementation and review plans. See [`superpowers/plans/README.md`](superpowers/plans/README.md) for the historical-plan boundary.
- [`superpowers/specs/`](superpowers/specs/) contains supporting development specifications; check current contracts/source before treating one as present behavior.

Historical files remain useful for understanding why a design changed. They should not be rewritten or cited as proof that an experimental result, release, or product capability exists today.
