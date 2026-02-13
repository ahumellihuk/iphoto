"""Data models for iphoto."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from uuid import uuid4


@dataclass
class VideoInfo:
    """Information about a video in the Photos library."""

    uuid: str
    filename: str
    original_filename: str
    date_created: datetime
    date_modified: datetime
    size_bytes: int
    duration_seconds: float
    width: int
    height: int
    location: Optional[tuple[float, float]] = None  # (lat, lon)
    place_name: Optional[str] = None
    moment_name: str = ""
    moment_pk: Optional[int] = None  # Unique moment identifier in Photos database
    is_local: bool = True  # False if video is in iCloud but not downloaded locally

    @property
    def size_mb(self) -> float:
        return self.size_bytes / (1024 * 1024)

    @property
    def size_gb(self) -> float:
        return self.size_bytes / (1024 * 1024 * 1024)

    @property
    def age_days(self) -> int:
        now = datetime.now(timezone.utc)
        date = self.date_created
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        return (now - date).days

    @property
    def duration_formatted(self) -> str:
        mins, secs = divmod(int(self.duration_seconds), 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"

    @property
    def size_formatted(self) -> str:
        if self.size_gb >= 1:
            return f"{self.size_gb:.2f} GB"
        return f"{self.size_mb:.1f} MB"


def video_to_dict(video: VideoInfo) -> dict:
    """Serialize VideoInfo to a JSON-friendly dict."""
    return {
        "uuid": video.uuid,
        "filename": video.filename,
        "original_filename": video.original_filename,
        "date_created": video.date_created.isoformat(),
        "date_modified": video.date_modified.isoformat(),
        "size_bytes": video.size_bytes,
        "duration_seconds": video.duration_seconds,
        "width": video.width,
        "height": video.height,
        "location": video.location,
        "place_name": video.place_name,
        "moment_name": video.moment_name,
        "moment_pk": video.moment_pk,
        "is_local": video.is_local,
    }


def video_from_dict(data: dict) -> VideoInfo:
    """Deserialize VideoInfo from a dict."""
    return VideoInfo(
        uuid=data["uuid"],
        filename=data.get("filename") or "unknown",
        original_filename=data.get("original_filename") or data.get("filename") or "unknown",
        date_created=datetime.fromisoformat(data["date_created"]),
        date_modified=datetime.fromisoformat(data["date_modified"]),
        size_bytes=data["size_bytes"],
        duration_seconds=data.get("duration_seconds", 0.0),
        width=data.get("width", 0),
        height=data.get("height", 0),
        location=tuple(data["location"]) if data.get("location") else None,
        place_name=data.get("place_name"),
        moment_name=data.get("moment_name", ""),
        moment_pk=data.get("moment_pk"),
        is_local=data.get("is_local", True),
    )


@dataclass
class MomentGroup:
    """Represents a moment with aggregate statistics."""

    name: str  # Display name: "Location • Date" format
    key: str = ""  # Stable selection key (pk-based when available)
    pk: Optional[int] = None  # Unique moment identifier in Photos database
    location_title: str = ""  # Just the location name (e.g., "London")
    videos: list[VideoInfo] = field(default_factory=list)
    threshold_mb: float = 100.0
    smart_threshold_mb: Optional[float] = None  # Per-moment optimal threshold

    @property
    def video_count(self) -> int:
        return len(self.videos)

    @property
    def total_size_bytes(self) -> int:
        return sum(v.size_bytes for v in self.videos)

    @property
    def total_size_gb(self) -> float:
        return self.total_size_bytes / (1024 ** 3)

    @property
    def total_size_formatted(self) -> str:
        gb = self.total_size_gb
        if gb >= 1:
            return f"{gb:.2f} GB"
        return f"{self.total_size_bytes / (1024 ** 2):.1f} MB"

    @property
    def date_range(self) -> str:
        """Returns formatted date range for display."""
        if not self.videos:
            return ""
        dates = [v.date_created for v in self.videos]
        min_date = min(dates).strftime("%Y-%m-%d")
        max_date = max(dates).strftime("%Y-%m-%d")
        if min_date == max_date:
            return min_date
        return f"{min_date} to {max_date}"

    def videos_above_threshold(self) -> list[VideoInfo]:
        """Returns videos larger than the threshold."""
        threshold_bytes = self.threshold_mb * 1024 * 1024
        return [v for v in self.videos if v.size_bytes >= threshold_bytes]

    def videos_below_threshold(self) -> list[VideoInfo]:
        """Returns videos smaller than the threshold."""
        threshold_bytes = self.threshold_mb * 1024 * 1024
        return [v for v in self.videos if v.size_bytes < threshold_bytes]

    @property
    def threshold_summary(self) -> str:
        """Summary of how many videos pass threshold."""
        above = len(self.videos_above_threshold())
        total = len(self.videos)
        return f"{above}/{total} above {self.threshold_mb:.0f}MB"

    @property
    def space_to_reclaim(self) -> float:
        """Space in GB that would be freed by archiving videos above threshold."""
        return sum(v.size_bytes for v in self.videos_above_threshold()) / (1024 ** 3)

    def calculate_smart_threshold(self) -> float:
        """Calculate optimal threshold for this moment's video distribution.

        Aims to archive ~90% of this moment's storage while skipping frequent small clips.
        Returns threshold in MB.
        """
        if len(self.videos) < 2:
            return 100.0

        sizes_mb = sorted([v.size_mb for v in self.videos])
        total_size = sum(sizes_mb)
        target_size = total_size * 0.90

        cumsum = 0
        for size in sorted(sizes_mb, reverse=True):
            cumsum += size
            if cumsum >= target_size:
                # Round to nearest 25MB boundary for clean thresholds
                threshold = int((size / 25) + 0.5) * 25
                return max(50.0, float(threshold))

        return 100.0


@dataclass
class BatchProgress:
    """Tracks progress for a single batch within a multi-batch session."""

    batch_number: int
    selected_uuids: list[str] = field(default_factory=list)
    exported_uuids: list[str] = field(default_factory=list)
    archived_uuids: list[str] = field(default_factory=list)
    deleted_uuids: list[str] = field(default_factory=list)
    failed_exports: dict[str, str] = field(default_factory=dict)
    failed_deletes: dict[str, str] = field(default_factory=dict)
    checksums: dict[str, str] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None

    @property
    def is_complete(self) -> bool:
        """Whether this batch is fully processed."""
        return self.completed_at is not None

    @property
    def success_count(self) -> int:
        """Number of successfully deleted videos."""
        return len(self.deleted_uuids)

    @property
    def failure_count(self) -> int:
        """Total number of failed operations."""
        return len(self.failed_exports) + len(self.failed_deletes)


@dataclass
class SessionState:
    """Tracks multi-batch archival session state for resumption."""

    session_id: str = field(default_factory=lambda: str(uuid4())[:8])
    staging_path: Path = field(default_factory=Path)
    external_path: Path = field(default_factory=Path)
    created_at: datetime = field(default_factory=datetime.now)

    # Configuration
    max_workers: int = 4
    threshold_mb: Optional[float] = None
    min_age_days: Optional[int] = None
    min_size_mb: Optional[float] = None
    use_moments: bool = True
    batch_size: Optional[int] = None
    export_timeout: int = 1800
    delete_timeout: int = 120
    delete_enabled: bool = True
    allow_ambiguous: bool = False
    library_path: Optional[str] = None
    manifest_path: Optional[str] = None

    # All selected videos for session
    all_selected_uuids: list[str] = field(default_factory=list)
    remaining_uuids: list[str] = field(default_factory=list)
    videos: list[VideoInfo] = field(default_factory=list)
    failed_export_uuids: list[str] = field(default_factory=list)
    failed_delete_uuids: list[str] = field(default_factory=list)

    # Batch tracking
    batches: list[BatchProgress] = field(default_factory=list)
    current_batch_number: int = 0

    # Session statistics
    total_exported: int = 0
    total_archived: int = 0
    total_deleted: int = 0
    total_failed_exports: int = 0
    total_failed_deletes: int = 0

    @property
    def current_batch(self) -> Optional[BatchProgress]:
        """Get the current/last batch."""
        if self.batches and self.current_batch_number > 0:
            return self.batches[self.current_batch_number - 1]
        return None

    @property
    def is_complete(self) -> bool:
        """Whether all selected videos have been processed."""
        return len(self.remaining_uuids) == 0

    @property
    def progress_pct(self) -> int:
        """Overall progress as percentage."""
        if not self.all_selected_uuids:
            return 0
        return int(100 * self.completed_count / len(self.all_selected_uuids))

    @property
    def completed_count(self) -> int:
        """Number of videos completed based on delete mode."""
        return self.total_deleted if self.delete_enabled else self.total_archived

    @property
    def batches_completed(self) -> int:
        """Number of completed batches."""
        return len([b for b in self.batches if b.is_complete])

    def add_batch(self, batch_number: int, video_uuids: list[str]) -> BatchProgress:
        """Create and add a new batch to the session."""
        batch = BatchProgress(batch_number=batch_number, selected_uuids=video_uuids)
        self.batches.append(batch)
        self.current_batch_number = batch_number
        return batch

    def complete_current_batch(self):
        """Mark current batch as complete."""
        if self.current_batch:
            self.current_batch.completed_at = datetime.now()


def filter_ambiguous_filenames(
    videos: list[VideoInfo],
    allow_ambiguous: bool = False,
) -> tuple[list[VideoInfo], dict[str, str]]:
    """Filter out videos with duplicate original filenames.

    Returns (safe_videos, failures) where failures maps uuid -> reason.
    """
    if allow_ambiguous:
        return videos, {}

    filename_map: dict[str, list[VideoInfo]] = {}
    for video in videos:
        filename_map.setdefault(video.original_filename, []).append(video)

    failures: dict[str, str] = {}
    for fn, vids in filename_map.items():
        if len(vids) > 1:
            for video in vids:
                failures[video.uuid] = f"Ambiguous filename '{fn}' (matches {len(vids)} items)"

    safe_videos = [v for v in videos if v.uuid not in failures]
    return safe_videos, failures
