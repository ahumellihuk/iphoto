"""Scan Photos library for videos using osxphotos."""

import os
import sqlite3
from datetime import datetime, timezone, MINYEAR
from datetime import datetime as dt_class
from typing import Optional

import osxphotos
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .models import VideoInfo, MomentGroup

console = Console()


def get_duration_map(library_path: Optional[str] = None) -> dict[str, float]:
    """Get video durations from Photos database."""
    if library_path:
        db_path = os.path.join(library_path, "database", "Photos.sqlite")
    else:
        db_path = os.path.expanduser(
            "~/Pictures/Photos Library.photoslibrary/database/Photos.sqlite"
        )

    duration_map: dict[str, float] = {}
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # Join ZASSET with ZEXTENDEDATTRIBUTES to get duration
        cursor.execute("""
            SELECT a.ZUUID, e.ZDURATION
            FROM ZASSET a
            JOIN ZEXTENDEDATTRIBUTES e ON a.ZEXTENDEDATTRIBUTES = e.Z_PK
            WHERE a.ZKIND = 1 AND e.ZDURATION > 0
        """)
        for uuid, duration in cursor.fetchall():
            duration_map[uuid] = duration
        conn.close()
    except Exception as e:
        console.print(f"[yellow]Warning: Could not read durations from database: {e}[/yellow]")

    return duration_map


def generate_moment_name(photo: osxphotos.PhotoInfo) -> str:
    """Generate a moment-style folder name like Photos export.

    Format: "Mon DD, YYYY" (e.g., "Mar 08, 2020")
    This matches the folder structure created by Photos when exporting unmodified originals.
    """
    date = photo.date
    if not date:
        return "Unknown Date"

    # Format like Photos export: "Mar 08, 2020"
    return date.strftime("%b %d, %Y")


def scan_videos(
    min_age_days: Optional[int] = None,
    min_size_mb: Optional[float] = None,
    library_path: Optional[str] = None,
) -> list[VideoInfo]:
    """Scan Photos library for videos matching criteria."""
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Opening Photos library...", total=None)

        # Open the Photos library
        photosdb = osxphotos.PhotosDB(dbfile=library_path)

        # Get duration map from database
        duration_map = get_duration_map(library_path)

        progress.add_task("Scanning for videos...", total=None)

        # Query all videos
        photos = photosdb.photos(movies=True, images=False)

        videos: list[VideoInfo] = []
        for photo in photos:
            # Skip if no original file available
            if not photo.original_filesize:
                continue

            # Get file size
            size_bytes = photo.original_filesize

            # Apply filters
            if min_size_mb and size_bytes < min_size_mb * 1024 * 1024:
                continue

            # Handle timezone-aware dates
            now = datetime.now(timezone.utc)
            date_created = photo.date
            if date_created:
                # Make naive datetime timezone-aware if needed
                if date_created.tzinfo is None:
                    date_created = date_created.replace(tzinfo=timezone.utc)
            else:
                date_created = now

            if min_age_days:
                age = (now - date_created).days
                if age < min_age_days:
                    continue

            # Get location
            location = None
            place_name = None
            if photo.location:
                location = photo.location
            if photo.place:
                place = photo.place
                if hasattr(place, "name"):
                    place_name = place.name

            # Get duration from our pre-fetched map
            duration = duration_map.get(photo.uuid, 0.0)

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

            # Check if video is locally available (not just in iCloud)
            # A video is considered local if it has a valid path or is not marked as cloud-only
            is_local = True
            if hasattr(photo, 'incloud') and photo.incloud:
                # Video is in iCloud - check if also available locally
                # If path is None or doesn't exist, it's not local
                if not photo.path or not os.path.exists(photo.path):
                    is_local = False

            # Use native moment name if available, otherwise fall back to date-based
            if not moment_name:
                moment_name = generate_moment_name(photo)

            video = VideoInfo(
                uuid=photo.uuid,
                filename=photo.filename or "unknown",
                original_filename=photo.original_filename or photo.filename or "unknown",
                date_created=date_created,
                date_modified=photo.date_modified or date_created,
                size_bytes=size_bytes,
                duration_seconds=duration,
                width=photo.width or 0,
                height=photo.height or 0,
                location=location,
                place_name=place_name,
                moment_name=moment_name,
                moment_pk=moment_pk,
                is_local=is_local,
            )
            videos.append(video)

    return videos


def rank_videos(
    videos: list[VideoInfo],
    sort_by: str = "size",
    descending: bool = True,
) -> list[VideoInfo]:
    """Sort videos by specified criteria.

    Args:
        sort_by: One of "size", "duration", "age", "date"
        descending: Sort in descending order (largest/longest/oldest first)
    """
    if sort_by == "duration":
        key = lambda v: v.duration_seconds
    elif sort_by == "age":
        key = lambda v: v.age_days
    elif sort_by == "date":
        key = lambda v: v.date_created
    else:  # default to size
        key = lambda v: v.size_bytes

    return sorted(videos, key=key, reverse=descending)


def group_by_moment(videos: list[VideoInfo], threshold_mb: Optional[float] = None) -> list[MomentGroup]:
    """Group videos by their moment PK and create MomentGroup objects.

    Group by moment_pk (unique identifier) rather than moment_name to get granular
    location + date groupings. Falls back to moment_name for videos without PKs.

    Each moment gets its own smart threshold calculated based on its video distribution.

    Args:
        videos: List of VideoInfo objects
        threshold_mb: Optional global threshold to apply (uses smart if None)

    Returns:
        List of MomentGroup objects sorted by total size descending
    """
    groups_dict: dict[Optional[int], list[VideoInfo]] = {}

    for video in videos:
        # Use moment_pk as the primary key if available, otherwise fall back to name
        moment_key = video.moment_pk if video.moment_pk else f"name_{video.moment_name or 'Unknown'}"

        if moment_key not in groups_dict:
            groups_dict[moment_key] = []
        groups_dict[moment_key].append(video)

    # Convert to MomentGroup objects with per-moment smart thresholds
    groups = []
    for moment_key, vids in groups_dict.items():
        # Use the first video's moment_name for the display (should be consistent within group)
        moment_name = vids[0].moment_name or "Unknown"
        moment_pk = vids[0].moment_pk

        group = MomentGroup(
            name=moment_name,
            pk=moment_pk,
            location_title=moment_name.split(" • ")[0] if " • " in moment_name else moment_name,
            videos=vids,
        )

        # Calculate per-moment smart threshold
        group.smart_threshold_mb = group.calculate_smart_threshold()

        # Use provided threshold or smart threshold
        group.threshold_mb = threshold_mb if threshold_mb is not None else group.smart_threshold_mb

        groups.append(group)

    # Sort by total size descending
    groups.sort(key=lambda g: g.total_size_bytes, reverse=True)

    return groups


def rank_moments(
    moments: list[MomentGroup], sort_by: str = "size", descending: bool = True
) -> list[MomentGroup]:
    """Sort moments by specified criteria.

    Args:
        moments: List of MomentGroup objects
        sort_by: One of "size", "count", "date"
        descending: Sort in descending order

    Returns:
        Sorted list of MomentGroup objects
    """
    if sort_by == "count":
        key = lambda m: m.video_count
    elif sort_by == "date":
        key = lambda m: min(v.date_created for v in m.videos) if m.videos else dt_class.min
    else:  # default to size
        key = lambda m: m.total_size_bytes

    return sorted(moments, key=key, reverse=descending)
