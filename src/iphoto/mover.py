"""Move exported videos to external archive with verification."""

import shutil
from pathlib import Path

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)

from .exporter import compute_sha256
from .models import format_bytes

console = Console()

DEFAULT_EXTERNAL_PATH = Path("/Volumes/AcerFA200/Photos-archive")


def check_external_mounted(external_path: Path) -> bool:
    """Check if external drive is mounted."""
    # Check if the volume exists
    if not external_path.parent.exists():
        return False

    # For /Volumes paths, check if the volume is mounted
    if str(external_path).startswith("/Volumes/"):
        volume_name = external_path.parts[2] if len(external_path.parts) > 2 else None
        if volume_name:
            volume_path = Path("/Volumes") / volume_name
            return volume_path.exists() and volume_path.is_dir()

    return external_path.parent.exists()


def get_available_space(path: Path) -> int:
    """Get available space in bytes at the given path."""
    import os

    # Find the nearest existing parent
    check_path = path
    while not check_path.exists() and check_path.parent != check_path:
        check_path = check_path.parent

    if check_path.exists():
        stat = os.statvfs(check_path)
        return stat.f_frsize * stat.f_bavail
    return 0


def move_to_archive(
    exported: dict[str, tuple[Path, str]],
    external_path: Path = DEFAULT_EXTERNAL_PATH,
    verify: bool = True,
) -> dict[str, Path]:
    """
    Move exported videos to external archive with verification.

    Args:
        exported: Dict of uuid -> (source_path, expected_checksum)
        external_path: Destination archive directory
        verify: Whether to verify checksums after copy

    Returns:
        Dict of uuid -> archived_path for successfully archived files
    """
    # Check external is mounted
    if not check_external_mounted(external_path):
        console.print(f"[red]Error: External drive not mounted at {external_path}[/red]")
        console.print("[yellow]Please connect and mount the external drive, then try again.[/yellow]")
        return {}

    # Check available space
    total_size = sum(path.stat().st_size for path, _ in exported.values() if path.exists())
    available = get_available_space(external_path)

    if total_size > available:
        console.print("[red]Error: Not enough space on external drive[/red]")
        console.print(f"  Required: {format_bytes(total_size)}")
        console.print(f"  Available: {format_bytes(available)}")
        return {}

    external_path.mkdir(parents=True, exist_ok=True)
    archived: dict[str, Path] = {}

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        console=console,
    ) as progress:
        move_task = progress.add_task(
            "Moving to archive...",
            total=len(exported),
        )

        for uuid, (source_path, expected_checksum) in exported.items():
            if not source_path.exists():
                console.print(f"[yellow]Warning: Source file missing: {source_path}[/yellow]")
                progress.advance(move_task)
                continue

            # Preserve folder structure (moment folders)
            relative_path = source_path.relative_to(source_path.parent.parent)
            dest_path = external_path / relative_path
            dest_path.parent.mkdir(parents=True, exist_ok=True)

            progress.update(
                move_task,
                description=f"Moving: {source_path.name[:40]}...",
            )

            try:
                # Copy file (not move, so we can verify before deleting)
                shutil.copy2(source_path, dest_path)

                # Verify checksum if requested
                if verify:
                    progress.update(
                        move_task,
                        description=f"Verifying: {source_path.name[:40]}...",
                    )
                    actual_checksum = compute_sha256(dest_path)

                    if actual_checksum != expected_checksum:
                        console.print(f"[red]Checksum mismatch for {source_path.name}![/red]")
                        console.print(f"  Expected: {expected_checksum}")
                        console.print(f"  Got: {actual_checksum}")
                        dest_path.unlink()  # Remove corrupted copy
                        progress.advance(move_task)
                        continue

                # Success - remove from staging
                source_path.unlink()
                archived[uuid] = dest_path

            except Exception as e:
                console.print(f"[red]Error moving {source_path.name}: {e}[/red]")

            progress.advance(move_task)

    console.print(f"\n[green]Archived {len(archived)} of {len(exported)} videos to {external_path}[/green]")
    return archived


def cleanup_staging(staging_path: Path) -> None:
    """Remove empty directories from staging."""
    if not staging_path.exists():
        return

    # Remove empty moment folders
    for folder in staging_path.iterdir():
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()

    # Remove staging folder if empty
    if not any(staging_path.iterdir()):
        staging_path.rmdir()
        console.print("[dim]Cleaned up staging directory[/dim]")
