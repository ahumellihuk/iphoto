# TODO - Priority Ordered

## 🔴 Critical - iCloud Export Issue

### Immediate (Next Session)

- [ ] **System-wide file search**
  - Check if Photos.app is exporting to unexpected location
  - Search for recently created .MOV files
  - Monitor ~/Pictures, Desktop, Downloads
  ```bash
  mdfind "kMDItemFSName == 'IMG_8997.MOV' && kMDItemFSCreationDate >= \$time.today"
  find / -name "*.MOV" -newer /tmp/timestamp 2>/dev/null | grep -v "/Volumes"
  ```

- [ ] **Monitor Photos.app logs**
  - Stream logs during export attempt
  - Look for errors, warnings, download attempts
  ```bash
  log stream --predicate 'subsystem == "com.apple.photos"' --level debug &
  # Then run export test
  ```

- [ ] **Test with Photos.app in foreground**
  - Ensure Photos.app is active and visible
  - Check for dialogs/prompts that might be hidden
  - Monitor UI during export
  ```applescript
  tell application "Photos"
      activate
      delay 2  -- Let UI settle
      -- export command
  end tell
  ```

### High Priority (This Week)

- [ ] **PhotoKit POC**
  - Research PyObjC setup
  - Create minimal test requesting video with download
  - Measure reliability vs AppleScript
  ```python
  from Foundation import *
  from Photos import *
  # PHImageManager.requestImageData...
  ```

- [ ] **Test different export destinations**
  - Try Desktop (known path)
  - Try ~/Downloads
  - Try user's home directory
  - Try external drive directly
  - Document which paths work/fail

- [ ] **Investigate export batch behavior**
  - Test exporting multiple videos at once
  - Check if batch succeeds where single fails
  - Monitor resource usage during batch

### Medium Priority (Next Week)

- [ ] **Hybrid approach POC**
  - Keep osxphotos for local videos (works great)
  - Implement alternative for iCloud videos
  - Could be PhotoKit, user-assisted, or Photos UI automation

- [ ] **User-assisted workflow design**
  - UI to show which videos need downloading
  - Detect when videos become local
  - Auto-proceed with export once ready
  - Good fallback if automation fails

- [ ] **Photos.app state management**
  - Determine what state changes affect export
  - Document when restart is needed
  - Add health checks before export

## 🟡 Important - Code Quality

- [ ] **Add comprehensive error handling**
  - Distinguish between timeout, not found, iCloud errors
  - Clear user messages for each error type
  - Recovery suggestions

- [ ] **Improve test coverage**
  - Unit tests for each module
  - Integration tests for full workflow
  - Mock Photos.app for reliable testing

- [ ] **Add logging**
  - Debug logs for troubleshooting
  - Separate log file per batch
  - Structured logging for analysis

- [ ] **Performance optimization**
  - Profile export bottlenecks
  - Optimize parallel workers
  - Reduce Photos.app calls

## 🟢 Nice to Have - Features

- [ ] **Progress estimation**
  - Better ETA calculations
  - Show download progress for iCloud
  - Visual progress bars

- [ ] **Smart moment selection**
  - ML-based suggestions
  - Detect duplicates
  - Identify "keeper" videos

- [ ] **Archive search**
  - Command to search manifest
  - Preview archived videos
  - Restore to Photos

- [ ] **Configuration file**
  - Save user preferences
  - Default thresholds per moment
  - Custom export rules

## 📝 Documentation

- [x] ✅ Create CLAUDE.md (complete project context)
- [x] ✅ Create INVESTIGATION.md (current issue tracking)
- [x] ✅ Create README.md (user guide)
- [x] ✅ Create quick-start.md (session bootstrap)
- [ ] Add inline code documentation
- [ ] Create architecture diagrams
- [ ] Write troubleshooting guide
- [ ] Create video walkthrough

## 🧹 Cleanup

- [ ] **Remove test files before commit**
  - test_*.py files
  - check_*.py files
  - debug_*.py files
  - /tmp output directories

- [ ] **Code cleanup**
  - Remove unused imports
  - Fix "claude" typo artifact (already done in scanner.py)
  - Consistent error handling
  - Type hints everywhere

- [ ] **Repository structure**
  - Move tests to tests/ directory
  - Organize documentation
  - Clean up temp files

## 🔬 Research Tasks

- [ ] **Compare with similar tools**
  - How does iCloud Photos Downloader handle this?
  - What does Hazel use for Photos automation?
  - Any open-source solutions?

- [ ] **Apple documentation deep dive**
  - PhotoKit complete API
  - Photos AppleScript dictionary edge cases
  - iCloud download API (if exists)

- [ ] **Community knowledge**
  - Search forums for Photos export issues
  - Check Stack Overflow
  - Apple Developer Forums

## 📊 Metrics & Validation

- [ ] **Success rate tracking**
  - Log success/failure for each export
  - Track by video type (local/iCloud)
  - Identify patterns in failures

- [ ] **Performance benchmarks**
  - Export speed per video size
  - Network bandwidth utilization
  - CPU/memory usage

- [ ] **User testing**
  - Test with different Photos libraries
  - Various macOS versions
  - Different network conditions

## 🎯 Definition of Done (v1.0)

**Core functionality:**
- [ ] 95%+ success rate for local video export
- [ ] 90%+ success rate for iCloud video export
- [ ] Clear error messages with recovery steps
- [ ] Complete end-to-end workflow tested

**User experience:**
- [ ] Intuitive CLI interface
- [ ] Progress tracking with ETA
- [ ] Dry-run mode for safety
- [ ] Resume capability working

**Quality:**
- [ ] Test coverage >80%
- [ ] Documentation complete
- [ ] No known data loss bugs
- [ ] Handles edge cases gracefully

**Performance:**
- [ ] Handles 1000+ video libraries
- [ ] Parallel export working
- [ ] Reasonable memory usage
- [ ] Network efficiency for iCloud

---

**Next Action:** Start with system-wide file search and Photos.app log monitoring to understand where exports are going (or failing).

**Priority Rationale:** Can't build features until core export works. Focus 100% on solving iCloud download issue before anything else.

**Timeline Goal:** Working iCloud export within 1 week, even if it's a hybrid/assisted solution.
