# iphoto

macOS CLI to archive old or large Apple Photos videos to external storage when your Mac cannot hold a full local sync and your iCloud storage is tight.

The workflow is selective and moment-based: identify heavy moments, export originals, verify checksums, write a manifest, then optionally delete from Photos.

## Why This Exists

Apple Photos + iCloud storage management is awkward when:
- You cannot keep the full library locally.
- You cannot afford to keep everything in iCloud.
- Large videos dominate storage usage.

`iphoto` helps you reclaim space without blind bulk deletion.

## Features

- Scan Apple Photos video metadata.
- Group videos by moment and interactively choose what to archive.
- Pick archive destination interactively with live free-space visibility.
- Export originals through Photos.app automation.
- Move exports to external storage with checksum validation.
- Keep a JSONL manifest for search/audit.
- Resume interrupted archive sessions.

## Requirements

- macOS 14+
- Python 3.12+
- Apple Photos library access
- External storage destination

## Install

```bash
uv sync
uv run iphoto version
```

After publishing to PyPI:

```bash
uv tool install iphoto
iphoto version
```

## Quick Usage

```bash
# Inspect library
iphoto scan

# Start interactive archival (includes destination picker with free-space info)
iphoto archive

# Skip destination picker in scripted runs
iphoto archive --no-choose-external

# Resume an interrupted run
iphoto resume

# Validate manifest checksums
iphoto verify /Volumes/Archive/videos

# Retry failures from last session
iphoto retry-failed

# Check session status
iphoto status
```

## Safety Model

- `archive` is interactive and shows what will be processed.
- File integrity is verified with SHA-256 checksums.
- Manifest records what was archived and where.
- Deletion is optional and explicit.

## Publishing

```bash
uv build
uv publish
```

Recommended: configure PyPI Trusted Publisher for this GitHub repository and publish from tagged releases.

## AI Assistance Disclosure

Portions of this codebase were developed with assistance from Claude and Codex. All proposed changes are reviewed and accepted by a human maintainer before release.

## Development

```bash
uv sync
uv run ruff check src/
uv run ruff format --check src/
uv run mypy src/iphoto/models.py
uv run pytest tests/ -v
```

See `AGENTS.md` and `CONTRIBUTING.md` for contribution workflow.

## Security

See `SECURITY.md` for reporting guidance.

## License

GPL-3.0-or-later. See `LICENSE`.
