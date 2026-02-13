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
from .exporter import export_videos, calculate_batch_size, compute_sha256
from .manifest import append_manifest_entries, build_manifest_entry, load_manifest
from .models import VideoInfo, MomentGroup, SessionState, BatchProgress, video_to_dict, video_from_dict
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
SESSION_FILE = Path.home() / ".iphoto_session.json"


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
            "min_age_days": session.min_age_days,
            "min_size_mb": session.min_size_mb,
            "use_moments": session.use_moments,
            "batch_size": session.batch_size,
            "export_timeout": session.export_timeout,
            "delete_timeout": session.delete_timeout,
            "delete_enabled": session.delete_enabled,
            "allow_ambiguous": session.allow_ambiguous,
            "library_path": session.library_path,
            "manifest_path": session.manifest_path,
            "all_selected_uuids": session.all_selected_uuids,
            "remaining_uuids": session.remaining_uuids,
            "failed_export_uuids": session.failed_export_uuids,
            "failed_delete_uuids": session.failed_delete_uuids,
            "current_batch_number": session.current_batch_number,
            "total_exported": session.total_exported,
            "total_archived": session.total_archived,
            "total_deleted": session.total_deleted,
            "total_failed_exports": session.total_failed_exports,
            "total_failed_deletes": session.total_failed_deletes,
            "videos": [video_to_dict(v) for v in session.videos],
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
) -> Optional[tuple[SessionState, list[VideoInfo]]]:
    """Resume existing session or create new one via scan+select."""
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
        threshold_mb=threshold_mb, min_age_days=min_age_days, min_size_mb=min_size_mb,
        use_moments=use_moments, batch_size=batch_size,
        export_timeout=export_timeout, delete_timeout=delete_timeout,
        delete_enabled=not no_delete, allow_ambiguous=allow_ambiguous,
        library_path=library, videos=selected,
    )
    session.manifest_path = str(external / f"iphoto_manifest_{session.session_id}.json")
    save_session(session)
    console.print(f"\n[cyan]Created session {session.session_id} with {len(selected)} videos[/cyan]\n")
    return session, all_videos


