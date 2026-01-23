"""Export videos from Photos library using osxphotos."""

import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock
from typing import Optional
from collections import deque

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


def get_osxphotos_path() -> str:
    """Get the full path to osxphotos executable.

    Uses shutil.which to find osxphotos in PATH, falling back to venv if needed.
    """
    # Try standard PATH first
    osxphotos_path = shutil.which("osxphotos")
    if osxphotos_path:
        return osxphotos_path

    # Try in current venv
    venv_path = Path(sys.prefix) / "bin" / "osxphotos"
    if venv_path.exists():
        return str(venv_path)

    # Fall back to command name (will fail with clear error if not available)
    return "osxphotos"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def sanitize_folder_name(name: str) -> str:
    """Sanitize a string for use as a folder name."""
    # Replace problematic characters
    for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        name = name.replace(char, '-')
    return name.strip()


class ParallelExporter:
    """Export videos in parallel using ThreadPoolExecutor."""

    def __init__(self, max_workers: int = 4, staging_path: Path = None):
        """Initialize parallel exporter.

        Args:
            max_workers: Maximum number of concurrent export tasks (default: 4)
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
    ) -> tuple[str, Optional[tuple[Path, str]], Optional[str]]:
        """Single video export task (runs in thread).

        Returns: (uuid, (path, checksum) or None, error_message or None)
        """
        result = None
        timeout_error = None

        try:
            # Create moment folder
            moment_folder = sanitize_folder_name(video.moment_name or "Unknown")
            export_dir = staging_path / moment_folder
            export_dir.mkdir(parents=True, exist_ok=True)

            # Try multiple export strategies for reliability
            osxphotos_cmd = get_osxphotos_path()

            # Determine which strategy to try first based on whether video is local
            if video.is_local:
                # Local video - direct export
                export_strategies = [
                    {
                        "name": "local-export",
                        "flags": [],  # Default export for local videos
                        "timeout_multiplier": 0.5,
                    },
                ]
            else:
                # iCloud-only video with "Optimize Mac Storage" enabled
                # Strategy 1: Try default export (might use cached versions)
                # Strategy 2: Try PhotoKit which sometimes has better iCloud handling
                # Strategy 3: Last resort - try download from iCloud (will fail if iCloud full)
                export_strategies = [
                    {
                        "name": "default-cached",
                        "flags": [],  # Default export, may use cached versions
                        "timeout_multiplier": 1.0,
                    },
                    {
                        "name": "photokit-cached",
                        "flags": ["--use-photokit"],  # PhotoKit might access cache better
                        "timeout_multiplier": 2.0,
                    },
                    {
                        "name": "photokit-download",
                        "flags": ["--use-photokit", "--download-missing"],  # Last resort: try download
                        "timeout_multiplier": 5.0,  # Extra time for iCloud download
                    },
                ]

            # Try multiple strategies for exporting
            for strategy in export_strategies:
                try:
                    cmd = [
                        osxphotos_cmd,
                        "export",
                        str(export_dir),
                        "--uuid", video.uuid,
                        "--overwrite",
                        "--update",  # CRITICAL: Prevents interactive prompts
                        "--no-progress",  # Disable progress (we have our own)
                    ]
                    cmd.extend(strategy["flags"])

                    if library_path:
                        cmd.extend(["--db", library_path])

                    strategy_timeout = int(timeout_seconds * strategy["timeout_multiplier"])

                    # CRITICAL: Set stdin=DEVNULL to prevent hanging on interactive prompts
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=strategy_timeout,
                        stdin=subprocess.DEVNULL,  # Don't wait for user input
                    )

                    # If succeeded, break the loop
                    if result.returncode == 0:
                        break

                except subprocess.TimeoutExpired:
                    # Try next strategy on timeout
                    if strategy == export_strategies[-1]:
                        # Last strategy, save the timeout
                        timeout_error = subprocess.TimeoutExpired(
                            cmd=cmd, timeout=strategy_timeout
                        )
                    continue

            # Handle export results
            if timeout_error:
                raise timeout_error

            # Parse osxphotos summary to detect actual failures
            export_count = 0
            missing_count = 0
            error_count = 0

            if result and result.stdout:
                for line in result.stdout.split('\n'):
                    if 'Processed:' in line:
                        # Parse counts from summary line
                        try:
                            match = re.search(r'exported:\s*(\d+).*missing:\s*(\d+).*error:\s*(\d+)', line)
                            if match:
                                export_count = int(match.group(1))
                                missing_count = int(match.group(2))
                                error_count = int(match.group(3))
                        except:
                            pass
                        break

            # Determine if export actually succeeded
            export_failed = (
                result.returncode != 0 or
                export_count == 0 or
                missing_count > 0 or
                error_count > 0
            )

            if export_failed:
                # Export failed - collect error details
                error_parts = []

                if result.returncode != 0:
                    error_parts.append(f"Exit code {result.returncode}")

                if missing_count > 0:
                    error_parts.append(f"Missing {missing_count} (iCloud download failed)")
                elif export_count == 0 and result.returncode == 0:
                    error_parts.append("File not exported (unknown reason)")

                if error_count > 0:
                    error_parts.append(f"Errors: {error_count}")

                if result.stderr:
                    stderr_snippet = result.stderr[:100].strip()
                    if stderr_snippet:
                        error_parts.append(f"stderr: {stderr_snippet}")

                error_msg = " | ".join(error_parts) if error_parts else "Export failed"
                return video.uuid, None, error_msg

            else:
                # Export succeeded - look for the exported file
                exported_path = None
                video_name_base = video.original_filename.rsplit('.', 1)[0]

                for f in export_dir.iterdir():
                    if not f.is_file():
                        continue
                    # Match by filename (osxphotos preserves original name)
                    if f.name == video.original_filename:
                        exported_path = f
                        break
                    # Match by stem (without extension)
                    if f.stem == video_name_base:
                        exported_path = f
                        break
                    # Partial match for truncated names
                    if f.stem.startswith(video_name_base[:15]):
                        exported_path = f
                        break

                if exported_path and exported_path.exists():
                    checksum = compute_sha256(exported_path)
                    return video.uuid, (exported_path, checksum), None
                else:
                    # osxphotos succeeded but file not found - unusual
                    error_msg = "File not found in staging after export"
                    return video.uuid, None, error_msg

        except subprocess.TimeoutExpired as e:
            # Timeout usually means osxphotos is waiting for input or hanging on iCloud download
            error_msg = f"Timeout after {timeout_seconds}s (may be waiting for input or iCloud connection)"
            return video.uuid, None, error_msg

        except Exception as e:
            error_msg = f"Exception: {str(e)[:200]}"
            return video.uuid, None, error_msg

    def export_batch(
        self,
        videos: list[VideoInfo],
        staging_path: Path,
        library_path: Optional[str] = None,
        timeout_seconds: int = 1800,
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

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all video exports as tasks
            future_to_video = {
                executor.submit(
                    self.export_video_task,
                    video,
                    staging_path,
                    library_path,
                    timeout_seconds,
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
                    f"Exporting batch ({self.max_workers} parallel)...",
                    total=len(videos),
                )

                for future in as_completed(future_to_video):
                    video = future_to_video[future]
                    uuid, result, error = future.result()

                    task_elapsed = time.time() - batch_start
                    completed_count += 1
                    remaining_count = len(videos) - completed_count

                    with self.progress_lock:
                        if error:
                            failures[uuid] = error
                            console.print(f"[yellow]✗ {video.original_filename}: {error}[/yellow]")
                        else:
                            results[uuid] = result
                            timing_stats.add_time(task_elapsed / completed_count if completed_count > 0 else 0)
                            console.print(f"[green]✓ {video.original_filename}[/green]")

                        # Update progress description with ETA
                        if remaining_count > 0:
                            estimated_remaining = timing_stats.estimate_remaining(remaining_count)
                            eta_str = timing_stats.format_eta(estimated_remaining)
                            elapsed_sec = time.time() - batch_start
                            progress.update(
                                task,
                                description=f"Exporting ({self.max_workers} parallel) — "
                                           f"{completed_count}/{len(videos)} — ETA: {eta_str}"
                            )
                        else:
                            progress.update(
                                task,
                                description=f"Exporting ({self.max_workers} parallel) — "
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
        # Get available staging space
        disk_usage = shutil.disk_usage(staging_path)
        available_bytes = disk_usage.free
        usable_bytes = available_bytes * 0.70  # 70% safety margin

        # Calculate average video size from remaining videos
        total_size = sum(v.size_bytes for v in remaining_videos)
        avg_size = total_size / len(remaining_videos)

        # Space-based batch size
        space_based = max(1, int(usable_bytes / avg_size))

        # Apply constraints
        batch_size = max(
            1,  # Minimum 1 video
            min(
                space_based,
                max_workers * 2,  # Don't queue too far ahead
                len(remaining_videos)
            )
        )

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
    max_workers: int = 1,  # Default to sequential for backward compatibility
) -> tuple[dict[str, tuple[Path, str]], dict[str, str]]:
    """
    Export videos to staging directory, organized by moment.
    Uses osxphotos CLI with smart strategy selection for iCloud videos.

    IMPORTANT: iCloud-only videos require special handling:
    - Videos are exported from Photos.app's local cache via --use-photos-export
    - This requires the Photos library to be iCloud-synced AND the videos to be
      available in Photos.app
    - If exports fail, verify iCloud Photo Sync is enabled in Photos.app settings

    Args:
        videos: List of VideoInfo objects to export
        staging_path: Path to staging directory
        library_path: Optional path to Photos library
        timeout_seconds: Timeout per video export in seconds
        max_workers: Number of parallel export workers (default: 1 for backward compatibility)

    Returns tuple of (successful_exports, failed_exports)
    - successful_exports: dict of uuid -> (exported_path, sha256_hash)
    - failed_exports: dict of uuid -> error_reason
    """
    staging_path.mkdir(parents=True, exist_ok=True)

    if not videos:
        console.print("[yellow]No videos to export[/yellow]")
        return {}, {}

    # Count iCloud videos and warn users
    icloud_videos = [v for v in videos if not v.is_local]
    icloud_count = len(icloud_videos)

    if icloud_count > 0:
        icloud_pct = int(100 * icloud_count / len(videos))
        console.print(f"\n[yellow]⚠ WARNING: {icloud_count}/{len(videos)} videos ({icloud_pct}%) are iCloud-only[/yellow]")
        console.print("[yellow]Attempting to export with fallback strategies:[/yellow]")
        console.print("[yellow]  1. Try default export (may use local cache)[/yellow]")
        console.print("[yellow]  2. Try PhotoKit interface (may handle iCloud better)[/yellow]")
        console.print("[yellow]  3. Download from iCloud if cache unavailable[/yellow]")
        console.print("\n[cyan]Troubleshooting if exports fail:[/cyan]")
        console.print("[cyan]  • Check iCloud Photo Sync is enabled in Photos.app settings[/cyan]")
        console.print("[cyan]  • Verify you can export videos manually from Photos.app[/cyan]")
        console.print("[cyan]  • If iCloud is full, free up space before exporting[/cyan]")
        console.print("[cyan]  • Try with longer timeout: iphoto archive --export-timeout 3600[/cyan]\n")

    # Use ParallelExporter for parallel or sequential export
    exporter = ParallelExporter(max_workers=max_workers, staging_path=staging_path)
    results, failures = exporter.export_batch(
        videos=videos,
        staging_path=staging_path,
        library_path=library_path,
        timeout_seconds=timeout_seconds,
    )

    if failures:
        console.print(f"\n[green]Successfully exported {len(results)} of {len(videos)} videos[/green]")
        console.print(f"[yellow]Failed to export {len(failures)} videos[/yellow]")
    else:
        console.print(f"\n[green]Exported {len(results)} of {len(videos)} videos[/green]")
    return results, failures
