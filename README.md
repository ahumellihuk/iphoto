# iPhoto Video Archiver

Intelligently archive large and old videos from Apple Photos to external storage, freeing up local disk space while maintaining searchability.

## Quick Start

```bash
# Setup
python -m venv .venv
source .venv/bin/activate
pip install -e .

# Scan your library
iphoto scan

# Archive videos (interactive)
iphoto archive

# Check status
iphoto status
```

## The Problem

- **iCloud Photos** keeps your entire library in the cloud
- **Mac storage** is limited and expensive
- **Large videos** (4K, long recordings) consume most space
- **Photos.app** doesn't let you selectively archive to external storage
- **Deleting** videos means losing them completely

## The Solution

This tool helps you:
1. 📊 **Identify** videos worth archiving (large, old, duplicates)
2. 📤 **Export** original files from Photos
3. 💾 **Archive** to external storage with organization
4. ✅ **Verify** with checksums
5. 🗑️ **Delete** from Photos library (after confirmation)
6. 📝 **Manifest** maintains searchable record of archived content

## Features

### Smart Selection
- **Moment-based grouping**: Archive by trip, event, or date
- **Size thresholds**: Auto-suggest optimal cutoffs per moment
- **Preview before archiving**: See exactly what will be deleted
- **Safety checks**: Verify external drive space and checksums

### Robust Processing
- **Batch processing**: Handle thousands of videos
- **Parallel export**: Fast multi-threaded exports
- **Resume capability**: Pick up where you left off
- **Error handling**: Retry failed exports/deletions

### Organization
- **Moment folders**: Videos grouped by Photos moments
- **Original filenames**: Preserved for easy identification
- **JSONL manifest**: Search archived content
- **Checksum verification**: Ensure integrity

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Photos Library                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                 │
│  │ Video 1  │  │ Video 2  │  │ Video 3  │  ...            │
│  │ (iCloud) │  │ (Local)  │  │ (iCloud) │                 │
│  └──────────┘  └──────────┘  └──────────┘                 │
└────────┬────────────────────────────────────────────────────┘
         │
         │ ① Scanner (osxphotos)
         │    - Reads Photos DB
         │    - Extracts metadata
         ↓
    ┌────────────────────────┐
    │ Video Inventory        │
    │ - 5408 videos          │
    │ - 1534 GB total        │
    │ - Moments grouped      │
    └──────┬─────────────────┘
           │
           │ ② Selector (Interactive TUI)
           │    - User chooses moments
           │    - Sets size thresholds
           ↓
      ┌─────────────────┐
      │ Selected Videos │
      │ - 150 videos    │
      │ - 250 GB        │
      └────┬────────────┘
           │
           │ ③ Exporter (AppleScript/osxphotos)
           │    - Exports from Photos.app
           │    - Parallel processing
           ↓
    ┌──────────────────────┐
    │ Staging Directory    │
    │ ~/PhotosStaging/     │
    │ ├─ London 2024/      │
    │ ├─ Japan Trip/       │
    │ └─ ...               │
    └────┬─────────────────┘
         │
         │ ④ Mover
         │    - Checksums
         │    - Copy to external
         ↓
    ┌──────────────────────┐
    │ External Archive     │
    │ /Volumes/Photos/     │
    │ ├─ London 2024/      │
    │ ├─ Japan Trip/       │
    │ └─ manifest.jsonl    │
    └────┬─────────────────┘
         │
         │ ⑤ Deleter
         │    - Remove from Photos
         ↓
    ┌──────────────────────┐
    │ Photos Library       │
    │ (250 GB freed)       │
    └──────────────────────┘
