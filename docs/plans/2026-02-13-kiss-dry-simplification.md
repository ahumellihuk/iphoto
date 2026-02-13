# KISS & DRY Simplification Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Eliminate duplicated logic, remove unnecessary abstractions, and simplify serialization across the iphoto codebase.

**Architecture:** Bottom-up — add shared utilities first (models.py), then simplify consumers (exporter.py, cli.py, selector.py). Each task is independently compilable.

**Tech Stack:** Python 3.10+, dataclasses, json

---

### Task 1: Add `format_bytes` utility and `completion_label` property

Three separate implementations of size formatting exist. Add one canonical function. Also add `completion_label` property to `SessionState` (used 7 times in cli.py).

**Files:**
- Modify: `src/iphoto/models.py`

**Step 1: Add `format_bytes` function to models.py**

Add after the `filter_ambiguous_filenames` function (after line 324):

```python
def format_bytes(n: int) -> str:
    """Format byte count as human-readable string."""
    gb = n / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    return f"{n / (1024 ** 2):.1f} MB"
```

**Step 2: Replace `VideoInfo.size_formatted` with `format_bytes` call**

Replace lines 53-57:
```python
@property
def size_formatted(self) -> str:
    return format_bytes(self.size_bytes)
```

**Step 3: Replace `MomentGroup.total_size_formatted` with `format_bytes` call**

Remove `total_size_gb` property (lines 120-122) entirely — it's only used by `total_size_formatted` and `space_to_reclaim`, both of which can use `total_size_bytes` directly.

Replace `total_size_formatted` (lines 124-129):
```python
@property
def total_size_formatted(self) -> str:
    return format_bytes(self.total_size_bytes)
```

Replace `space_to_reclaim` (lines 160-163):
```python
@property
def space_to_reclaim(self) -> float:
    """Space in GB that would be freed by archiving videos above threshold."""
    return sum(v.size_bytes for v in self.videos_above_threshold()) / (1024 ** 3)
```

(Keep `space_to_reclaim` as-is — it returns float GB for arithmetic, not for display.)

**Step 4: Add `completion_label` property to `SessionState`**

Add after `completed_count` property (after line 282):
```python
@property
def completion_label(self) -> str:
    """'Deleted' or 'Archived' depending on delete mode."""
    return "Deleted" if self.delete_enabled else "Archived"
```

**Step 5: Verify compilation**

```bash
python3 -m py_compile src/iphoto/models.py
```

**Step 6: Commit**

```bash
git add src/iphoto/models.py
git commit -m "refactor: add format_bytes utility and completion_label property"
```

---

### Task 2: Consolidate size formatting across consumers

Replace all duplicate size formatting in selector.py, cli.py, and mover.py with `format_bytes`.

**Files:**
- Modify: `src/iphoto/selector.py`
- Modify: `src/iphoto/cli.py`
- Modify: `src/iphoto/mover.py`

**Step 1: Replace `format_total_size` in selector.py**

Replace the `format_total_size` function (lines 20-26) with:
```python
def format_total_size(videos: list[VideoInfo]) -> str:
    """Format total size of videos."""
    return format_bytes(sum(v.size_bytes for v in videos))
```

Add `format_bytes` to the import from `.models` (line 11):
```python
from .models import VideoInfo, MomentGroup, format_bytes
```

**Step 2: Replace `1024**3` constants in selector.py**

In `calculate_selection_stats` (lines 64-71), replace:
```python
    return {
        'moments_selected': len(selected_moment_objs),
        'videos_archived': len(archived_videos),
        'videos_skipped': len(skipped_videos),
        'archived_size_gb': archived_size_bytes / (1024 ** 3),
        'skipped_size_gb': skipped_size_bytes / (1024 ** 3),
        'total_size_gb': total_size_bytes / (1024 ** 3),
    }
```
(Keep as-is — these return floats for arithmetic comparison, not display strings.)

In `get_free_disk_space` (lines 29-35), replace:
```python
def get_free_disk_space(path: Path) -> Optional[float]:
    """Get free disk space in GB for the given path."""
    try:
        stat = shutil.disk_usage(str(path))
        return stat.free / (1024 ** 3)
    except Exception:
        return None
```
(Keep as-is — returns float GB for arithmetic.)

