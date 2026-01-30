# iCloud Export Investigation

**Created:** 2026-01-30
**Status:** Active Investigation
**Priority:** Critical - Blocks primary use case

## Problem Statement

Photos.app AppleScript export returns "SUCCESS" but files don't appear, especially for iCloud videos. This blocks the entire archival workflow.

## Reproduction Steps

### Minimal Test Case

```python
import subprocess
from pathlib import Path

output_dir = Path("/tmp/photos_test")
output_dir.mkdir(exist_ok=True)

applescript = f'''
tell application "Photos"
    set testItem to (first media item whose filename is "IMG_8997.MOV")
    set exportPath to POSIX file "{output_dir}"
    export {{testItem}} to exportPath with using originals
end tell
'''

result = subprocess.run(["osascript", "-e", applescript],
                       capture_output=True, text=True, timeout=60)
print(f"Result: {result.stdout}")

# Wait and check
import time
time.sleep(30)
print(f"Files: {list(output_dir.glob('*'))}")
```

**Expected:** File appears in output_dir
**Actual:** No file, but AppleScript returns success

## Evidence Collected

### Test Results Matrix

| Video | Type | AppleScript Result | File Appeared | Notes |
|-------|------|-------------------|---------------|-------|
| IMG_3038.MOV | Local | SUCCESS (via ParallelExporter) | ✓ Yes (19.7s) | Only successful case |
| IMG_3038.MOV | Local | SUCCESS (direct call) | ✗ No | Same code, different outcome |
| IMG_3038.MOV | Local | ERROR -1712 (timeout) | ✗ No | After multiple runs |
| IMG_8997.MOV | iCloud | SUCCESS (13.9s) | ✗ No | Too fast for download |
| IMG_7803.MOV | iCloud | ERROR (file not created after 90s) | ✗ No | Via ParallelExporter |

### Timing Analysis

**Successful export:**
- Export call → File appears: ~20 seconds
- File size: 2.0 GB
- Network: Not needed (local)

**Failed iCloud export:**
- Export call returns: 13.9 seconds
- Expected download time: 2+ minutes for 2GB @ 1Mbps
- Actual file appearance: Never

**Conclusion:** Photos.app is NOT downloading from iCloud during export

## Hypotheses

### H1: Photos.app Doesn't Auto-Download (LIKELY)

**Evidence:**
- iCloud export returns in 13.9s (too fast for 2GB download)
- File never appears even after 120s wait
- Local video works (no download needed)

**Test:** Check if video is cached locally first

### H2: Export Path Ignored (POSSIBLE)

**Evidence:**
- AppleScript returns success
- No errors about path
- File doesn't appear in specified location

**Test:** Search entire system for exported files

### H3: Race Condition in Photos.app (POSSIBLE)

**Evidence:**
- First export worked
- Subsequent exports fail
- Behavior changes after Photos.app restart

**Test:** Add delays, check Photos.app state

### H4: Requires User Interaction (POSSIBLE)

**Evidence:**
- GUI export might work differently than AppleScript
- Photos.app may queue exports for user confirmation

**Test:** Try with Photos.app in foreground and user logged in

## Experiments Queue

### 🔄 In Progress

- [ ] None currently running

### ⏳ Planned

1. **Search for exported files**
   ```bash
   # Check if Photos.app is exporting elsewhere
   mdfind "kMDItemFSName == 'IMG_8997.MOV'"
   find ~ -name "IMG_8997.MOV" -newer /tmp/timestamp 2>/dev/null
   ```

2. **Monitor Photos.app during export**
   ```bash
   # Watch Photos.app log
   log stream --predicate 'subsystem == "com.apple.photos"' --level debug
   ```

3. **Test export to different locations**
   - Desktop
   - Downloads
   - External drive
   - User's home directory

4. **Test with Photos.app in foreground**
   ```applescript
   tell application "Photos"
       activate  -- Bring to front
       delay 2   -- Let UI settle
       -- then export
   end tell
   ```

5. **Check for dialogs/prompts**
   - Export might trigger confirmation dialog
   - Photos might be waiting for user response

6. **Try batch export**
   ```applescript
   export {item1, item2, item3} to exportPath
   ```

7. **Test PhotoKit alternative**
   ```python
   # Use PyObjC to call PhotoKit framework
   from Foundation import *
   from Photos import *
   ```

### ✅ Completed

1. ✅ **Verified filename lookup** - Uses correct `original_filename`
2. ✅ **Confirmed one successful export** - Proves concept can work
3. ✅ **Tested with restart** - Behavior changes but still fails
4. ✅ **Confirmed iCloud status** - Videos correctly identified as iCloud-only

## Alternative Approaches

### Option 1: Pre-Download with Photos UI

**Concept:** User manually downloads iCloud videos first

