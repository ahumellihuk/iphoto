"""Interactive video selection UI."""

import shutil
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .models import VideoInfo, MomentGroup, format_bytes
from .scanner import rank_videos, rank_moments

console = Console()

VIDEOS_PER_PAGE = 20
MOMENTS_PER_PAGE = 10


def format_total_size(videos: list[VideoInfo]) -> str:
    """Format total size of videos."""
    return format_bytes(sum(v.size_bytes for v in videos))


def get_free_disk_space(path: Path) -> Optional[float]:
    """Get free disk space in GB for the given path."""
    try:
        stat = shutil.disk_usage(str(path))
        return stat.free / (1024 * 1024 * 1024)
    except Exception:
        return None


def format_threshold(threshold_mb: Optional[float], smart_threshold_mb: Optional[float] = None) -> str:
    """Format threshold value for display."""
    if threshold_mb is not None:
        return f"{threshold_mb:.0f} MB"
    if smart_threshold_mb is not None:
        return f"{smart_threshold_mb:.0f} MB"
    return "-"




def calculate_selection_stats(moments: list[MomentGroup], selected_moment_keys: set[str]) -> dict:
    """Calculate statistics for current selection."""
    selected_moment_objs = [m for m in moments if m.key in selected_moment_keys]

    archived_videos = []
    skipped_videos = []

    for moment in selected_moment_objs:
        archived_videos.extend(moment.videos_above_threshold())
        skipped_videos.extend(moment.videos_below_threshold())

    archived_size_bytes = sum(v.size_bytes for v in archived_videos)
    skipped_size_bytes = sum(v.size_bytes for v in skipped_videos)
    total_size_bytes = archived_size_bytes + skipped_size_bytes

    return {
        'moments_selected': len(selected_moment_objs),
        'videos_archived': len(archived_videos),
        'videos_skipped': len(skipped_videos),
        'archived_size_gb': archived_size_bytes / (1024 ** 3),
        'skipped_size_gb': skipped_size_bytes / (1024 ** 3),
        'total_size_gb': total_size_bytes / (1024 ** 3),
    }


def display_videos(
    videos: list[VideoInfo],
    page: int = 0,
    show_index: bool = True,
) -> None:
    """Display a page of videos in a table."""
    start = page * VIDEOS_PER_PAGE
    end = min(start + VIDEOS_PER_PAGE, len(videos))
    page_videos = videos[start:end]

    table = Table(title=f"Videos {start + 1}-{end} of {len(videos)} (Total: {format_total_size(videos)})")

    if show_index:
        table.add_column("#", style="dim", width=4)
    table.add_column("Date", style="cyan", width=10)
    table.add_column("Size", style="green", width=8)
    table.add_column("Len", width=8)  # Duration/Length
    table.add_column("Moment", style="yellow", width=20)
    table.add_column("Filename", style="dim")

    for i, video in enumerate(page_videos):
        idx = str(start + i + 1) if show_index else ""
        table.add_row(
            idx,
            video.date_created.strftime("%Y-%m-%d"),
            video.size_formatted,
            video.duration_formatted,
            video.moment_name[:20] if video.moment_name else "-",
            video.original_filename,
        )

    console.print(table)


def display_moments(
    moments: list[MomentGroup],
    page: int = 0,
    selected_moments: set[str] = None,
) -> None:
    """Display a page of moments in a table."""
    selected_moments = selected_moments or set()
    start = page * MOMENTS_PER_PAGE
    end = min(start + MOMENTS_PER_PAGE, len(moments))
    page_moments = moments[start:end]

    # Calculate totals across all moments
    total_videos = sum(m.video_count for m in moments)
    total_size = sum(m.total_size_bytes for m in moments)
    total_reclaim = sum(m.space_to_reclaim for m in moments)

    table = Table(
        title=f"Moments {start + 1}-{end} of {len(moments)} "
        f"({total_videos} videos, {format_total_size([v for m in moments for v in m.videos])})"
    )

    table.add_column("#", style="dim", width=4)
    table.add_column("Moment Name", style="cyan", width=28)
    table.add_column("Videos", style="yellow", width=8)
    table.add_column("Total Size", style="dim", width=11)
    table.add_column("To Reclaim", style="green", width=11)
    table.add_column("Smart Threshold", style="magenta", width=15)
    table.add_column("✓", width=2)

    for i, moment in enumerate(page_moments):
        idx = str(start + i + 1)
        selected_mark = "✓" if moment.key in selected_moments else ""

        threshold_display = format_threshold(moment.smart_threshold_mb, moment.threshold_mb)

        table.add_row(
            idx,
            moment.name[:28],
            str(moment.video_count),
            moment.total_size_formatted,
            f"{moment.space_to_reclaim:.2f} GB",
            threshold_display,
            selected_mark,
        )

    console.print(table)


