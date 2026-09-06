# AGENTS

Shared contributor and agent instructions for this repository.

## Scope

This repository holds two things:

- `src/iphoto`: a macOS-only Python CLI that archives selected Apple Photos videos to external storage. It is the frozen reference implementation: bug fixes only, no new features.
- `docs/` and `spike/`: the north star, live state, research, specs, and the PhotoKit spike for the native macOS product that succeeds the CLI. Read `docs/NORTH-STAR.md` first, then `docs/STATE.md`.

## Repo Goals

- Keep workflows reliable and safe over clever.
- Preserve user trust: no silent destructive behavior.
- Keep docs and UX concise for a modern CLI.

## Local Setup

```bash
uv sync
uv run iphoto version
```

## Quality Gates

Run before opening a PR:

```bash
uv run ruff check src/
uv run ruff format --check src/
uv run mypy src/iphoto/models.py
uv run pytest tests/ -v
```

## Docs Discipline

The documentation is a system with one home per fact. These rules bind every session, human or agent.

1. **One home per fact.** If a fact appears twice, one is a pointer. Duplication is the top cause of drift.
2. **Status lives only in `docs/STATE.md` and `docs/COVERAGE.md`.** Never write "current status", "done", or percentages into a spec, README, or research doc.
3. **Specs are immutable dated records** in `docs/specs/`. Correct one only with a dated `UPDATE:` line at the top. A new decision is a new dated spec. Shipped specs move to `docs/archive/specs/`.
4. **Update in the same commit.** A slice is not done until its STATE `Now` line moves to `CHANGELOG.md`, its COVERAGE row flips, and STATE `Now` and `Next` are rewritten, all in the commit that ships the code.
5. **Point, never re-copy.** Detail lives in specs and research; STATE and COVERAGE point at it.
6. **The live ledger has one writer.** STATE, COVERAGE, and CHANGELOG are written by the execution channel alone. A parallel session or design channel writes only under `docs/specs/` or `docs/research/`; its outcomes enter the ledger through the next execution update.
7. **Every change is checked against the invariants** in `docs/NORTH-STAR.md`. A change that would break one is out, or must show an explicit reviewed fence.

Tier map: `docs/NORTH-STAR.md` (binding intent, invariants, phases) · `docs/STATE.md` (Now, Next, Gate, Decisions pending) · `docs/COVERAGE.md` (system × status × owner × invariant) · `CHANGELOG.md` (one line per shipped change) · `docs/specs/` and `docs/archive/specs/` (immutable design records) · `docs/plans/` (per-slice plans) · `docs/journal/` (per-session records) · `docs/research/` (dated evidence).

## Code Map

- `src/iphoto/cli.py`: Typer entrypoints and session orchestration.
- `src/iphoto/scanner.py`: Photos metadata scan.
- `src/iphoto/selector.py`: interactive moment/threshold selection.
- `src/iphoto/applescript_exporter.py`: Photos.app export automation.
- `src/iphoto/exporter.py`: export pipeline and checksum handling.
- `src/iphoto/mover.py`: transfer to archive destination.
- `src/iphoto/deleter.py`: optional deletion from Photos.
- `src/iphoto/manifest.py`: JSONL manifest I/O.
- `src/iphoto/models.py`: core dataclasses and pure helpers.
- `spike/`: sandboxed PhotoKit spike harness (Swift app bundle built by Makefile) plus Python sample and scoring scripts. Not product code; kept for re-measurement.

## Contribution Expectations

- Keep changes focused and small.
- Prefer readable, explicit code over abstraction layers.
- Preserve backwards-compatible CLI behavior unless intentionally changed.
- Add or update tests when behavior changes.
- Update `README.md` when user-visible commands or behavior change.

## Safety Requirements

- Deletion must remain explicit and user-confirmed.
- Do not remove checksum verification for archived files.
- Do not weaken resume/retry behavior without replacement.
- Never add destructive git/file commands to docs or scripts.

## AI Usage

- AI tooling (Claude/Codex) may be used to draft code or docs.
- Human maintainer review is required before merge or release.
- Agent-generated changes must pass the same tests and safety checks.

## Agent Operating Notes

- Make minimal diffs and avoid unrelated refactors.
- Read existing patterns first; match style and imports.
- Use `rg` for search and prefer direct file edits.
- If blocked by environment/tooling limits, state exactly what could not be verified.

## Commit and PR Style

- Use conventional-style commit prefixes when possible (`feat:`, `fix:`, `refactor:`, `docs:`, `chore:`).
- PR descriptions should include:
  - user-visible impact
  - safety implications (export/delete/verification)
  - test evidence
