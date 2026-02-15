"""Manifest utilities for archived videos."""

import json
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from .models import VideoInfo


def load_manifest(path: Path) -> list[dict]:
    """Load manifest entries from disk."""
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())
    except Exception:
        return []


def write_manifest(path: Path, entries: list[dict]) -> None:
    """Write manifest entries to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entries, indent=2))


def append_manifest_entries(path: Path, new_entries: Iterable[dict]) -> None:
    """Append or update entries in the manifest by UUID."""
    entries = load_manifest(path)
    by_uuid = {entry.get("uuid"): entry for entry in entries if entry.get("uuid")}
    for entry in new_entries:
        if entry.get("uuid"):
            by_uuid[entry["uuid"]] = entry
    write_manifest(path, list(by_uuid.values()))


def build_manifest_entry(
    video: VideoInfo,
    archived_path: Path,
    checksum: str,
    session_id: str,
) -> dict:
    """Build a manifest entry for an archived video."""
    return {
        "uuid": video.uuid,
        "original_filename": video.original_filename,
        "moment_name": video.moment_name,
        "size_bytes": video.size_bytes,
        "checksum": checksum,
        "archived_path": str(archived_path),
        "date_created": video.date_created.isoformat(),
        "archived_at": datetime.now().isoformat(),
        "session_id": session_id,
    }