def display_moment_detail(moment: MomentGroup) -> None:
    """Display detailed view of a single moment with its videos."""
    console.print(f"\n[bold cyan]Moment: {moment.name}[/bold cyan]")
    console.print(f"  Total: {moment.video_count} videos, {moment.total_size_formatted}")
    console.print(f"  Date Range: {moment.date_range}")

    threshold_display = format_threshold(moment.threshold_mb, moment.smart_threshold_mb)
    console.print(f"  Threshold: {threshold_display}")

    above = moment.videos_above_threshold()
    below = moment.videos_below_threshold()

    console.print(f"\n[green]Videos above threshold ({len(above)}):[/green]")
    if above:
        display_videos(above, show_index=False)
    else:
        console.print("  [dim]None[/dim]")

    if below:
        console.print(f"\n[yellow]Videos below threshold ({len(below)}) - will be skipped:[/yellow]")
        below_size = sum(v.size_bytes for v in below)
        console.print(f"  [dim]Skipping {len(below)} videos totaling {format_total_size(below)}[/dim]")


def display_summary(videos: list[VideoInfo]) -> None:
    """Display summary statistics."""
    if not videos:
        console.print("[yellow]No videos found matching criteria.[/yellow]")
        return

    total_size = sum(v.size_bytes for v in videos)
    oldest = min(videos, key=lambda v: v.date_created)
    largest = max(videos, key=lambda v: v.size_bytes)
    longest = max(videos, key=lambda v: v.duration_seconds)

    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Total videos: {len(videos)}")
    console.print(f"  Total size: {format_total_size(videos)}")
    console.print(f"  Longest: {longest.duration_formatted} ({longest.original_filename})")
    console.print(f"  Largest: {largest.size_formatted} ({largest.original_filename})")
    console.print(f"  Oldest: {oldest.date_created.strftime('%Y-%m-%d')} ({oldest.age_days} days)")