**Step 3: Replace `completion_label` in cli.py**

Replace all 7 occurrences of `completion_label = "Deleted" if session.delete_enabled else "Archived"` (lines 221, 529, 578, 779, 792, 832, 851) with `session.completion_label`. Also replace `existing_session.delete_enabled` variant on line 221.

Note: On line 221, `existing_session` is the variable name, so use `existing_session.completion_label`.

Search-and-replace patterns in cli.py:
- `completion_label = "Deleted" if session.delete_enabled else "Archived"` → delete these lines and use `session.completion_label` inline
- `completion_label = "Deleted" if existing_session.delete_enabled else "Archived"` → delete and use `existing_session.completion_label`
- All uses of `completion_label` variable → replace with `session.completion_label` (or `existing_session.completion_label`)

**Step 4: Replace bytes-to-GB in mover.py**

In `move_to_archive` (lines 82-83), replace:
```python
        console.print(f"  Required: {total_size / (1024**3):.2f} GB")
        console.print(f"  Available: {available / (1024**3):.2f} GB")
```
with:
```python
        console.print(f"  Required: {format_bytes(total_size)}")
        console.print(f"  Available: {format_bytes(available)}")
```

Add import at top of mover.py:
```python
from .models import format_bytes
```

**Step 5: Replace bytes-to-GB in cli.py archive()**

Lines 515-516 (batch size critical error):
```python
console.print(f"[red]CRITICAL: Largest remaining video ({format_bytes(first_video.size_bytes)}) "
             f"exceeds available space ({format_bytes(int(usable_bytes))})[/red]")
```

Line 525 (batch total size):
```python
console.print(f"Videos: {len(batch_videos)} | Size: {format_bytes(sum(v.size_bytes for v in batch_videos))}")
```

Add `format_bytes` to the models import in cli.py (line 19).

**Step 6: Verify compilation**

```bash
python3 -m py_compile src/iphoto/selector.py && python3 -m py_compile src/iphoto/cli.py && python3 -m py_compile src/iphoto/mover.py
```

**Step 7: Commit**

```bash
git add src/iphoto/selector.py src/iphoto/cli.py src/iphoto/mover.py
git commit -m "refactor: consolidate size formatting and completion_label usage"
```

---

### Task 3: Replace `ParallelExporter` class with a plain function

`ParallelExporter` is a 170-line class that always runs with `max_workers=1`. Replace with a simple sequential loop function. Remove `TimingStats` class too — replace with Rich's built-in `TimeRemainingColumn`.

**Files:**
- Modify: `src/iphoto/exporter.py`

**Step 1: Delete `TimingStats` class (lines 29-66)**

Remove the entire class.

**Step 2: Delete `ParallelExporter` class (lines 86-254)**

Remove the entire class.

**Step 3: Remove unused imports**

Remove from imports: `deque` (from collections), `ThreadPoolExecutor`, `as_completed` (from concurrent.futures), `Lock` (from threading), `SpinnerColumn`.

Updated imports:
```python
import hashlib
import os
import shutil
import time
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from .models import VideoInfo, filter_ambiguous_filenames
from .applescript_exporter import activate_photos, export_via_applescript
```

**Step 4: Add `_export_single_video` function**

Add after `sanitize_folder_name` (replacing `ParallelExporter.export_video_task`):