```

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

# Parallel workers
iphoto archive --workers 4

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

## Configuration

### Recommended Setup

1. **External Drive**: USB 3.0+ or Thunderbolt, formatted APFS/HFS+
2. **Staging Space**: ~50GB free on Mac for temporary exports
3. **Photos Library**: Ensure Photos.app can access it
4. **Automation**: Grant Terminal/iTerm access to Photos in System Preferences

### Defaults

```python
DEFAULT_STAGING = ~/PhotosStaging
DEFAULT_EXTERNAL = /Volumes/AcerFA200/Photos-Archive
DEFAULT_THRESHOLD = 100 MB
DEFAULT_WORKERS = 4
DEFAULT_TIMEOUT = 1800s (30min for iCloud downloads)
```

## Current Status

⚠️ **Active Development** - iCloud export feature under investigation

**What Works:**
- ✅ Scanning and video identification
- ✅ Moment-based selection UI
- ✅ Local video export and archival
- ✅ Manifest generation
- ✅ Resume capability

**Known Issues:**
- ⚠️ **iCloud video export unreliable** - Photos.app doesn't consistently download from iCloud during export
- See [INVESTIGATION.md](INVESTIGATION.md) for details

**For Developers:**
- See [CLAUDE.md](CLAUDE.md) for complete project context
- See [INVESTIGATION.md](INVESTIGATION.md) for current issue investigation

## Safety Features

### Pre-Flight Checks
- ✅ Verify external drive has space
- ✅ Check staging directory writeable
- ✅ Validate Photos library accessible
- ✅ Confirm selections before deletion

### During Processing
- ✅ SHA256 checksums for every file
- ✅ Verify file exists before deletion
- ✅ State saved after each phase
- ✅ Can resume from interruption

### Post-Archive
- ✅ Manifest of all archived videos
- ✅ Verification command to check integrity
- ✅ Original files on external drive

## Manifest Format

Archived videos are tracked in `manifest.jsonl`:

```json
{"uuid": "ABC-123", "filename": "IMG_1234.MOV", "moment": "London 2024",
 "size_bytes": 2147483648, "date_created": "2024-06-15T14:30:00",
 "archived_path": "/Volumes/Photos/London 2024/IMG_1234.MOV",
 "checksum": "sha256:abc123...", "archived_at": "2026-01-30T10:00:00"}
```

Search your archive:
```bash
# Find videos from a location
grep "London" manifest.jsonl

# Find large videos
jq 'select(.size_bytes > 1000000000)' manifest.jsonl

# Find videos from date range
jq 'select(.date_created > "2024-01-01")' manifest.jsonl
```

## Recovery

### Restore Videos

1. Locate video in manifest
2. Copy from external archive back to Mac
3. Import into Photos.app via drag-and-drop
4. Photos will recognize and restore metadata

### Emergency Stop

If something goes wrong:
```bash
# Stop at current phase (safe - no data loss)
Ctrl+C

# Resume later
iphoto resume

# Or start fresh
rm ~/.iphoto_session.json
```

## Development

### Project Structure

```
iphoto/
├── src/iphoto/
│   ├── cli.py                 # CLI entry point
│   ├── scanner.py             # Photos library scanning
│   ├── selector.py            # Interactive selection UI
│   ├── exporter.py            # Parallel export orchestration
│   ├── applescript_exporter.py # AppleScript export implementation
│   ├── mover.py               # Archive to external storage
│   ├── deleter.py             # Delete from Photos
│   ├── manifest.py            # Manifest management
│   └── models.py              # Data models
├── tests/
│   ├── test_export2.py        # Filename validation tests
│   ├── test_local_video.py    # Local export test
│   └── test_icloud_export.py  # iCloud diagnostic test
├── CLAUDE.md                  # Complete project context
├── INVESTIGATION.md           # Current issue investigation
└── README.md                  # This file
```

### Running Tests

```bash
source .venv/bin/activate

# Validate filename lookup
python test_export2.py

# Test local video export
python test_local_video.py

# Test iCloud export (currently failing)
python test_icloud_export.py
```

### Contributing

1. Read [CLAUDE.md](CLAUDE.md) for full context
2. Check [INVESTIGATION.md](INVESTIGATION.md) for current issues
3. Write tests for new features
4. Ensure type hints on all functions
5. Use Rich console for user output

## Requirements

- macOS 14+ (tested on macOS 26.2)
- Python 3.11+
- Photos.app
- osxphotos library
- External storage drive

## License

MIT

## Acknowledgments

- [osxphotos](https://github.com/RhetTbull/osxphotos) by Rhet Turnbull - Excellent Photos library interface
- [Rich](https://github.com/Textualize/rich) - Beautiful terminal UI
- [Typer](https://github.com/tiangolo/typer) - CLI framework

## Support

**Issues:** See [INVESTIGATION.md](INVESTIGATION.md) for known issues

**Documentation:**
- [CLAUDE.md](CLAUDE.md) - Full technical context
- [INVESTIGATION.md](INVESTIGATION.md) - Current investigation
- [README.md](README.md) - This file (user guide)

---

**Status:** Active development - local archival works, iCloud export under investigation
**Version:** 0.2.0-alpha
**Last Updated:** 2026-01-30
