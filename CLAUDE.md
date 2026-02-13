# iPhoto Video Archiver - Project Context

## Project Overview

A Python CLI tool for archiving large/old videos from Apple Photos to external storage. The tool helps users reclaim local storage by moving infrequently accessed videos to external drives while maintaining a searchable manifest.

### Primary Goal
Solve the iCloud photo storage problem: users have massive video libraries in iCloud but can't download them all locally due to disk space constraints. This tool selectively archives videos to external storage and removes them from the local Photos library.

## Architecture

### Core Components

1. **Scanner** (`scanner.py`)
   - Uses `osxphotos` library to read Photos database
   - Extracts video metadata: UUID, filename, size, location, moments
   - Determines if videos are local or iCloud-only

2. **Selector** (`selector.py`)
   - Interactive TUI for selecting videos/moments to archive
   - Smart threshold suggestions based on video size distribution
   - Moment-based grouping for intuitive selection

3. **Exporter** (`exporter.py`, `applescript_exporter.py`)
   - **Current approach**: AppleScript-based export via Photos.app
   - **Previous approach**: osxphotos library (replaced due to iCloud issues)
   - Sequential export enforced (no `max_workers` param; parallel was removed for reliability)
   - `ExportResult` NamedTuple wraps export outcomes (replaces raw tuples)
   - `_poll_for_file` helper extracted for post-export file verification
   - Checksum verification

4. **Mover** (`mover.py`)
   - Transfers exported videos to external storage
   - Organizes by moment folders
   - Verifies checksums

5. **Deleter** (`deleter.py`)
   - Removes archived videos from Photos library
   - Safety checks and verification

6. **Shared Utilities** (`models.py`)
   - `filter_ambiguous_filenames` — deduplicates videos with non-unique original filenames (used by exporter and deleter)
   - `SessionState` / `BatchProgress` — session persistence (replaced old `BatchState`)

7. **Manifest** (`manifest.py`)
   - JSONL manifest of all archived videos
   - Enables search and recovery of archived content

## Critical Issue: iCloud Export Problem

### The Core Challenge

**Why we switched from osxphotos to AppleScript:**
- osxphotos couldn't reliably download iCloud videos during export
- AppleScript was chosen because Photos.app's export function should trigger iCloud downloads automatically

### Current Status: AppleScript Export Failing

#### Findings (2026-01-30)

**Test Results:**
```
Local video test (IMG_3038.MOV):
  ✓ ONE successful export via ParallelExporter (2GB in 19.7s)
  ✗ Subsequent direct AppleScript calls fail silently

iCloud video test (IMG_8997.MOV):
  ✗ AppleScript reports "SUCCESS" in 13.9s
  ✗ File never appears (waited 120s)
```

**Key Observations:**

1. **AppleScript behavior is inconsistent:**
   - Sometimes returns error `-1712` (AppleEvent timed out)
   - Sometimes returns "SUCCESS" but no file appears
   - One successful export proves the approach CAN work

2. **Path specification is correct:**
   - Using `POSIX file "/path/to/dir"`
   - Photos.app does recognize this syntax
   - The one successful export used identical code

3. **Filename lookup works:**
   - ✓ Using `video.original_filename` (e.g., "IMG_3038.MOV")
   - ✗ NOT using `video.filename` (UUID-based internal name)
   - This was validated and is working correctly

4. **Photos.app state matters:**
   - Export success seems tied to Photos.app state
   - Restarting Photos.app changes behavior
   - May need to be in foreground (uses `activate` before export)

### The AppleScript Export Implementation

**Location:** `src/iphoto/applescript_exporter.py:59-187`

**How it works:**
```applescript
tell application "Photos"
    set theItems to (every media item whose filename is "{filename}")
    set theItem to item 1 of theItems
    set exportPath to POSIX file "{output_dir}"

    with timeout of {timeout} seconds
        export {theItem} to exportPath with using originals
    end timeout
end tell
```

**Post-export verification:**
- Waits up to 90s (configurable) for file to appear
- Polls every 1-2 seconds checking if file exists
- Verifies file size > 0 bytes

