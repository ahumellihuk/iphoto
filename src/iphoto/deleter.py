"""Delete videos from Photos library via album-based workflow.

AppleScript's `delete` command fails with -10000 (sandboxing restriction).
Instead, we create a temporary album containing the archived videos so the
user can select-all and delete from Photos.app UI in one step.
"""

import photoscript
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm

from .models import VideoInfo, filter_ambiguous_filenames

console = Console()

ALBUM_NAME = "iphoto - Ready to Delete"


def delete_from_photos(
    videos: list[VideoInfo],
    dry_run: bool = False,
    timeout_seconds: int = 120,
    allow_ambiguous: bool = False,
) -> tuple[list[str], dict[str, str]]:
    """
    Stage videos for deletion by adding them to a dedicated album.

    The user then selects all in the album in Photos.app and deletes manually.
    Videos go to "Recently Deleted" and can be recovered for 30 days.

    Returns tuple of (staged_uuids, failed)
    """
    if not videos:
        return [], {}

    videos, failures = filter_ambiguous_filenames(videos, allow_ambiguous)
    if failures:
        console.print(
            f"[yellow]Skipped {len(failures)} videos with duplicate filenames.[/yellow]"
        )

    if not videos:
        return [], failures

    console.print(f"\n[bold]Staging {len(videos)} videos for deletion...[/bold]")

    if dry_run:
        console.print("[cyan][DRY RUN] Would add to album for deletion:[/cyan]")
        for v in videos:
            console.print(f"  [dim]- {v.original_filename} ({v.size_formatted})[/dim]")
        return [v.uuid for v in videos], failures

    try:
        lib = photoscript.PhotosLibrary()
        lib.activate()

        # Create or get the album
        album = None
        try:
            album = lib.album(ALBUM_NAME)
        except Exception:
            pass
        if album is None:
            album = lib.create_album(ALBUM_NAME)
            console.print(f"[dim]Created album '{ALBUM_NAME}'[/dim]")

        staged: list[str] = []

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Adding to delete album...", total=len(videos))

            for video in videos:
                progress.update(task, description=f"Adding: {video.original_filename[:40]}...")
                try:
                    photo = photoscript.Photo(video.uuid)
                    album.add([photo])
                    staged.append(video.uuid)
                except Exception as e:
                    failures[video.uuid] = str(e)
                    console.print(f"  [yellow]Could not add {video.original_filename}: {e}[/yellow]")
                progress.advance(task)

        console.print(f"\n[green]Added {len(staged)} videos to album '{ALBUM_NAME}'[/green]")
        console.print(f"\n[bold cyan]To complete deletion:[/bold cyan]")
        console.print(f"  1. Open Photos.app > Albums > '{ALBUM_NAME}'")
        console.print(f"  2. Select All (Cmd+A)")
        console.print(f"  3. Right-click > Delete {len(staged)} Videos")
        console.print(f"  4. Items go to Recently Deleted (30-day recovery)")

        return staged, failures

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        for v in videos:
            if v.uuid not in failures:
                failures[v.uuid] = str(e)
        return [], failures