def _export_batch_phase(
    batch_videos: list[VideoInfo],
    staging: Path,
    session: SessionState,
    batch: BatchProgress,
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

    exported, export_failures = export_videos(
        batch_videos, staging,
        library_path=session.library_path,
        timeout_seconds=session.export_timeout,
        allow_ambiguous=session.allow_ambiguous,
    )
    batch.exported_uuids = list(exported.keys())
    batch.failed_exports = export_failures
    batch.checksums = {uuid: cs for uuid, (_, cs) in exported.items()}
    session.total_exported += len(exported)
    session.total_failed_exports += len(export_failures)
    if export_failures:
        session.failed_export_uuids = sorted(
            set(session.failed_export_uuids).union(export_failures.keys())
        )
    save_session(session)
    return exported, export_failures


def _archive_batch_phase(
    exported: dict[str, tuple[Path, str]],
    batch_videos: list[VideoInfo],
    all_videos_map: dict[str, VideoInfo],
    session: SessionState,
    batch: BatchProgress,
    dry_run: bool,
) -> dict[str, Path]:
    """Phase 2+3: Archive to external and optionally delete from Photos."""
    console.print(f"\n[bold]Phase 2:[/bold] Archiving to external drive...")
    if dry_run:
        console.print(f"[cyan][DRY RUN] Would archive {len(exported)} videos[/cyan]")
        archived = dict(exported)
    else:
        archived = move_to_archive(exported, session.external_path)
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
            archived_videos,
            dry_run=dry_run,
            timeout_seconds=session.delete_timeout,
            allow_ambiguous=session.allow_ambiguous,
        )
        if not dry_run:
            batch.deleted_uuids = deleted
            batch.failed_deletes = delete_failures
            session.total_deleted += len(deleted)
            session.total_failed_deletes += len(delete_failures)
            if delete_failures:
                session.failed_delete_uuids = sorted(
                    set(session.failed_delete_uuids).union(delete_failures.keys())
                )

    batch.completed_at = datetime.now()
    save_session(session)
    return archived


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
    allow_ambiguous: bool = typer.Option(
        False, "--allow-ambiguous", help="Allow duplicate filenames (may match wrong item)"
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

    # Resume or create session
    result = _resume_or_create_session(
        staging=staging, external=external, min_age_days=min_age_days,
        min_size_mb=min_size_mb, threshold_mb=threshold_mb, use_moments=use_moments,
        batch_size=batch_size, export_timeout=export_timeout, delete_timeout=delete_timeout,
        no_delete=no_delete, allow_ambiguous=allow_ambiguous, library=library,
    )
    if not result:
        return
    session, all_videos = result

    # Ensure staging directory exists before disk usage checks
    staging.mkdir(parents=True, exist_ok=True)

    # Pre-flight check: verify external drive is mounted (skip in dry-run)
    if not dry_run:
        from .mover import check_external_mounted
        if not check_external_mounted(external):
            console.print(f"[red]Error: External drive not mounted at {external}[/red]")
            console.print("[yellow]Connect the external drive and try again.[/yellow]")
            save_session(session)
            return

    # Enforce serial AppleScript export for stability across session
    if max_workers != 1:
        console.print("[yellow]Forcing --workers=1 for AppleScript stability.[/yellow]")
        max_workers = 1
        session.max_workers = 1
        save_session(session)

    # Build video lookup for session
    all_videos_map = {v.uuid: v for v in all_videos}

    # Filter missing UUIDs (library changed since session start)
    missing_uuids = [u for u in session.remaining_uuids if u not in all_videos_map]
    if missing_uuids:
        console.print(
            f"[yellow]Warning: {len(missing_uuids)} videos are no longer in the library and will be skipped.[/yellow]"
        )
        session.remaining_uuids = [u for u in session.remaining_uuids if u in all_videos_map]
        save_session(session)

    # Batch processing loop with timing
    batch_num = session.current_batch_number + 1
    session_start_time = time.time()
    batch_times = []  # Track time per batch for ETA

    while session.remaining_uuids:
        batch_start_time = time.time()

        # Calculate batch size
        remaining_videos = [all_videos_map[uuid] for uuid in session.remaining_uuids if uuid in all_videos_map]
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
            batch_videos = []
            for uuid in session.remaining_uuids:
                video = all_videos_map[uuid]
                current_size = sum(v.size_bytes for v in batch_videos)
                if current_size + video.size_bytes <= usable_bytes:
                    batch_videos.append(video)
                else:
                    break

            if not batch_videos:
                first_video = all_videos_map[session.remaining_uuids[0]]
                console.print(f"[red]CRITICAL: Largest remaining video ({first_video.size_bytes / (1024**3):.2f} GB) "
                             f"exceeds available space ({usable_bytes / (1024**3):.2f} GB)[/red]")
                console.print("[red]Cannot proceed. Free up staging space and retry.[/red]")
                return

            batch_uuids = [v.uuid for v in batch_videos]
            console.print(f"[yellow]Batch size adjusted from {calculated_batch_size} to {len(batch_videos)} "
                         f"to fit available staging space[/yellow]")

        batch = session.add_batch(batch_num, batch_uuids)
        total_size_gb = sum(v.size_bytes for v in batch_videos) / (1024 ** 3)
        estimated_batches = len(session.all_selected_uuids) // calculated_batch_size + 1
        console.print(f"\n[bold cyan]--- Batch {batch_num}/{estimated_batches} ---[/bold cyan]")
        console.print(f"Videos: {len(batch_videos)} | Size: {total_size_gb:.2f} GB")
        completion_label = "Deleted" if session.delete_enabled else "Archived"
        console.print(
            f"Session: {session.completed_count}/{len(session.all_selected_uuids)} "
            f"videos {completion_label.lower()} ({session.progress_pct}%)\n"
        )

        # Phase 1: Export
        phase1_start = time.time()
        exported, export_failures = _export_batch_phase(batch_videos, staging, session, batch, dry_run)

        if not exported:
            console.print("[red]Batch export failed. Stopping.[/red]")
            save_session(session)
            return

        phase1_time = time.time() - phase1_start
        console.print(f"[green]Exported: {len(exported)} videos in {phase1_time:.1f}s[/green]")
        if export_failures:
            console.print(f"[yellow]Failed: {len(export_failures)} videos[/yellow]")

        # Phase 2+3: Archive and delete
        phase2_start = time.time()
        archived = _archive_batch_phase(exported, batch_videos, all_videos_map, session, batch, dry_run)
        phase23_time = time.time() - phase2_start

        if not archived:
            console.print("[red]Archive failed. Stopping.[/red]")
            save_session(session)
            return

        # Update session state
        session.remaining_uuids = [u for u in session.remaining_uuids if u not in batch_uuids]
        save_session(session)

        # Track batch timing for ETA
        batch_total_time = time.time() - batch_start_time
        batch_times.append(batch_total_time)

        # Calculate and show statistics
        console.print(f"\n[bold cyan]Batch {batch_num} Complete[/bold cyan]")
        console.print(f"  Time: {batch_total_time:.1f}s (Export: {phase1_time:.1f}s, Archive+Delete: {phase23_time:.1f}s)")

        elapsed_total = time.time() - session_start_time
        avg_batch_time = sum(batch_times) / len(batch_times) if batch_times else 0
        remaining_batches = max(
            0, (len(session.all_selected_uuids) - session.completed_count) // calculated_batch_size
        )
        eta_remaining = avg_batch_time * remaining_batches

        completion_label = "Deleted" if session.delete_enabled else "Archived"
        console.print(
            f"[dim]Session progress: {session.completed_count}/{len(session.all_selected_uuids)} "
            f"videos {completion_label.lower()} ({session.progress_pct}%)[/dim]"
        )
        console.print(f"[dim]Elapsed: {elapsed_total/60:.1f}m | Avg batch: {avg_batch_time:.1f}s | Remaining: ~{eta_remaining/60:.1f}m[/dim]")

        # Continue or pause
        if session.remaining_uuids:
            if continuous:
                batch_num += 1
                continue
            else:
                remaining_count = len(session.remaining_uuids)
                if not Confirm.ask(f"\n{remaining_count} videos remaining. Continue?"):
                    console.print("[yellow]Session paused. Run 'iphoto archive' to resume.[/yellow]")
                    return
                batch_num += 1
        else:
            break

    # Final Summary
    console.print("\n[bold green]Session Complete[/bold green]")
    console.print(f"  Session: {session.session_id}")
    console.print(f"  Exported: {session.total_exported}/{len(session.all_selected_uuids)}")
    console.print(f"  Archived: {session.total_archived}/{session.total_exported}")
    if session.delete_enabled:
        console.print(f"  Deleted: {session.total_deleted}/{session.total_archived}")
    console.print(f"  Location: {external}")
    if session.manifest_path:
        console.print(f"  Manifest: {session.manifest_path}")

    unresolved_failures = len(session.failed_export_uuids) + len(session.failed_delete_uuids)
    if unresolved_failures > 0:
        console.print(
            f"\n[yellow]Failures remaining: {unresolved_failures} "
            f"(exports: {len(session.failed_export_uuids)}, deletes: {len(session.failed_delete_uuids)})[/yellow]"
        )
        console.print("[dim]Use 'iphoto retry-failed' to retry.[/dim]")
    else:
        console.print(f"\n[green]No failures![/green]")

    clear_session()


@app.command()
def retry_failed(
    exports: bool = typer.Option(True, "--exports/--no-exports", help="Retry failed exports"),
    deletes: bool = typer.Option(True, "--deletes/--no-deletes", help="Retry failed deletions"),
) -> None:
    """Retry failed exports and/or deletions from the current session."""
    session = load_session()

    if not session:
        console.print("[yellow]No interrupted session found.[/yellow]")
        return

    if not session.videos:
        console.print("[yellow]Session has no stored video metadata. Cannot retry.[/yellow]")
        return

    all_videos_map = {v.uuid: v for v in session.videos}

    if exports:
        failed_export_videos = [all_videos_map[u] for u in session.failed_export_uuids if u in all_videos_map]
        if failed_export_videos:
            console.print(f"[bold]Retrying {len(failed_export_videos)} failed exports...[/bold]")
            exported, export_failures = export_videos(
                failed_export_videos,
                Path(session.staging_path),
                library_path=session.library_path,
                timeout_seconds=session.export_timeout,
                max_workers=session.max_workers,
                allow_ambiguous=session.allow_ambiguous,
            )
            if exported:
                session.total_exported += len(exported)
            archived = {}
            if exported:
                archived = move_to_archive(exported, Path(session.external_path))
                if archived:
                    session.total_archived += len(archived)
                if archived and session.manifest_path:
                    manifest_entries = []
                    for uuid, dest_path in archived.items():
                        video = all_videos_map.get(uuid)
                        if not video:
                            continue
                        checksum = None
                        if uuid in exported:
                            checksum = exported[uuid][1]
                        if not checksum and dest_path.exists():
                            checksum = compute_sha256(dest_path)
                        manifest_entries.append(
                            build_manifest_entry(
                                video=video,
                                archived_path=dest_path,
                                checksum=checksum or "",
                                session_id=session.session_id,
                            )
                        )
                    if manifest_entries:
                        append_manifest_entries(Path(session.manifest_path), manifest_entries)

                if session.delete_enabled and archived:
                    archived_videos = [all_videos_map[u] for u in archived if u in all_videos_map]
                    deleted, delete_failures = delete_from_photos(
                        archived_videos,
                        dry_run=False,
                        timeout_seconds=session.delete_timeout,
                        allow_ambiguous=session.allow_ambiguous,
                    )
                    session.total_deleted += len(deleted)
                    session.total_failed_deletes += len(delete_failures)
                    if delete_failures:
                        session.failed_delete_uuids = sorted(
                            set(session.failed_delete_uuids).union(delete_failures.keys())
                        )
            # Update failed export list (replace, don't accumulate)
            session.failed_export_uuids = sorted(export_failures.keys())
            save_session(session)
        else:
            console.print("[green]No failed exports to retry.[/green]")

    if deletes:
        if not session.delete_enabled:
            console.print("[yellow]Session was created with --no-delete; skipping delete retries.[/yellow]")
            return
        failed_delete_videos = [all_videos_map[u] for u in session.failed_delete_uuids if u in all_videos_map]
        if failed_delete_videos:
            console.print(f"[bold]Retrying {len(failed_delete_videos)} failed deletions...[/bold]")
            deleted, delete_failures = delete_from_photos(
                failed_delete_videos,
                dry_run=False,
                timeout_seconds=session.delete_timeout,
                allow_ambiguous=session.allow_ambiguous,
            )
            session.total_deleted += len(deleted)
            session.total_failed_deletes += len(delete_failures)
            session.failed_delete_uuids = sorted(delete_failures.keys())
            save_session(session)
        else:
            console.print("[green]No failed deletions to retry.[/green]")


@app.command()
def verify(
    manifest: Optional[Path] = typer.Option(
        None, "--manifest", "-m", help="Path to manifest JSON (defaults to current session)"
    )
) -> None:
    """Verify archived files against the manifest."""
    session = load_session()
    if not manifest:
        if session and session.manifest_path:
            manifest = Path(session.manifest_path)
        else:
            console.print("[yellow]No manifest specified and no session manifest found.[/yellow]")
            return

    entries = load_manifest(manifest)
    if not entries:
        console.print(f"[yellow]Manifest is empty or unreadable: {manifest}[/yellow]")
        return

    missing = 0
    mismatched = 0
    checked = 0

    console.print(f"[bold]Verifying {len(entries)} archived files...[/bold]")
    for entry in entries:
        archived_path = Path(entry.get("archived_path", ""))
        checksum = entry.get("checksum", "")
        if not archived_path.exists():
            missing += 1
            continue
        if checksum:
            actual = compute_sha256(archived_path)
            if actual != checksum:
                mismatched += 1
        checked += 1

    console.print(f"[green]Verified: {checked}[/green]")
    if missing:
        console.print(f"[yellow]Missing: {missing}[/yellow]")
    if mismatched:
        console.print(f"[red]Checksum mismatch: {mismatched}[/red]")


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
    completion_label = "Deleted" if session.delete_enabled else "Archived"
    console.print(
        f"  Progress: {session.completed_count}/{len(session.all_selected_uuids)} "
        f"videos {completion_label.lower()} ({session.progress_pct}%)"
    )
    console.print(f"  Batches completed: {session.batches_completed}/{len(session.batches)}")
    console.print(f"  Remaining: {len(session.remaining_uuids)} videos\n")

    # Show batch details
    if session.batches:
        console.print("[bold]Batch Summary:[/bold]")
        for batch in session.batches:
            status = "✓ Complete" if batch.is_complete else "⏳ In Progress"
            completion_label = "Deleted" if session.delete_enabled else "Archived"
            completed = len(batch.deleted_uuids) if session.delete_enabled else len(batch.archived_uuids)
            console.print(
                f"  Batch {batch.batch_number}: {completed}/{len(batch.selected_uuids)} {completion_label.lower()} {status}"
            )

    if not Confirm.ask("\nResume this session?"):
        if Confirm.ask("Clear this session?"):
            clear_session()
        return

    # Resume session - archive command will handle it
    console.print("\n[cyan]Resuming archive command...[/cyan]")

    archive(
        staging=session.staging_path,
        external=session.external_path,
        min_age_days=session.min_age_days,
        min_size_mb=session.min_size_mb,
        threshold_mb=session.threshold_mb,
        use_moments=session.use_moments,
        batch_size=session.batch_size,
        export_timeout=session.export_timeout,
        delete_timeout=session.delete_timeout,
        no_delete=not session.delete_enabled,
        allow_ambiguous=session.allow_ambiguous,
        library=session.library_path,
        max_workers=session.max_workers,
        continuous=True,
    )


@app.command()
def status() -> None:
    """Show status of current/last batch including failures."""
    session = load_session()

    if session:
        console.print(f"[bold]Session {session.session_id} Status[/bold]")
        console.print(f"Created: {session.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n")

        completion_label = "Deleted" if session.delete_enabled else "Archived"
        console.print("[bold]Progress:[/bold]")
        console.print(f"  Selected:  {len(session.all_selected_uuids)} videos")
        console.print(f"  Exported:  {session.total_exported}/{len(session.all_selected_uuids)}")
        console.print(f"  Archived:  {session.total_archived}/{session.total_exported}")
        console.print(f"  {completion_label}:   {session.completed_count}/{len(session.all_selected_uuids)}")

        if session.failed_export_uuids or session.failed_delete_uuids:
            console.print(
                f"\n[bold yellow]Failures:[/bold yellow] "
                f"{len(session.failed_export_uuids)} export, {len(session.failed_delete_uuids)} delete"
            )
        else:
            console.print("\n[green]No failures![/green]")

        if session.batches:
            console.print("\n[bold]Batches:[/bold]")
            for batch in session.batches:
                status = "✓ Complete" if batch.is_complete else "⏳ In Progress"
                completion_label = "Deleted" if session.delete_enabled else "Archived"
                completed = len(batch.deleted_uuids) if session.delete_enabled else len(batch.archived_uuids)
                console.print(
                    f"  Batch {batch.batch_number}: {completed}/{len(batch.selected_uuids)} {completion_label.lower()} {status}"
                )

        if Confirm.ask("\nClear this session?"):
            clear_session()
            console.print("[green]Session cleared.[/green]")
        return

    console.print("[yellow]No session found.[/yellow]")
    console.print("[dim]Use 'iphoto archive' to start a new session.[/dim]")


@app.command()
def version() -> None:
    """Show version information."""
    console.print(f"iphoto version {__version__}")


if __name__ == "__main__":
    app()
