# Codebase Overhaul Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Full overhaul of the iphoto codebase — dead code removal, function decomposition, deduplication, dependency fixes, and documentation updates.

**Architecture:** Bottom-up approach starting from leaf modules (models, manifest, mover) and working inward to the largest file (cli.py). Each task is a self-contained change that keeps the codebase working.

**Tech Stack:** Python 3.10+, typer, rich, osxphotos, photoscript

---

### Task 1: Remove dead `BatchState` class and related code from models.py

**Files:**
- Modify: `src/iphoto/models.py:189-223`

**Step 1: Remove BatchState class**

Delete the entire `BatchState` class (lines 189-223) and the blank line before it. This class was replaced by `SessionState` + `BatchProgress` and is no longer used anywhere except cli.py's dead state functions (which we remove in Task 7).

**Step 2: Remove `BatchProgress.total_size_bytes` property**

Delete lines 240-244 (the `total_size_bytes` property that always returns 0). It's never called and the comment says "computed externally."

**Step 3: Add comment to smart threshold rounding**

At `models.py:183`, add a comment explaining the rounding formula:

```python
                # Round down to nearest 25MB boundary for clean thresholds
                threshold = int((size / 25) + 0.5) * 25
```

**Step 4: Verify import still works**

Run: `cd /Users/camoiloc/IdeaProjects/iphoto && source .venv/bin/activate && python -c "from iphoto.models import VideoInfo, MomentGroup, SessionState, BatchProgress, video_to_dict, video_from_dict; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add src/iphoto/models.py
git commit -m "refactor: remove dead BatchState class and unused total_size_bytes property"
```

---

### Task 2: Add `ExportResult` NamedTuple and extract polling helper in applescript_exporter.py

**Files:**
- Modify: `src/iphoto/applescript_exporter.py`

**Step 1: Replace `Tuple` import with `NamedTuple` and add `ExportResult`**

At the top of the file, replace:
```python
from typing import Optional, Tuple
```
with:
```python
from typing import NamedTuple, Optional
```

Add after the imports:
```python

class ExportResult(NamedTuple):
    """Result of an AppleScript export attempt."""
    success: bool
    path: Optional[Path]
    error: Optional[str]
```

**Step 2: Extract file polling into `_poll_for_file` helper**

Add this function before `export_via_applescript`:
```python
def _poll_for_file(
    output_dir: Path,
    filename: str,
    timeout_seconds: int,
    poll_interval: float,
) -> Optional[Path]:
    """Poll for an exported file to appear with non-zero size."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        found = _find_exported_file(output_dir, filename)
        if found and found.stat().st_size > 0:
            return found
        time.sleep(poll_interval)
    # Final check
    found = _find_exported_file(output_dir, filename)
    if found and found.stat().st_size > 0:
        return found
    return None
```

**Step 3: Update `export_via_applescript` return type and use helpers**

Change the signature return type from `Tuple[bool, Optional[Path], Optional[str]]` to `ExportResult`.

Replace the polling block (lines 167-177) with:
```python
                if output == "SUCCESS":
                    found = _poll_for_file(output_dir, filename, post_export_wait_seconds, post_export_poll_seconds)
                    if found:
                        return ExportResult(True, found, None)
                    last_error = f"Export reported success but file not created after {post_export_wait_seconds}s"
```

Update all `return` statements to use `ExportResult(...)`:
- `return True, found, None` → `return ExportResult(True, found, None)`
- `return False, None, "..."` → `return ExportResult(False, None, "...")`

**Step 4: Verify import works**

Run: `python -c "from iphoto.applescript_exporter import ExportResult, export_via_applescript; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add src/iphoto/applescript_exporter.py
git commit -m "refactor: add ExportResult NamedTuple and extract polling helper"
```

---

### Task 3: Extract shared ambiguous filename check utility

**Files:**
- Modify: `src/iphoto/models.py` (add utility function)
- Modify: `src/iphoto/exporter.py` (use shared utility)
- Modify: `src/iphoto/deleter.py` (use shared utility)

**Step 1: Add `filter_ambiguous_filenames` to models.py**