**Current timeout settings:**
- Local videos: 30s post-export wait
- iCloud videos: 90s post-export wait
- Export timeout: 30min (1800s) default

## Investigation Results

### What We Know Works

1. ✅ **UUID → Filename mapping**
   - Scanner correctly extracts both `filename` (UUID-based) and `original_filename` (display name)
   - Exporter correctly uses `original_filename` for AppleScript lookup
   - Photos.app successfully finds videos by `original_filename`

2. ✅ **Local video export (when it works)**
   - Successfully exported 2GB video in 19.7s
   - File appeared with correct checksum
   - Organized into proper moment folder

3. ✅ **Full workflow (scan → select → export → move → delete)**
   - All components integrate correctly
   - State management via `SessionState` + `BatchProgress` with resumption logic
   - Manifest generation works

### What's Broken

1. ❌ **Inconsistent AppleScript export**
   - Photos.app claims success but doesn't export files
   - Behavior changes between runs
   - No clear pattern for when it works vs. fails

2. ❌ **iCloud video downloads**
   - Photos.app doesn't download from iCloud during export
   - Export reports success before download completes
   - Files never appear even after extended wait times

## Technical Details

### Data Flow

```
1. Scanner (osxphotos) → VideoInfo objects
   - uuid: Internal Photos DB UUID
   - filename: UUID-based filename from Photos DB
   - original_filename: User-facing filename (e.g., IMG_1234.MOV)
   - is_local: True if file exists locally, False if iCloud-only

2. Selector → User chooses videos/moments

3. Exporter → AppleScript export (sequential)
   - Uses original_filename to lookup in Photos.app
   - Ambiguous filenames filtered via shared filter_ambiguous_filenames (models.py)
   - Photos.app exports to staging directory
   - Verifies file appeared via _poll_for_file helper

4. Mover → Copy to external storage
   - Organized by moment folders
   - SHA256 checksum verification

5. Deleter → Remove from Photos library
   - Uses osxphotos or AppleScript

6. Manifest → JSONL record of archived videos
```

### File Naming Convention

**In Photos Database (osxphotos):**
- `filename`: `D7697F77-2D7E-4E52-8687-2EE5270FFDD8.mov` (UUID-based)
- `original_filename`: `IMG_3038.MOV` (user-facing)

**In Photos.app AppleScript:**
- Lookup by: `original_filename` (e.g., "IMG_3038.MOV")
- Export preserves: `original_filename`

**Critical:** Must use `original_filename` for AppleScript, NOT `filename`!

### Dependencies

**Runtime:**
- Python 3.11+
- osxphotos 0.74.2+ (for database reading)
- photoscript (AppleScript bridge for Photos.app)
- Photos.app (macOS system app)
- typer, rich (CLI/TUI)

**System:**
- macOS 14+ (tested on macOS 26.2)
- Access to Photos library
- External storage for archive destination

## Open Questions & Next Steps

### Immediate Investigation Needed

1. **Why does Photos.app export work sometimes but not others?**
   - Is there a race condition?
   - Does Photos.app need specific state/focus?
   - Are there undocumented AppleScript requirements?

2. **How to reliably trigger iCloud downloads?**
   - Can we pre-download before export?
   - Is there a way to check download status?
   - Should we use a different API (PhotoKit framework)?

3. **Alternative approaches to consider:**
   - Use Photos.app GUI automation instead of AppleScript
   - Direct PhotoKit framework via PyObjC
   - Hybrid: osxphotos for local, AppleScript for iCloud
   - Manual user-driven export with tool coordination

### Potential Solutions

**Option A: Fix AppleScript reliability**
- Add Photos.app state management
- Implement backoff/retry with state resets
- Monitor Photos.app logs for errors
- Test with Photos in foreground vs background

**Option B: PhotoKit Framework**
- Use PyObjC to call PhotoKit directly
- PHImageManager for downloads
- PHAssetResourceManager for export
- More control but more complex

**Option C: Hybrid Approach**
- osxphotos for local videos (works well)
- Manual user export for iCloud videos
- Tool coordinates and verifies

**Option D: User-Assisted Flow**
- Tool identifies videos to archive
- User manually exports via Photos.app UI
- Tool picks up exports and continues workflow

