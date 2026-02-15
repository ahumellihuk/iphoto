"""Export videos from Photos library using AppleScript."""

import hashlib
import shutil
import time
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
)

from .applescript_exporter import activate_photos, export_via_applescript
from .models import VideoInfo, filter_ambiguous_filenames

console = Console()


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
    for char in ["/", "\\", ":", "*", "?", '"', "<", ">", "|"]:
        name = name.replace(char, "-")
    return name.strip()


def _export_single_video(
    video: VideoInfo,
    staging_path: Path,
    timeout_seconds: int = 1800,
    icloud_timeout_seconds: int | None = None,
) -> tuple[str, tuple[Path, str] | None, str | None]:
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


def _export_batch(
    videos: list[VideoInfo],
    staging_path: Path,
    timeout_seconds: int = 1800,
    icloud_timeout_seconds: int | None = None,
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
                video,
                staging_path,
                timeout_seconds,
                icloud_timeout_seconds,
            )

            if error:
                failures[uuid] = error
                console.print(f"[yellow]✗ {video.original_filename}: {error}[/yellow]")
            else:
                results[uuid] = result
                console.print(f"[green]✓ {video.original_filename}[/green]")

            progress.update(task, description=f"Exporting — {i + 1}/{len(videos)}")
            progress.advance(task)

    total_time = time.time() - batch_start
    success_rate = len(results) / len(videos) * 100 if videos else 0
    console.print(
        f"\n[dim]Batch summary: {len(results)}/{len(videos)} exported "
        f"in {total_time:.1f}s ({success_rate:.0f}% success)[/dim]"
    )

    return results, failures


def calculate_batch_size(
    staging_path: Path,
    remaining_videos: list[VideoInfo],
    override_size: int | None = None,
) -> int:
    """Calculate optimal batch size based on available staging space.

    Strategy:
    - Get available staging space with 70% safety margin
    - Calculate average video size from remaining videos
    - Compute how many videos fit in available space
    - Minimum 1 video, maximum remaining video count

    Args:
        staging_path: Path to staging directory
        remaining_videos: List of VideoInfo objects to process
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

        available_gb = usable_bytes / (1024**3)
        total_batch_size_gb = (batch_size * avg_size) / (1024**3)

        console.print(
            f"[dim]Batch size: {batch_size} videos ({total_batch_size_gb:.2f}/{available_gb:.2f} GB available)[/dim]"
        )
        return batch_size

    except Exception as e:
        console.print(f"[yellow]Warning: Could not calculate batch size: {e}[/yellow]")
        return min(len(remaining_videos), 5)


def export_videos(
    videos: list[VideoInfo],
    staging_path: Path,
    library_path: str | None = None,
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

    videos, pre_failures = filter_ambiguous_filenames(videos, allow_ambiguous)
    if pre_failures:
        console.print(
            f"[yellow]Skipped {len(pre_failures)} videos with duplicate filenames."
            " Use --allow-ambiguous to override.[/yellow]"
        )

    # Count iCloud videos and inform users
    icloud_videos = [v for v in videos if not v.is_local]
    icloud_count = len(icloud_videos)

    if icloud_count > 0:
        icloud_pct = int(100 * icloud_count / len(videos))
        console.print(f"\n[cyan](i) {icloud_count}/{len(videos)} videos ({icloud_pct}%) are iCloud-only[/cyan]")
        console.print("[cyan]Photos.app will download these automatically during export.[/cyan]")
        console.print("\n[dim]Troubleshooting if exports fail:[/dim]")
        console.print("[dim]  • Ensure iCloud Photo Library is enabled in Photos.app[/dim]")
        console.print("[dim]  • Verify Photos.app is running and not paused for sync[/dim]")
        console.print("[dim]  • Check that videos are accessible in Photos.app[/dim]\n")

    # Export sequentially (AppleScript is inherently sequential)
    icloud_timeout_seconds = max(timeout_seconds, 3600)
    results, failures = _export_batch(
        videos=videos,
        staging_path=staging_path,
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