Add at the end of `models.py`:
```python
def filter_ambiguous_filenames(
    videos: list[VideoInfo],
    allow_ambiguous: bool = False,
) -> tuple[list[VideoInfo], dict[str, str]]:
    """Filter out videos with duplicate original filenames.

    Returns (safe_videos, failures) where failures maps uuid -> reason.
    """
    if allow_ambiguous:
        return videos, {}

    filename_map: dict[str, list[VideoInfo]] = {}
    for video in videos:
        filename_map.setdefault(video.original_filename, []).append(video)

    failures: dict[str, str] = {}
    for fn, vids in filename_map.items():
        if len(vids) > 1:
            for video in vids:
                failures[video.uuid] = f"Ambiguous filename '{fn}' (matches {len(vids)} items)"

    safe_videos = [v for v in videos if v.uuid not in failures]
    return safe_videos, failures
```

**Step 2: Update exporter.py to use shared utility**

In `exporter.py`, replace lines 356-370 (the ambiguous filename block in `export_videos`) with:
```python
    from .models import filter_ambiguous_filenames
    videos, pre_failures = filter_ambiguous_filenames(videos, allow_ambiguous)
    if pre_failures:
        console.print(
            f"[yellow]Skipped {len(pre_failures)} videos with duplicate filenames. Use --allow-ambiguous to override.[/yellow]"
        )
```

**Step 3: Update deleter.py to use shared utility**

In `deleter.py`, replace lines 37-51 (the ambiguous filename block) with:
```python
    from .models import filter_ambiguous_filenames
    videos, failures = filter_ambiguous_filenames(videos, allow_ambiguous)
    if failures:
        console.print(
            f"[yellow]Skipped {len(failures)} videos with duplicate filenames.[/yellow]"
        )
```

Adjust `videos = list(videos)` to make a mutable copy if needed (the parameter is already `list[VideoInfo]`).

**Step 4: Verify imports work**

Run: `python -c "from iphoto.models import filter_ambiguous_filenames; from iphoto.exporter import export_videos; from iphoto.deleter import delete_from_photos; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add src/iphoto/models.py src/iphoto/exporter.py src/iphoto/deleter.py
git commit -m "refactor: extract shared ambiguous filename filter to models.py"
```

---

### Task 4: Clean up exporter.py — remove misleading params and deduplicate

**Files:**
- Modify: `src/iphoto/exporter.py`

**Step 1: Remove `settle_delay_seconds` parameter from `export_video_task`**

Remove the `settle_delay_seconds: float = 0.5` parameter and the corresponding sleep block (lines 155-156). This parameter adds unnecessary delay.

**Step 2: Remove `max_workers` parameter from `export_videos`**

Remove the `max_workers` parameter from `export_videos()` signature and the enforcement block (lines 385-388). Hardcode `max_workers=1` when creating `ParallelExporter`:

```python
    exporter = ParallelExporter(max_workers=1, staging_path=staging_path)
```

**Step 3: Update `ParallelExporter.__init__` default**

Change the docstring to just say "Sequential exporter" instead of mentioning parallel workers:

```python
class ParallelExporter:
    """Export videos from Photos using AppleScript (sequential for reliability)."""

    def __init__(self, staging_path: Path = None):
        self.staging_path = staging_path
        self.progress_lock = Lock()
```

Remove `max_workers` from `__init__` and hardcode `self.max_workers = 1` or just use `1` directly in `ThreadPoolExecutor(max_workers=1)`.

Wait — actually, keep `max_workers` in `ParallelExporter` since `export_batch` uses it in progress display. Instead, simplify `export_videos`:

Just remove `max_workers` param from `export_videos` and hardcode `ParallelExporter(max_workers=1, ...)`.

**Step 4: Clean up progress bar text**

In `export_batch`, replace references to `self.max_workers` in progress text:
- `f"Exporting ({self.max_workers} parallel)..."` → `f"Exporting..."`
- Same for the other description strings.

**Step 5: Verify**

Run: `python -c "from iphoto.exporter import export_videos, ParallelExporter, calculate_batch_size; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add src/iphoto/exporter.py
git commit -m "refactor: simplify exporter by removing misleading parallel params"
```

---

### Task 5: Extract threshold formatting helper in selector.py

