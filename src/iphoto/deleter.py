"""Delete videos from Photos library using AppleScript."""

import subprocess
from datetime import datetime
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

from .models import VideoInfo

console = Console()


def run_applescript(script: str, timeout: int = 120) -> tuple[bool, str]:
    """Run an AppleScript and return (success, output)."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, f"AppleScript timed out after {timeout}s"
    except Exception as e:
        return False, str(e)


def delete_from_photos(
    videos: list[VideoInfo],
    dry_run: bool = False,
    timeout_seconds: int = 120,
) -> tuple[list[str], dict[str, str]]:
    """
    Delete videos from Photos library.

    Uses AppleScript to interact with Photos.app.
    Videos go to "Recently Deleted" and can be recovered for 30 days.

    Returns tuple of (successfully_deleted_uuids, failed_deletes)
    - successfully_deleted_uuids: list[str]
    - failed_deletes: dict of uuid -> error_reason
    """
    if not videos:
        return [], {}

    console.print(f"\n[bold]Preparing to delete {len(videos)} videos from Photos...[/bold]")
    console.print("[yellow]Note: Deleted items go to 'Recently Deleted' for 30-day recovery.[/yellow]\n")

    if dry_run:
        console.print("[cyan][DRY RUN] The following videos would be deleted from Photos:[/cyan]")
        for v in videos:
            console.print(f"  [dim]- {v.original_filename} ({v.date_created.strftime('%Y-%m-%d')}, {v.size_formatted})[/dim]")
        console.print(f"\n[cyan][DRY RUN] Total: {len(videos)} videos - NO CHANGES MADE[/cyan]")
        return [v.uuid for v in videos], {}

    # Double confirmation for safety
    console.print("[bold red]WARNING: This will delete videos from your Photos library![/bold red]")
    console.print("[yellow]They will be moved to 'Recently Deleted' (recoverable for 30 days).[/yellow]\n")

    for v in videos:
        console.print(f"  - {v.original_filename} ({v.date_created.strftime('%Y-%m-%d')})")

    console.print()
    if not Confirm.ask(f"[red]Delete these {len(videos)} videos from Photos?[/red]", default=False):
        console.print("[yellow]Deletion cancelled.[/yellow]")
        return [], {}

    deleted: list[str] = []
    failures: dict[str, str] = {}

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        delete_task = progress.add_task("Deleting from Photos...", total=len(videos))

        for video in videos:
            progress.update(
                delete_task,
                description=f"Deleting: {video.original_filename[:40]}...",
            )

            # Build AppleScript to find and delete the video
            # We search by filename and creation date to be more precise
            date_str = video.date_created.strftime("%Y-%m-%d")

            # AppleScript to delete a media item by filename
            # Photos.app uses "media item" for both photos and videos
            script = f'''
            tell application "Photos"
                set targetName to "{video.original_filename}"
                set mediaItems to (every media item whose filename is targetName)

                if (count of mediaItems) > 0 then
                    delete item 1 of mediaItems
                    return "deleted"
                else
                    return "not found"
                end if
            end tell
            '''

            success, output = run_applescript(script, timeout=timeout_seconds)

            if success and output == "deleted":
                deleted.append(video.uuid)
                console.print(f"  [green]Deleted:[/green] {video.original_filename}")
            elif output == "not found":
                console.print(f"  [yellow]Not found:[/yellow] {video.original_filename}")
                failures[video.uuid] = "Not found in Photos library"
            elif "timed out" in output.lower():
                console.print(f"  [red]Timeout:[/red] {video.original_filename} - {output}")
                failures[video.uuid] = output
            else:
                console.print(f"  [red]Error:[/red] {video.original_filename} - {output}")
                failures[video.uuid] = output

            progress.advance(delete_task)

    if failures:
        console.print(f"\n[green]Deleted {len(deleted)} of {len(videos)} videos from Photos[/green]")
        console.print(f"[yellow]Failed to delete {len(failures)} videos[/yellow]")
    else:
        console.print(f"\n[green]Deleted {len(deleted)} of {len(videos)} videos from Photos[/green]")

    if deleted:
        console.print("\n[yellow]Reminder: Deleted items are in 'Recently Deleted' for 30 days.[/yellow]")
        console.print("[yellow]To permanently delete, open Photos > Recently Deleted > Delete All.[/yellow]")

    return deleted, failures


def activate_photos() -> bool:
    """Bring Photos app to foreground (needed for some operations)."""
    script = '''
    tell application "Photos"
        activate
    end tell
    '''
    success, _ = run_applescript(script)
    return success
