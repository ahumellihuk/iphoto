# iPhoto Video Archiver

[![CI](https://github.com/camoiloc/iphoto/actions/workflows/ci.yml/badge.svg)](https://github.com/camoiloc/iphoto/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)

Intelligently archive large and old videos from Apple Photos to external storage, freeing up local disk space while maintaining searchability.

## Quick Start

```bash
# Install with uv
uv sync

# Scan your library
uv run iphoto scan

# Archive videos (interactive)
uv run iphoto archive

# Check status
uv run iphoto status
```

Or install globally:

```bash
uv tool install .
iphoto scan
```

## The Problem

- **iCloud Photos** keeps your entire library in the cloud
- **Mac storage** is limited and expensive
- **Large videos** (4K, long recordings) consume most space
- **Photos.app** doesn't let you selectively archive to external storage
- **Deleting** videos means losing them completely

## The Solution

This tool helps you:
1. **Identify** videos worth archiving (large, old, duplicates)
2. **Export** original files from Photos
3. **Archive** to external storage with organization
4. **Verify** with checksums
5. **Delete** from Photos library (after confirmation)
6. **Manifest** maintains searchable record of archived content

## Features

### Smart Selection
- **Moment-based grouping**: Archive by trip, event, or date
- **Size thresholds**: Auto-suggest optimal cutoffs per moment
- **Preview before archiving**: See exactly what will be deleted
- **Safety checks**: Verify external drive space and checksums

### Robust Processing
- **Batch processing**: Handle thousands of videos
- **Sequential export**: Reliable AppleScript-based exports
- **Resume capability**: Pick up where you left off
- **Error handling**: Retry failed exports/deletions

### Organization
- **Moment folders**: Videos grouped by Photos moments
- **Original filenames**: Preserved for easy identification
- **JSONL manifest**: Search archived content
- **Checksum verification**: Ensure integrity

## Usage

### Basic Workflow

```bash
# 1. Scan your library
iphoto scan

# 2. Start archival (interactive)
iphoto archive

# 3. Follow prompts to:
#    - Select moments to archive
#    - Set size thresholds
#    - Review selection
#    - Confirm export/archive/delete

# 4. Check status anytime
iphoto status
```

### Advanced Options

```bash
# Dry run (preview without changes)
iphoto archive --dry-run

# Filter by age/size
iphoto archive --min-age 365 --min-size 500

# Custom locations
iphoto archive -s ~/staging -e /Volumes/MyDrive/archive

# Skip deletion (archive only)
iphoto archive --no-delete

# Resume interrupted session
iphoto resume
```

### Verification

```bash
# Verify archived files against manifest
iphoto verify /Volumes/MyDrive/archive

# Retry failed operations
iphoto retry-failed
```

## Requirements

- macOS 14+
- Python 3.12+
- Photos.app
- External storage drive

## Development

### Setup

```bash
# Clone and install
git clone https://github.com/camoiloc/iphoto.git
cd iphoto
uv sync

# Run linter
uv run ruff check src/
uv run ruff format --check src/

# Run tests
uv run pytest tests/ -v

# Type checking
uv run mypy src/iphoto/models.py

# Install pre-commit hooks
uv run pre-commit install
```

### Project Structure

```
iphoto/
├── src/iphoto/
│   ├── cli.py                 # CLI entry point
│   ├── scanner.py             # Photos library scanning
│   ├── selector.py            # Interactive selection UI
│   ├── exporter.py            # Export orchestration
│   ├── applescript_exporter.py # AppleScript export implementation
│   ├── mover.py               # Archive to external storage
│   ├── deleter.py             # Delete from Photos
│   ├── manifest.py            # Manifest management
│   └── models.py              # Data models
├── tests/
│   └── test_models.py         # Unit tests for pure-logic functions
├── .github/workflows/ci.yml   # GitHub Actions CI
├── CLAUDE.md                  # Full project context
└── README.md                  # This file
```

### Contributing

1. Read [CLAUDE.md](CLAUDE.md) for full technical context
2. Write tests for new features
3. Ensure `uv run ruff check src/` and `uv run pytest` pass
4. Type hints on all functions
5. Use Rich console for user output

## Current Status

**Active Development** - iCloud export feature under investigation

**What Works:**
- Scanning and video identification
- Moment-based selection UI
- Local video export and archival
- Manifest generation
- Resume capability

**Known Issues:**
- iCloud video export unreliable - Photos.app doesn't consistently download from iCloud during export

## License

[GPL-3.0-or-later](LICENSE)

## Acknowledgments

- [osxphotos](https://github.com/RhetTbull/osxphotos) by Rhet Turnbull - Excellent Photos library interface
- [Rich](https://github.com/Textualize/rich) - Beautiful terminal UI
- [Typer](https://github.com/tiangolo/typer) - CLI framework
