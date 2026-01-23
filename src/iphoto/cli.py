"""CLI for iphoto - Apple Photos video archiver."""

import json
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from uuid import uuid4

import typer
from rich.console import Console
from rich.prompt import Confirm

from . import __version__
from .deleter import delete_from_photos
from .exporter import export_videos, calculate_batch_size
from .models import BatchState, VideoInfo, MomentGroup, SessionState, BatchProgress
from .mover import DEFAULT_EXTERNAL_PATH, cleanup_staging, move_to_archive
from .scanner import rank_videos, scan_videos, group_by_moment
from .selector import display_summary, display_videos, interactive_select, interactive_select_moments, display_moments

app = typer.Typer(
    name="iphoto",
    help="Archive old/large videos from Apple Photos to external storage.",
    no_args_is_help=True,
)
console = Console()

DEFAULT_STAGING = Path.home() / "PhotosStaging"
STATE_FILE = Path.home() / ".iphoto_state.json"
SESSION_FILE = Path.home() / ".iphoto_session.json"


def save_state(state: BatchState) -> None:
    """Save batch state for resumption."""
    data = {
        "batch_id": state.batch_id,
        "staging_path": str(state.staging_path),
        "external_path": str(state.external_path),
        "selected_uuids": state.selected_uuids,
        "exported_uuids": state.exported_uuids,
        "archived_uuids": state.archived_uuids,
        "deleted_uuids": state.deleted_uuids,
        "checksums": state.checksums,
        "created_at": state.created_at.isoformat(),
        "failed_exports": state.failed_exports,
        "failed_deletes": state.failed_deletes,
    }
    STATE_FILE.write_text(json.dumps(data, indent=2))


def load_state() -> Optional[BatchState]:
    """Load batch state if exists."""
    if not STATE_FILE.exists():
        return None
    try:
        data = json.loads(STATE_FILE.read_text())
        return BatchState(
            batch_id=data["batch_id"],
            staging_path=Path(data["staging_path"]),
            external_path=Path(data["external_path"]),
            selected_uuids=data["selected_uuids"],
            exported_uuids=data["exported_uuids"],
            archived_uuids=data["archived_uuids"],
            deleted_uuids=data["deleted_uuids"],
            checksums=data["checksums"],
            created_at=datetime.fromisoformat(data["created_at"]),
            failed_exports=data.get("failed_exports", {}),
            failed_deletes=data.get("failed_deletes", {}),
        )
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load state: {e}[/yellow]")
        return None