```python
def _export_single_video(
    video: VideoInfo,
    staging_path: Path,
    timeout_seconds: int = 1800,
    icloud_timeout_seconds: Optional[int] = None,
) -> tuple[str, Optional[tuple[Path, str]], Optional[str]]:
    """Export one video via AppleScript.

    Returns: (uuid, (path, checksum) or None, error or None)
    """
    try:
        export_dir = staging_path / sanitize_folder_name(video.moment_name or "Unknown")
        export_dir.mkdir(parents=True, exist_ok=True)

        # Skip if already exported with correct size
        existing = export_dir / video.original_filename
        if existing.exists() and existing.stat().st_size == video.size_bytes:
            return video.uuid, (existing, compute_sha256(existing)), None

        effective_timeout = timeout_seconds
        if not video.is_local:
            effective_timeout = max(timeout_seconds, icloud_timeout_seconds or 3600)

        success, exported_path, error_msg = export_via_applescript(
            uuid=video.uuid,
            filename=video.original_filename,
            output_dir=export_dir,
            timeout=effective_timeout,
            max_retries=3,
            delay_between_retries=1.0,
            post_export_wait_seconds=90 if not video.is_local else 30,
            post_export_poll_seconds=2.0 if not video.is_local else 1.0,
        )

        if not success:
            return video.uuid, None, error_msg
        if not exported_path or not exported_path.exists():
            return video.uuid, None, "Export reported success but file not found"

        return video.uuid, (exported_path, compute_sha256(exported_path)), None

    except Exception as e:
        return video.uuid, None, f"Exception: {str(e)[:200]}"
```

**Step 5: Add `_export_batch` function**

Add after `_export_single_video` (replacing `ParallelExporter.export_batch`):

```python
def _export_batch(
    videos: list[VideoInfo],
    staging_path: Path,
    library_path: Optional[str] = None,
    timeout_seconds: int = 1800,
    icloud_timeout_seconds: Optional[int] = None,
) -> tuple[dict[str, tuple[Path, str]], dict[str, str]]:
    """Export videos sequentially with progress tracking.

    Returns: (successful_exports, failed_exports)
    """
    results: dict[str, tuple[Path, str]] = {}
    failures: dict[str, str] = {}

    if not videos:
        return results, failures

    activate_photos()
    batch_start = time.time()

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Exporting...", total=len(videos))

        for i, video in enumerate(videos):
            uuid, result, error = _export_single_video(
                video, staging_path, timeout_seconds, icloud_timeout_seconds,
            )

            if error:
                failures[uuid] = error
                console.print(f"[yellow]✗ {video.original_filename}: {error}[/yellow]")
            else:
                results[uuid] = result
                console.print(f"[green]✓ {video.original_filename}[/green]")

            progress.update(
                task,
                description=f"Exporting — {i + 1}/{len(videos)}",
            )
            progress.advance(task)

    total_time = time.time() - batch_start
    success_rate = len(results) / len(videos) * 100 if videos else 0
    console.print(f"\n[dim]Batch summary: {len(results)}/{len(videos)} exported "
                 f"in {total_time:.1f}s ({success_rate:.0f}% success)[/dim]")

    return results, failures
```

**Step 6: Update `export_videos` to use `_export_batch`**

Replace lines 367-376 (the ParallelExporter usage):
```python
    # Export sequentially (AppleScript is inherently sequential)
    icloud_timeout_seconds = max(timeout_seconds, 3600)
    results, failures = _export_batch(
        videos=videos,
        staging_path=staging_path,
        library_path=library_path,
        timeout_seconds=timeout_seconds,
        icloud_timeout_seconds=icloud_timeout_seconds,
    )
```

**Step 7: Verify compilation**

```bash
python3 -m py_compile src/iphoto/exporter.py
```

**Step 8: Commit**

```bash
git add src/iphoto/exporter.py
git commit -m "refactor: replace ParallelExporter class with simple sequential functions"
```

---

### Task 4: Auto-serialize SessionState with JSON encoder

Replace 150 lines of manual dict-building in `save_session`/`load_session` with `dataclasses.asdict()` + custom JSON encoder.

**Files:**
- Modify: `src/iphoto/models.py` — remove `video_to_dict`/`video_from_dict`, add JSON helpers
- Modify: `src/iphoto/cli.py` — rewrite `save_session`/`load_session`

**Step 1: Add JSON serialization helpers to models.py**

Replace `video_to_dict` and `video_from_dict` (lines 60-97) with:

```python
import json as _json
from dataclasses import asdict

class _IPhotoEncoder(_json.JSONEncoder):
    """JSON encoder for iphoto dataclasses."""
    def default(self, o):
        if isinstance(o, datetime):
            return {"__datetime__": o.isoformat()}
        if isinstance(o, Path):
            return {"__path__": str(o)}
        return super().default(o)


def _iphoto_decoder(o: dict):
    """JSON object hook for iphoto dataclasses."""
    if "__datetime__" in o:
        return datetime.fromisoformat(o["__datetime__"])
    if "__path__" in o:
        return Path(o["__path__"])
    return o
```