**Files:**
- Modify: `src/iphoto/selector.py`

**Step 1: Add helper function**

Add after `get_free_disk_space()`:
```python
def format_threshold(threshold_mb: Optional[float], smart_threshold_mb: Optional[float] = None) -> str:
    """Format threshold value for display."""
    if threshold_mb is not None:
        return f"{threshold_mb:.0f} MB"
    if smart_threshold_mb is not None:
        return f"{smart_threshold_mb:.0f} MB"
    return "-"
```

**Step 2: Replace all 4 duplicated threshold formatting blocks**

In `display_moments` (lines 132-138), replace with:
```python
        threshold_display = format_threshold(moment.smart_threshold_mb, moment.threshold_mb)
```

In `display_moment_detail` (lines 159-165), replace with:
```python
    threshold_display = format_threshold(moment.threshold_mb, moment.smart_threshold_mb)
```

In `interactive_select_moments` preview block (lines 421-424), replace with:
```python
            filter_desc = f"after {threshold_mb:.0f}MB filter" if threshold_mb is not None else "using per-moment smart thresholds"
```
(This one is a different pattern — description text, not a threshold value — so keep it inline but simplified.)

In the final confirmation block (lines 507-510), replace with:
```python
        threshold_desc = f"below {threshold_mb:.0f}MB" if threshold_mb is not None else "below smart threshold"
```
(Same — inline ternary is fine for this case.)

**Step 3: Verify**

Run: `python -c "from iphoto.selector import interactive_select_moments, display_moments; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add src/iphoto/selector.py
git commit -m "refactor: extract threshold formatting helper in selector"
```

---

### Task 6: Break up `interactive_select_moments` in selector.py

**Files:**
- Modify: `src/iphoto/selector.py`

**Step 1: Extract `_display_selection_summary` helper**

Extract lines 356-381 (the selection summary and disk space display) into:
```python
def _display_selection_summary(
    moments: list[MomentGroup],
    selected_moments: set[str],
    free_space_gb: Optional[float],
) -> None:
    """Display current selection stats and disk space info."""
    stats = calculate_selection_stats(moments, selected_moments)

    if selected_moments:
        console.print(f"\n[bold][green]Current Selection[/green][/bold]")
        console.print(f"  Moments: {stats['moments_selected']} selected")
        console.print(
            f"  Videos: [green]{stats['videos_archived']}[/green] to archive, "
            f"[yellow]{stats['videos_skipped']}[/yellow] will stay in Photos"
        )
        console.print(
            f"  Space: [bold green]{stats['archived_size_gb']:.2f} GB[/bold green] to reclaim, "
            f"[dim]{stats['skipped_size_gb']:.2f} GB[/dim] skipped"
        )

    if free_space_gb is not None:
        status = "+" if stats.get('archived_size_gb', 0) <= free_space_gb else "!"
        console.print(f"\n[cyan]{status} External drive free space: {free_space_gb:.2f} GB[/cyan]")
        if stats.get('archived_size_gb', 0) > free_space_gb:
            console.print(
                f"  [yellow]Selection ({stats['archived_size_gb']:.2f} GB) exceeds free space![/yellow]"
            )
```

**Step 2: Extract `_display_moment_commands` helper**

Extract lines 383-393 (the commands help text):
```python
def _display_moment_commands(threshold_mb: Optional[float]) -> None:
    """Display available commands for moment selection."""
    console.print("\n[bold]Commands:[/bold]")
    console.print("  [cyan]n[/cyan]/[cyan]p[/cyan] - next/previous page")
    console.print("  [cyan]1,2,3[/cyan] or [cyan]1-10[/cyan] - select moment(s)")
    console.print("  [cyan]expand N[/cyan] - show videos in moment N")
    if threshold_mb is not None:
        console.print(f"  [cyan]reset[/cyan] - reset to smart thresholds (override: {threshold_mb:.0f}MB)")
    else:
        console.print("  [cyan]threshold N[/cyan] - apply N MB threshold to all moments")
    console.print("  [cyan]preview[/cyan] - preview selected videos after filtering")
    console.print("  [cyan]sort size|count|date[/cyan] - reorder list")
    console.print("  [cyan]clear[/cyan] - clear selection, [cyan]done[/cyan] - proceed, [cyan]q[/cyan] - quit")
```