## Testing Approach

### Validated Tests

**Location:** `/Users/camoiloc/Projects/iphoto/test_*.py`

1. `test_export2.py` - Validates filename vs original_filename
   - ✓ Confirms original_filename works
   - ✓ Confirms filename fails

2. `test_local_video.py` - Full workflow test
   - ✓ One successful end-to-end export

3. `test_icloud_export.py` - iCloud download diagnostic
   - ❌ Shows AppleScript success without file

4. `debug_export.py` - AppleScript debugging
   - Shows timeout errors and false successes

### How to Reproduce the Issue

```bash
source .venv/bin/activate

# Test local video export
python test_local_video.py

# Test iCloud video export
python test_icloud_export.py

# Run full workflow
iphoto archive --dry-run --min-size 2000
```

## Development Guidelines

### When Working on This Project

1. **Test with both local and iCloud videos**
   - Local: Fast, good for iteration
   - iCloud: Real problem case, slower

2. **Always check original_filename vs filename**
   - AppleScript needs original_filename
   - Never use UUID-based filename for lookup

3. **Monitor Photos.app state**
   - Check if it's running
   - Note foreground vs background
   - Consider restart between tests

4. **Verify files actually appear**
   - Don't trust AppleScript return values
   - Poll for file existence
   - Check file size > 0

5. **Note decomposed CLI helpers**
   - `archive()` is split into `_resume_or_create_session`, `_export_batch_phase`, `_archive_batch_phase`
   - `interactive_select_moments` is split into `_display_selection_summary`, `_display_moment_commands`, `_confirm_moment_selection`
   - `format_threshold` helper extracted in selector.py

### Code Style

- Type hints on all functions
- Rich console for user feedback
- Comprehensive error handling
- State persistence for resumability (via `SessionState` + `BatchProgress`)

## Historical Context

### Migration from osxphotos to AppleScript

**Commit:** `1511b8d Replace osxphotos with AppleScript-based export`

**Rationale:**
- osxphotos export couldn't handle iCloud downloads
- AppleScript expected to trigger Photos.app downloads
- Photos.app is the authoritative source

**Result:**
- Successfully implemented AppleScript export
- But iCloud download problem persists
- Now investigating Photos.app behavior

### Prior Art

This tool builds on experience with:
- osxphotos library (excellent for metadata, poor for iCloud)
- Apple Photos AppleScript dictionary
- macOS file system automation

## Quick Start for New Sessions

### Essential Context Checklist

- [ ] Problem: Archive videos from Photos to external storage
- [ ] Main issue: iCloud videos won't download during export
- [ ] Using AppleScript to talk to Photos.app
- [ ] Must use `original_filename` not `filename` for lookups
- [ ] Export behavior is inconsistent - investigation ongoing
- [ ] Test files available in root directory (test_*.py)

### First Commands to Run

```bash
# Activate environment
source .venv/bin/activate

# Check syntax (previously had 'claude' typo in scanner.py)
python -c "import iphoto.cli"

# See what videos exist
iphoto scan

# Run a test
python test_local_video.py
```

## Resources

### Apple Documentation

- [Photos AppleScript Dictionary](https://developer.apple.com/library/archive/documentation/AppleScript/Conceptual/AppleScriptLangGuide/)
- Photos.app: System Preferences → Privacy → Automation
- PhotoKit Framework (alternative approach)

### Related Projects

- [osxphotos](https://github.com/RhetTbull/osxphotos) - Excellent metadata reader
- iCloud Photos Downloader - Similar problem space

## Glossary

- **Moment**: Photos.app grouping of media by time/location
- **Original**: Unedited version of photo/video (vs. edited)
- **iCloud-only**: Media in iCloud but not downloaded locally
- **UUID**: Unique identifier in Photos database
- **Staging**: Temporary local directory before moving to external storage
- **Manifest**: JSONL file tracking all archived videos

---

**Last Updated:** 2026-02-13
**Version:** 0.2.0a1
**Status:** Active development - investigating AppleScript export reliability
**Primary Issue:** iCloud video export not working despite AppleScript success messages