Actually, let's keep this simpler. The problem with `asdict` is that it recursively converts nested dataclasses, which is what we want, but `datetime` and `Path` aren't JSON-serializable. Let's use a focused approach:

Replace `video_to_dict` and `video_from_dict` (lines 60-97) with a simpler approach — keep `video_to_dict` but make it shorter with `dataclasses.asdict`:

```python
from dataclasses import asdict as _asdict


def video_to_dict(video: VideoInfo) -> dict:
    """Serialize VideoInfo to a JSON-friendly dict."""
    d = _asdict(video)
    d["date_created"] = video.date_created.isoformat()
    d["date_modified"] = video.date_modified.isoformat()
    # location is already a tuple or None — JSON-safe
    return d


def video_from_dict(data: dict) -> VideoInfo:
    """Deserialize VideoInfo from a dict."""
    data = dict(data)  # Don't mutate original
    data["date_created"] = datetime.fromisoformat(data["date_created"])
    data["date_modified"] = datetime.fromisoformat(data["date_modified"])
    if data.get("location"):
        data["location"] = tuple(data["location"])
    # Drop unknown keys (forward compat)
    valid_fields = {f.name for f in VideoInfo.__dataclass_fields__.values()}
    data = {k: v for k, v in data.items() if k in valid_fields}
    return VideoInfo(**data)
```

**Step 2: Add `to_dict` / `from_dict` to `SessionState`**

Add to the `SessionState` class (after `complete_current_batch`):

```python
    def to_dict(self) -> dict:
        """Serialize session to a JSON-friendly dict."""
        return {
            "session_id": self.session_id,
            "staging_path": str(self.staging_path),
            "external_path": str(self.external_path),
            "created_at": self.created_at.isoformat(),
            "threshold_mb": self.threshold_mb,
            "min_age_days": self.min_age_days,
            "min_size_mb": self.min_size_mb,
            "use_moments": self.use_moments,
            "batch_size": self.batch_size,
            "export_timeout": self.export_timeout,
            "delete_timeout": self.delete_timeout,
            "delete_enabled": self.delete_enabled,
            "allow_ambiguous": self.allow_ambiguous,
            "library_path": self.library_path,
            "manifest_path": self.manifest_path,
            "all_selected_uuids": self.all_selected_uuids,
            "remaining_uuids": self.remaining_uuids,
            "failed_export_uuids": self.failed_export_uuids,
            "failed_delete_uuids": self.failed_delete_uuids,
            "current_batch_number": self.current_batch_number,
            "total_exported": self.total_exported,
            "total_archived": self.total_archived,
            "total_deleted": self.total_deleted,
            "total_failed_exports": self.total_failed_exports,
            "total_failed_deletes": self.total_failed_deletes,
            "videos": [video_to_dict(v) for v in self.videos],
            "batches": [
                {
                    "batch_number": b.batch_number,
                    "selected_uuids": b.selected_uuids,
                    "exported_uuids": b.exported_uuids,
                    "archived_uuids": b.archived_uuids,
                    "deleted_uuids": b.deleted_uuids,
                    "failed_exports": b.failed_exports,
                    "failed_deletes": b.failed_deletes,
                    "checksums": b.checksums,
                    "started_at": b.started_at.isoformat(),
                    "completed_at": b.completed_at.isoformat() if b.completed_at else None,
                }
                for b in self.batches
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        """Deserialize session from a dict."""
        session = cls(
            session_id=data["session_id"],
            staging_path=Path(data["staging_path"]),
            external_path=Path(data["external_path"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            threshold_mb=data.get("threshold_mb"),
            min_age_days=data.get("min_age_days"),
            min_size_mb=data.get("min_size_mb"),
            use_moments=data.get("use_moments", True),
            batch_size=data.get("batch_size"),
            export_timeout=data.get("export_timeout", 1800),
            delete_timeout=data.get("delete_timeout", 120),
            delete_enabled=data.get("delete_enabled", True),
            allow_ambiguous=data.get("allow_ambiguous", False),
            library_path=data.get("library_path"),
            manifest_path=data.get("manifest_path"),
            all_selected_uuids=data["all_selected_uuids"],
            remaining_uuids=data["remaining_uuids"],
            failed_export_uuids=data.get("failed_export_uuids", []),
            failed_delete_uuids=data.get("failed_delete_uuids", []),
            current_batch_number=data["current_batch_number"],
            total_exported=data["total_exported"],
            total_archived=data["total_archived"],
            total_deleted=data["total_deleted"],
            total_failed_exports=data.get("total_failed_exports", 0),
            total_failed_deletes=data.get("total_failed_deletes", 0),
        )
        session.videos = [video_from_dict(v) for v in data.get("videos", [])]
        for bd in data.get("batches", []):
            session.batches.append(BatchProgress(
                batch_number=bd["batch_number"],
                selected_uuids=bd.get("selected_uuids", []),
                exported_uuids=bd.get("exported_uuids", []),
                archived_uuids=bd.get("archived_uuids", []),
                deleted_uuids=bd.get("deleted_uuids", []),
                failed_exports=bd.get("failed_exports", {}),
                failed_deletes=bd.get("failed_deletes", {}),
                checksums=bd.get("checksums", {}),
                started_at=datetime.fromisoformat(bd["started_at"]),
                completed_at=datetime.fromisoformat(bd["completed_at"]) if bd.get("completed_at") else None,
            ))
        return session
```

