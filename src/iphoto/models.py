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
        return format_bytes(self.size_bytes)


def video_to_dict(video: VideoInfo) -> dict:
    """Serialize VideoInfo to a JSON-friendly dict."""
    d = {f.name: getattr(video, f.name) for f in video.__dataclass_fields__.values()}
    d["date_created"] = video.date_created.isoformat()
    d["date_modified"] = video.date_modified.isoformat()
    return d


def video_from_dict(data: dict) -> VideoInfo:
    """Deserialize VideoInfo from a dict."""
    data = dict(data)
    data["date_created"] = datetime.fromisoformat(data["date_created"])
    data["date_modified"] = datetime.fromisoformat(data["date_modified"])
    if data.get("location"):
        data["location"] = tuple(data["location"])
    valid = {f.name for f in VideoInfo.__dataclass_fields__.values()}
    return VideoInfo(**{k: v for k, v in data.items() if k in valid})


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
    def total_size_formatted(self) -> str:
        return format_bytes(self.total_size_bytes)

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
    def completion_label(self) -> str:
        """'Deleted' or 'Archived' depending on delete mode."""
        return "Deleted" if self.delete_enabled else "Archived"

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

    def to_dict(self) -> dict:
        """Serialize session to JSON-friendly dict."""
        return {
            "session_id": self.session_id,
            "staging_path": str(self.staging_path),
            "external_path": str(self.external_path),
            "created_at": self.created_at.isoformat(),
            "threshold_mb": self.threshold_mb,
            "min_age_days": self.min_age_days,
            "min_size_mb": self.min_size_mb,
            "use_moments": self.use_moments,
            "batch_size": self.batch_size,
            "export_timeout": self.export_timeout,
            "delete_timeout": self.delete_timeout,
            "delete_enabled": self.delete_enabled,
            "allow_ambiguous": self.allow_ambiguous,
            "library_path": self.library_path,
            "manifest_path": self.manifest_path,
            "all_selected_uuids": self.all_selected_uuids,
            "remaining_uuids": self.remaining_uuids,
            "failed_export_uuids": self.failed_export_uuids,
            "failed_delete_uuids": self.failed_delete_uuids,
            "current_batch_number": self.current_batch_number,
            "total_exported": self.total_exported,
            "total_archived": self.total_archived,
            "total_deleted": self.total_deleted,
            "total_failed_exports": self.total_failed_exports,
            "total_failed_deletes": self.total_failed_deletes,
            "videos": [video_to_dict(v) for v in self.videos],
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
                for b in self.batches
            ],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionState":
        """Deserialize session from a dict."""
        session = cls(
            session_id=data["session_id"],
            staging_path=Path(data["staging_path"]),
            external_path=Path(data["external_path"]),
            created_at=datetime.fromisoformat(data["created_at"]),
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
        for bd in data.get("batches", []):
            session.batches.append(BatchProgress(
                batch_number=bd["batch_number"],
                selected_uuids=bd.get("selected_uuids", []),
                exported_uuids=bd.get("exported_uuids", []),
                archived_uuids=bd.get("archived_uuids", []),
                deleted_uuids=bd.get("deleted_uuids", []),
                failed_exports=bd.get("failed_exports", {}),
                failed_deletes=bd.get("failed_deletes", {}),
                checksums=bd.get("checksums", {}),
                started_at=datetime.fromisoformat(bd["started_at"]),
                completed_at=datetime.fromisoformat(bd["completed_at"]) if bd.get("completed_at") else None,
            ))
        return session


def format_bytes(n: int) -> str:
    """Format byte count as human-readable string."""
    gb = n / (1024 ** 3)
    if gb >= 1:
        return f"{gb:.2f} GB"
    return f"{n / (1024 ** 2):.1f} MB"


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