def clear_state() -> None:
    """Clear saved batch state."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()


def save_session(session: SessionState) -> None:
    """Save multi-batch session state for resumption."""
    try:
        data = {
            "session_id": session.session_id,
            "staging_path": str(session.staging_path),
            "external_path": str(session.external_path),
            "created_at": session.created_at.isoformat(),
            "max_workers": session.max_workers,
            "threshold_mb": session.threshold_mb,
            "all_selected_uuids": session.all_selected_uuids,
            "remaining_uuids": session.remaining_uuids,
            "current_batch_number": session.current_batch_number,
            "total_exported": session.total_exported,
            "total_archived": session.total_archived,
            "total_deleted": session.total_deleted,
            "total_failed_exports": session.total_failed_exports,
            "total_failed_deletes": session.total_failed_deletes,
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
                for b in session.batches
            ],
        }
        SESSION_FILE.write_text(json.dumps(data, indent=2))
    except Exception as e:
        console.print(f"[yellow]Warning: Could not save session: {e}[/yellow]")


def load_session() -> Optional[SessionState]:
    """Load multi-batch session state for resumption."""
    if not SESSION_FILE.exists():
        return None

    try:
        data = json.loads(SESSION_FILE.read_text())
        session = SessionState(
            session_id=data["session_id"],
            staging_path=Path(data["staging_path"]),
            external_path=Path(data["external_path"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            max_workers=data["max_workers"],
            threshold_mb=data.get("threshold_mb"),
            all_selected_uuids=data["all_selected_uuids"],
            remaining_uuids=data["remaining_uuids"],
            current_batch_number=data["current_batch_number"],
            total_exported=data["total_exported"],
            total_archived=data["total_archived"],
            total_deleted=data["total_deleted"],
            total_failed_exports=data.get("total_failed_exports", 0),
            total_failed_deletes=data.get("total_failed_deletes", 0),
        )

        # Reconstruct batches
        for batch_data in data.get("batches", []):
            batch = BatchProgress(
                batch_number=batch_data["batch_number"],
                selected_uuids=batch_data.get("selected_uuids", []),
                exported_uuids=batch_data.get("exported_uuids", []),
                archived_uuids=batch_data.get("archived_uuids", []),
                deleted_uuids=batch_data.get("deleted_uuids", []),
                failed_exports=batch_data.get("failed_exports", {}),
                failed_deletes=batch_data.get("failed_deletes", {}),
                checksums=batch_data.get("checksums", {}),
                started_at=datetime.fromisoformat(batch_data["started_at"]),
                completed_at=datetime.fromisoformat(batch_data["completed_at"]) if batch_data.get("completed_at") else None,
            )
            session.batches.append(batch)

        return session
    except Exception as e:
        console.print(f"[yellow]Warning: Could not load session: {e}[/yellow]")
        return None


def clear_session() -> None:
    """Clear saved multi-batch session state."""
    if SESSION_FILE.exists():
        SESSION_FILE.unlink()


@app.command()
def scan(
    min_age_days: Optional[int] = typer.Option(
        None, "--min-age", "-a", help="Minimum age in days"
    ),
    min_size_mb: Optional[float] = typer.Option(
        None, "--min-size", "-s", help="Minimum size in MB"
    ),
    sort_by: str = typer.Option(
        "size", "--sort", help="Sort by: size, duration, age, date"
    ),
    limit: int = typer.Option(
        50, "--limit", "-n", help="Number of videos to display"
    ),
    group_by: str = typer.Option(
        "flat", "--group-by", help="Grouping: flat or moment"
    ),
    library: Optional[str] = typer.Option(
        None, "--library", "-l", help="Path to Photos library"
    ),
) -> None:
    """Scan Photos library and display archivable videos."""
    console.print("[bold]Scanning Photos library for videos...[/bold]\n")

    videos = scan_videos(
        min_age_days=min_age_days,
        min_size_mb=min_size_mb,
        library_path=library,
    )

    if not videos:
        console.print("[yellow]No videos found matching criteria.[/yellow]")
        return

    # Show iCloud status
    icloud_count = len([v for v in videos if not v.is_local])
    if icloud_count:
        console.print(f"[cyan]{icloud_count} videos in iCloud (will be downloaded during export)[/cyan]\n")

    if group_by == "moment":
        moments = group_by_moment(videos)
        console.print(f"[bold]Found {len(moments)} moments:[/bold]\n")
        display_moments(moments[:limit])
    else:
        videos = rank_videos(videos, sort_by=sort_by)
        display_summary(videos)

        console.print(f"\n[bold]Top {min(limit, len(videos))} videos:[/bold]")
        display_videos(videos[:limit])

    console.print(f"\n[dim]Use 'iphoto archive' to start archiving.[/dim]")


@app.command()
def archive(
    staging: Path = typer.Option(
        DEFAULT_STAGING, "--staging", "-s", help="Local staging directory"
    ),
    external: Path = typer.Option(
        DEFAULT_EXTERNAL_PATH, "--external", "-e", help="External archive directory"
    ),
    min_age_days: Optional[int] = typer.Option(
        None, "--min-age", "-a", help="Minimum age in days"
    ),
    min_size_mb: Optional[float] = typer.Option(
        None, "--min-size", "-m", help="Minimum size in MB"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-n", help="Preview without making changes"
    ),
    no_delete: bool = typer.Option(
        False, "--no-delete", help="Archive but don't delete from Photos"
    ),
    threshold_mb: Optional[float] = typer.Option(
        None, "--threshold", "-t", help="Size threshold in MB (None = auto-suggest based on distribution)"
    ),
    use_moments: bool = typer.Option(
        True, "--use-moments/--no-moments", help="Use moment-based grouping (default: True)"
    ),
    library: Optional[str] = typer.Option(
        None, "--library", "-l", help="Path to Photos library"
    ),
    export_timeout: int = typer.Option(
        1800, "--export-timeout", help="Timeout per video export in seconds (default: 30min for iCloud downloads)"
    ),
    delete_timeout: int = typer.Option(
        120, "--delete-timeout", help="Timeout per video deletion in seconds (default: 2min)"
    ),
    max_workers: int = typer.Option(
        1, "--workers", "-w", help="Number of parallel export workers (default: 1)"
    ),
    batch_size: Optional[int] = typer.Option(
        None, "--batch-size", help="Override automatic batch sizing (optional)"
    ),
    continuous: bool = typer.Option(
        True, "--continuous/--interactive", help="Process all batches without prompting (default: True)"
    ),
) -> None:
    """Batch-based archive workflow: auto-size batches, export parallel, archive, delete."""
    console.print("[bold]iphoto - Video Archive Tool[/bold]\n")

    if dry_run:
        console.print("[bold cyan]=" * 50)
        console.print("[bold cyan]DRY RUN MODE - No changes will be made[/bold cyan]")
        console.print("[bold cyan]=" * 50 + "\n")

    # Check for existing session
    existing_session = load_session()
    if existing_session and not existing_session.is_complete:
        console.print(f"[bold cyan]Found interrupted session {existing_session.session_id}[/bold cyan]")
        console.print(f"  Progress: {existing_session.total_deleted}/{len(existing_session.all_selected_uuids)} videos completed")
        console.print(f"  Batches completed: {existing_session.batches_completed}")
        if Confirm.ask("Resume this session?"):
            # Resume from session - session will be updated and saved
            all_videos = scan_videos(
                min_age_days=min_age_days,
                min_size_mb=min_size_mb,
                library_path=library,
            )
            session = existing_session
        else:
            if Confirm.ask("Clear this session and start fresh?"):
                clear_session()
            return
    else:
        # New session - scan and select
        console.print("[bold]Step 1:[/bold] Scanning Photos library...\n")
        all_videos = scan_videos(
            min_age_days=min_age_days,
            min_size_mb=min_size_mb,
            library_path=library,
        )

        if not all_videos:
            console.print("[yellow]No videos found matching criteria.[/yellow]")
            return

        # Show iCloud status
        icloud_count = len([v for v in all_videos if not v.is_local])
        if icloud_count:
            console.print(f"[cyan]{icloud_count} videos in iCloud (will use local cache for export)[/cyan]\n")

        all_videos = rank_videos(all_videos, sort_by="size")
        display_summary(all_videos)

        # Step 2: Interactive selection
        console.print("\n[bold]Step 2:[/bold] Select videos to archive...\n")

        if use_moments and len(all_videos) > 0:
            # Moment-based workflow
            moments = group_by_moment(all_videos)
            console.print(f"[cyan]Grouped into {len(moments)} moments[/cyan]\n")
            selected = interactive_select_moments(
                moments,
                external_path=external,
                threshold_mb=threshold_mb
            )
        else:
            # Traditional flat workflow
            all_videos = rank_videos(all_videos, sort_by="size")
            selected = interactive_select(all_videos, max_size_gb=None)

        if not selected:
            console.print("[yellow]No videos selected. Exiting.[/yellow]")
            return

        # Create new session
        session = SessionState(
            staging_path=staging,
            external_path=external,
            all_selected_uuids=[v.uuid for v in selected],
            remaining_uuids=[v.uuid for v in selected],
            max_workers=max_workers,
            threshold_mb=threshold_mb,
        )
        save_session(session)
        console.print(f"\n[cyan]Created session {session.session_id} with {len(selected)} videos[/cyan]\n")

    # Build video lookup for session
    all_videos_map = {v.uuid: v for v in all_videos}

    # Batch processing loop with timing
    batch_num = session.current_batch_number + 1
    session_start_time = time.time()
    batch_times = []  # Track time per batch for ETA

    while session.remaining_uuids:
        batch_start_time = time.time()

        # Calculate batch size
        remaining_videos = [all_videos_map[uuid] for uuid in session.remaining_uuids]
        calculated_batch_size = calculate_batch_size(
            staging_path=staging,
            remaining_videos=remaining_videos,
            max_workers=max_workers,
            override_size=batch_size,
        )

        # Create batch
        batch_uuids = session.remaining_uuids[:calculated_batch_size]
        batch_videos = [all_videos_map[uuid] for uuid in batch_uuids]

        # Safety check: verify batch actually fits in staging space
        actual_batch_size_bytes = sum(v.size_bytes for v in batch_videos)
        disk_usage = shutil.disk_usage(staging)
        usable_bytes = disk_usage.free * 0.70

        # If batch exceeds available space, reduce it
        if actual_batch_size_bytes > usable_bytes:
            # Reduce batch size to fit available space
            batch_videos = []
            for uuid in session.remaining_uuids:
                video = all_videos_map[uuid]
                current_size = sum(v.size_bytes for v in batch_videos)
                if current_size + video.size_bytes <= usable_bytes:
                    batch_videos.append(video)
                else:
                    break

            if not batch_videos:
                # Even one video won't fit - critical space issue
                console.print(f"[red]✗ CRITICAL: Largest remaining video ({video.size_bytes / (1024**3):.2f} GB) "
                             f"exceeds available space ({usable_bytes / (1024**3):.2f} GB)[/red]")
                console.print("[red]Cannot proceed. Free up staging space and retry.[/red]")
                return

            batch_uuids = [v.uuid for v in batch_videos]
            console.print(f"[yellow]⚠ Batch size adjusted from {calculated_batch_size} to {len(batch_videos)} "
                         f"to fit available staging space[/yellow]")

        batch = session.add_batch(batch_num, batch_uuids)
        total_size_gb = sum(v.size_bytes for v in batch_videos) / (1024 ** 3)
        estimated_batches = len(session.all_selected_uuids) // calculated_batch_size + 1
        console.print(f"\n[bold cyan]═══ Batch {batch_num}/{estimated_batches} ═══[/bold cyan]")
        console.print(f"Videos: {len(batch_videos)} | Size: {total_size_gb:.2f} GB")
        console.print(f"Session: {session.total_deleted}/{len(session.all_selected_uuids)} videos ({session.progress_pct}%)\n")

        # === Phase 1: Parallel Export ===
        phase1_start = time.time()
        console.print(f"[bold]Phase 1:[/bold] Exporting {len(batch_videos)} videos...")
        if not dry_run:
            exported, export_failures = export_videos(
                batch_videos,
                staging,
                library_path=library,
                timeout_seconds=export_timeout,
                max_workers=max_workers
            )
            batch.exported_uuids = list(exported.keys())
            batch.failed_exports = export_failures
            batch.checksums = {uuid: cs for uuid, (_, cs) in exported.items()}
            session.total_exported += len(exported)
            session.total_failed_exports += len(export_failures)
            save_session(session)
        else:
            console.print("[cyan][DRY RUN] Would export the following videos:[/cyan]")
            from .selector import format_total_size
            for v in batch_videos:
                console.print(f"  [dim]- {v.original_filename} ({v.size_formatted})[/dim]")
            console.print(f"  [cyan]Total: {format_total_size(batch_videos)}[/cyan]")
            exported = {v.uuid: (staging / v.original_filename, "dry") for v in batch_videos}
            export_failures = {}

        if not exported:
            console.print("[red]Batch export failed. Stopping.[/red]")
            save_session(session)
            return

        phase1_time = time.time() - phase1_start
        console.print(f"[green]✓ Exported: {len(exported)} videos in {phase1_time:.1f}s[/green]")
        if export_failures:
            console.print(f"[yellow]⚠ Failed: {len(export_failures)} videos[/yellow]")

        # === Phase 2: Archive to External ===
        phase2_start = time.time()
        console.print(f"\n[bold]Phase 2:[/bold] Archiving to external drive...")

        if not dry_run:
            archived = move_to_archive(exported, external)
            batch.archived_uuids = list(archived.keys())
            session.total_archived += len(archived)
            save_session(session)
            cleanup_staging(staging)
        else:
            console.print(f"[cyan][DRY RUN] Would archive {len(exported)} videos[/cyan]")
            archived = exported

        if not archived:
            console.print("[red]Archive failed. Stopping.[/red]")
            save_session(session)
            return

        phase2_time = time.time() - phase2_start
        console.print(f"[green]✓ Archived: {len(archived)} videos in {phase2_time:.1f}s[/green]")

        # === Phase 3: Delete from Photos ===
        phase3_time = 0
        if not no_delete:
            phase3_start = time.time()
            console.print(f"\n[bold]Phase 3:[/bold] Deleting from Photos...")

            archived_videos = [v for v in batch_videos if v.uuid in archived]
            deleted, delete_failures = delete_from_photos(
                archived_videos, dry_run=dry_run, timeout_seconds=delete_timeout
            )

            if not dry_run:
                batch.deleted_uuids = deleted
                batch.failed_deletes = delete_failures
                session.total_deleted += len(deleted)
                session.total_failed_exports += len(delete_failures)
                batch.completed_at = datetime.now()
                save_session(session)

            phase3_time = time.time() - phase3_start
            console.print(f"[green]✓ Deleted: {len(deleted)} videos in {phase3_time:.1f}s[/green]")
            if delete_failures:
                console.print(f"[yellow]⚠ Failed: {len(delete_failures)} videos[/yellow]")
        else:
            batch.completed_at = datetime.now()
            session.total_deleted += len(archived)
            save_session(session)

        # Update session state
        session.remaining_uuids = [u for u in session.remaining_uuids if u not in batch_uuids]
        save_session(session)

        # Track batch timing for ETA
        batch_total_time = time.time() - batch_start_time
        batch_times.append(batch_total_time)

        # Calculate and show statistics
        console.print(f"\n[bold cyan]Batch {batch_num} Complete[/bold cyan]")
        console.print(f"  Time: {batch_total_time:.1f}s (Export: {phase1_time:.1f}s, Archive: {phase2_time:.1f}s, Delete: {phase3_time:.1f}s)")

        # Session-level progress
        elapsed_total = time.time() - session_start_time
        avg_batch_time = sum(batch_times) / len(batch_times) if batch_times else 0
        remaining_batches = max(0, (len(session.all_selected_uuids) - session.total_deleted) // calculated_batch_size)
        eta_remaining = avg_batch_time * remaining_batches

        console.print(f"[dim]Session progress: {session.total_deleted}/{len(session.all_selected_uuids)} videos ({session.progress_pct}%)[/dim]")
        console.print(f"[dim]Elapsed: {elapsed_total/60:.1f}m | Avg batch: {avg_batch_time:.1f}s | Remaining: ~{eta_remaining/60:.1f}m[/dim]")

        # Continue or pause
        if session.remaining_uuids:
            if continuous:
                # Continue to next batch automatically
                batch_num += 1
                continue
            else:
                # Interactive mode - prompt between batches
                remaining_count = len(session.remaining_uuids)
                if not Confirm.ask(f"\n{remaining_count} videos remaining. Continue?"):
                    console.print("[yellow]Session paused. Run 'iphoto archive' to resume.[/yellow]")
                    return
                batch_num += 1
        else:
            break

    # === Final Summary ===
    console.print("\n[bold green]✓ Session Complete[/bold green]")
    console.print(f"  Session: {session.session_id}")
    console.print(f"  Exported: {session.total_exported}/{len(session.all_selected_uuids)}")
    console.print(f"  Archived: {session.total_archived}/{session.total_exported}")
    if not no_delete:
        console.print(f"  Deleted: {session.total_deleted}/{session.total_archived}")
    console.print(f"  Location: {external}")

    if session.total_failed_exports + session.total_failed_deletes > 0:
        console.print(f"\n[yellow]Failures: {session.total_failed_exports + session.total_failed_deletes} total[/yellow]")
    else:
        console.print(f"\n[green]No failures![/green]")

    clear_session()


@app.command()
def resume() -> None:
    """Resume an interrupted multi-batch session."""
    session = load_session()

    if not session:
        console.print("[yellow]No interrupted session found.[/yellow]")
        console.print("[dim]Use 'iphoto archive' to start a new session.[/dim]")
        return

    console.print(f"[bold cyan]Found interrupted session {session.session_id}[/bold cyan]")
    console.print(f"  Created: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    console.print(f"  Selected: {len(session.all_selected_uuids)} videos total")
    console.print(f"  Progress: {session.total_deleted}/{len(session.all_selected_uuids)} videos completed ({session.progress_pct}%)")
    console.print(f"  Batches completed: {session.batches_completed}/{len(session.batches)}")
    console.print(f"  Remaining: {len(session.remaining_uuids)} videos\n")

    # Show batch details
    if session.batches:
        console.print("[bold]Batch Summary:[/bold]")
        for batch in session.batches:
            status = "✓ Complete" if batch.is_complete else "⏳ In Progress"
            console.print(f"  Batch {batch.batch_number}: {len(batch.deleted_uuids)}/{len(batch.selected_uuids)} deleted {status}")

    if not Confirm.ask("\nResume this session?"):
        if Confirm.ask("Clear this session?"):
            clear_session()
        return

    # Resume session - archive command will handle it
    console.print("\n[cyan]Resuming archive command...[/cyan]")

    # Call archive with the session's original parameters
    # Note: We can't easily recover all original parameters from session,
    # so just let the archive command reload and continue
    archive(
        staging=session.staging_path,
        external=session.external_path,
        max_workers=session.max_workers,
        continuous=True,  # Resume in continuous mode
    )


@app.command()
def status() -> None:
    """Show status of current/last batch including failures."""
    state = load_state()

    if not state:
        console.print("[yellow]No batch state found.[/yellow]")
        console.print("[dim]Use 'iphoto archive' to start a new batch.[/dim]")
        return

    console.print(f"[bold]Batch {state.batch_id} Status[/bold]")
    console.print(f"Created: {state.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Progress summary
    console.print("[bold]Progress:[/bold]")
    console.print(f"  Selected:  {len(state.selected_uuids)} videos")
    console.print(f"  Exported:  {len(state.exported_uuids)}/{len(state.selected_uuids)}")
    console.print(f"  Archived:  {len(state.archived_uuids)}/{len(state.exported_uuids)}")
    console.print(f"  Deleted:   {len(state.deleted_uuids)}/{len(state.archived_uuids)}")

    # Failure details
    total_failures = len(state.failed_exports) + len(state.failed_deletes)
    if total_failures > 0:
        console.print(f"\n[bold yellow]Failures: {total_failures} total[/bold yellow]")

        if state.failed_exports:
            console.print(f"\n[yellow]Export failures ({len(state.failed_exports)}):[/yellow]")
            for uuid, reason in state.failed_exports.items():
                console.print(f"  {uuid[:8]}: {reason}")

        if state.failed_deletes:
            console.print(f"\n[yellow]Deletion failures ({len(state.failed_deletes)}):[/yellow]")
            for uuid, reason in state.failed_deletes.items():
                console.print(f"  {uuid[:8]}: {reason}")
    else:
        console.print("\n[green]No failures![/green]")

    # Cleanup option
    if Confirm.ask("\nClear batch state?"):
        clear_state()
        console.print("[green]Batch state cleared.[/green]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"iphoto version {__version__}")


if __name__ == "__main__":
    app()