**Step 3: Simplify `save_session` and `load_session` in cli.py**

Replace `save_session` (lines 35-83):
```python
def save_session(session: SessionState) -> None:
    """Save multi-batch session state for resumption."""
    try:
        SESSION_FILE.write_text(json.dumps(session.to_dict(), indent=2))
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save session: {e}[/yellow]")
```

Replace `load_session` (lines 86-141):
```python
def load_session() -> Optional[SessionState]:
    """Load multi-batch session state for resumption."""
    if not SESSION_FILE.exists():
        return None
    try:
        return SessionState.from_dict(json.loads(SESSION_FILE.read_text()))
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load session: {e}[/yellow]")
        return None
```

Remove `video_to_dict, video_from_dict` from the models import in cli.py (line 19) — they're no longer used directly in cli.py. Update to:
```python
from .models import VideoInfo, MomentGroup, SessionState, BatchProgress, format_bytes
```

**Step 4: Verify compilation**

```bash
python3 -m py_compile src/iphoto/models.py && python3 -m py_compile src/iphoto/cli.py
```

**Step 5: Commit**

```bash
git add src/iphoto/models.py src/iphoto/cli.py
git commit -m "refactor: move session serialization into SessionState.to_dict/from_dict"
```

---

### Task 5: Remove `ExportResult` NamedTuple

`ExportResult` is defined in applescript_exporter.py but immediately unpacked at every call site. Remove it and use a plain tuple.

**Files:**
- Modify: `src/iphoto/applescript_exporter.py`

**Step 1: Remove `ExportResult` class (lines 13-17)**

Delete:
```python
class ExportResult(NamedTuple):
    """Result of an AppleScript export attempt."""
    success: bool
    path: Optional[Path]
    error: Optional[str]
```

Remove `NamedTuple` from the `typing` import (line 10):
```python
from typing import Optional
```

**Step 2: Update return type annotation of `export_via_applescript`**

Change line 133:
```python
) -> tuple[bool, Optional[Path], Optional[str]]:
```

**Step 3: Replace `ExportResult(...)` returns with plain tuples**

Line 195: `return ExportResult(True, found, None)` → `return True, found, None`
Line 196 (error): the `last_error` assignment stays
Line 198: `return ExportResult(False, None, ...)` → `return False, None, f"Video uuid={uuid} not found in Photos library"`
Line 226: `return ExportResult(False, None, ...)` → `return False, None, f"Export failed after {max_retries} attempts: {last_error}"`

**Step 4: Verify compilation**

```bash
python3 -m py_compile src/iphoto/applescript_exporter.py && python3 -m py_compile src/iphoto/exporter.py
```

**Step 5: Commit**

