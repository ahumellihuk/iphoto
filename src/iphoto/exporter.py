"""Export videos from Photos library using AppleScript."""

import hashlib
import os
import shutil
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Optional

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from .models import VideoInfo
from .applescript_exporter import activate_photos, export_via_applescript

console = Console()


class TimingStats:
    """Track timing statistics for ETA calculation."""

    def __init__(self, window_size: int = 5):
        """Initialize timing stats with moving window."""
        self.window_size = window_size
        self.times: deque = deque(maxlen=window_size)
        self.start_time = time.time()

    def add_time(self, seconds: float) -> None:
        """Add a measured time to the window."""
        self.times.append(seconds)

    @property
    def avg_time(self) -> float:
        """Get average time from window."""
        if not self.times:
            return 0.0
        return sum(self.times) / len(self.times)

    def estimate_remaining(self, remaining_count: int) -> float:
        """Estimate seconds remaining for remaining items."""
        if not self.times:
            return 0.0
        return self.avg_time * remaining_count

    def format_eta(self, remaining_seconds: float) -> str:
        """Format seconds into human-readable ETA."""
        if remaining_seconds <= 0:
            return "Done"
        hours, remainder = divmod(int(remaining_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours > 0:
            return f"{hours}h {minutes}m"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def sanitize_folder_name(name: str) -> str:
    """Sanitize a string for use as a folder name."""
    # Replace problematic characters
    for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(char, '-')
    return name.strip()


class ParallelExporter:
    """Export videos using AppleScript (sequential by default for reliability)."""

    def __init__(self, max_workers: int = 1, staging_path: Path = None):
        """Initialize exporter.

        Args:
            max_workers: Maximum number of concurrent export tasks (default: 1 for AppleScript reliability)
                        AppleScript API is sequential and flaky, so parallel workers may cause issues.
            staging_path: Path to staging directory
        """
        self.max_workers = max_workers
        self.staging_path = staging_path
        self.progress_lock = Lock()

    def export_video_task(
        self,
        video: VideoInfo,
        staging_path: Path,
        library_path: Optional[str] = None,
        timeout_seconds: int = 1800,
        icloud_timeout_seconds: Optional[int] = None,
    ) -> tuple[str, Optional[tuple[Path, str]], Optional[str]]:
        """Single video export task using AppleScript.

        Returns: (uuid, (path, checksum) or None, error_message or None)
        """
        try:
            # Create moment folder
            moment_folder = sanitize_folder_name(video.moment_name or "Unknown")
            export_dir = staging_path / moment_folder
            export_dir.mkdir(parents=True, exist_ok=True)

            # Skip re-export if file already exists in staging with correct size
            existing = export_dir / video.original_filename
            if existing.exists() and existing.stat().st_size == video.size_bytes:
                checksum = compute_sha256(existing)
                return video.uuid, (existing, checksum), None

            # Export video via AppleScript
            activate_photos()
            effective_timeout = timeout_seconds
            if not video.is_local:
                if icloud_timeout_seconds:
                    effective_timeout = max(timeout_seconds, icloud_timeout_seconds)
                else:
                    effective_timeout = max(timeout_seconds, 3600)
            # Use UUID for precise lookup (avoids duplicate filename issues)
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

            # Verify exported file exists
            if not exported_path or not exported_path.exists():
                return video.uuid, None, "Export reported success but file not found"

            # Compute checksum of exported file
            checksum = compute_sha256(exported_path)
            return video.uuid, (exported_path, checksum), None

        except Exception as e:
            error_msg = f"Exception: {str(e)[:200]}"
            return video.uuid, None, error_msg

    def export_batch(
        self,
        videos: list[VideoInfo],
        staging_path: Path,
        library_path: Optional[str] = None,
        timeout_seconds: int = 1800,
        icloud_timeout_seconds: Optional[int] = None,
    ) -> tuple[dict[str, tuple[Path, str]], dict[str, str]]:
        """Export videos in parallel with timing and ETA.

        Returns: (successful_exports, failed_exports)
        """
        results: dict[str, tuple[Path, str]] = {}
        failures: dict[str, str] = {}

        if not videos:
            return results, failures

        timing_stats = TimingStats(window_size=min(5, len(videos)))
        completed_count = 0
        batch_start = time.time()

        activate_photos()
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all video exports as tasks
            future_to_video = {
                executor.submit(
                    self.export_video_task,
                    video,
                    staging_path,
                    library_path,
                    timeout_seconds,
                    icloud_timeout_seconds,
                ): video
                for video in videos
            }

            # Process completions with progress tracking
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                console=console,
            ) as progress:
                task = progress.add_task(
                    f"Exporting...",
                    total=len(videos),
                )

                for future in as_completed(future_to_video):
                    video = future_to_video[future]
                    uuid, result, error = future.result()

                    completed_count += 1
                    remaining_count = len(videos) - completed_count

                    video_elapsed = time.time() - batch_start
                    per_video = video_elapsed / completed_count if completed_count > 0 else 0

                    with self.progress_lock:
                        if error:
                            failures[uuid] = error
                            console.print(f"[yellow]✗ {video.original_filename}: {error}[/yellow]")
                        else:
                            results[uuid] = result
                            timing_stats.add_time(per_video)
                            console.print(f"[green]✓ {video.original_filename}[/green]")

                        # Update progress description with ETA
                        if remaining_count > 0:
                            estimated_remaining = timing_stats.estimate_remaining(remaining_count)
                            eta_str = timing_stats.format_eta(estimated_remaining)
                            elapsed_sec = time.time() - batch_start
                            progress.update(
                                task,
                                description=f"Exporting — "
                                           f"{completed_count}/{len(videos)} — ETA: {eta_str}"
                            )
                        else:
                            progress.update(
                                task,
                                description=f"Exporting — "
                                           f"{completed_count}/{len(videos)} — Done"
                            )
                        progress.advance(task)

            # Batch summary
            total_time = time.time() - batch_start
            success_rate = len(results) / len(videos) * 100 if videos else 0
            console.print(f"\n[dim]Batch summary: {len(results)}/{len(videos)} exported in {total_time:.1f}s "
                         f"({success_rate:.0f}% success)[/dim]")

        return results, failures


def calculate_batch_size(
    staging_path: Path,
    remaining_videos: list[VideoInfo],
    max_workers: int = 4,
    override_size: Optional[int] = None,
) -> int:
    """Calculate optimal batch size based on available staging space.

    Strategy:
    - Get available staging space with 70% safety margin
    - Calculate average video size from remaining videos
    - Compute how many videos fit in available space
    - Apply worker multiple (don't queue too far ahead)
    - Minimum 1 video, maximum remaining video count

    Args:
        staging_path: Path to staging directory
        remaining_videos: List of VideoInfo objects to process
        max_workers: Number of parallel workers (batch size shouldn't exceed this × 2)
        override_size: If provided, use this size instead of calculating

    Returns:
        Recommended batch size in number of videos
    """
    if override_size:
        return min(override_size, len(remaining_videos))

    if not remaining_videos:
        return 0

    try:
        staging_path.mkdir(parents=True, exist_ok=True)
        # Get available staging space
        disk_usage = shutil.disk_usage(staging_path)
        available_bytes = disk_usage.free
        usable_bytes = available_bytes * 0.70  # 70% safety margin

        # Calculate average video size from remaining videos
        total_size = sum(v.size_bytes for v in remaining_videos)
        avg_size = total_size / len(remaining_videos)

        # Space-based batch size
        space_based = max(1, int(usable_bytes / avg_size))

        # Apply constraints: fit in available space, don't exceed remaining count
        batch_size = max(1, min(space_based, len(remaining_videos)))

        available_gb = usable_bytes / (1024 ** 3)
        total_batch_size_gb = (batch_size * avg_size) / (1024 ** 3)

        console.print(
            f"[dim]Batch size: {batch_size} videos "
            f"({total_batch_size_gb:.2f}/{available_gb:.2f} GB available)[/dim]"
        )
        return batch_size

    except Exception as e:
        console.print(f"[yellow]Warning: Could not calculate batch size: {e}[/yellow]")
        return max(1, min(len(remaining_videos), max_workers * 2))


def export_videos(
    videos: list[VideoInfo],
    staging_path: Path,
    library_path: Optional[str] = None,
    timeout_seconds: int = 1800,  # 30 minutes - iCloud downloads can be slow
    allow_ambiguous: bool = False,
) -> tuple[dict[str, tuple[Path, str]], dict[str, str]]:
    """
    Export videos to staging directory, organized by moment.
    Uses Photos.app AppleScript API to export videos directly from Photos.

    IMPORTANT: iCloud-only videos:
    - Photos.app automatically downloads videos from iCloud during export
    - Works even when iCloud storage is full (doesn't require iCloud space)
    - Requires Photos.app to be running and iCloud Photo Library enabled
    - Export uses "Export Unmodified Originals" mode

    Args:
        videos: List of VideoInfo objects to export
        staging_path: Path to staging directory
        library_path: Optional path to Photos library (not used with AppleScript)
        timeout_seconds: Timeout per video export in seconds

    Returns tuple of (successful_exports, failed_exports)
    - successful_exports: dict of uuid -> (exported_path, sha256_hash)
    - failed_exports: dict of uuid -> error_reason
    """
    staging_path.mkdir(parents=True, exist_ok=True)

    if not videos:
        console.print("[yellow]No videos to export[/yellow]")
        return {}, {}

    from .models import filter_ambiguous_filenames
    videos, pre_failures = filter_ambiguous_filenames(videos, allow_ambiguous)
    if pre_failures:
        console.print(
            f"[yellow]Skipped {len(pre_failures)} videos with duplicate filenames. Use --allow-ambiguous to override.[/yellow]"
        )

    # Count iCloud videos and inform users
    icloud_videos = [v for v in videos if not v.is_local]
    icloud_count = len(icloud_videos)

    if icloud_count > 0:
        icloud_pct = int(100 * icloud_count / len(videos))
        console.print(f"\n[cyan]ℹ {icloud_count}/{len(videos)} videos ({icloud_pct}%) are iCloud-only[/cyan]")
        console.print("[cyan]Photos.app will download these automatically during export.[/cyan]")
        console.print("\n[dim]Troubleshooting if exports fail:[/dim]")
        console.print("[dim]  • Ensure iCloud Photo Library is enabled in Photos.app[/dim]")
        console.print("[dim]  • Verify Photos.app is running and not paused for sync[/dim]")
        console.print("[dim]  • Check that videos are accessible in Photos.app[/dim]\n")

    # Use ParallelExporter for sequential export (AppleScript is inherently sequential)
    exporter = ParallelExporter(max_workers=1, staging_path=staging_path)
    icloud_timeout_seconds = max(timeout_seconds, 3600)
    results, failures = exporter.export_batch(
        videos=videos,
        staging_path=staging_path,
        library_path=library_path,
        timeout_seconds=timeout_seconds,
        icloud_timeout_seconds=icloud_timeout_seconds,
    )

    # Merge any pre-filter failures
    if pre_failures:
        failures.update(pre_failures)

    if failures:
        total_count = len(videos) + len(pre_failures)
        console.print(f"\n[green]Successfully exported {len(results)} of {total_count} videos[/green]")
        console.print(f"[yellow]Failed to export {len(failures)} videos[/yellow]")
    else:
        console.print(f"\n[green]Exported {len(results)} of {len(videos)} videos[/green]")
    return results, failures
