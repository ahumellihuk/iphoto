"""Extract representative thumbnail frames from video files using AVFoundation."""

from __future__ import annotations

import tempfile
from pathlib import Path

_AVFOUNDATION_AVAILABLE = False
try:
    import AppKit  # noqa: F401
    import AVFoundation  # noqa: F401
    from CoreMedia import CMTimeMakeWithSeconds, kCMTimeZero  # noqa: F401

    _AVFOUNDATION_AVAILABLE = True
except ImportError:
    pass


def extract_thumbnail(video_path: Path, at_seconds: float = 2.0) -> Path | None:
    """Extract a representative frame from a video file as a JPEG.

    Uses AVFoundation via PyObjC (already installed). Returns a path to a
    temporary JPEG file the caller is responsible for deleting, or None if
    extraction fails for any reason.
    """
    if not _AVFOUNDATION_AVAILABLE:
        return None
    try:
        return _avfoundation_thumbnail(video_path, at_seconds)
    except Exception:
        return None


def _avfoundation_thumbnail(video_path: Path, at_seconds: float) -> Path | None:
    import AppKit
    import AVFoundation
    from CoreMedia import CMTimeMakeWithSeconds, kCMTimeZero
    from Foundation import NSURL

    url = NSURL.fileURLWithPath_(str(video_path.resolve()))
    asset = AVFoundation.AVURLAsset.assetWithURL_(url)

    generator = AVFoundation.AVAssetImageGenerator.alloc().initWithAsset_(asset)
    generator.setAppliesPreferredTrackTransform_(True)  # correct orientation

    # Try requested time first, fall back to start of video
    time = CMTimeMakeWithSeconds(at_seconds, 600)
    cg_image, _actual, error = generator.copyCGImageAtTime_actualTime_error_(time, None, None)
    if error or cg_image is None:
        cg_image, _actual, error = generator.copyCGImageAtTime_actualTime_error_(kCMTimeZero, None, None)

    if cg_image is None:
        return None

    ns_image = AppKit.NSImage.alloc().initWithCGImage_size_(cg_image, AppKit.NSSize(0, 0))
    tiff = ns_image.TIFFRepresentation()
    if not tiff:
        return None

    bitmap = AppKit.NSBitmapImageRep.imageRepWithData_(tiff)
    jpeg_data = bitmap.representationUsingType_properties_(
        AppKit.NSBitmapImageFileTypeJPEG,
        {AppKit.NSImageCompressionFactor: 0.85},
    )
    if not jpeg_data:
        return None

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    jpeg_data.writeToFile_atomically_(str(tmp_path), True)
    return tmp_path