**Pros:**
- Guaranteed to work
- Uses Photos.app native UI
- No AppleScript fragility

**Cons:**
- Manual step required
- Slow for large libraries
- Defeats automation goal

**Implementation:**
1. Tool identifies iCloud videos
2. User opens Photos and downloads them
3. Tool detects when local and proceeds with export

### Option 2: PhotoKit Framework (Recommended)

**Concept:** Use macOS PhotoKit framework directly via PyObjC

**Pros:**
- Official Apple API
- Can request resources and wait for download
- More control over download process

**Cons:**
- More complex implementation
- Requires PyObjC setup
- Steeper learning curve

**Implementation:**
```python
from Foundation import NSBundle
from Photos import PHAsset, PHImageManager, PHAssetResource

# Request download
PHImageManager.defaultManager().requestImageDataForAsset_options_resultHandler_(
    asset, options, handler
)
```

### Option 3: Hybrid osxphotos + AppleScript

**Concept:** Use osxphotos for local, different approach for iCloud

**Pros:**
- osxphotos works great for local videos
- Can handle two classes of videos differently

**Cons:**
- Still need to solve iCloud problem
- Complex dual-path logic

**Implementation:**
- Local videos: osxphotos export
- iCloud videos: User-assisted or PhotoKit

### Option 4: iCloud Photos Downloader Integration

**Concept:** Use existing iCloud downloader tools

**Pros:**
- Leverages existing solutions
- Can download outside Photos.app

**Cons:**
- Additional dependency
- May not integrate with Photos library
- Authentication complexity

## Research Notes

### Photos.app Export Behavior

**From testing:**
- Export command accepts: `alias`, `POSIX file`, `file`
- Returns immediately (doesn't block for download)
- No progress callback mechanism
- Silent failures common

**AppleScript Dictionary says:**
```
export (list of media items) to file
    with using originals -- export originals (Boolean)
```

**Missing:** No mention of iCloud download behavior!

### iCloud Download Mechanism

**Known facts:**
- Photos.app can trigger downloads via UI
- Right-click → "Download Original" works
- Viewing in Photos app triggers download
- Export via UI "Export Unmodified Original" should download

**Unknown:**
- Does AppleScript export trigger download?
- How to detect download progress?
- Can we wait for download completion?

### PhotoKit Research

**Relevant classes:**
- `PHAsset` - Represents a photo/video
- `PHAssetResource` - Access to underlying files
- `PHImageManager` - Handles requests including downloads
- `PHAssetResourceManager` - Downloads resources

**Key method:**
```objc
requestImageDataForAsset:options:resultHandler:
```

**Options can specify:**
- Network access allowed (downloads from iCloud)
- Progress handler
- Version (original vs edited)

## Next Session Recommendations

### Immediate Actions

1. **Search for exported files system-wide**
   - Photos.app might be exporting to default location
   - Check ~/Pictures, Desktop, Downloads

2. **Monitor Photos.app logs during export**
   - Look for errors, download attempts, path issues

3. **Test with Photos.app in foreground**
   - Activate Photos before export
   - Check for dialogs/prompts

### If Above Fails

4. **Implement PhotoKit POC**
   - Create minimal PyObjC test
   - Request one video with download
   - Measure success rate

5. **Consider user-assisted workflow**
   - Identify iCloud videos
   - Ask user to download in Photos
   - Auto-detect when ready

## Questions for User

- **Would you accept a user-assisted flow?** (Manual download step)
- **Willing to use PhotoKit?** (More complex but more reliable)
- **Can you test with Photos.app in foreground?** (Maybe needs focus)
- **Any Photos.app preferences that might affect export?**

## Success Criteria

**MVP:**
- [ ] 90%+ success rate for local video export
- [ ] 90%+ success rate for iCloud video export
- [ ] Reliable way to detect when iCloud videos are ready
- [ ] Clear error messages when exports fail

**Ideal:**
- [ ] Fully automated iCloud download + export
- [ ] Progress tracking for downloads
- [ ] Parallel download + export pipeline
- [ ] Resume capability for interrupted downloads

## Resources

### Code References

- `src/iphoto/applescript_exporter.py:59-187` - Current implementation
- `test_icloud_export.py` - Diagnostic test showing failure
- `test_local_video.py` - Shows successful local export

### External Links

- [PhotoKit Documentation](https://developer.apple.com/documentation/photokit)
- [PyObjC Documentation](https://pyobjc.readthedocs.io/)
- [osxphotos GitHub](https://github.com/RhetTbull/osxphotos)
- [Photos AppleScript Dictionary](https://iworkautomation.com/numbers/script-menu.html)

---

**Status:** Awaiting next investigation session
**Blocker:** Need to determine why AppleScript export doesn't download from iCloud
**Next Step:** System-wide file search + Photos.app log monitoring
