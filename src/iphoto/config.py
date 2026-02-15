"""Shared configuration defaults for iphoto."""

from pathlib import Path

DEFAULT_STAGING = Path.home() / "Pictures" / "iphotoArchiveStaging"
SESSION_FILE = Path.home() / ".iphoto_session.json"
LAST_DESTINATION_FILE = Path.home() / ".iphoto_last_destination"

DEFAULT_EXPORT_TIMEOUT = 1800
DEFAULT_DELETE_TIMEOUT = 120
ICLOUD_MIN_TIMEOUT = 3600
STAGING_SAFETY_MARGIN = 0.70

DELETE_ALBUM_NAME = "iphoto - Ready to Delete"
