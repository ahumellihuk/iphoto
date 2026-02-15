# AGENTS

Shared contributor and agent instructions for this repository.

## Scope

This project is a macOS-only Python CLI that archives selected Apple Photos videos to external storage when local disk and iCloud storage are both constrained.

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