def interactive_select(
    videos: list[VideoInfo],
    max_size_gb: Optional[float] = None,
) -> list[VideoInfo]:
    """Interactively select videos to archive."""
    if not videos:
        return []

    selected: list[VideoInfo] = []
    page = 0
    total_pages = (len(videos) + VIDEOS_PER_PAGE - 1) // VIDEOS_PER_PAGE

    while True:
        console.clear()
        display_videos(videos, page)

        if selected:
            console.print(f"\n[green]Selected: {len(selected)} videos ({format_total_size(selected)})[/green]")

        console.print("\n[bold]Commands:[/bold]")
        console.print("  [cyan]n[/cyan] - next page, [cyan]p[/cyan] - previous page")
        console.print("  [cyan]1,2,3[/cyan] or [cyan]1-10[/cyan] - select by number(s)")
        console.print("  [cyan]all[/cyan] - select all on page, [cyan]top N[/cyan] - select top N")
        console.print("  [cyan]sort size|duration|age|date[/cyan] - reorder list")
        console.print("  [cyan]clear[/cyan] - clear selection, [cyan]done[/cyan] - proceed, [cyan]q[/cyan] - quit")

        if max_size_gb:
            console.print(f"\n[yellow]Note: Batch limit is {max_size_gb} GB[/yellow]")

        choice = Prompt.ask("\nEnter command").strip().lower()

        if choice == "n" and page < total_pages - 1:
            page += 1
        elif choice == "p" and page > 0:
            page -= 1
        elif choice == "q":
            if Confirm.ask("Quit without archiving?"):
                return []
        elif choice == "done":
            if not selected:
                console.print("[yellow]No videos selected. Select some videos first.[/yellow]")
                Prompt.ask("Press Enter to continue")
            else:
                break
        elif choice == "clear":
            selected = []
        elif choice == "all":
            start = page * VIDEOS_PER_PAGE
            end = min(start + VIDEOS_PER_PAGE, len(videos))
            for v in videos[start:end]:
                if v not in selected:
                    selected.append(v)
        elif choice.startswith("top "):
            try:
                n = int(choice[4:])
                selected = videos[:n]
            except ValueError:
                console.print("[red]Invalid number[/red]")
                Prompt.ask("Press Enter to continue")
        elif choice.startswith("sort "):
            sort_key = choice[5:].strip()
            if sort_key in ("size", "duration", "age", "date"):
                videos = rank_videos(videos, sort_by=sort_key)
                page = 0  # Reset to first page
                selected = []  # Clear selection since indices changed
                console.print(f"[green]Sorted by {sort_key}[/green]")
            else:
                console.print("[red]Invalid sort key. Use: size, duration, age, date[/red]")
                Prompt.ask("Press Enter to continue")
        elif "-" in choice:
            # Range selection: 1-10
            try:
                parts = choice.split("-")
                start_idx = int(parts[0]) - 1
                end_idx = int(parts[1])
                for v in videos[start_idx:end_idx]:
                    if v not in selected:
                        selected.append(v)
            except (ValueError, IndexError):
                console.print("[red]Invalid range[/red]")
                Prompt.ask("Press Enter to continue")
        elif "," in choice or choice.isdigit():
            # Individual selection: 1,2,3 or just 1
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(",")]
                for idx in indices:
                    if 0 <= idx < len(videos):
                        v = videos[idx]
                        if v not in selected:
                            selected.append(v)
            except ValueError:
                console.print("[red]Invalid selection[/red]")
                Prompt.ask("Press Enter to continue")

        # Check batch size limit
        if max_size_gb:
            current_size_gb = sum(v.size_bytes for v in selected) / (1024**3)
            if current_size_gb > max_size_gb:
                console.print(f"[yellow]Warning: Selection exceeds {max_size_gb} GB limit ({current_size_gb:.2f} GB)[/yellow]")
                Prompt.ask("Press Enter to continue")

    # Final confirmation
    console.clear()
    console.print(f"\n[bold]Selected {len(selected)} videos for archiving:[/bold]")
    display_videos(selected, show_index=False)
    console.print(f"\nTotal size: [green]{format_total_size(selected)}[/green]")

    if not Confirm.ask("\nProceed with archiving these videos?"):
        return []

    return selected


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