**Step 3: Extract `_confirm_moment_selection` helper**

Extract lines 495-520 (the final confirmation block):
```python
def _confirm_moment_selection(
    moments: list[MomentGroup],
    selected_moments: set[str],
    threshold_mb: Optional[float],
) -> list[VideoInfo]:
    """Show final selection and get user confirmation. Returns filtered videos or empty list."""
    selected_moment_objs = [m for m in moments if m.key in selected_moments]
    final_videos = []
    for moment in selected_moment_objs:
        final_videos.extend(moment.videos_above_threshold())

    console.clear()
    console.print(f"\n[bold]Selected {len(selected_moments)} moments:[/bold]")
    for moment in selected_moment_objs:
        above = len(moment.videos_above_threshold())
        below = len(moment.videos_below_threshold())
        threshold_desc = f"below {threshold_mb:.0f}MB" if threshold_mb is not None else "below smart threshold"
        console.print(f"  - {moment.name}: {above} videos (skipping {below} {threshold_desc})")

    console.print(f"\n[bold]Total to archive: {len(final_videos)} videos[/bold]")
    display_videos(final_videos, show_index=False)
    console.print(f"\nTotal size: [green]{format_total_size(final_videos)}[/green]")

    if not Confirm.ask("\nProceed with archiving these videos?"):
        return []
    return final_videos
```

**Step 4: Update `interactive_select_moments` to use helpers**

Replace the extracted sections with calls to the new helpers. The main function should be ~80-100 lines (down from 205).

**Step 5: Verify**

Run: `python -c "from iphoto.selector import interactive_select_moments; print('OK')"`
Expected: `OK`

**Step 6: Commit**

```bash
git add src/iphoto/selector.py
git commit -m "refactor: decompose interactive_select_moments into smaller helpers"
```

---

### Task 7: Remove dead BatchState code from cli.py

**Files:**
- Modify: `src/iphoto/cli.py`

**Step 1: Remove `save_state`, `load_state`, `clear_state` functions**

Delete lines 36-82 (the three BatchState state management functions). Also remove the `STATE_FILE` constant (line 32).

**Step 2: Update imports**

In line 19, remove `BatchState` from the import:
```python
from .models import VideoInfo, MomentGroup, SessionState, BatchProgress, video_to_dict, video_from_dict
```

**Step 3: Remove BatchState usage from `status` command**

In the `status` command (lines 940-963), remove the entire fallback block that uses `load_state()`:
```python
    state = load_state()
    if not state:
        ...
    ...
```

Replace with just:
```python
    console.print("[yellow]No session found.[/yellow]")
    console.print("[dim]Use 'iphoto archive' to start a new session.[/dim]")
```

**Step 4: Verify**

Run: `python -c "from iphoto.cli import app; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add src/iphoto/cli.py
git commit -m "refactor: remove dead BatchState functions and STATE_FILE from cli"
```

---

### Task 8: Fix undefined `video` variable bug in cli.py

**Files:**
- Modify: `src/iphoto/cli.py:492-497`

**Step 1: Fix the bug**

The current code at line 492-497:
```python
            if not batch_videos:
                # Even one video won't fit - critical space issue
                console.print(f"[red]✗ CRITICAL: Largest remaining video ({video.size_bytes / (1024**3):.2f} GB) "
                             f"exceeds available space ({usable_bytes / (1024**3):.2f} GB)[/red]")
```

The variable `video` comes from the `for uuid in session.remaining_uuids:` loop above but is only set if the loop runs. Fix by using the first remaining video explicitly:

```python
            if not batch_videos:
                first_video = all_videos_map[session.remaining_uuids[0]]
                console.print(f"[red]CRITICAL: Largest remaining video ({first_video.size_bytes / (1024**3):.2f} GB) "
                             f"exceeds available space ({usable_bytes / (1024**3):.2f} GB)[/red]")
                console.print("[red]Cannot proceed. Free up staging space and retry.[/red]")
                return
```

**Step 2: Commit**

```bash
git add src/iphoto/cli.py
git commit -m "fix: undefined video variable in batch size adjustment"
```