```bash
git add src/iphoto/applescript_exporter.py
git commit -m "refactor: remove ExportResult NamedTuple, use plain tuple"
```

---

### Task 6: Simplify moment extraction in scanner.py

Replace defensive `hasattr` chains with simpler `getattr` calls.

**Files:**
- Modify: `src/iphoto/scanner.py`

**Step 1: Simplify moment info extraction (lines 126-151)**

Replace the entire block:
```python
            # Get moment info from osxphotos moment_info
            moment_name = None
            moment_pk = None
            try:
                if hasattr(photo, 'moment_info') and photo.moment_info:
                    mi = photo.moment_info
                    # Extract moment PK (unique identifier)
                    if hasattr(mi, 'pk') and mi.pk:
                        moment_pk = mi.pk

                    # Create composite moment name: "Location • Date" format
                    location_title = None
                    if hasattr(mi, 'title') and mi.title:
                        location_title = mi.title

                    if location_title and hasattr(mi, 'start_date') and mi.start_date:
                        # Format: "London • May 15, 2024"
                        start_date = mi.start_date
                        if start_date.tzinfo:
                            start_date = start_date.astimezone().replace(tzinfo=None)
                        date_str = start_date.strftime("%b %d, %Y")
                        moment_name = f"{location_title} • {date_str}"
                    elif location_title:
                        moment_name = location_title
            except Exception:
                pass  # Fall back to date-based name if moment extraction fails
```

With:
```python
            # Get moment info from osxphotos
            moment_name = None
            moment_pk = None
            try:
                mi = getattr(photo, 'moment_info', None)
                if mi:
                    moment_pk = getattr(mi, 'pk', None) or None
                    title = getattr(mi, 'title', None)
                    start_date = getattr(mi, 'start_date', None)
                    if title and start_date:
                        if start_date.tzinfo:
                            start_date = start_date.astimezone().replace(tzinfo=None)
                        moment_name = f"{title} • {start_date.strftime('%b %d, %Y')}"
                    elif title:
                        moment_name = title
            except Exception:
                pass
```

**Step 2: Verify compilation**

```bash
python3 -m py_compile src/iphoto/scanner.py
```

**Step 3: Commit**

```bash
git add src/iphoto/scanner.py
git commit -m "refactor: simplify moment extraction with getattr"
```

---

### Task 7: Remove `MomentGroup.total_size_gb` and deduplicate threshold_bytes

Small cleanup: remove the unused `total_size_gb` intermediate property and deduplicate `threshold_bytes` calculation.

**Files:**
- Modify: `src/iphoto/models.py`

**Step 1: Remove `total_size_gb` property (lines 120-122)**

Delete:
```python
    @property
    def total_size_gb(self) -> float:
        return self.total_size_bytes / (1024 ** 3)
```

**Step 2: Deduplicate threshold_bytes in `videos_above_threshold` / `videos_below_threshold`**

Replace both methods (lines 143-151) with:
```python
    @property
    def _threshold_bytes(self) -> float:
        return self.threshold_mb * 1024 * 1024

    def videos_above_threshold(self) -> list[VideoInfo]:
        """Returns videos larger than the threshold."""
        return [v for v in self.videos if v.size_bytes >= self._threshold_bytes]

    def videos_below_threshold(self) -> list[VideoInfo]:
        """Returns videos smaller than the threshold."""
        return [v for v in self.videos if v.size_bytes < self._threshold_bytes]
```

**Step 3: Verify compilation**

```bash
python3 -m py_compile src/iphoto/models.py
```

**Step 4: Commit**

```bash
git add src/iphoto/models.py
git commit -m "refactor: remove redundant total_size_gb and deduplicate threshold_bytes"
```

---

### Task 8: Final verification

**Step 1: Compile all modules**

```bash
for f in src/iphoto/*.py; do python3 -m py_compile "$f"; done
```

**Step 2: Check no references to removed symbols**

```bash
# Should find zero results:
grep -r "TimingStats\|ParallelExporter\|ExportResult" src/iphoto/ --include="*.py"
grep -r "total_size_gb" src/iphoto/ --include="*.py"  # Only in calculate_batch_size (OK)
```
