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

Or install as a tool:

```bash
uv tool install .
iphoto version
```

## Quick Usage

```bash
# Inspect library
iphoto scan

# Start interactive archival
iphoto archive

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

## Development

```bash
uv sync
uv run ruff check src/
uv run ruff format --check src/
uv run mypy src/iphoto/models.py
uv run pytest tests/ -v
```

## License

GPL-3.0-or-later. See `LICENSE`.
