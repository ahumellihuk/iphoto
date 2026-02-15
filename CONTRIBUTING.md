# Contributing

Thanks for contributing to `iphoto`.

## Prerequisites

- macOS 14+
- Python 3.12+
- `uv`

## Setup

```bash
git clone https://github.com/camoiloc/iphoto.git
cd iphoto
uv sync
uv run iphoto version
```

## Before Opening a PR

```bash
uv run ruff check src/
uv run ruff format --check src/
uv run mypy src/iphoto/models.py
uv run pytest tests/ -v
```

## Scope and Style

- Keep PRs small and focused.
- Maintain safety-first behavior for export, checksum verification, and delete flows.
- Add tests when behavior changes.
- Update `README.md` when CLI behavior changes.

## Pull Requests

- Use clear commit messages (`feat:`, `fix:`, `docs:`, etc.).
- Fill out the PR template completely.
- Include user-visible impact and test evidence.

## AI-assisted Contributions

AI assistance is allowed, but submitters are fully responsible for correctness, licensing, and safety of all contributions.