---

### Task 9: Decompose `archive()` command in cli.py

**Files:**
- Modify: `src/iphoto/cli.py`

This is the largest refactoring task. The 442-line `archive()` function will be broken into focused helper functions.

**Step 1: Extract `_resume_or_create_session` helper**

Extract lines 311-420 (session resume + scan/select + session creation):
```python
def _resume_or_create_session(
    staging: Path,
    external: Path,
    min_age_days: Optional[int],
    min_size_mb: Optional[float],
    threshold_mb: Optional[float],
    use_moments: bool,
    batch_size: Optional[int],
    export_timeout: int,
    delete_timeout: int,
    no_delete: bool,
    allow_ambiguous: bool,
    library: Optional[str],
    max_workers: int,
) -> Optional[tuple[SessionState, list[VideoInfo]]]:
    """Resume existing session or create new one via scan+select.

    Returns (session, all_videos) or None if user cancels.
    """
    existing_session = load_session()
    if existing_session and not existing_session.is_complete:
        console.print(f"[bold cyan]Found interrupted session {existing_session.session_id}[/bold cyan]")
        completion_label = "Deleted" if existing_session.delete_enabled else "Archived"
        console.print(
            f"  Progress: {existing_session.completed_count}/{len(existing_session.all_selected_uuids)} "
            f"videos {completion_label.lower()}"
        )
        console.print(f"  Batches completed: {existing_session.batches_completed}")
        if Confirm.ask("Resume this session?"):
            session = existing_session
            if not session.manifest_path:
                session.manifest_path = str(external / f"iphoto_manifest_{session.session_id}.json")
                save_session(session)
            if session.videos:
                return session, session.videos
            else:
                all_videos = scan_videos(
                    min_age_days=session.min_age_days,
                    min_size_mb=session.min_size_mb,
                    library_path=session.library_path,
                )
                return session, all_videos
        else:
            if Confirm.ask("Clear this session and start fresh?"):
                clear_session()
            return None

    # New session
    console.print("[bold]Step 1:[/bold] Scanning Photos library...\n")
    all_videos = scan_videos(min_age_days=min_age_days, min_size_mb=min_size_mb, library_path=library)
    if not all_videos:
        console.print("[yellow]No videos found matching criteria.[/yellow]")
        return None

    icloud_count = len([v for v in all_videos if not v.is_local])
    if icloud_count:
        console.print(f"[cyan]{icloud_count} videos in iCloud (will use local cache for export)[/cyan]\n")

    all_videos = rank_videos(all_videos, sort_by="size")
    display_summary(all_videos)

    console.print("\n[bold]Step 2:[/bold] Select videos to archive...\n")
    if use_moments and all_videos:
        moments = group_by_moment(all_videos)
        console.print(f"[cyan]Grouped into {len(moments)} moments[/cyan]\n")
        selected = interactive_select_moments(moments, external_path=external, threshold_mb=threshold_mb)
    else:
        selected = interactive_select(all_videos, max_size_gb=None)

    if not selected:
        console.print("[yellow]No videos selected. Exiting.[/yellow]")
        return None

    session = SessionState(
        staging_path=staging, external_path=external,
        all_selected_uuids=[v.uuid for v in selected],
        remaining_uuids=[v.uuid for v in selected],
        max_workers=max_workers, threshold_mb=threshold_mb,
        min_age_days=min_age_days, min_size_mb=min_size_mb,
        use_moments=use_moments, batch_size=batch_size,
        export_timeout=export_timeout, delete_timeout=delete_timeout,
        delete_enabled=not no_delete, allow_ambiguous=allow_ambiguous,
        library_path=library, videos=selected,
    )
    session.manifest_path = str(external / f"iphoto_manifest_{session.session_id}.json")
    save_session(session)
    console.print(f"\n[cyan]Created session {session.session_id} with {len(selected)} videos[/cyan]\n")
    return session, all_videos
```

**Step 2: Extract `_export_batch_phase` helper**