def interactive_select_moments(
    moments: list[MomentGroup],
    external_path: Optional[Path] = None,
    threshold_mb: Optional[float] = None,
) -> list[VideoInfo]:
    """Interactively select moments, returning filtered videos above threshold.

    Args:
        moments: List of MomentGroup objects
        external_path: Path to external archive (for free space check)
        threshold_mb: Optional global threshold to apply to all moments
                     If None, uses each moment's smart threshold

    Returns:
        List of VideoInfo objects from selected moments, filtered by threshold
    """
    if not moments:
        return []

    # If global threshold provided, apply to all moments; otherwise use per-moment smart thresholds
    if threshold_mb is not None:
        for moment in moments:
            moment.threshold_mb = threshold_mb
    # else: moments already have smart_threshold_mb set, which is used as threshold_mb

    # Get free disk space
    free_space_gb = None
    if external_path:
        free_space_gb = get_free_disk_space(external_path)

    selected_moments: set[str] = set()
    page = 0
    total_pages = (len(moments) + MOMENTS_PER_PAGE - 1) // MOMENTS_PER_PAGE

    while True:
        console.clear()
        display_moments(moments, page, selected_moments)

        _display_selection_summary(moments, selected_moments, free_space_gb)
        _display_moment_commands(threshold_mb)

        choice = Prompt.ask("\nEnter command").strip().lower()

        # Handle commands
        if choice == "n" and page < total_pages - 1:
            page += 1
        elif choice == "p" and page > 0:
            page -= 1
        elif choice == "q":
            if Confirm.ask("Quit without archiving?"):
                return []
        elif choice == "done":
            if not selected_moments:
                console.print("[yellow]No moments selected.[/yellow]")
                Prompt.ask("Press Enter to continue")
            else:
                break
        elif choice == "clear":
            selected_moments.clear()
        elif choice == "preview":
            console.clear()
            selected_moment_objs = [m for m in moments if m.key in selected_moments]
            filtered_videos = []
            for moment in selected_moment_objs:
                filtered_videos.extend(moment.videos_above_threshold())

            # Safe formatting for threshold in preview
            if threshold_mb is not None:
                filter_desc = f"after {threshold_mb:.0f}MB filter"
            else:
                filter_desc = "using per-moment smart thresholds"
            console.print(f"\n[bold]Preview: Videos to Archive ({filter_desc})[/bold]")
            console.print(f"Total: {len(filtered_videos)} videos\n")

            display_videos(filtered_videos, show_index=False)
            console.print("\n[cyan]Press Enter to return to moment selection[/cyan]")
            Prompt.ask("")
        elif choice.startswith("threshold "):
            try:
                new_threshold = float(choice[10:])
                threshold_mb = new_threshold
                for moment in moments:
                    moment.threshold_mb = new_threshold
                console.print(f"[green]Global threshold set to {new_threshold:.0f}MB (overrides smart thresholds)[/green]")
                Prompt.ask("Press Enter to continue")
            except ValueError:
                console.print("[red]Invalid threshold value[/red]")
                Prompt.ask("Press Enter to continue")
        elif choice == "reset":
            threshold_mb = None
            for moment in moments:
                moment.threshold_mb = moment.smart_threshold_mb
            console.print("[green]Reset to smart per-moment thresholds[/green]")
            Prompt.ask("Press Enter to continue")
        elif choice.startswith("expand "):
            try:
                idx = int(choice[7:]) - 1
                if 0 <= idx < len(moments):
                    console.clear()
                    display_moment_detail(moments[idx])
                    Prompt.ask("\nPress Enter to continue")
                else:
                    console.print("[red]Invalid moment number[/red]")
                    Prompt.ask("Press Enter to continue")
            except ValueError:
                console.print("[red]Invalid moment number[/red]")
                Prompt.ask("Press Enter to continue")
        elif choice.startswith("sort "):
            sort_key = choice[5:].strip()
            if sort_key in ("size", "count", "date"):
                moments = rank_moments(moments, sort_by=sort_key)
                page = 0
                selected_moments.clear()
                console.print(f"[green]Sorted by {sort_key}[/green]")
                Prompt.ask("Press Enter to continue")
            else:
                console.print("[red]Invalid sort key. Use: size, count, date[/red]")
                Prompt.ask("Press Enter to continue")
        elif "-" in choice:
            # Range selection: 1-10
            try:
                parts = choice.split("-")
                start_idx = int(parts[0]) - 1
                end_idx = int(parts[1])
                for moment in moments[start_idx:end_idx]:
                    selected_moments.add(moment.key)
            except (ValueError, IndexError):
                console.print("[red]Invalid range[/red]")
                Prompt.ask("Press Enter to continue")
        elif "," in choice or choice.isdigit():
            # Individual selection: 1,2,3 or just 1
            try:
                indices = [int(x.strip()) - 1 for x in choice.split(",")]
                for idx in indices:
                    if 0 <= idx < len(moments):
                        selected_moments.add(moments[idx].key)
            except ValueError:
                console.print("[red]Invalid selection[/red]")
                Prompt.ask("Press Enter to continue")


    return _confirm_moment_selection(moments, selected_moments, threshold_mb)