Extract the Phase 1 export block:
```python
def _export_batch_phase(
    batch_videos: list[VideoInfo],
    staging: Path,
    library: Optional[str],
    export_timeout: int,
    allow_ambiguous: bool,
    dry_run: bool,
) -> tuple[dict[str, tuple[Path, str]], dict[str, str]]:
    """Phase 1: Export videos from Photos to staging."""
    console.print(f"[bold]Phase 1:[/bold] Exporting {len(batch_videos)} videos...")
    if dry_run:
        from .selector import format_total_size
        console.print("[cyan][DRY RUN] Would export the following videos:[/cyan]")
        for v in batch_videos:
            console.print(f"  [dim]- {v.original_filename} ({v.size_formatted})[/dim]")
        console.print(f"  [cyan]Total: {format_total_size(batch_videos)}[/cyan]")
        return {v.uuid: (staging / v.original_filename, "dry") for v in batch_videos}, {}
    return export_videos(
        batch_videos, staging, library_path=library,
        timeout_seconds=export_timeout, allow_ambiguous=allow_ambiguous,
    )
```

**Step 3: Extract `_archive_batch_phase` helper**

Extract Phase 2 + Phase 3 (archive + manifest + delete):
```python
def _archive_batch_phase(
    exported: dict[str, tuple[Path, str]],
    external: Path,
    batch_videos: list[VideoInfo],
    all_videos_map: dict[str, VideoInfo],
    session: SessionState,
    batch: BatchProgress,
    delete_timeout: int,
    allow_ambiguous: bool,
    dry_run: bool,
) -> dict[str, Path]:
    """Phase 2+3: Archive to external and delete from Photos."""
    console.print(f"\n[bold]Phase 2:[/bold] Archiving to external drive...")
    if dry_run:
        console.print(f"[cyan][DRY RUN] Would archive {len(exported)} videos[/cyan]")
        return dict(exported)  # type: ignore

    archived = move_to_archive(exported, external)
    batch.archived_uuids = list(archived.keys())
    session.total_archived += len(archived)
    save_session(session)
    cleanup_staging(session.staging_path)

    # Update manifest
    if session.manifest_path and archived:
        manifest_entries = []
        for uuid, dest_path in archived.items():
            video = all_videos_map.get(uuid)
            if not video:
                continue
            checksum = batch.checksums.get(uuid)
            if not checksum and dest_path.exists():
                checksum = compute_sha256(dest_path)
            manifest_entries.append(
                build_manifest_entry(video=video, archived_path=dest_path, checksum=checksum or "", session_id=session.session_id)
            )
        if manifest_entries:
            append_manifest_entries(Path(session.manifest_path), manifest_entries)

    if not archived:
        return {}

    # Phase 3: Delete
    if session.delete_enabled:
        console.print(f"\n[bold]Phase 3:[/bold] Deleting from Photos...")
        archived_videos = [v for v in batch_videos if v.uuid in archived]
        deleted, delete_failures = delete_from_photos(
            archived_videos, dry_run=False, timeout_seconds=delete_timeout, allow_ambiguous=allow_ambiguous,
        )
        batch.deleted_uuids = deleted
        batch.failed_deletes = delete_failures
        session.total_deleted += len(deleted)
        session.total_failed_deletes += len(delete_failures)
        if delete_failures:
            session.failed_delete_uuids = sorted(set(session.failed_delete_uuids).union(delete_failures.keys()))

    batch.completed_at = datetime.now()
    save_session(session)
    return archived
```

**Step 4: Simplify `archive()` to orchestrator**

The `archive()` function should now be ~100 lines:
1. Print header + dry-run banner
2. Call `_resume_or_create_session()`
3. Pre-flight checks (external mounted, workers)
4. Batch loop calling `_export_batch_phase` and `_archive_batch_phase`
5. Final summary

**Step 5: Remove `max_workers` param from `archive()` and related commands**

Since exporter now hardcodes sequential, remove `max_workers` from:
- `archive()` signature (keep the CLI option but ignore it / print deprecation warning)
- Actually: keep the CLI option for backwards compat, just don't pass it through. Or remove entirely.

Decision: Remove the `--workers` CLI option. Users shouldn't think they can parallelize.

**Step 6: Verify**

Run: `python -c "from iphoto.cli import app; print('OK')"`
Expected: `OK`

**Step 7: Commit**

```bash
git add src/iphoto/cli.py
git commit -m "refactor: decompose archive() into focused helper functions"
```

---

### Task 10: Update exporter.py callers after max_workers removal

**Files:**
- Modify: `src/iphoto/cli.py` (remove max_workers references)
- Modify: `src/iphoto/exporter.py` (verify export_videos signature)

**Step 1: Remove max_workers from cli.py**

Remove the `--workers` option from `archive()` command. Remove the enforcement block (lines 436-440). Remove `max_workers` from session creation and resume logic.

In `SessionState`, `max_workers` field is still there for backwards compat with saved sessions — leave it but don't use it.

**Step 2: Update `retry_failed` to not pass max_workers**

In `retry_failed`, remove `max_workers=session.max_workers` from the `export_videos` call.

**Step 3: Update `resume` to not pass max_workers**

In `resume`, remove `max_workers=session.max_workers` from the `archive()` call.

**Step 4: Verify**

Run: `python -c "from iphoto.cli import app; print('OK')"`
Expected: `OK`

**Step 5: Commit**

```bash
git add src/iphoto/cli.py src/iphoto/exporter.py
git commit -m "refactor: remove max_workers plumbing from CLI after exporter simplification"
```

---

### Task 11: Fix dependencies and version

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/iphoto/__init__.py`

**Step 1: Add photoscript dependency**

In `pyproject.toml`, add to dependencies:
```toml
dependencies = [
    "osxphotos>=0.68.0",
    "photoscript>=0.3.0",
    "typer>=0.9.0",
    "rich>=13.0.0",
]
```

**Step 2: Update version**

In `pyproject.toml`, change version to `"0.2.0a1"` (PEP 440 alpha format).
In `src/iphoto/__init__.py`, change to `__version__ = "0.2.0a1"`.

**Step 3: Commit**

```bash
git add pyproject.toml src/iphoto/__init__.py
git commit -m "chore: add photoscript dependency and bump version to 0.2.0a1"
```

---

### Task 12: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `TODO.md`

**Step 1: Update CLAUDE.md**

Key changes:
- Remove references to `BatchState` (replaced by `SessionState`)
- Update file line counts to reflect refactored code
- Note that `max_workers` is no longer a user-facing option
- Update the "Development Guidelines" section to mention the extracted helpers
- Update "Data Flow" to note `filter_ambiguous_filenames` shared utility
- Update version to 0.2.0a1

**Step 2: Update README.md**

Key changes:
- Fix version from "0.2.0-alpha" to "0.2.0a1"
- Remove `--workers 4` from advanced options (sequential is enforced)
- Fix "Parallel export" claim to "Sequential export (for reliability)"
- Remove mention of `tests/` directory (tests are gitignored)
- Update "DEFAULT_WORKERS = 4" to remove or note sequential default

**Step 3: Update TODO.md**

Key changes:
- Check off cleanup items that were completed:
  - [x] Remove unused code (BatchState)
  - [x] Code cleanup (function decomposition, deduplication)
  - [x] Fix photoscript dependency
  - [x] Consistent error handling (ambiguous filename shared utility)

**Step 4: Commit**

```bash
git add CLAUDE.md README.md TODO.md
git commit -m "docs: update documentation to reflect codebase overhaul"
```

---

### Task 13: Final verification

**Step 1: Check all imports work**

Run: `python -c "from iphoto.cli import app; from iphoto.models import VideoInfo, SessionState, filter_ambiguous_filenames; from iphoto.applescript_exporter import ExportResult; print('All imports OK')"`
Expected: `All imports OK`

**Step 2: Check CLI loads**

Run: `iphoto --help`
Expected: Help output with scan, archive, verify, resume, retry-failed, status, version commands.

**Step 3: Check no syntax errors**

Run: `python -m py_compile src/iphoto/cli.py && python -m py_compile src/iphoto/models.py && python -m py_compile src/iphoto/exporter.py && python -m py_compile src/iphoto/applescript_exporter.py && python -m py_compile src/iphoto/selector.py && python -m py_compile src/iphoto/deleter.py && echo "All clean"`
Expected: `All clean`

**Step 4: Commit any fixes**

If any issues, fix and commit.
